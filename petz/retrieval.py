"""Embeddings Ollama + banco SQLite/sqlite-vec persistente com busca por cosseno."""
import hashlib
import json
import math
import os
import sqlite3
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from .ollama_client import OllamaClient
from typing import Any
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.retrievers import BaseRetriever

ROOT = Path(__file__).resolve().parents[1]
CHUNK_VERSION = 'words-110-overlap-25-prefix-v1'
QUERY_PREFIX = 'task: search result | query: '
DOC_PREFIX = 'title: Política Pet Aurora | text: '

# Converte o texto para minúsculas e remove acentos.
def norm(text):
    return ''.join(c for c in unicodedata.normalize('NFD', text.lower()) if unicodedata.category(c) != 'Mn')

class RetrievalError(RuntimeError):
    """Erro público sem texto de usuário ou corpo de erro remoto."""

@dataclass(frozen=True)
class Chunk:
    id: str
    source: str
    title: str
    text: str
    score: float = 0.0

# Divide as políticas Markdown em trechos de até 110 palavras, com sobreposição de 25.
def chunk_documents(directory):
    chunks = []
    for path in sorted(Path(directory).glob('*.md')):
        text = path.read_text(encoding='utf-8')
        title = text.splitlines()[0].lstrip('# ').strip()
        words = text.split('\n',1)[-1].split()
        for index,start in enumerate(range(0,len(words),85)):
            chunks.append(Chunk(f'{path.stem}:{index}',f'kit/politicas/{path.name}',title,' '.join(words[start:start+110])))
            if start+110 >= len(words): break
    return chunks

class OllamaEmbeddings(Embeddings):
    # Prepara o cliente centralizado e identifica o modelo de embeddings configurado.
    def __init__(self):
        self.client = OllamaClient()
        self.model = self.client.settings.embedding_model

    # Consulta o nome e o digest do modelo para detectar mudanças no índice.
    def identity(self):
        try:
            models = self.client.tags()['models']
            name = self.model if ':' in self.model else self.model+':latest'
            match = next((m for m in models if m['name'] in {name,self.model}),None)
            if not match: raise RetrievalError(f'Modelo de embeddings ausente. Execute: ollama pull {self.model}')
            return self.model+':'+match['digest']
        except (OSError,ValueError,KeyError,TypeError) as error:
            raise RetrievalError('Não foi possível verificar o modelo de embeddings no Ollama.') from error

    # Aplica o prefixo de consulta ou documento, gera vetores e valida seus valores e dimensões.
    def embed(self,texts,query=False):
        if not texts: return []
        prefix = os.getenv('EMBEDDING_QUERY_PREFIX',QUERY_PREFIX) if query else os.getenv('EMBEDDING_DOCUMENT_PREFIX',DOC_PREFIX)
        try:
            vectors = self.client.embed([prefix+t for t in texts])['embeddings']
            if not isinstance(vectors,list) or len(vectors) != len(texts): raise ValueError('count')
            dimension = None
            for vector in vectors:
                if not isinstance(vector,list) or not vector or any(not isinstance(x,(int,float)) or isinstance(x,bool) or not math.isfinite(x) for x in vector): raise ValueError('vector')
                if sum(x*x for x in vector) < 1e-12: raise ValueError('zero vector')
                dimension = dimension or len(vector)
                if len(vector) != dimension: raise ValueError('dimension')
            return vectors
        except (OSError,ValueError,KeyError,TypeError) as error:
            raise RetrievalError('Falha ao gerar embeddings. Confira o modelo e EMBEDDING_TIMEOUT.') from error

    # Gera embeddings de documentos pela interface do LangChain.
    def embed_documents(self,texts):
        return self.embed(texts)

    # Gera o embedding de uma pergunta pela interface do LangChain.
    def embed_query(self,text):
        return self.embed([text],query=True)[0]

