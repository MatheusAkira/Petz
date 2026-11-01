"""python -m petz.index: indexação explícita e idempotente das políticas."""
import json
from .retrieval import Retriever, RetrievalError

def main():
    try:
        print(json.dumps(Retriever().index(),ensure_ascii=False,indent=2))
    except RetrievalError as error:
        print(f'Erro: {error}')
        raise SystemExit(1)

if __name__ == '__main__': main()
