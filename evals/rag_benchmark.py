"""Avaliação RAG isolada com checkpoints: python -m evals.rag_benchmark."""
import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from petz.retrieval import ROOT, Retriever, chunk_documents
from .suite import environment, run_rag_case


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--datasets', nargs='+', type=Path, default=[
        ROOT/'evals/datasets/rag_cases.json', ROOT/'evals/datasets/rag_regression_cases.json'])
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    golds = [case for path in args.datasets for case in json.loads(path.read_text(encoding='utf-8'))]
    if len({case['id'] for case in golds}) != len(golds):
        parser.error('Os IDs dos casos precisam ser únicos.')
    folder = args.output or ROOT/'evals/runs'/('rag-benchmark-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f'))
    folder.mkdir(parents=True, exist_ok=False)
    report = {'status':'running', 'environment':environment(),
              'scope':'RAG isolado: recuperação e seleção extrativa; sem classificador ou juiz semântico.',
              'datasets':[str(path) for path in args.datasets], 'planned':len(golds), 'rag':[]}
    def save():
        report['passed'] = sum(case['passed'] for case in report['rag'])
        report['completed'] = len(report['rag'])
        target = folder/'results.json'
        temporary = folder/'results.tmp'
        temporary.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        temporary.replace(target)
    save()
    print(f'Resultados: {folder}',flush=True)
    retriever = Retriever()
    all_chunks = chunk_documents(ROOT/'kit/politicas')
    # Embeddings primeiro: evita alternar os dois modelos na memória a cada caso.
    prepared = []
    for gold in golds:
        started = time.perf_counter()
        try:
            prepared.append((gold,retriever.search(gold['question']),None,(time.perf_counter()-started)*1000))
        except Exception as error:
            prepared.append((gold,[],type(error).__name__,(time.perf_counter()-started)*1000))
        print(f'Recuperação: {gold["id"]}',flush=True)
    for gold,hits,error,retrieval_ms in prepared:
        if error:
            row = {'id':gold['id'],'question':gold['question'],'passed':False,'errors':['Falha de recuperação: '+error]}
        else:
            row = run_rag_case(gold,1,retriever,all_chunks,hits=hits)
        row['retrieval_ms'] = round(retrieval_ms,3)
        report['rag'].append(row)
        save()
        print(f'{gold["id"]}: {"PASSOU" if row["passed"] else "FALHOU"} {row["errors"]}',flush=True)
    report['status'] = 'passed' if all(case['passed'] for case in report['rag']) else 'failed'
    save()
    print(f'{report["passed"]}/{report["planned"]}; {folder / "results.json"}',flush=True)
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
