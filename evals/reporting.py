"""Formatação do relatório Markdown, sem executar testes ou chamar modelos."""
import json
import math
import re
import statistics
from .metrics import METRIC_MAP
from .semantic import METRICS as SEMANTIC_METRICS

def cell(value):
    return str(value).replace('|','\\|').replace('\n','<br>')

def quote(text):
    return '\n'.join('> '+line for line in str(text).splitlines()) or '> —'

def latency_summary(rows):
    values = sorted(r['latency_ms'] for r in rows if 'latency_ms' in r)
    if not values: return '—'
    return f"p50: {statistics.median(values):.2f} ms · p95: {values[max(0,math.ceil(.95*len(values))-1)]:.2f} ms"

# Consolida as métricas disponíveis sem transformar etapas ausentes em aprovações.
def consolidated_table(report, compact=False):
    rows = []
    grouped = {}
    def add(stage,metric,value,note='—'):
        rows.append(f'| {cell(stage)} | {cell(metric)} | {cell(value)} | {cell(note)} |')
        grouped.setdefault(stage,[]).append((metric,value,note))
    def percent(passed,total):
        return f'{100*passed/total:.2f}%' if total else 'Não disponível'
    add('Execução','Estado',report['status'],f"Modo: {report['mode']}")
    for key,label in [('kit','Kit'),('preflight','Ollama e índice')]:
        item = report.get(key,{})
        add(label,'Resultado',item.get('status','pendente'),item.get('summary','Etapa ainda não executada.'))
    unit = report.get('unit',{})
    add('Engenharia','Estado',unit.get('status','pendente'),unit.get('summary','Etapa ainda não executada.'))
    if 'count' in unit:
        skipped = len(re.findall(r'\.\.\. skipped\b',unit.get('output','')))
        failed,errors = unit.get('failures',0),unit.get('errors',0)
        passed = max(0,unit['count']-failed-errors-skipped)
        add('Engenharia','Testes executados',unit['count'])
        add('Engenharia','Aprovados',passed,'Contagem por método de teste; não por assert.')
        add('Engenharia','Falhas',failed)
        add('Engenharia','Erros',errors)
        add('Engenharia','Ignorados',skipped)
        add('Engenharia','Taxa de aprovação',percent(passed,unit['count']),'Inclui ignorados no denominador.')
    for key,label in [('conversations','Atendimento'),('rag','RAG')]:
        cases = report[key]
        total,planned = len(cases),report['planned'][key]
        passed = sum(c['passed'] for c in cases)
        add(label,'Cenários concluídos / planejados',f'{total} / {planned}','Etapa não executada' if not total else 'Cada repetição conta como uma execução.')
        add(label,'Aprovados',passed if total else 'Não executado')
        add(label,'Reprovados',total-passed if total else 'Não executado')
        add(label,'Taxa de aprovação',percent(passed,total),'Verificações automáticas; não equivale a qualidade semântica certificada.')
        values = sorted(c['latency_ms'] for c in cases if 'latency_ms' in c)
        if values:
            timings = {'Latência média':statistics.mean(values),'Latência p50':statistics.median(values),
                'Latência p95':values[max(0,math.ceil(.95*len(values))-1)],
                'Latência mínima':values[0],'Latência máxima':values[-1],'Tempo acumulado dos cenários':sum(values)}
            for metric,value in timings.items():
                add(label,metric,f'{value:.2f} ms','Tempo total por cenário; pode incluir vários turnos e chamadas.')
    areas = sorted({c.get('area','sem categoria') for c in report['conversations']})
    for area in areas:
        cases = [c for c in report['conversations'] if c.get('area','sem categoria') == area]
        passed = sum(c['passed'] for c in cases)
        add('Atendimento por área',area,f'{passed} / {len(cases)} — {percent(passed,len(cases))}','Cenários aprovados / executados.')
    metrics = [c['retrieval'] for c in report['rag'] if 'source_hit' in c.get('retrieval',{})]
    names = {'source_hit':'Acerto de fonte','precision_returned':'Precisão dos chunks retornados',
        'chunk_recall_at_k':'Recall de chunks@k','mrr':'MRR','ndcg_at_k':'nDCG@k','evidence_coverage':'Cobertura de evidências'}
    for key,label in names.items():
        value = f'{sum(m[key] for m in metrics)/len(metrics):.4f}' if metrics else 'Não disponível'
        add('Recuperação RAG',label,value,f'Média em {len(metrics)} casos positivos com métricas disponíveis; escala 0–1.')
    negatives = [c for c in report['rag'] if 'retrieval_empty' in c.get('retrieval',{})]
    if negatives:
        abstained = sum(c.get('generation',{}).get('supported') is False for c in negatives)
        add('Abstenção RAG','Respostas sem suporte declarado',f'{abstained} / {len(negatives)}',percent(abstained,len(negatives))+' nos casos negativos com recuperação registrada.')
        add('Abstenção RAG','Recuperações vazias',f"{sum(c['retrieval']['retrieval_empty'] for c in negatives)} / {len(negatives)}",'Ausência de trechos acima do limiar.')
    if report['rag']:
        supported = sum(c.get('generation',{}).get('supported') is True for c in report['rag'])
        unsupported = sum(c.get('generation',{}).get('supported') is False for c in report['rag'])
        add('Geração RAG','Saídas com suporte e citações validadas',supported,'Validação de existência literal; não prova fidelidade de todas as afirmações.')
        add('Geração RAG','Saídas sem suporte declarado',unsupported,'Inclui abstenção sem geração quando não há trechos.')
        add('Geração RAG','Casos sem saída validada',len(report['rag'])-supported-unsupported,'Consultar os erros de execução de cada caso.')
        known = [c for c in report['rag'] if 'generation' in c and ('source_hit' in c.get('retrieval',{}) or 'retrieval_empty' in c.get('retrieval',{}))]
        tp = sum('retrieval_empty' in c['retrieval'] and not c['generation']['supported'] for c in known)
        fp = sum('source_hit' in c['retrieval'] and not c['generation']['supported'] for c in known)
        fn = sum('retrieval_empty' in c['retrieval'] and c['generation']['supported'] for c in known)
        tn = sum('source_hit' in c['retrieval'] and c['generation']['supported'] for c in known)
        add('Abstenção RAG','Taxa de decisão correta',percent(tp+tn,len(known)),'Responder/se abster conforme a referência, nos casos com saída registrada.')
        add('Abstenção RAG','Precisão da abstenção',percent(tp,tp+fp),'Abstenções corretas / abstenções previstas; casos com saída registrada.')
        add('Abstenção RAG','Recall da abstenção',percent(tp,tp+fn),'Abstenções corretas / casos negativos com saída registrada.')
        add('Abstenção RAG','Recusas indevidas',fp,'Casos positivos com supported=false.')
        add('Abstenção RAG','Respostas indevidas',fn,'Casos negativos com supported=true; não implica sozinho provar alucinação.')
    judged = [c['semantic'] for c in report['rag'] if c.get('semantic',{}).get('status') == 'avaliado']
    scored = [c['semantic'] for c in report['rag'] if c.get('semantic',{}).get('status') in {'avaliado','parcial'}]
    semantic = report.get('semantic',{})
    add('Juiz semântico','Estado',semantic.get('status','não executado'),'Aplicado à geração RAG; atendimento mantém os checks determinísticos.')
    same = semantic.get('same_as_generator')
    independence = 'Mesmo gerador; avaliação não independente.' if same is True else 'Modelo distinto; calibração humana pendente.' if same is False else 'Independência não registrada.'
    add('Juiz semântico','Modelo',semantic.get('model','Não registrado'),independence)
    add('Juiz semântico','Framework',semantic.get('framework','juiz personalizado legado'),semantic.get('framework_version','Versão não registrada'))
    add('Juiz semântico','Casos avaliados',f"{len(judged)} / {len(report['rag'])}",'Casos sem geração validada podem ficar não aplicáveis.')
    eligible_judgments = sum('generation' in c for c in report['rag'])
    add('Juiz semântico','Taxa de julgamentos válidos',percent(len(judged),eligible_judgments),'Julgamentos válidos / casos com saída disponível para julgar.')
    add('Juiz semântico','Rubrica',semantic.get('rubric_version','Não registrada'))
    add('Juiz semântico','Erros',sum(c.get('semantic',{}).get('status') == 'erro' for c in report['rag']))
    add('Juiz semântico','Avaliações parciais',sum(c.get('semantic',{}).get('status') == 'parcial' for c in report['rag']),'Notas válidas são mantidas; falhas não entram nas médias.')
    add('Juiz semântico','Falhas por métrica',sum(len(c.get('semantic',{}).get('metric_errors',{})) for c in report['rag']))
    add('Juiz semântico','Casos sem resposta para julgar',sum(c.get('semantic',{}).get('status') == 'não executado' for c in report['rag']),'Não recebem uma nota fictícia.')
    for key,label in SEMANTIC_METRICS.items():
        values = [s['scores'][key] for s in scored if s['scores'].get(key) is not None]
        add('Geração RAG · juiz LLM',label,f'{statistics.mean(values):.4f}' if values else 'Não avaliado',
            f'Estimativa em {len(values)} casos aplicáveis; escala 0–1; sem calibração humana.')
    judge_times = [s['latency_ms'] for s in [c.get('semantic',{}) for c in report['rag']] if 'latency_ms' in s]
    if judge_times:
        ordered = sorted(judge_times)
        for label,value in [('média',statistics.mean(ordered)),('p50',statistics.median(ordered)),('p95',ordered[max(0,math.ceil(.95*len(ordered))-1)]),('mínima',ordered[0]),('máxima',ordered[-1])]:
            add('Juiz semântico','Latência '+label,f'{value:.2f} ms','Separada da latência de busca e geração do assistente.')
    add('Revisão humana','Correção, fidelidade, completude e utilidade','Pendente','Não são substituídas pelos checks textuais ou pelas citações literais.')
    if compact:
        lines = ['## Avaliação geral — todas as métricas','',
            'Resultados agregados por etapa, sem casos individuais. Notas semânticas: escala 0–1. Tempos: milissegundos. Etapas não executadas não representam aprovação.','']
        for stage,values in grouped.items():
            lines += [f'### {stage}','','| Métrica | Resultado | Base / interpretação |','| --- | ---: | --- |']
            lines += [f'| {cell(metric)} | {cell(value)} | {cell(note)} |' for metric,value,note in values]
            lines += ['']
        lines += ['**Limitações da avaliação:** as taxas refletem somente esta amostra. As notas do juiz são consultivas e sem limiar calibrado. Confira sua cobertura e independência acima. Revisão humana pendente.']
        return lines
    return ['## Tabela consolidada de todas as etapas','',
        'As taxas usam apenas os cenários executados, salvo indicação contrária. Resultados não disponíveis não representam aprovação.','',
        '| Etapa | Métrica / resultado | Valor | Base / observação |','| --- | --- | ---: | --- |',*rows]

