"""Único ponto de criação de clientes Ollama: HTTP e LangChain."""
import json
from urllib.request import Request, urlopen
from langchain_ollama import ChatOllama
from .config import get_ollama_settings

# Configurações específicas de cada tarefa, compartilhando os mesmos modelos e URL.
CHAT_PROFILES = {
    'classification': {'num_predict':160},
    'catalog': {'num_predict':240},
    'rag': {'num_predict':650,'num_ctx':4096},
    'judge': {'num_predict':1200,'num_ctx':4096},
}

# Cria um cliente LangChain configurado para a tarefa.
def create_chat_model(purpose):
    """Cria um ChatOllama configurado para a tarefa, sem prompts ou regras de negócio."""
    settings = get_ollama_settings()
    profile = CHAT_PROFILES[purpose]
    timeout = settings.judge_timeout if purpose == 'judge' else settings.rag_timeout if purpose == 'rag' else settings.chat_timeout
    model = settings.judge_model if purpose == 'judge' else settings.chat_model
    return ChatOllama(model=model,base_url=settings.base_url,
        temperature=0,keep_alive=settings.keep_alive,client_kwargs={'timeout':timeout},**profile)

class OllamaClient:
    """Cliente HTTP pequeno para tools e embeddings com truncate=false explícito."""
    # Carrega as configurações do cliente.
    def __init__(self,settings=None):
        self.settings = settings or get_ollama_settings()

    # Faz a requisição HTTP e retorna a resposta em JSON.
    def _request(self,path,payload=None,*,timeout):
        data = json.dumps(payload).encode() if payload is not None else None
        request = Request(self.settings.base_url+path,data=data,headers={'Content-Type':'application/json'})
        with urlopen(request,timeout=timeout) as response:
            return json.load(response)

    # Envia mensagens ao modelo de classificação.
    def chat(self,messages,**parameters):
        payload = {'model':self.settings.chat_model,'stream':False,'keep_alive':self.settings.keep_alive,
            'options':{'temperature':0,**CHAT_PROFILES['classification']},'messages':messages,**parameters}
        return self._request('/api/chat',payload,timeout=self.settings.chat_timeout)

    # Lista os modelos instalados no Ollama.
    def tags(self):
        return self._request('/api/tags',timeout=self.settings.embedding_timeout)

    # Gera embeddings dos textos sem truncar a entrada.
    def embed(self,texts):
        payload = {'model':self.settings.embedding_model,'input':texts,'truncate':False,'keep_alive':self.settings.keep_alive}
        return self._request('/api/embed',payload,timeout=self.settings.embedding_timeout)
