import json
import os
import unittest
from io import BytesIO
from unittest.mock import patch
from petz.config import get_ollama_settings
from petz.ollama_client import OllamaClient, create_chat_model

class OllamaClientTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ,{
            'OLLAMA_URL':'http://localhost:12345/', 'OLLAMA_MODEL':'test-chat',
            'EMBEDDING_MODEL':'test-embed','OLLAMA_TIMEOUT':'91',
            'RAG_TIMEOUT':'92','EMBEDDING_TIMEOUT':'93','OLLAMA_KEEP_ALIVE':'7m',
        })
        self.environment.start()

    def tearDown(self): self.environment.stop()

    def test_langchain_profiles_share_models_url_and_settings(self):
        for purpose,predict,timeout in [('classification',160,91),('catalog',240,91),('rag',650,92)]:
            with self.subTest(purpose=purpose), patch('petz.ollama_client.ChatOllama') as model:
                create_chat_model(purpose)
                options = model.call_args.kwargs
                self.assertEqual(options['base_url'],'http://localhost:12345')
                self.assertEqual(options['model'],'test-chat')
                self.assertEqual(options['temperature'],0)
                self.assertEqual(options['num_predict'],predict)
                self.assertEqual(options['client_kwargs']['timeout'],timeout)
                self.assertEqual(options['keep_alive'],'7m')
                if purpose == 'rag': self.assertEqual(options['num_ctx'],4096)

    def test_http_chat_preserves_tools_and_structured_output(self):
        client = OllamaClient()
        for parameters in [{'tools':[{'type':'function'}]}, {'format':{'type':'object'}}]:
            with self.subTest(parameters=parameters), patch('petz.ollama_client.urlopen',return_value=BytesIO(b'{"message":{}}')) as call:
                client.chat([{'role':'user','content':'Pergunta ficticia'}],**parameters)
                request = call.call_args.args[0]
                payload = json.loads(request.data)
                self.assertEqual(request.full_url,'http://localhost:12345/api/chat')
                self.assertEqual(payload['model'],'test-chat')
                self.assertEqual(payload['options']['num_predict'],160)
                self.assertEqual(call.call_args.kwargs['timeout'],91)
                self.assertFalse(payload['stream'])
                self.assertEqual(payload['keep_alive'],'7m')
                for key,value in parameters.items(): self.assertEqual(payload[key],value)

    def test_embeddings_and_tags_use_same_server_and_embedding_timeout(self):
        client = OllamaClient()
        with patch('petz.ollama_client.urlopen',return_value=BytesIO(b'{"embeddings":[[1,0]]}')) as call:
            client.embed(['texto'])
            request = call.call_args.args[0]
            payload = json.loads(request.data)
            self.assertEqual(request.full_url,'http://localhost:12345/api/embed')
            self.assertEqual(payload['model'],'test-embed')
            self.assertFalse(payload['truncate'])
            self.assertEqual(call.call_args.kwargs['timeout'],93)
        with patch('petz.ollama_client.urlopen',return_value=BytesIO(b'{"models":[]}')) as call:
            client.tags()
            self.assertEqual(call.call_args.args[0].get_method(),'GET')
            self.assertEqual(call.call_args.args[0].full_url,'http://localhost:12345/api/tags')
            self.assertEqual(call.call_args.kwargs['timeout'],93)

    def test_new_clients_read_new_configuration_without_import_reload(self):
        self.assertEqual(get_ollama_settings().chat_model,'test-chat')
        old_client = OllamaClient()
        with patch.dict(os.environ,{'OLLAMA_MODEL':'another-model'}):
            self.assertEqual(OllamaClient().settings.chat_model,'another-model')
            self.assertEqual(old_client.settings.chat_model,'test-chat')

    def test_judge_has_separate_model_and_timeout(self):
        with patch.dict(os.environ,{'JUDGE_MODEL':'independent-judge','JUDGE_TIMEOUT':'180'}), patch('petz.ollama_client.ChatOllama') as model:
            create_chat_model('judge')
            self.assertEqual(model.call_args.kwargs['model'],'independent-judge')
            self.assertEqual(model.call_args.kwargs['client_kwargs']['timeout'],180)

if __name__ == '__main__': unittest.main()
