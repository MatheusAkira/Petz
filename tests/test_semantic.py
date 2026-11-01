import unittest
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
from evals.semantic import METRICS, judge_rag_case

class SemanticTests(unittest.TestCase):
    hits = [{'id':'r:0','text':'Pix: até 5 dias úteis.'}]

    def row(self):
        return {'question':'Prazo Pix?','passed':False,'hits':self.hits,
                'generation':{'answer':'Até 5 dias úteis.','supported':True}}

    def metrics(self):
        return {key:SimpleNamespace(score=.8,reason='Supported by reference',measure=MagicMock()) for key in METRICS}

    def judge(self,row,metrics):
        case = SimpleNamespace(expected_output='Reference')
        with patch('evals.semantic.build_metrics',return_value=metrics), patch('evals.semantic.make_test_case',return_value=case):
            return judge_rag_case(row,{'evidence':['Reference'],'should_abstain':False})

    def test_native_scores_are_not_renormalized_and_original_result_is_unchanged(self):
        row = self.row(); result = self.judge(row,self.metrics())
        self.assertEqual(result['status'],'avaliado')
        self.assertEqual(result['scores'],{key:.8 for key in METRICS})
        self.assertEqual(result['framework'],'deepeval')
        self.assertFalse(row['passed'])

    def test_failed_metric_preserves_other_scores_and_records_partial_status(self):
        metrics=self.metrics(); metrics['correctness'].measure.side_effect=TimeoutError('local timeout')
        result=self.judge(self.row(),metrics)
        self.assertEqual(result['status'],'parcial')
        self.assertIsNone(result['scores']['correctness'])
        self.assertEqual(result['scores']['faithfulness'],.8)
        self.assertIn('correctness',result['metric_errors'])

    def test_invalid_scores_are_errors_instead_of_fabricated_numbers(self):
        for invalid in (True,1.1,-1,float('nan'),float('inf')):
            with self.subTest(score=invalid):
                metrics=self.metrics(); metrics['faithfulness'].score=invalid
                result=self.judge(self.row(),metrics)
                self.assertIsNone(result['scores']['faithfulness'])
                self.assertEqual(result['metric_results']['faithfulness']['status'],'erro')

    def test_missing_generation_never_initializes_deepeval(self):
        with patch('evals.semantic.build_metrics') as factory:
            result=judge_rag_case({}, {})
        factory.assert_not_called()
        self.assertEqual(result['status'],'não executado')

    def test_initialization_failure_is_not_a_fallback_to_old_judge(self):
        with patch('evals.semantic.make_test_case',side_effect=ImportError('missing dependency')):
            result=judge_rag_case(self.row(),{'evidence':[],'should_abstain':False})
        self.assertEqual(result['status'],'erro')
        self.assertNotIn('scores',result)

    def test_standard_abstention_skips_faithfulness_but_measures_other_metrics(self):
        row=self.row(); row['generation']={'supported':False,'answer':'Sem evidência recuperada.'}
        metrics=self.metrics(); result=self.judge(row,metrics)
        self.assertIsNone(result['scores']['faithfulness'])
        metrics['faithfulness'].measure.assert_not_called()
        metrics['correctness'].measure.assert_called_once()

    def test_deepeval_case_separates_retrieved_context_from_reference(self):
        from evals.deepeval_backend import make_test_case
        case=make_test_case(self.row(),{'evidence':['Reference facts'],'should_abstain':False})
        self.assertEqual(case.retrieval_context,['Pix: até 5 dias úteis.'])
        self.assertEqual(case.expected_output,'Reference facts')
        abstention=make_test_case(self.row(),{'evidence':[],'should_abstain':True})
        self.assertTrue(abstention.expected_output)

    def test_backend_uses_only_explicit_local_judge_and_no_uncalibrated_threshold(self):
        from evals.deepeval_backend import build_metrics, LocalJudge
        metrics=build_metrics()
        self.assertEqual(set(metrics),set(METRICS))
        for metric in metrics.values():
            self.assertIsInstance(metric.model,LocalJudge)
            self.assertIsNone(metric.threshold)
            self.assertFalse(metric.async_mode)
        self.assertEqual(type(metrics['faithfulness']).__name__,'FaithfulnessMetric')
        self.assertEqual(type(metrics['relevance']).__name__,'AnswerRelevancyMetric')

    def test_adapter_uses_centralized_client_and_structured_schema(self):
        from evals.deepeval_backend import LocalJudge
        from pydantic import BaseModel
        class Schema(BaseModel):
            score: float
        with patch('evals.deepeval_backend.create_chat_model') as factory:
            factory.return_value.with_structured_output.return_value.invoke.return_value=Schema(score=.8)
            judge=LocalJudge()
            result=judge.generate('Evaluate',schema=Schema)
        factory.assert_called_once_with('judge')
        self.assertEqual(result.score,.8)
        factory.return_value.with_structured_output.assert_called_once_with(Schema,method='json_schema')

    def test_partial_scores_are_included_only_in_their_applicable_averages(self):
        from evals.reporting import consolidated_table
        semantic={'status':'parcial','scores':{key:(None if key=='faithfulness' else .5) for key in METRICS},
                  'metric_errors':{'faithfulness':'timeout'}}
        report={'status':'concluído','mode':'completo','planned':{'conversations':0,'rag':1},'conversations':[],
                'rag':[{'passed':True,'semantic':semantic}]}
        text='\n'.join(consolidated_table(report))
        self.assertIn('| Completude | 0.5000 |',text)
        self.assertIn('| Fidelidade semântica | Não avaliado |',text)
        self.assertIn('| Avaliações parciais | 1 |',text)

    def test_summary_has_stage_mapping_and_ignores_nonapplicable_scores(self):
        from evals.reporting import consolidated_table, render_markdown
        scores = {k:1.0 for k in METRICS}
        report = {'run_id':'test','started_at':'2026-10-31','status':'concluído','mode':'completo','environment':{},
            'planned':{'conversations':0,'rag':2},'conversations':[],
            'semantic':{'model':'test-judge','same_as_generator':True,'status':'concluído'},
            'rag':[{'id':'a','repeat':1,'passed':True,'errors':[],'latency_ms':1,
                'semantic':{'status':'avaliado','scores':{**scores,'faithfulness':.75},'reasons':{k:'Motivo' for k in METRICS}}},
                {'id':'b','repeat':1,'passed':False,'errors':[],'latency_ms':1,
                'semantic':{'status':'avaliado','scores':{**scores,'faithfulness':None,'completeness':0},'reasons':{k:'Motivo' for k in METRICS}}}]}
        table='\n'.join(consolidated_table(report))
        self.assertIn('| Fidelidade semântica | 0.7500 |',table)
        self.assertIn('| Completude | 0.5000 |',table)
        self.assertIn('avaliação não independente',table)
        text=render_markdown(report)
        self.assertIn('| Geração RAG | Fidelidade semântica | DeepEval FaithfulnessMetric |',text)
        self.assertIn('| Recuperação RAG | Recall de chunks@k |',text)

if __name__ == '__main__': unittest.main()
