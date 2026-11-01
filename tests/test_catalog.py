import tempfile
import unittest
import os
from pathlib import Path
from unittest.mock import patch
from petz.assistant import Assistant
from petz.catalog import ProductQueryError, validate_product_query, extract_product_query

def filters(**values):
    return {'query':None,'species':None,'category':None,'budget':None,'new_search':False,'alternatives':'none',**values}

class ProductTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.bot = Assistant(log_path=Path(self.tmp.name)/'trace')
        self.router = patch('petz.llm.plan',return_value='produto')
        self.router.start()
    def tearDown(self):
        self.router.stop()
        self.tmp.cleanup()

    def test_missing_theme_survives_species_and_never_returns_unrelated_skus(self):
        with patch('petz.catalog.extract_product_query',side_effect=[filters(query='computadorgamer'),filters(species='gato')]):
            first = self.bot.ask('vc tem o produto computadorgamer?')
            second = self.bot.ask('gato')
        for reply in [first,second]:
            self.assertEqual(reply.data['skus'],[])
            self.assertIn('Não encontrei',reply.text)
            self.assertNotIn('SKU002',reply.text)
        self.assertEqual(self.bot.context['product']['query'],'computadorgamer')
        self.assertIn('para gato',second.text)

    def test_catalog_overview_resets_missing_theme_and_lists_real_stock(self):
        with patch('petz.llm.plan',side_effect=['produto','catalogo']), patch('petz.catalog.extract_product_query',return_value=filters(query='Computador Gamer')) as extract:
            self.bot.ask('Tem produto Computador Gamer?')
            reply = self.bot.ask('quais produtos vc tem?')
        self.assertEqual(reply.route,'catalogo')
        self.assertTrue(reply.data['skus'])
        self.assertIn('ração',reply.text)
        self.assertEqual(self.bot.context['product'],{})
        self.assertEqual(extract.call_count,1)
        for sku in reply.data['skus']:
            self.assertGreater(int(next(p for p in self.bot.products if p['SKU']==sku)['estoque']),0)
        with patch('petz.catalog.extract_product_query',return_value=filters(species='gato')):
            followup = self.bot.ask('gato')
        self.assertTrue(followup.data['skus'])
        self.assertNotIn('query',followup.data['filters'])

    def test_catalog_overview_recovers_from_previous_extraction_error(self):
        self.bot.context['product_needs_query'] = True
        with patch('petz.llm.plan',return_value='catalogo'), patch('petz.catalog.extract_product_query') as extract:
            reply = self.bot.ask('O que vocês vendem?')
        self.assertEqual(reply.route,'catalogo')
        self.assertNotIn('product_needs_query',self.bot.context)
        extract.assert_not_called()

    def test_alternatives_require_consent_and_preserve_species_budget(self):
        steps = [filters(query='Computador Gamer',species='gato',budget=35),filters(alternatives='accept')]
        with patch('petz.catalog.extract_product_query',side_effect=steps):
            self.assertEqual(self.bot.ask('Computador Gamer para gato até 35').data['skus'],[])
            reply = self.bot.ask('sim, mostre outras opções')
        self.assertTrue(reply.data['skus'])
        self.assertNotIn('query',reply.data['filters'])
        for sku in reply.data['skus']:
            product = next(p for p in self.bot.products if p['SKU']==sku)
            self.assertEqual(product['especie'],'gato')
            self.assertLessEqual(float(product['preco']),35)
            self.assertGreater(int(product['estoque']),0)

    def test_rejecting_alternatives_keeps_original_query(self):
        with patch('petz.catalog.extract_product_query',side_effect=[filters(query='Notebook'),filters(alternatives='reject')]):
            self.bot.ask('Tem produto Notebook?')
            reply = self.bot.ask('Não quero outras opções')
        self.assertEqual(reply.data['skus'],[])
        self.assertEqual(reply.data['filters']['query'],'Notebook')
        self.assertNotIn('Quer que',reply.text)

    def test_exact_sku_and_out_of_stock_are_not_replaced(self):
        with patch('petz.catalog.extract_product_query',return_value=filters(query='SKU002',species='gato')):
            self.assertEqual(self.bot.ask('Quero SKU002 para gato').data['skus'],['SKU002'])
        with patch('petz.catalog.extract_product_query',return_value=filters(query='SKU014',species='gato',new_search=True)):
            self.assertEqual(self.bot.ask('Outra busca: SKU014 para gato').data['skus'],[])

    def test_generic_recommendation_keeps_category_on_species_correction(self):
        with patch('petz.catalog.extract_product_query',side_effect=[filters(category='racao',species='cao'),filters(species='gato')]):
            self.bot.ask('Recomende ração para cão')
            reply = self.bot.ask('Na verdade é para gato')
        self.assertTrue(reply.data['skus'])
        self.assertEqual(reply.data['filters']['category'],'racao')
        for sku in reply.data['skus']:
            product = next(p for p in self.bot.products if p['SKU']==sku)
            self.assertEqual((product['categoria'],product['especie']),('racao','gato'))

    def test_explicit_new_search_can_replace_old_theme(self):
        with patch('petz.catalog.extract_product_query',side_effect=[filters(query='Computador Gamer'),filters(new_search=True,category='areia',species='gato')]):
            self.bot.ask('Computador Gamer')
            reply = self.bot.ask('Nova busca: areia para gato')
        self.assertTrue(reply.data['skus'])
        self.assertNotIn('query',reply.data['filters'])

    def test_invalid_or_failed_extraction_does_not_change_context(self):
        with self.assertRaises(ProductQueryError):
            validate_product_query(filters(query='nome inventado'),'gato')
        with patch('petz.catalog.extract_product_query',side_effect=ProductQueryError('Falha de extração')):
            reply = self.bot.ask('Tem Computador Gamer?')
        self.assertEqual(reply.route,'erro_produto')
        self.assertNotIn('product',self.bot.context)

    def test_failed_name_extraction_cannot_turn_species_into_generic_recommendations(self):
        with patch('petz.catalog.extract_product_query',side_effect=[ProductQueryError('Falha'),filters(species='gato')]):
            self.bot.ask('tem produto computadorgamer?')
            reply = self.bot.ask('gato')
        self.assertEqual(reply.route,'pedir_produto')
        self.assertNotIn('SKU',reply.text)

    def test_name_spacing_does_not_count_as_invented_name(self):
        self.assertEqual(validate_product_query(filters(query='Computador Gamer'),'tem computadorgamer?')['query'],'Computador Gamer')

    def test_species_alone_is_not_a_specific_product_name(self):
        self.assertIsNone(validate_product_query(filters(query='gato',species='gato'),'gato')['query'])

    def test_species_correction_cannot_clear_theme_even_if_model_marks_consent(self):
        response = validate_product_query(filters(query='gato',species='gato',new_search=True,alternatives='accept'),'gato')
        with patch('petz.catalog.extract_product_query',side_effect=[filters(query='Computador Gamer'),response]):
            self.bot.ask('Tem produto Computador Gamer?')
            reply = self.bot.ask('gato')
        self.assertEqual(reply.data['skus'],[])
        self.assertEqual(reply.data['filters']['query'],'Computador Gamer')

    def test_food_species_budget_extraction_and_configured_timeout(self):
        result = filters(category='racao',species='gato',budget=100)
        with patch.dict(os.environ,{'OLLAMA_TIMEOUT':'150'}), patch('petz.ollama_client.ChatOllama') as model:
            model.return_value.with_structured_output.return_value.invoke.return_value = result
            actual = extract_product_query('Tem ração para gato até 100 reais?',{'query':'NomeAnteriorNaoDeveIr','awaiting_alternatives':True})
            self.assertEqual(actual,result)
            self.assertEqual(model.call_args.kwargs['client_kwargs']['timeout'],150)
            self.assertEqual(model.call_args.kwargs['keep_alive'],'5m')
            sent = model.return_value.with_structured_output.return_value.invoke.call_args.args[0]
            self.assertNotIn('NomeAnteriorNaoDeveIr',str(sent))

    def test_extraction_timeout_has_specific_message(self):
        from httpx import ReadTimeout
        with patch('petz.ollama_client.ChatOllama') as model:
            model.return_value.with_structured_output.return_value.invoke.side_effect = ReadTimeout('timeout')
            with self.assertRaisesRegex(ProductQueryError,'demorou além do limite'):
                extract_product_query('Ração para gato')

    def test_shared_timeout_default_and_invalid_values(self):
        from petz.config import ollama_timeout
        with patch.dict(os.environ,{},clear=True):
            self.assertEqual(ollama_timeout(),120)
        for value in ['0','-1','nan','inf','abc']:
            with self.subTest(value=value), patch.dict(os.environ,{'OLLAMA_TIMEOUT':value}):
                with self.assertRaises(ValueError): ollama_timeout()

if __name__ == '__main__': unittest.main()
