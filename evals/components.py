"""Avaliações isoladas de intenção e filtros; relatórios separados por componente."""
import json
import statistics
import time
from pathlib import Path

GROUPS = {'classification':'Classificação de intenção', 'extraction':'Extração de filtros', 'rag':'Geração de respostas com RAG'}
FIELDS = ('query','species','category','budget','new_search','alternatives')

def run_component(case,repeat,group):
    """Chama a função de produção diretamente, sem inferir seu resultado pela rota final."""
    from petz.llm import plan
    from petz.catalog import extract_product_query
    start = time.perf_counter()
    row = {'id':case['id'],'repeat':repeat,'message':case['message'],'context':case.get('context',{}),
           'expected':case['expected'],'passed':False,'errors':[]}
    try:
        row['actual'] = plan(row['message'],row['context']) if group == 'classification' else extract_product_query(row['message'],row['context'])
        row['passed'] = row['actual'] == row['expected']
        if not row['passed']:
            row['errors'] = ['Intenção diferente da referência.'] if group == 'classification' else [f'Campo divergente: {key}' for key in FIELDS if row['actual'].get(key) != row['expected'][key]]
    except Exception as error:
        row['errors'] = [f'{type(error).__name__}: {error}']
    row['latency_ms'] = round((time.perf_counter()-start)*1000,3)
    return row

def component_metrics(rows,group,planned):
    """Erros contam como falhas; notas ausentes não são tratadas como zero medições."""
    total = len(rows)
    rate = lambda value,denominator=total: f'{value/denominator:.4f}' if denominator else 'Não avaliado'
    metrics = [('Executados / planejados',f'{total} / {planned}'),('Acertos exatos',sum(r['passed'] for r in rows)),
               ('Acurácia / exact match',rate(sum(r['passed'] for r in rows))),
               ('Saídas validadas',rate(sum('actual' in r for r in rows))),('Erros de execução',sum('actual' not in r for r in rows))]
    if group == 'classification':
        labels = sorted({r['expected'] for r in rows})
        per_label = []
        for label in labels:
            tp = sum(r['expected'] == label and r.get('actual') == label for r in rows)
            fp = sum(r['expected'] != label and r.get('actual') == label for r in rows)
            fn = sum(r['expected'] == label and r.get('actual') != label for r in rows)
            precision = tp/(tp+fp) if tp+fp else 0
            recall = tp/(tp+fn) if tp+fn else 0
            per_label.append((label,precision,recall,2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 0))
        for index,name in [(1,'Precisão macro'),(2,'Recall macro'),(3,'F1 macro')]:
            metrics.append((name,f'{statistics.mean(item[index] for item in per_label):.4f}' if per_label else 'Não avaliado'))
    else:
        for field in FIELDS:
            metrics.append((f'Acurácia · {field}',rate(sum('actual' in r and r['actual'].get(field) == r['expected'][field] for r in rows))))
        metrics.append(('Acurácia micro dos seis campos',rate(sum('actual' in r and r['actual'].get(field) == r['expected'][field] for r in rows for field in FIELDS),total*len(FIELDS))))
        positives = [(r,field) for r in rows for field in FIELDS if r['expected'][field] not in (None,False,'none')]
        metrics.append(('Acerto em campos informativos',rate(sum('actual' in r and r['actual'].get(field) == r['expected'][field] for r,field in positives),len(positives))))
    times = sorted(r['latency_ms'] for r in rows)
    if times:
        import math
        for name,value in [('média',statistics.mean(times)),('p50',statistics.median(times)),('p95',times[max(0,math.ceil(.95*len(times))-1)])]:
            metrics.append(('Latência '+name,f'{value:.2f} ms'))
    return metrics

def group_summary(report):
    from .reporting import cell
    lines = ['## Comparação final dos três grupos','', '| Grupo | Métrica | Resultado |','| --- | --- | ---: |']
    for group in ('classification','extraction'):
        for metric,value in component_metrics(report.get(group,[]),group,report['planned'].get(group,0)):
            lines.append(f'| {GROUPS[group]} | {cell(metric)} | {cell(value)} |')
    lines += ['', 'As métricas de recuperação, geração, abstenção e juiz semântico do terceiro grupo constam nas tabelas RAG abaixo. Não se aplica fidelidade semântica de texto a um rótulo de intenção ou a filtros JSON.']
    return lines

