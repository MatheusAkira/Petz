import json
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from petz.retrieval import ROOT, Chunk, chunk_documents
from evals.suite import retrieval_metrics, generation_checks, render_markdown, reserve_report_path

class EvaluationSuiteTests(unittest.TestCase):
    def test_group_reservation_does_not_create_main_report(self):
        with TemporaryDirectory() as directory:
            base = reserve_report_path(Path(directory)/'RELATORIO.md',groups_only=True)
            self.assertFalse(base.exists())
            self.assertTrue(base.with_name(base.stem+'_CLASSIFICATION.md').exists())

    def test_report_names_preserve_existing_files_and_are_unique(self):
        with TemporaryDirectory() as directory:
            base = Path(directory)/'RELATORIO.md'
            base.write_text('original',encoding='utf-8')
            first = reserve_report_path(base)
            first.write_text('primeira execução',encoding='utf-8')
            second = reserve_report_path(base)
            self.assertNotEqual(first,second)
            self.assertEqual(base.read_text(encoding='utf-8'),'original')
            self.assertEqual(first.read_text(encoding='utf-8'),'primeira execução')
            self.assertRegex(first.name,r'^RELATORIO_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}-\d{6}(?:-\d+)?\.md$')

    def test_gold_passages_exist_in_current_chunks(self):
        chunks = chunk_documents(ROOT/'kit'/'politicas')
        cases = json.loads((ROOT/'evals'/'datasets'/'rag_cases.json').read_text(encoding='utf-8'))
        for case in cases:
            if not case['should_abstain']:
                with self.subTest(case=case['id']):
                    metrics = retrieval_metrics(chunks,case,chunks)
                    self.assertEqual(metrics['evidence_coverage'],1)

    def test_ranking_metrics_penalize_wrong_first_result_and_missing_evidence(self):
        right = Chunk('a','kit/politicas/reembolso.md','Título','Pix leva cinco dias úteis.')
        wrong = Chunk('b','kit/politicas/frete.md','Título','Outro tema.')
        gold = {'source':'reembolso','evidence':['Pix leva cinco dias úteis.'],'should_abstain':False}
        metrics = retrieval_metrics([wrong,right],gold,[right,wrong])
        self.assertEqual(metrics['precision_returned'],.5)
        self.assertEqual(metrics['mrr'],.5)
        self.assertLess(metrics['ndcg_at_k'],1)
        self.assertEqual(retrieval_metrics([],gold,[right])['evidence_coverage'],0)

    def test_valid_quote_does_not_automatically_pass_factual_checks(self):
        chunk = Chunk('a','kit/politicas/reembolso.md','Título','Pix leva cinco dias úteis.')
        gold = {'source':'reembolso','should_abstain':False,'answer_patterns':['cinco dias']}
        output = {'supported':True,'answer':'Pix leva dez dias.','citations':[{'chunk_id':'a','quote':chunk.text}]}
        self.assertTrue(generation_checks(output,gold,[chunk]))

    def test_markdown_marks_unexecuted_online_steps(self):
        report = {'run_id':'test','started_at':'2026-10-30','status':'em execução','mode':'offline','environment':{},
            'planned':{'conversations':36,'rag':11},'conversations':[],'rag':[]}
        text = render_markdown(report)
        self.assertIn('0 / 36',text)
        self.assertIn('Etapa não executada',text)
        self.assertIn('pendentes',text)

    def test_results_are_at_end_with_individual_tests_and_readable_rag(self):
        report = {'run_id':'format','started_at':'2026-10-31','status':'concluído','mode':'completo','environment':{},
            'planned':{'conversations':0,'rag':1},'conversations':[],
            'unit':{'status':'passou','output':'test_example (test_example.Example.test_example) ... ok\n'},
            'rag':[{'id':'pix','repeat':1,'question':'Prazo?','passed':True,'errors':[],'latency_ms':12,
                'hits':[{'id':'reembolso:0','source':'kit/politicas/reembolso.md','score':.9,'text':'Pix leva cinco dias úteis.'}],
                'generation':{'supported':True,'answer':'Até cinco dias úteis.','citations':[{'chunk_id':'reembolso:0','quote':'Pix leva cinco dias úteis.'}]}}]}
        text = render_markdown(report)
        results = text.index('## Resultados dos testes')
        self.assertLess(text.index('## Como repetir'),results)
        self.assertLess(text.index('## Interpretação'),results)
        self.assertGreater(text.index('`test_example`'),results)
        self.assertGreater(text.index('**Resposta gerada:**'),results)
        self.assertIn('| Trecho | Fonte | Similaridade |',text)
        self.assertIn('| Trecho | Evidência literal |',text)
        self.assertIn('> Até cinco dias úteis.',text)
        self.assertGreater(text.index('## Avaliação geral — todas as métricas'),text.index('**Resposta gerada:**'))
        self.assertIn('| MRR | Não disponível |',text)
        summary = text.split('## Avaliação geral — todas as métricas')[1]
        self.assertIn('| MRR | Não disponível |',summary)
        self.assertIn('### Recuperação RAG',summary)
        self.assertIn('| Métrica | Resultado | Base / interpretação |',summary)
        self.assertEqual(text.count('<details>'),text.count('</details>'))
        self.assertNotIn('**Resposta gerada:**',summary)
        self.assertIn('</details>',text[:text.index('## Avaliação geral — todas as métricas')])
        self.assertTrue(text.rstrip().endswith('Revisão humana pendente.'))

if __name__ == '__main__': unittest.main()
