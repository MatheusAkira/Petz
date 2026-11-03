import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from langchain_core.runnables import RunnableLambda

from petz.assistant import Assistant
from petz.rag import GenerationError, generate_answer, validate_answer
from petz.retrieval import Chunk, Retriever, RetrievalError, OllamaEmbeddings, chunk_documents

class FakeEmbeddings:
    model = 'fake-for-engineering-tests'
    calls = 0
    def identity(self): return 'fake-digest-v1'
    def embed(self,texts,query=False):
        self.calls += 1
        # Vetores fixos para testar banco real; não representam avaliação semântica.
        return [[1.0,0.0,0.0] if 'Pix' in t else [0.0,1.0,0.0] for t in texts]

class VectorStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.docs = self.root/'docs'; self.docs.mkdir()
        (self.docs/'reembolso.md').write_text('# Reembolso\nPix em até cinco dias úteis.',encoding='utf-8')
        (self.docs/'frete.md').write_text('# Frete\nFrete grátis acima do limite regional.',encoding='utf-8')
        self.embedder = FakeEmbeddings()
        self.store = Retriever(self.root/'vector.sqlite3',self.docs,self.embedder)
    def tearDown(self): self.tmp.cleanup()

    def test_actual_sqlite_vec_persistence_ranking_and_idempotency(self):
        result = self.store.index()
        self.assertTrue(result['changed'])
        calls = self.embedder.calls
        self.assertFalse(self.store.index()['changed'])
        self.assertEqual(calls,self.embedder.calls)
        reopened = Retriever(self.root/'vector.sqlite3',self.docs,self.embedder)
        hits = reopened.search('Pix',limit=2,min_score=0.5)
        self.assertEqual([c.source for c in hits],['kit/politicas/reembolso.md'])
        self.assertAlmostEqual(hits[0].score,1.0)

    def test_langchain_retriever_preserves_text_sources_and_scores(self):
        self.store.index()
        docs = self.store.as_langchain_retriever().invoke('Pix')
        self.assertEqual(docs[0].metadata['chunk_id'],'reembolso:0')
        self.assertEqual(docs[0].metadata['source'],'kit/politicas/reembolso.md')
        self.assertIn('Pix',docs[0].page_content)
        self.assertAlmostEqual(docs[0].metadata['score'],1.0)

    def test_explicit_title_recovers_below_threshold_without_lowering_it(self):
        self.store.index()
        # Fake embeddings assign Pix to a vector orthogonal to the frete document.
        hits = self.store.search('Pix: quero informações sobre frete',min_score=0.9)
        freight = next(c for c in hits if c.id == 'frete:0')
        self.assertEqual(freight.score,0.0)
        self.assertTrue(freight.title_match)

    def test_generic_title_words_do_not_bypass_threshold(self):
        self.store.index()
        self.assertEqual(self.store.search('políticas da loja Pix',min_score=0.9)[0].id,'reembolso:0')
        self.assertEqual(len(self.store.search('políticas da loja Pix',min_score=0.9)),1)
        with patch.object(self.embedder,'embed',return_value=[[0.0,0.0,1.0]]):
            self.assertEqual(self.store.search('Como funciona o programa de fidelidade?'),[])

    def test_modified_deleted_documents_and_model_invalidate_index(self):
        self.store.index()
        (self.docs/'frete.md').unlink()
        with self.assertRaises(RetrievalError): self.store.search('Pix')
        self.assertEqual(self.store.index()['chunks'],1)
        with patch.object(self.embedder,'identity',return_value='different-model-digest'):
            with self.assertRaises(RetrievalError): self.store.search('Pix')

    def test_failed_embedding_keeps_old_index(self):
        self.store.index()
        old = (self.docs/'frete.md').read_text(encoding='utf-8')
        (self.docs/'frete.md').write_text('# Frete\nNova política.',encoding='utf-8')
        with patch.object(self.embedder,'embed',side_effect=RetrievalError('offline')):
            with self.assertRaises(RetrievalError): self.store.index()
        (self.docs/'frete.md').write_text(old,encoding='utf-8')
        self.assertEqual(self.store.search('Pix')[0].id,'reembolso:0')

    def test_missing_index_and_invalid_dimensions(self):
        with self.assertRaises(RetrievalError): self.store.search('Pix')
        self.store.index()
        with patch.object(self.embedder,'embed',return_value=[[1.0,0.0]]):
            with self.assertRaises(RetrievalError): self.store.search('Pix')

    def test_chunk_size_overlap_and_last_words(self):
        (self.docs/'long.md').write_text('# Long\n'+' '.join('word'+str(i) for i in range(300)),encoding='utf-8')
        chunks = [c for c in chunk_documents(self.docs) if c.id.startswith('long:')]
        self.assertTrue(all(len(c.text.split()) <= 110 for c in chunks))
        self.assertEqual(chunks[0].text.split()[-25:],chunks[1].text.split()[:25])
        self.assertIn('word299',chunks[-1].text)

    def test_short_policy_keeps_conditions_and_exceptions_together(self):
        text = ' '.join('word'+str(i) for i in range(200))
        (self.docs/'short.md').write_text('# Short\n'+text,encoding='utf-8')
        chunks = [c for c in chunk_documents(self.docs) if c.id.startswith('short:')]
        self.assertEqual(len(chunks),1)
        self.assertEqual(chunks[0].text,text)