class Retriever:
    # Define os caminhos do banco e das políticas e o gerador de embeddings.
    def __init__(self,db_path=None,directory=None,embedder=None):
        self.db_path = Path(db_path) if db_path else Path(os.getenv('VECTOR_DB_PATH',str(ROOT/'data'/'policies.sqlite3')))
        self.directory = Path(directory) if directory else ROOT/'kit'/'politicas'
        self.embedder = embedder or OllamaEmbeddings()

    # Adapta a busca vetorial para uso como retriever do LangChain.
    def as_langchain_retriever(self):
        return PolicyRetriever(store=self)

    # Abre o banco SQLite e carrega a extensão de busca vetorial sqlite-vec.
    def _connect(self):
        try:
            import sqlite_vec
        except ImportError as error:
            raise RetrievalError('Instale as dependências: python -m pip install -r requirements.txt') from error
        self.db_path.parent.mkdir(parents=True,exist_ok=True)
        db = sqlite3.connect(str(self.db_path))
        try:
            db.enable_load_extension(True)
            sqlite_vec.load(db)
            db.enable_load_extension(False)
            return db
        except (sqlite3.Error,AttributeError) as error:
            db.close()
            raise RetrievalError('Não foi possível carregar sqlite-vec neste Python.') from error

    # Calcula um hash dos textos, modelo e configurações para detectar necessidade de reindexação.
    def _fingerprint(self,chunks,identity):
        payload = {'chunks':[asdict(c) for c in chunks],'model':identity,'version':CHUNK_VERSION,
            'query_prefix':os.getenv('EMBEDDING_QUERY_PREFIX',QUERY_PREFIX),
            'document_prefix':os.getenv('EMBEDDING_DOCUMENT_PREFIX',DOC_PREFIX)}
        return hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

    # Cria ou atualiza o índice vetorial; evita recalcular embeddings quando nada mudou.
    def index(self):
        chunks = chunk_documents(self.directory)
        if not chunks: raise RetrievalError('Nenhuma política Markdown encontrada.')
        identity = self.embedder.identity()
        fingerprint = self._fingerprint(chunks,identity)
        db = self._connect()
        try:
            db.execute('CREATE TABLE IF NOT EXISTS manifest (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
            previous = dict(db.execute('SELECT key,value FROM manifest'))
            if previous.get('fingerprint') == fingerprint:
                return {'changed':False,'chunks':len(chunks),'model':self.embedder.model,'path':str(self.db_path)}
            vectors = []
            for start in range(0,len(chunks),8):
                vectors.extend(self.embedder.embed([c.title+'\n'+c.text for c in chunks[start:start+8]]))
            dimension = len(vectors[0])
            if any(len(v) != dimension for v in vectors): raise RetrievalError('Dimensões inconsistentes nos embeddings.')
            # Falhas remotas ocorrem antes desta transação, preservando o índice anterior.
            db.execute('BEGIN IMMEDIATE')
            with db:
                db.execute('DROP TABLE IF EXISTS vectors')
                db.execute('DROP TABLE IF EXISTS chunks')
                db.execute('CREATE TABLE chunks (id INTEGER PRIMARY KEY, chunk_id TEXT UNIQUE, source TEXT, title TEXT, body TEXT)')
                db.execute(f'CREATE VIRTUAL TABLE vectors USING vec0(embedding float[{dimension}] distance_metric=cosine)')
                for rowid,(chunk,vector) in enumerate(zip(chunks,vectors),1):
                    db.execute('INSERT INTO chunks VALUES (?,?,?,?,?)',(rowid,chunk.id,chunk.source,chunk.title,chunk.text))
                    db.execute('INSERT INTO vectors(rowid,embedding) VALUES (?,?)',(rowid,json.dumps(vector)))
                db.execute('DELETE FROM manifest')
                db.executemany('INSERT INTO manifest VALUES (?,?)',[('fingerprint',fingerprint),('dimension',str(dimension)),('model',identity)])
            return {'changed':True,'chunks':len(chunks),'dimension':dimension,'model':self.embedder.model,'path':str(self.db_path)}
        finally:
            db.close()

    # Verifica o índice e busca trechos por similaridade de cosseno, aplicando limite e escore mínimo.
    def search(self,query,limit=None,min_score=None):
        if not self.db_path.exists(): raise RetrievalError('Índice ausente. Execute: python -m petz.index')
        limit = limit if limit is not None else int(os.getenv('RAG_TOP_K','4'))
        threshold = min_score if min_score is not None else float(os.getenv('RAG_MIN_SCORE','0.45'))
        if not 1 <= limit <= 20 or not -1 <= threshold <= 1: raise RetrievalError('Configuração RAG_TOP_K/RAG_MIN_SCORE inválida.')
        db = self._connect()
        try:
            meta = dict(db.execute('SELECT key,value FROM manifest'))
            if meta.get('fingerprint') != self._fingerprint(chunk_documents(self.directory),self.embedder.identity()):
                raise RetrievalError('Políticas ou modelo mudaram. Atualize: python -m petz.index')
            vector = self.embedder.embed([query],query=True)[0]
            if len(vector) != int(meta['dimension']): raise RetrievalError('Dimensão diferente do índice. Reindexe as políticas.')
            rows = db.execute('''WITH nearest AS (
                SELECT rowid,distance FROM vectors WHERE embedding MATCH ? AND k = ?
            ) SELECT c.chunk_id,c.source,c.title,c.body,n.distance
              FROM nearest n JOIN chunks c ON c.id=n.rowid ORDER BY n.distance''',(json.dumps(vector),limit)).fetchall()
            return [Chunk(row[0],row[1],row[2],row[3],round(1-row[4],6)) for row in rows if math.isfinite(row[4]) and 1-row[4] >= threshold]
        except sqlite3.Error as error:
            raise RetrievalError('Índice vetorial inválido. Execute: python -m petz.index') from error
        finally:
            db.close()

class PolicyRetriever(BaseRetriever):
    """Adapter LangChain para o índice existente; mantém cosseno, limiar e manifesto."""
    store: Any

    # Converte os trechos encontrados em Documents do LangChain, preservando fontes e escores.
    def _get_relevant_documents(self,query,*,run_manager):
        return [Document(page_content=c.text,metadata={'chunk_id':c.id,'source':c.source,'title':c.title,'score':c.score}) for c in self.store.search(query)]
