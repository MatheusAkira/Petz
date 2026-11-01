"""Configuração compartilhada das chamadas ao modelo local."""
import math
import os
from dataclasses import dataclass

# Lê e valida um tempo positivo em segundos, usando o padrão se necessário.
def positive_seconds(name,default):
    value = float(os.getenv(name,str(default)))
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f'{name} deve ser um número positivo de segundos.')
    return value

# Retorna o timeout de classificação e extração (padrão: 120 segundos).
def ollama_timeout():
    """Limite por chamada; inclui a espera pelo carregamento inicial do modelo."""
    return positive_seconds('OLLAMA_TIMEOUT',120)

# Agrupa as configurações do Ollama em um objeto imutável.
@dataclass(frozen=True)
class OllamaSettings:
    base_url: str
    chat_model: str
    embedding_model: str
    chat_timeout: float
    rag_timeout: float
    embedding_timeout: float
    keep_alive: str
    judge_model: str
    judge_timeout: float

# Lê o ambiente e monta as configurações com padrões e timeouts validados.
def get_ollama_settings():
    """Lê o ambiente na criação do cliente, sem congelar valores no import."""
    chat_model = os.getenv('OLLAMA_MODEL','qwen2.5:3b')
    return OllamaSettings(
        base_url=os.getenv('OLLAMA_URL','http://localhost:11434').rstrip('/'),
        chat_model=chat_model,
        embedding_model=os.getenv('EMBEDDING_MODEL','embeddinggemma'),
        chat_timeout=ollama_timeout(),
        rag_timeout=positive_seconds('RAG_TIMEOUT',120),
        embedding_timeout=positive_seconds('EMBEDDING_TIMEOUT',120),
        keep_alive=os.getenv('OLLAMA_KEEP_ALIVE','5m'),
        judge_model=os.getenv('JUDGE_MODEL',chat_model),
        judge_timeout=positive_seconds('JUDGE_TIMEOUT',180),
    )