def render_group(report,group):
    from .reporting import cell, quote, result_details, consolidated_table
    lines = [f'# Avaliação — {GROUPS[group]}','',f"**Execução:** `{report['run_id']}`  ",f"**Início:** {report['started_at']}  ",f"**Estado:** {report['status']}",'',
             '## 1. Testes executados','']
    rows = report.get(group,[])
    if not rows: lines += ['Não executado. Nenhuma aprovação pode ser inferida.','']
    if group == 'rag':
        lines += ['Procedimento: recuperar evidências, gerar resposta estruturada, validar citações e fatos esperados e, quando habilitado, aplicar o juiz semântico.','']
        golds = {r['id']:r for r in json.loads((Path(__file__).parent/'datasets'/'rag_cases.json').read_text(encoding='utf-8'))}
        for row in rows:
            gold = golds.get(row['id'],{})
            lines += [f"### Referência — {row['id']}",'','```json',json.dumps(gold,ensure_ascii=False,indent=2),'```','']
            lines += result_details(row,'RAG')
        lines += ['## 2. Avaliação final do grupo','']
        table = consolidated_table(report)
        lines += ['| Etapa | Métrica | Resultado | Base / interpretação |','| --- | --- | ---: | --- |']
        lines += [line for line in table if line.startswith(('| RAG |','| Recuperação RAG |','| Abstenção RAG |','| Geração RAG |','| Geração RAG ·','| Juiz semântico |','| Revisão humana |'))]
        lines += ['', 'Citações e checks textuais não comprovam suporte semântico completo. Juiz automático sem calibração humana; confira modelo e independência.']
    else:
        lines += ['Procedimento: chamar diretamente a função de produção com mensagem e contexto explícitos; comparar a saída validada com uma referência fixa. Erros e timeouts contam como falhas.','']
        for row in rows:
            lines += [f"### {row['id']} · repetição {row['repeat']}",'','**Mensagem:**','',quote(row['message']),'','**Contexto fornecido:**','','```json',json.dumps(row['context'],ensure_ascii=False,indent=2),'```','',
                      '| Referência esperada | Saída validada obtida | Resultado | Tempo |','| --- | --- | --- | ---: |',
                      f"| {cell(json.dumps(row['expected'],ensure_ascii=False))} | {cell(json.dumps(row.get('actual'),ensure_ascii=False)) if 'actual' in row else 'Sem saída válida'} | {'ACERTOU' if row['passed'] else 'FALHOU'} | {row['latency_ms']:.2f} ms |",'']
            if group == 'extraction':
                lines += ['| Campo | Esperado | Obtido | Acertou? |','| --- | --- | --- | --- |']
                for field in FIELDS:
                    actual = row.get('actual',{})
                    lines.append(f"| {field} | {cell(json.dumps(row['expected'][field],ensure_ascii=False))} | {cell(json.dumps(actual.get(field),ensure_ascii=False)) if 'actual' in row else 'Não disponível'} | {'Sim' if 'actual' in row and actual.get(field) == row['expected'][field] else 'Não'} |")
                lines += ['']
            lines += ['- '+error for error in row['errors']]+['']
        lines += ['## 2. Avaliação final do grupo','','| Métrica | Resultado |','| --- | ---: |']
        lines += [f'| {cell(metric)} | {cell(value)} |' for metric,value in component_metrics(rows,group,report['planned'].get(group,0))]
        if group == 'classification' and rows:
            lines += ['', '### Matriz de confusão (formato longo)','','| Esperado | Obtido | Quantidade |','| --- | --- | ---: |']
            from collections import Counter
            for (expected,actual),count in sorted(Counter((r['expected'],r.get('actual','ERRO')) for r in rows).items()):
                lines.append(f'| {cell(expected)} | {cell(actual)} | {count} |')
        lines += ['', 'Escala das taxas: 0–1. Macro: média das classes presentes nas referências executadas; classes ausentes não foram avaliadas. Campos ausentes/null também contam na acurácia de filtros; consulte a métrica de campos informativos. As saídas são as devolvidas pelas funções de produção, após validações e correções; não são o texto bruto do modelo.', '', 'Amostra preparada para regressão; revisão independente e calibração humana pendentes.']
    return '\n'.join(lines)+'\n'

def write_group_reports(report,output,directory):
    """Compartilha a data da execução e preserva os arquivos de execuções anteriores."""
    files = {}
    for group in GROUPS:
        path = output.with_name(output.stem+'_'+group.upper()+'.md')
        files[group] = path.name
        text = render_group(report,group)
        path.write_text(text,encoding='utf-8')
        if directory/path.name != path:
            (directory/path.name).write_text(text,encoding='utf-8')
    return files