def result_details(row,group):
    state = 'APROVADO' if row['passed'] else 'REPROVADO'
    lines = [f"#### {group} · {row['id']} · repetição {row['repeat']}",'',
        f"**Resultado:** {state} · **Tempo:** {row.get('latency_ms',0):.2f} ms",'']
    if row.get('errors'):
        lines += ['**Verificações reprovadas:**','']+['- '+error for error in row['errors']]+['']
    for index,turn in enumerate(row.get('turns',[]),1):
        lines += [f'**Turno {index} — pergunta**','',quote(turn['input']),'',
            '**Resposta**','',quote(turn['answer']),'',
            f"**Rota:** `{turn['route']}`  ",
            '**Fontes:** '+(', '.join(f'`{source}`' for source in turn['sources']) or 'nenhuma'), '']
    if 'question' in row:
        lines += ['**Pergunta**','',quote(row['question']),'']
    if 'expected' in row:
        lines += ['**Expectativas verificadas:**','', '| Campo | Esperado |','| --- | --- |']
        lines += [f'| `{key}` | {cell(json.dumps(value,ensure_ascii=False))} |' for key,value in row['expected'].items()]+['']
    if 'hits' in row:
        lines += ['**Trechos recuperados:**','']
        if row['hits']:
            lines += ['| Trecho | Fonte | Similaridade |','| --- | --- | ---: |']
            for hit in row['hits']:
                lines.append(f"| `{cell(hit['id'])}` | `{cell(hit['source'])}` | {hit['score']:.4f} |")
            lines += ['', '**Evidências recuperadas (texto):**','']
            for hit in row['hits']:
                lines += [f"**{hit['id']}**",'',quote(hit['text']),'']
            lines += ['']
        else:
            lines += ['Nenhum trecho acima do limiar.','']
    if 'generation' in row:
        output = row['generation']
        lines += [f"**Suporte declarado pelo modelo:** {'sim' if output['supported'] else 'não'}",'',
            '**Resposta gerada:**','',quote(output['answer']),'']
        if output.get('citations'):
            lines += ['**Citações:**','', '| Trecho | Evidência literal |','| --- | --- |']
            lines += [f"| `{cell(c['chunk_id'])}` | {cell(c['quote'])} |" for c in output['citations']]+['']
        else:
            lines += ['**Citações:** nenhuma.','']
    if 'semantic' in row:
        semantic = row['semantic']
        lines += ['**Avaliação semântica automática:** '+semantic['status'],'']
        if semantic.get('status') in {'avaliado','parcial'}:
            lines += [f"**Juiz:** `{semantic.get('model','não registrado')}` · **Rubrica:** `{semantic.get('rubric_version','não registrada')}`",'']
            lines += [f"**Framework:** {semantic.get('framework','juiz personalizado legado')} {semantic.get('framework_version','')}",'']
            lines += ['| Métrica · geração RAG | Nota (0–1) | Justificativa do juiz |','| --- | ---: | --- |']
            for key,label in SEMANTIC_METRICS.items():
                score = semantic['scores'][key]
                state = semantic.get('metric_results',{}).get(key,{}).get('status')
                missing = 'Erro na métrica' if state == 'erro' else 'Não aplicável'
                lines.append(f"| {label} | {score if score is not None else missing} | {cell(semantic['reasons'][key])} |")
            lines += ['']
            if semantic.get('metric_results'):
                lines += ['**Métodos e execução do DeepEval:**','','| Métrica | Implementação | Estado | Tempo (ms) |','| --- | --- | --- | ---: |']
                for key,item in semantic['metric_results'].items():
                    lines.append(f"| {cell(SEMANTIC_METRICS[key])} | {cell(item['metric'])} | {cell(item['status'])} | {item.get('latency_ms',0):.2f} |")
                lines += ['']
            if semantic.get('reference_facts'):
                lines += ['**Fatos de referência usados pelo juiz:**','']+['- '+fact for fact in semantic['reference_facts']]+['']
            for evidence in semantic.get('evidence',[]):
                lines += [f"**Evidência do juiz — {evidence['chunk_id']}:**",'',quote(evidence['quote']),'']
        else:
            lines += [semantic.get('reason','Etapa ainda não concluída.'),'']
    lines += ['---','']
    return lines

