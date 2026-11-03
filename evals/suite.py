"""python -m evals.suite: testes, atendimento, RAG e relatório Markdown incremental."""
import argparse
import hashlib
import io
import json
import math
import os
import platform
import re
import time
import unittest
from contextlib import redirect_stdout
from dataclasses import asdict
from datetime import date, datetime, timezone, timedelta
from importlib.metadata import version
from pathlib import Path

from kit.validate import validate
from petz.assistant import Assistant
from petz.config import get_ollama_settings
from petz.ollama_client import OllamaClient, CHAT_PROFILES
from petz.rag import generate_answer, validate_answer
from petz.retrieval import ROOT, Retriever, chunk_documents, norm
from .checks import check
from .reporting import render_markdown
from .semantic import judge_rag_case, RUBRIC_VERSION
from .components import run_component, write_group_reports

def normalized(text):
    return ' '.join(norm(text).split())

# Mede ranking de chunks rotulados por fonte e passagens de referência independentes.
def retrieval_metrics(hits,gold,all_chunks):
    if gold['should_abstain']:
        return {'retrieval_empty':not hits,'unexpected_hits':len(hits)}
    source = f"kit/politicas/{gold['source']}.md"
    evidence = [normalized(e) for e in gold['evidence']]
    valid = lambda c:c.source == source and any(e in normalized(c.text) for e in evidence)
    relevant = {c.id for c in all_chunks if valid(c)}
    if not relevant:
        raise ValueError('Referência sem chunk correspondente: revise o dataset e o chunking.')
    # Também detecta referência que deixou de existir após mudança nas políticas.
    if any(not any(c.source == source and e in normalized(c.text) for c in all_chunks) for e in evidence):
        raise ValueError('Passagem de referência ausente dos chunks: revisão do dataset necessária.')
    labels = [int(c.id in relevant) for c in hits]
    found = sum(labels)
    covered = sum(any(c.source == source and e in normalized(c.text) for c in hits) for e in evidence)
    dcg = sum(label/math.log2(index+2) for index,label in enumerate(labels))
    ideal = sum(1/math.log2(index+2) for index in range(min(len(relevant),len(hits))))
    return {'source_hit':any(c.source == source for c in hits),
        'precision_returned':found/len(hits) if hits else 0,
        'chunk_recall_at_k':found/len(relevant),
        'mrr':next((1/(index+1) for index,label in enumerate(labels) if label),0),
        'ndcg_at_k':dcg/ideal if ideal else 0,
        'evidence_coverage':covered/len(evidence), 'gold_chunk_ids':sorted(relevant)}

# Confere fatos por padrões explícitos; não substitui julgamento semântico humano.
def generation_checks(output,gold,hits):
    validated = validate_answer(output,hits)
    errors = []
    if bool(validated['supported']) == gold['should_abstain']:
        errors.append('Abstenção/resposta diferente do esperado.')
    if not gold['should_abstain'] and validated['supported']:
        for pattern in gold['answer_patterns']:
            if not re.search(pattern,validated['answer'],re.IGNORECASE): errors.append(f'Fato/padrão esperado ausente: {pattern}')
        for pattern in gold.get('forbidden_patterns',[]):
            if re.search(pattern,validated['answer'],re.IGNORECASE): errors.append(f'Afirmação proibida presente: {pattern}')
        sources = {c.id:c.source for c in hits}
        if not any(sources[c['chunk_id']] == f"kit/politicas/{gold['source']}.md" for c in validated['citations']):
            errors.append('Resposta não cita a fonte esperada.')
    return errors

