import unittest
from unittest.mock import patch

from petz.rag import GenerationError, prepare_evidence, render_selection, generate_answer
from petz.retrieval import Chunk, chunk_documents, ROOT
from evals.suite import generation_checks


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.chunk = Chunk('policy:0','policy.md','Política',
            'O serviço não cancela pedidos existentes.\n\nO prazo é de 5 dias após a aprovação.')
        self.evidence = prepare_evidence([self.chunk])

    def test_response_preserves_negation_and_source_exactly(self):
        result = render_selection({'supported':True,'evidence_ids':['E1']},self.evidence,[self.chunk])
        self.assertEqual(result['answer'],'O serviço não cancela pedidos existentes.')
        self.assertEqual(result['answer'],result['citations'][0]['quote'])
        self.assertIn(result['answer'],self.chunk.text)

    def test_deadline_keeps_approval_condition(self):
        result = render_selection({'supported':True,'evidence_ids':['E2']},self.evidence,[self.chunk])
        self.assertEqual(result['answer'],'O prazo é de 5 dias após a aprovação.')

    def test_model_cannot_supply_its_own_answer_or_quote(self):
        for field in ['answer','quote','citations']:
            with self.subTest(field=field), self.assertRaises(GenerationError):
                render_selection({'supported':True,'evidence_ids':['E1'],field:'Inventado'},self.evidence,[self.chunk])

    def test_unknown_duplicate_empty_and_ill_typed_selections_fail_closed(self):
        for output in [
            {'supported':True,'evidence_ids':['E99']},
            {'supported':True,'evidence_ids':['E1','E1']},
            {'supported':True,'evidence_ids':[]},
            {'supported':'true','evidence_ids':['E1']},
            {'supported':True,'evidence_ids':[{}]},
            {'supported':False,'evidence_ids':['E1']},
        ]:
            with self.subTest(output=output), self.assertRaises(GenerationError):
                render_selection(output,self.evidence,[self.chunk])

    def test_no_chunks_abstains_without_model_call(self):
        with patch('petz.rag.structured_model') as model:
            self.assertFalse(generate_answer('Qual a regra?',[])['supported'])
        model.assert_not_called()

    def test_evidence_paragraphs_remain_verbatim_in_actual_policies(self):
        chunks = chunk_documents(ROOT/'kit/politicas')
        evidence = prepare_evidence(chunks)
        by_id = {chunk.id:chunk for chunk in chunks}
        self.assertGreater(len(evidence),len(chunks))
        for item in evidence:
            self.assertIn(item['text'],by_id[item['chunk_id']].text)
        refund = next(item for item in evidence if 'Em compras pagas por Pix' in item['text'])
        self.assertIn('O prazo começa após a aprovação',refund['text'])
        subscription = next(item for item in evidence if 'pode pausar' in item['text'])
        self.assertIn('não cancela automaticamente pedidos existentes',subscription['text'])

    def test_forbidden_claim_is_checked_even_with_a_valid_citation(self):
        result = {'supported':True,'answer':'O serviço cancela tudo automaticamente.',
                  'citations':[{'chunk_id':self.chunk.id,'quote':self.evidence[0]['text']}]}
        gold = {'should_abstain':False,'source':'test','answer_patterns':[],
                'forbidden_patterns':['cancela tudo automaticamente']}
        self.assertTrue(any('proibida' in error for error in generation_checks(result,gold,[self.chunk])))


if __name__ == '__main__':
    unittest.main()
