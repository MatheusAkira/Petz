import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from evals.components import component_metrics, run_component, render_group, write_group_reports
from petz.retrieval import ROOT

class ComponentEvaluationTests(unittest.TestCase):
    def test_classification_errors_reduce_macro_recall_and_accuracy(self):
        rows = [{'expected':'pedido','actual':'pedido','passed':True,'latency_ms':1},
                {'expected':'trocas','passed':False,'latency_ms':2}]
        values = dict(component_metrics(rows,'classification',2))
        self.assertEqual(values['Acurácia / exact match'],'0.5000')
        self.assertEqual(values['Recall macro'],'0.5000')
        self.assertEqual(values['F1 macro'],'0.5000')
        self.assertEqual(values['Erros de execução'],1)

    def test_extraction_metrics_distinguish_whole_object_and_fields(self):
        expected = {'query':None,'species':'gato','category':'racao','budget':100,'new_search':False,'alternatives':'none'}
        rows = [{'expected':expected,'actual':{**expected,'budget':50},'passed':False,'latency_ms':1}]
        values = dict(component_metrics(rows,'extraction',1))
        self.assertEqual(values['Acurácia / exact match'],'0.0000')
        self.assertEqual(values['Acurácia micro dos seis campos'],'0.8333')
        self.assertEqual(values['Acerto em campos informativos'],'0.6667')

    def test_direct_call_preserves_context_expected_and_actual(self):
        case = {'id':'I','message':'1004','context':{'pending':'trocas'},'expected':'trocas'}
        with patch('petz.llm.plan',return_value='pedido') as model:
            row = run_component(case,1,'classification')
        model.assert_called_once_with('1004',{'pending':'trocas'})
        self.assertEqual(row['actual'],'pedido')
        self.assertFalse(row['passed'])
        self.assertTrue(row['errors'])

    def test_datasets_cover_intent_enum_and_all_filter_fields(self):
        from petz.llm import INTENTS
        from petz.catalog import validate_product_query, SCHEMA
        intents = json.loads((ROOT/'evals/datasets/classification_cases.json').read_text(encoding='utf-8'))
        self.assertEqual({r['expected'] for r in intents},set(INTENTS))
        filters = json.loads((ROOT/'evals/datasets/extraction_cases.json').read_text(encoding='utf-8'))
        self.assertEqual(len({r['id'] for r in filters}),len(filters))
        for row in filters:
            self.assertEqual(set(row['expected']),set(SCHEMA['required']))
            self.assertEqual(validate_product_query(row['expected'],row['message']),row['expected'])

    def test_group_documents_separate_procedure_details_and_final_metrics(self):
        report = {'run_id':'test','started_at':'2026-10-31','status':'concluído','mode':'offline','environment':{},
                  'planned':{'classification':1,'extraction':1,'rag':0,'conversations':0},'rag':[],'conversations':[],
                  'classification':[{'id':'I','message':'Olá','context':{},'expected':'identidade','actual':'desconhecido','passed':False,'errors':['Intenção diferente'],'repeat':1,'latency_ms':2}]}
        text = render_group(report,'classification')
        self.assertLess(text.index('## 1. Testes executados'),text.index('## 2. Avaliação final do grupo'))
        self.assertIn('FALHOU',text)
        self.assertIn('Matriz de confusão',text)
        self.assertIn('Não executado',render_group(report,'extraction'))
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)/'RELATORIO_data.md'
            files = write_group_reports(report,base,Path(directory))
            self.assertEqual(len(files),3)
            self.assertTrue(all((Path(directory)/name).exists() for name in files.values()))

if __name__ == '__main__': unittest.main()