class GenerationTests(unittest.TestCase):
    def setUp(self):
        self.chunk = Chunk('reembolso:0','kit/politicas/reembolso.md','Reembolso','Pix: até 5 dias úteis. Sempre no meio original.',0.9)

    def test_citations_must_have_known_chunk_and_verbatim_quote(self):
        good = {'supported':True,'answer':'Pix em até 5 dias úteis.','citations':[{'chunk_id':self.chunk.id,'quote':'Pix: até 5 dias úteis.'}]}
        self.assertEqual(validate_answer(good,[self.chunk]),good)
        for citation in [{'chunk_id':'inventado:0','quote':self.chunk.text}, {'chunk_id':self.chunk.id,'quote':'Pix leva apenas duas horas.'}]:
            with self.assertRaises(GenerationError): validate_answer({**good,'citations':[citation]},[self.chunk])
        with self.assertRaises(GenerationError): validate_answer({**good,'citations':[]},[self.chunk])

    def test_generation_receives_retrieved_text(self):
        result = {'supported':True,'evidence_ids':['E1']}
        prompts = []
        def fake_model(prompt):
            prompts.append(prompt)
            return result
        with patch('petz.rag.structured_model',return_value=RunnableLambda(fake_model)):
            answer = generate_answer('Qual o prazo do Pix?',[self.chunk])
            self.assertEqual(answer['answer'],self.chunk.text)
            messages = prompts[0].to_messages()
            self.assertIn(self.chunk.text,messages[1].content)
            self.assertIn('Qual o prazo do Pix?',messages[1].content)

    def test_chain_rejects_invented_citation(self):
        output = {'supported':True,'evidence_ids':['inventado']}
        with patch('petz.rag.structured_model',return_value=RunnableLambda(lambda _:output)):
            with self.assertRaises(GenerationError): generate_answer('Prazo?',[self.chunk])

    def test_invalid_selection_is_repaired_with_one_retry(self):
        question = 'Qual o prazo do Pix?'
        outputs = iter([{'supported':True,'evidence_ids':['invalid']},
                        {'supported':True,'evidence_ids':['E1']}])
        with patch('petz.rag.structured_model',return_value=RunnableLambda(lambda _:next(outputs))) as model:
            result = generate_answer(question,[self.chunk])
        self.assertEqual(result['answer'],self.chunk.text)
        self.assertEqual(model.call_count,2)

    def test_invalid_citations_remain_blocked_after_retry(self):
        output = {'supported':True,'evidence_ids':['invented']}
        with patch('petz.rag.structured_model',return_value=RunnableLambda(lambda _:output)) as model:
            with self.assertRaises(GenerationError) as raised:
                generate_answer('Prazo?',[self.chunk])
        self.assertEqual(raised.exception.code,'invalid_selection')
        self.assertEqual(model.call_count,2)

    def test_service_error_is_not_retried(self):
        def fail(_):
            raise TimeoutError('remote content must not be logged')
        with patch('petz.rag.structured_model',return_value=RunnableLambda(fail)) as model:
            with self.assertRaises(GenerationError) as raised:
                generate_answer('Prazo?',[self.chunk])
        self.assertEqual(raised.exception.code,'model_error')
        self.assertNotIn('remote content',str(raised.exception))
        self.assertEqual(model.call_count,1)

    def test_explicit_negative_answer_is_extracted_without_inference(self):
        chunk = Chunk('assinatura:0','kit/politicas/assinatura.md','Assinatura',
                      'Encerrar uma assinatura não cancela automaticamente pedidos existentes.')
        with patch('petz.rag.structured_model') as model:
            answer = generate_answer('Encerrar uma assinatura cancela automaticamente pedidos existentes?',[chunk])
        self.assertEqual(answer['answer'],chunk.text)
        self.assertEqual(answer['citations'][0]['quote'],chunk.text)
        model.assert_not_called()

    def test_conflicting_literal_statements_do_not_choose_a_side(self):
        from petz.rag import direct_answer
        chunks = [Chunk('a','a','A','Encerrar uma assinatura não cancela automaticamente pedidos existentes.'),
                  Chunk('b','b','B','Encerrar uma assinatura cancela automaticamente pedidos existentes.')]
        self.assertIsNone(direct_answer('Encerrar uma assinatura cancela automaticamente pedidos existentes?',chunks))

    def test_langchain_model_uses_json_schema_and_timeout(self):
        from petz.rag import structured_model, SCHEMA
        with patch('petz.ollama_client.ChatOllama') as model:
            structured_model()
            self.assertIn('timeout',model.call_args.kwargs['client_kwargs'])
            model.return_value.with_structured_output.assert_called_once_with(SCHEMA,method='json_schema')

    def test_empty_retrieval_abstains_without_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot = Assistant(log_path=Path(tmp)/'trace')
            with patch('petz.llm.plan',return_value='assinatura'), patch.object(bot.retriever,'search',return_value=[]), patch('petz.rag.generate_answer') as generate:
                reply = bot.ask('Como funciona?')
                self.assertEqual(reply.route,'abstencao')
                self.assertIn('Não sei',reply.text)
                self.assertEqual(reply.data['rag']['reason'],'no_evidence')
                generate.assert_not_called()

    def test_generation_failure_logs_reason_without_remote_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'trace'
            bot = Assistant(log_path=path)
            with patch('petz.llm.plan',return_value='reembolso'), patch.object(bot.retriever,'search',return_value=[self.chunk]), patch('petz.rag.generate_answer',side_effect=GenerationError('private content','invalid_citation')):
                reply = bot.ask('Meu email e dados pessoais')
            event = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(reply.route,'erro_rag')
            self.assertEqual(event['rag']['reason'],'invalid_citation')
            self.assertEqual(event['rag']['chunks'][0]['source'],self.chunk.source)
            self.assertNotIn('private content',path.read_text(encoding='utf-8'))

    def test_missing_index_is_visible_and_does_not_crash_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot = Assistant(log_path=Path(tmp)/'trace')
            with patch('petz.llm.plan',return_value='assinatura'), patch.object(bot.retriever,'search',side_effect=RetrievalError('Índice ausente')):
                self.assertEqual(bot.ask('Como funciona?').route,'erro_rag')

    def test_unsupported_generation_uses_same_abstention_as_unknown_intent(self):
        from petz.assistant import ABSTENTION_TEXT
        with tempfile.TemporaryDirectory() as tmp:
            bot = Assistant(log_path=Path(tmp)/'trace')
            result = {'supported':False,'answer':'Texto não fundamentado que não deve ser exibido.','citations':[]}
            with patch('petz.llm.plan',return_value='assinatura'), patch.object(bot.retriever,'search',return_value=[self.chunk]), patch('petz.rag.generate_answer',return_value=result):
                reply = bot.ask('Qual o programa de fidelidade?')
            self.assertEqual(reply.route,'abstencao')
            self.assertEqual(reply.text,ABSTENTION_TEXT)

    def test_malformed_embeddings_are_rejected(self):
        for vectors in [[[float('nan')]],[[0.0,0.0]],[],[[1.0],[1.0,0.0]]]:
            with patch('petz.ollama_client.urlopen',return_value=BytesIO(json.dumps({'embeddings':vectors}).encode())):
                with self.assertRaises(RetrievalError): OllamaEmbeddings().embed(['a'])

if __name__ == '__main__': unittest.main()