# Mantém orientações no início e reúne todos os resultados na seção final.
def render_markdown(report):
    from .components import GROUPS, group_summary
    lines = ['# Relatório de avaliação do Pet Aurora','',
        f"**Arquivo:** `{report.get('report_file','não registrado')}`",'',
        f"- Execução: `{report['run_id']}`",
        f"- Início: {report['started_at']}",
        f"- Estado: **{report['status']}**; modo: `{report['mode']}`.",
        '- Data dos pedidos nos testes: **29/10/2026**, fixa para reproduzir os resultados.',
        '- Este relatório avalia a amostra definida; não certifica ausência de erros em toda pergunta possível.',
        '', '## Documentos por grupo','',
        *[f"- [{GROUPS[group]}]({name})" for group,name in report.get('group_reports',{}).items()],
        'Cada documento contém duas etapas: testes individuais (entrada, contexto, referência, saída e acerto/erro) e avaliação final com as métricas do grupo. Atendimento completo e engenharia são verificações complementares.',
        '', '## Ambiente e reprodutibilidade','', '```json',json.dumps(report['environment'],ensure_ascii=False,indent=2),'```','',
        '## Interpretação e revisão humana','',
        '- Testes de engenharia usam respostas simuladas em vários cenários; não medem compreensão da LLM.',
        '- Atendimento e RAG, quando executados, usam o Ollama real. O juiz semântico é uma etapa separada, quando habilitada.',
        '- Citações literais e padrões textuais não provam fidelidade ou completude semântica. Uma paráfrase correta pode falhar em um check textual.',
        '- Para cada resposta, revisar fatos, exceções, suporte de cada afirmação, utilidade e ausência de dados indevidos.',
        '- As notas semânticas são estimativas do juiz, não garantias de fidelidade completa. Revisão humana e calibração independente estão **pendentes**.',
        '- Se o juiz for o mesmo modelo do gerador, a avaliação não é independente e pode compartilhar seus vieses; confira o modelo na tabela final.',
        '- As notas semânticas são consultivas: não alteram passed dos checks determinísticos e ainda não têm limiar de aprovação calibrado.',
        '- Os casos e referências foram preparados com auxílio de IA; não são um conjunto independente revisado por especialistas.',
        '- Com uma repetição, não há medida confiável de estabilidade. Use --repeats 3 para comparar resultados por caso.',
        '- Código 1 indica falha automática ou execução completa bloqueada. Etapas não executadas não são aprovações.',
        '', '## Como repetir','', '```powershell',
        r'.\.venv\Scripts\python.exe -m evals.suite',
        r'.\.venv\Scripts\python.exe -m evals.suite --offline --output evals/RELATORIO-OFFLINE.md',
        r'.\.venv\Scripts\python.exe -m evals.suite --repeats 3',
        '```','',
        '## Métricas e etapas de aplicação','',
        '| Etapa | Métrica | Método | Critério / limite |','| --- | --- | --- | --- |',
        *[f'| {cell(stage)} | {cell(metric)} | {cell(method)} | {cell(note)} |' for stage,metric,method,note in METRIC_MAP],
        '',
        '<details>','<summary>Detalhes técnicos e resultados individuais (opcional)</summary>','',
        '## Resultados dos testes','',
        '### 1. Engenharia e preparação','',
        '| Etapa | Estado | Resultado |','| --- | --- | --- |']
    for key,label in [('kit','Validação do kit'),('unit','Testes de engenharia'),('preflight','Ollama e índice')]:
        item = report.get(key,{'status':'pendente'})
        lines.append(f"| {label} | {item['status']} | {cell(item.get('summary','—'))} |")
    unit = report.get('unit',{})
    if unit.get('output'):
        tests = re.findall(r'^(test\S+)\s+\(([^)]+)\)\s+\.\.\.\s+(.+)$',unit['output'],re.MULTILINE)
        if tests:
            lines += ['', '**Resultados individuais de engenharia:**','', '| Módulo / classe | Teste | Resultado |','| --- | --- | --- |']
            for name,identifier,status in tests:
                labels = {'ok':'APROVADO','FAIL':'REPROVADO','ERROR':'ERRO'}
                lines.append(f"| `{cell(identifier.rsplit('.',1)[0])}` | `{cell(name)}` | {cell(labels.get(status.strip(),status.strip()))} |")
        lines += ['', '<details>','<summary>Saída original completa dos testes de engenharia</summary>','',
            '```text',unit['output'].rstrip(),'```','','</details>','']
    for key,title in [('conversations','2. Atendimento com modelo real'),('rag','3. Recuperação e geração RAG')]:
        rows = report[key]
        lines += ['',f'### {title}','',
            f"Concluídos: **{len(rows)} / {report['planned'][key]}**. Aprovados nas verificações automáticas: **{sum(r['passed'] for r in rows)}**."]
        if not rows:
            lines += ['', 'Etapa não executada; não representa aprovação.']
            continue
        lines += ['', '**Latência por cenário:** '+latency_summary(rows)+'.','',
            '| Caso | Repetição | Resultado | Falhas | Tempo (ms) |','| --- | ---: | --- | --- | ---: |']
        for row in rows:
            lines.append(f"| {row['id']} | {row['repeat']} | {'APROVADO' if row['passed'] else 'REPROVADO'} | {cell('; '.join(row['errors']) or '—')} | {row['latency_ms']:.2f} |")
    metrics = [r['retrieval'] for r in report['rag'] if r.get('retrieval') and 'source_hit' in r['retrieval']]
    if metrics:
        lines += ['', '### 4. Métricas de recuperação','', '| Métrica | Média |','| --- | ---: |']
        for metric in ['source_hit','precision_returned','chunk_recall_at_k','mrr','ndcg_at_k','evidence_coverage']:
            lines.append(f"| `{metric}` | {sum(m[metric] for m in metrics)/len(metrics):.4f} |")
        lines += ['', 'Relevância definida por fonte e passagem literal de referência. A precisão usa apenas os resultados retornados; o limiar pode reduzir a quantidade abaixo de k. Essas métricas não medem toda forma de relevância semântica.']
    for key,title in [('conversations','Detalhes dos cenários de atendimento'),('rag','Detalhes dos cenários de RAG')]:
        if report[key]:
            lines += ['',f'### {title}','']
            for row in report[key]: lines += result_details(row,'Atendimento' if key == 'conversations' else 'RAG')
    lines += ['','</details>','',*group_summary(report),'',*consolidated_table(report,compact=True)]
    return '\n'.join(lines)+'\n'
