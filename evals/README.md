# Avaliações

| Local | Conteúdo |
| --- | --- |
| `datasets/` | Referências de classificação, filtros, RAG e conversas de regressão. |
| `docs/COMO_EXECUTAR.md` | Comandos e interpretação das métricas. |
| `docs/ANALISE.md` | Análise e histórico de resultados. |
| `runs/<execução>/` | Único destino dos três relatórios e do `results.json`. |
| Arquivos `.py` | Execução, verificações, métricas, juiz semântico e formatação. |

Execute na raiz do projeto:

A avaliação semântica RAG usa **DeepEval 4.3.2**, com juiz Ollama local. `FaithfulnessMetric` e `AnswerRelevancyMetric` são métricas nativas; correção, completude e utilidade usam `GEval` com critérios do projeto. As demais avaliações continuam determinísticas. Instale as dependências com `python -m pip install -r requirements.txt`.

```powershell
.\.venv\Scripts\python.exe -m evals.suite
```


O terminal informa a pasta da execução. `--output MEU-RELATORIO.md` altera apenas o nome base dos três documentos dentro dessa pasta, sem exportá-los para outro diretório. Data e hora são adicionadas automaticamente.

Relatórios antigos que estavam na raiz foram movidos para suas respectivas execuções. Quando já havia uma cópia com o mesmo nome, o arquivo movido recebeu o sufixo `_ROOT_COPY`, preservando ambos. Arquivos sem execução identificável ficam em `runs/importados/`.