def source_hash():
    digest = hashlib.sha256()
    for folder in ['petz','kit','tests','evals']:
        for path in sorted((ROOT/folder).rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts and (path.suffix == '.py' or path.name in {'cases.json','regression_cases.json','rag_cases.json','rag_regression_cases.json','classification_cases.json','extraction_cases.json'} or folder == 'kit'):
                digest.update(path.relative_to(ROOT).as_posix().encode()); digest.update(path.read_bytes())
    return digest.hexdigest()

def environment():
    settings = get_ollama_settings()
    return {'python':platform.python_version(),'system':platform.platform(),
        'models':{'chat':settings.chat_model,'embeddings':settings.embedding_model},
        'timeouts':{'chat':settings.chat_timeout,'rag':settings.rag_timeout,'embedding':settings.embedding_timeout},
        'profiles':CHAT_PROFILES,'top_k':int(os.getenv('RAG_TOP_K','4')),'min_score':float(os.getenv('RAG_MIN_SCORE','0.45')),
        'versions':{p:version(p) for p in ['langchain-core','langchain-ollama','sqlite-vec','deepeval']},'source_sha256':source_hash()}

def run_units():
    buffer = io.StringIO()
    suite = unittest.defaultTestLoader.discover(str(ROOT/'tests'))
    result = unittest.TextTestRunner(stream=buffer,verbosity=2).run(suite)
    return {'status':'passou' if result.wasSuccessful() else 'falhou',
        'summary':f'{result.testsRun} testes; {len(result.failures)} falhas; {len(result.errors)} erros; {len(result.skipped)} ignorados.',
        'count':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'output':buffer.getvalue()}

def run_conversation(case,repeat):
    start = time.perf_counter()
    row = {'id':case['id'],'area':case['area'],'repeat':repeat,'passed':False,'errors':[],'turns':[],'expected':case['expect']}
    try:
        bot = Assistant(case.get('customer','cliente-1'),date(2026,10,29))
        for index,message in enumerate(case['turns']):
            reply = bot.ask(message)
            row['turns'].append({'input':message,**asdict(reply),'answer':reply.text})
            if str(index) in case.get('expect_turns',{}): row['errors'].extend(check(reply,case['expect_turns'][str(index)],bot.products))
        row['errors'].extend(check(reply,case['expect'],bot.products))
        if case['expect'].get('skus_empty') and reply.data.get('skus') != []: row['errors'].append('Esperado nenhum SKU.')
        if case['expect'].get('skus_nonempty') and not reply.data.get('skus'): row['errors'].append('Esperado ao menos um SKU.')
        if reply.route in {'erro_modelo','erro_rag','erro_produto','erro_pedido'} and 'status_code' not in case['expect']:
            row['errors'].append('Erro de execução no fluxo: '+reply.route)
        row['passed'] = not row['errors']
    except Exception as error:
        row['errors'].append(f'Exceção durante execução: {type(error).__name__}')
    row['latency_ms'] = round((time.perf_counter()-start)*1000,3)
    return row

def run_rag_case(gold,repeat,retriever,all_chunks,*,hits=None):
    start = time.perf_counter()
    row = {'id':gold['id'],'repeat':repeat,'question':gold['question'],'passed':False,'errors':[]}
    try:
        hits = retriever.search(gold['question']) if hits is None else hits
        row['hits'] = [asdict(c) for c in hits]
        row['retrieval'] = retrieval_metrics(hits,gold,all_chunks)
        if not gold['should_abstain'] and row['retrieval']['evidence_coverage'] < 1:
            row['errors'].append('Recuperação incompleta das passagens de referência.')
        output = generate_answer(gold['question'],hits) if hits else {'supported':False,'answer':'Sem evidência recuperada.','citations':[]}
        row['generation'] = output
        row['errors'].extend(generation_checks(output,gold,hits))
        row['passed'] = not row['errors']
    except Exception as error:
        row['errors'].append(f'{type(error).__name__}: {error}')
    row['latency_ms'] = round((time.perf_counter()-start)*1000,3)
    return row

def judge_settings(generator_model=None):
    settings = get_ollama_settings()
    return {'model':settings.judge_model,'same_as_generator':settings.judge_model==(generator_model or settings.chat_model),
        'timeout':settings.judge_timeout,'rubric_version':RUBRIC_VERSION,'stage':'Geração RAG',
        'human_calibrated':False,'framework':'deepeval','framework_version':version('deepeval'),
        'threshold':None,'profile':CHAT_PROFILES['judge'],'temperature':0,
        'evaluation_code_sha256':source_hash()}

# Reserva um arquivo exclusivo por execução; os checkpoints atualizam só esse arquivo.
def reserve_report_path(requested=None,offline=False,groups_only=False):
    base = Path(requested) if requested else ROOT/'evals'/('RELATORIO-OFFLINE.md' if offline else 'RELATORIO.md')
    stamp = datetime.now(timezone(timedelta(hours=-3))).strftime('%Y-%m-%d_%H-%M-%S-%f')
    base.parent.mkdir(parents=True,exist_ok=True)
    counter = 0
    while True:
        suffix = f'-{counter}' if counter else ''
        target = base.with_name(f'{base.stem}_{stamp}{suffix}.md')
        reservation = target.with_name(target.stem+'_CLASSIFICATION.md') if groups_only else target
        if groups_only and any(target.with_name(target.stem+'_'+group+'.md').exists() for group in ('EXTRACTION','RAG')):
            counter += 1
            continue
        try:
            with reservation.open('x',encoding='utf-8'):
                pass
            return target
        except FileExistsError:
            counter += 1

# Julga respostas já salvas, sem refazer buscas ou gerar novas respostas do assistente.
def judge_saved(path,output):
    report = json.loads(Path(path).read_text(encoding='utf-8'))
    original_id,original_status = report['run_id'],report['status']
    report['source_run_id'] = original_id
    report['run_id'] = original_id+'-semantic-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
    generator_model = report['environment']['models']['chat']
    report['semantic'] = {**judge_settings(generator_model),'enabled':True,'status':'em execução','started_at':datetime.now(timezone.utc).isoformat()}
    report['status'] = original_status+'; avaliação semântica em execução'
    directory = ROOT/'evals'/'runs'/report['run_id']; directory.mkdir(parents=True)
    golds = {g['id']:g for g in json.loads((ROOT/'evals'/'datasets'/'rag_cases.json').read_text(encoding='utf-8'))}
    output = reserve_report_path(directory/(Path(output).name if output else 'RELATORIO.md'),groups_only=True)
    report.pop('report_file',None)
    def save():
        report['group_reports'] = write_group_reports(report,output,directory)
        (directory/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    save()
    try:
        tags = OllamaClient().tags()['models']
        model = report['semantic']['model']
        match = next((m for m in tags if m['name'] in {model,model+':latest'}),None)
        if not match: raise ValueError('Modelo juiz não instalado: '+model)
        report['semantic']['digest'] = match['digest']
        for row in report['rag']:
            row['semantic'] = judge_rag_case(row,golds[row['id']],generator_model) if row['id'] in golds else {'status':'não executado','reason':'Referência não encontrada.'}
            save()
            print(f"Juiz RAG {row['id']}: {row['semantic']['status']}",flush=True)
        report['semantic']['status'] = 'concluído'
        report['status'] = original_status+'; avaliação semântica concluída'
    except KeyboardInterrupt:
        report['semantic']['status'] = 'interrompido'; report['status'] = original_status+'; semântica incompleta'; save(); return 130
    except Exception as error:
        report['semantic']['status'] = 'erro'; report['semantic']['error'] = str(error)
        report['status'] = original_status+'; falha na etapa semântica'; save(); return 1
    save()
    print('Relatórios:',', '.join(report['group_reports'].values()),flush=True)
    return int(any(r.get('semantic',{}).get('status') in {'erro','parcial'} or not r['passed'] for r in report['rag']) or any(not r['passed'] for r in report['conversations']))

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offline',action='store_true',help='Somente kit e testes; não chama Ollama.')
    parser.add_argument('--repeats',type=int,default=1,help='Repetições das avaliações reais (1 a 10).')
    parser.add_argument('--output',type=Path,help='Nome base dos relatórios dentro de runs/<execução>; diretórios informados são ignorados.')
    parser.add_argument('--no-semantic',action='store_true',help='Desativa o juiz LLM; mantém as checagens determinísticas.')
    parser.add_argument('--judge-saved',type=Path,help='Avalia semanticamente o results.json informado, sem repetir a geração.')
    args = parser.parse_args(argv)
    if not 1 <= args.repeats <= 10: parser.error('--repeats deve estar entre 1 e 10')
    if args.judge_saved:
        if args.offline or args.no_semantic: parser.error('--judge-saved não pode ser combinado com --offline ou --no-semantic')
        return judge_saved(args.judge_saved,args.output)
    cases = json.loads((ROOT/'evals'/'datasets'/'cases.json').read_text(encoding='utf-8'))+json.loads((ROOT/'evals'/'datasets'/'regression_cases.json').read_text(encoding='utf-8'))
    golds = json.loads((ROOT/'evals'/'datasets'/'rag_cases.json').read_text(encoding='utf-8'))
    component_cases = {group:json.loads((ROOT/'evals'/'datasets'/filename).read_text(encoding='utf-8')) for group,filename in
                       [('classification','classification_cases.json'),('extraction','extraction_cases.json')]}
    now = datetime.now(timezone.utc)
    run_id = now.strftime('%Y%m%dT%H%M%S')+'-'+str(time.time_ns()%1000000)
    run_dir = ROOT/'evals'/'runs'/run_id
    run_dir.mkdir(parents=True)
    report = {'run_id':run_id,'started_at':now.astimezone(timezone(timedelta(hours=-3))).isoformat(),
        'status':'em execução','mode':'offline' if args.offline else 'completo','environment':environment(),
        'planned':{'conversations':len(cases)*args.repeats,'rag':len(golds)*args.repeats,
                   **{group:len(data)*args.repeats for group,data in component_cases.items()}},
        'conversations':[],'rag':[],'classification':[],'extraction':[]}
    report['semantic'] = {**judge_settings(),'enabled':not args.offline and not args.no_semantic,
        'status':'não executado' if args.offline or args.no_semantic else 'pendente'}
    output = reserve_report_path(run_dir/(args.output.name if args.output else ('RELATORIO-OFFLINE.md' if args.offline else 'RELATORIO.md')),args.offline,groups_only=True)
    print('Pasta dos relatórios:',output.parent,flush=True)
    def save():
        report['group_reports'] = write_group_reports(report,output,run_dir)
        (run_dir/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    save()
    try:
        try:
            with redirect_stdout(io.StringIO()): validate()
            report['kit'] = {'status':'passou','summary':'Contagens, referências e coerência do kit válidas.'}
        except Exception as error:
            report['kit'] = {'status':'falhou','summary':type(error).__name__}
        report['unit'] = run_units(); save()
        print(report['unit']['summary'],flush=True)
        if args.offline:
            report['preflight'] = {'status':'não executado','summary':'Modo offline: Ollama não consultado.'}
        else:
            try:
                tags = OllamaClient().tags()['models']
                report['environment']['installed_models'] = [{'name':m['name'],'digest':m['digest']} for m in tags]
                available = {m['name'] for m in tags}
                for name in report['environment']['models'].values():
                    if (name if ':' in name else name+':latest') not in available and name not in available:
                        raise ValueError('Modelo configurado não instalado: '+name)
                if report['semantic']['enabled']:
                    judge_model = report['semantic']['model']
                    if judge_model not in available and judge_model+':latest' not in available:
                        raise ValueError('Modelo juiz não instalado: '+judge_model)
                    report['semantic']['status'] = 'em execução'
                retriever = Retriever()
                # Valida índice e embeddings antes de iniciar a rodada longa; não reindexa silenciosamente.
                retriever.search('Prazo do reembolso por Pix')
                report['preflight'] = {'status':'passou','summary':'Ollama, modelos e índice disponíveis.'}
            except Exception as error:
                report['preflight'] = {'status':'falhou','summary':f'{type(error).__name__}: {error}'}
                report['status'] = 'bloqueado por pré-requisito'; save()
                return 1
            save()
            for repeat in range(1,args.repeats+1):
                for group,data in component_cases.items():
                    for case in data:
                        row = run_component(case,repeat,group)
                        report[group].append(row); save()
                        print(f"{group} {case['id']} [{repeat}]: {'PASSOU' if row['passed'] else 'FALHOU'}",flush=True)
                for case in cases:
                    row = run_conversation(case,repeat); report['conversations'].append(row); save()
                    print(f"Atendimento {case['id']} [{repeat}]: {'PASSOU' if row['passed'] else 'FALHOU'}",flush=True)
                all_chunks = chunk_documents(retriever.directory)
                for gold in golds:
                    row = run_rag_case(gold,repeat,retriever,all_chunks)
                    if report['semantic']['enabled']: row['semantic'] = judge_rag_case(row,gold)
                    report['rag'].append(row); save()
                    print(f"RAG {gold['id']} [{repeat}]: {'PASSOU' if row['passed'] else 'FALHOU'}",flush=True)
        if report['semantic']['enabled']: report['semantic']['status'] = 'concluído'
        failed = any(report[k]['status'] == 'falhou' for k in ['kit','unit']) or any(not r['passed'] for r in report['conversations']+report['rag']+report['classification']+report['extraction']) or any(r.get('semantic',{}).get('status') in {'erro','parcial'} for r in report['rag'])
        report['status'] = ('offline concluído' if args.offline else 'concluído')+(' com falhas' if failed else ' sem falhas automáticas')
        save()
        print('Relatórios:',', '.join(report['group_reports'].values()),flush=True)
        return 1 if failed else 0
    except KeyboardInterrupt:
        report['status'] = 'interrompido; execução incompleta'; save()
        return 130
    except Exception as error:
        report['status'] = 'falha de execução: '+type(error).__name__; save()
        raise

if __name__ == '__main__': raise SystemExit(main())
