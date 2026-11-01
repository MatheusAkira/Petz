# Como executar os testes e ler o relatório

## Avaliação RAG com DeepEval

Instale/atualize as dependências na raiz:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

A suíte usa DeepEval 4.3.2, com `LLMTestCase` contendo pergunta, resposta real, trechos recuperados e referência. O juiz é sempre o adapter local `LocalJudge`, que usa as configurações centralizadas do Ollama. Não exige chave OpenAI ou login no Confident AI. A telemetria DeepEval é desativada pelo adapter; as métricas são executadas via `measure`, sem envio de resultados à plataforma.

| Dimensão | Implementação |
| --- | --- |
| Fidelidade ao contexto | `FaithfulnessMetric` (nativa, modo LLM) |
| Relevância da resposta | `AnswerRelevancyMetric` (nativa, modo LLM) |
| Correção diante da referência | `GEval` com etapas próprias |
| Completude diante da referência | `GEval` com etapas próprias |
| Utilidade para o cliente | `GEval` com etapas próprias |

As notas já vêm na escala 0–1 e são preservadas sem divisão adicional. Os limiares do DeepEval são `None`: notas continuam consultivas, sem aprovação artificial. Cada métrica registra implementação, justificativa, latência e erro. Se uma falhar, as outras continuam: o caso fica parcial, a nota ausente não entra na média e o comando retorna falha. Abstenções padronizadas e casos sem contexto não recebem nota de fidelidade; as outras dimensões continuam sendo avaliadas. As citações da resposta continuam validadas pelo pipeline RAG, mas não se atribuem citações literais verificadas às justificativas do DeepEval.

No `results.json`, `metric_results` também preserva diagnósticos disponíveis do DeepEval (afirmações, fatos extraídos, vereditos e etapas G-Eval). Eles ajudam a investigar uma nota que contradiz a justificativa. Uma execução sem exceções indica que a integração funcionou, não que o julgamento esteja correto. O teste real inicial com `qwen2.5:3b` apresentou uma justificativa de fidelidade inconsistente com a nota; não corrigimos notas por interpretação textual. Calibre o juiz com referências humanas e considere um modelo local mais capaz.

`JUDGE_MODEL` seleciona o modelo local; sem essa variável, usa `OLLAMA_MODEL`. `JUDGE_TIMEOUT` limita cada chamada ao Ollama, não a avaliação inteira. DeepEval pode fazer várias chamadas por métrica e levar mais tempo que o juiz antigo. Usar o mesmo modelo gerador mantém a avaliação não independente. A calibração humana continua pendente. As notas de rodadas antigas (`rag-semantic-2`) não são diretamente comparáveis às novas (`deepeval-rag-1`).

O comando padrão continua `python -m evals.suite`. Para apenas reavaliar respostas já salvas, use `python -m evals.suite --judge-saved evals/runs/<execução>/results.json`; substitua o identificador pela pasta real. Os novos arquivos ficam em outra rodada, preservando os anteriores. `--no-semantic` pula DeepEval; `--offline` não chama modelos. Os três relatórios continuam somente em `evals/runs/`.

## Organização atual dos arquivos

Os cenários ficam em `evals/datasets/`, os guias em `evals/docs/` e todos os relatórios ficam **somente em `evals/runs/<execução>/`**, junto do `results.json`. Não há cópias na raiz de `evals`. `--output` define apenas o nome base: mesmo quando um diretório é informado, os documentos permanecem dentro da pasta da execução. O terminal mostra esse destino. Exemplos antigos de caminhos de saída abaixo devem ser interpretados como nomes base.

## Três grupos de avaliação da LLM

O comando completo `python -m evals.suite` gera apenas três documentos com a mesma data/hora:

| Documento | Etapa 1: testes | Etapa 2: métricas agregadas |
| --- | --- | --- |
| `RELATORIO_<data>_CLASSIFICATION.md` | 28 mensagens/contextos, intenção esperada e obtida, acerto/erro | Acurácia, precisão/recall/F1 macro, matriz de confusão, saídas validadas, erros e latência |
| `RELATORIO_<data>_EXTRACTION.md` | 16 mensagens/contextos, JSON esperado/obtido e comparação dos seis campos | Exact match, acurácia por campo/micro, campos informativos, saídas validadas, erros e latência |
| `RELATORIO_<data>_RAG.md` | Pergunta, referência, evidências recuperadas, resposta, citações, verificações e juiz | Recuperação/ranking, geração, abstenção, cinco notas semânticas, cobertura e latências |

Os nomes podem começar por `RELATORIO-OFFLINE` ou pelo nome base de `--output`. Cada repetição multiplica os casos. Intenção e filtros são testados diretamente em `plan` e `extract_product_query`, sem deduzir seus resultados pela rota final. As saídas registradas são as validadas pela aplicação, incluindo correções/retries internos. Os datasets são `classification_cases.json` e `extraction_cases.json`; o RAG continua em `rag_cases.json`.

O modo offline produz os documentos, mas marca os grupos de LLM como não executados. Reavaliar um JSON antigo com `--judge-saved` não inventa resultados de classificação ou filtros: esses grupos aparecem como não executados se não existiam na execução original. Revisão humana das referências continua pendente. As novas chamadas de intenção e filtros aumentam o tempo da execução completa.

## Arquivos com data e hora

Cada execução cria um arquivo exclusivo, por exemplo `evals/RELATORIO_2026-10-31_15-30-00-123456.md`. No modo offline, o prefixo é `RELATORIO-OFFLINE`. O horário usa Brasília (UTC−3). O caminho aparece no terminal e no cabeçalho do documento.

`--output evals/MEU-RELATORIO.md` define apenas o nome base: a data e a hora também serão acrescentadas. Relatórios anteriores são preservados. Durante uma execução, os checkpoints atualizam somente o arquivo reservado para ela. A cópia na pasta da execução usa o mesmo nome.

No final, a avaliação geral traz uma tabela por etapa: engenharia, atendimento, recuperação, geração, abstenção e julgamento semântico, com métricas, resultados e bases de cálculo. Os casos individuais ficam em uma seção recolhida; as evidências não usam blocos recolhidos aninhados.

## 1. Abra o terminal na pasta do projeto

No VS Code, use **Terminal → Novo Terminal** e execute:

```powershell
cd C:\Users\akira\Desktop\Petz
```

## 2. Rode a verificação rápida

Não precisa abrir o Ollama para este comando:

```powershell
.\.venv\Scripts\python.exe -m evals.suite --offline --output evals/RELATORIO-OFFLINE.md
```

Ele valida o kit e executa os testes de engenharia. Abra `evals/RELATORIO-OFFLINE.md` no VS Code; `Ctrl+Shift+V` abre a prévia do Markdown. As etapas de modelo real ficam marcadas como **não executadas**.

## 3. Prepare o Ollama e o índice para a avaliação completa

Mantenha o aplicativo Ollama aberto. Neste workspace os modelos e o ambiente já foram instalados. Em outra máquina, prepare primeiro:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
ollama pull qwen2.5:3b
ollama pull embeddinggemma
```

Crie ou confira o índice:

```powershell
.\.venv\Scripts\python.exe -m petz.index
```

Se nada mudou, esse comando não recalcula os embeddings. Se precisar de mais tempo por chamada:

```powershell
$env:OLLAMA_TIMEOUT = '120'
$env:RAG_TIMEOUT = '120'
```

## 4. Execute tudo

```powershell
.\.venv\Scripts\python.exe -m evals.suite
```

O comando roda testes de engenharia, 36 cenários de atendimento e onze casos de recuperação/geração RAG, em sequência. Não digite perguntas durante essa execução: o próprio programa envia os casos. O modelo local pode levar vários minutos ou mais para concluir. Cada resultado aparece no terminal e é salvo no relatório imediatamente.

## 5. Abra o resultado

- **`evals/runs/<execução>/RELATORIO_<data>_<GRUPO>.md`**: três relatórios específicos, atualizados após cada caso. Não é criado um relatório principal nem cópias na raiz de `evals`.
- **`evals/runs/<identificador>/RELATORIO.md`**: cópia da rodada.
- **`evals/runs/<identificador>/results.json`**: dados detalhados da rodada.

O relatório mostra o estado da execução, ambiente, testes aprovados/reprovados, fontes, trechos, respostas, métricas e latência. Se encerrar com código 1, procure os casos **FALHOU** ou o pré-requisito bloqueado. Isso pode indicar um erro real do modelo ou uma expectativa textual rígida; revise a resposta e a fonte antes de concluir a causa.

Todos os resultados ficam na seção final **Resultados dos testes**: preparação, tabela individual dos testes de engenharia, tabelas de atendimento e RAG, métricas e detalhes de cada cenário. Perguntas e respostas aparecem em blocos de citação; fontes, similaridades e evidências aparecem em tabelas. Os textos dos chunks e a saída original dos testes ficam em blocos expansíveis, preservando os dados sem sobrecarregar a leitura.

Uma rodada anterior não é sobrescrita. Apenas os três documentos da rodada atual são atualizados. Resultados complementares de engenharia e atendimento ficam no `results.json`. Se interromper com `Ctrl+C`, os casos já salvos permanecem e os documentos ficam marcados como incompletos.

## Opções adicionais

A execução completa inclui um juiz LLM para fidelidade semântica, correção factual, completude, relevância e utilidade da **geração RAG**. O relatório mostra a etapa de cada métrica, o modelo avaliador, as notas, justificativas e evidências. Notas não substituem a revisão humana nem mudam a aprovação dos checks determinísticos. Por padrão, o mesmo modelo é usado como gerador e juiz; isso fica registrado como avaliação não independente.

Para usar outro juiz local instalado, defina `$env:JUDGE_MODEL = 'nome-do-modelo'` antes do comando. Não há download automático. Para desativar o juiz nesta rodada, use `--no-semantic`; no modo `--offline`, ele não é chamado.

É possível julgar uma rodada salva sem refazer as respostas: `python -m evals.suite --judge-saved evals/runs/<identificador>/results.json`, usando o Python da `.venv` e substituindo o identificador pela pasta real. Essa opção cria uma nova rodada, preserva os resultados originais e salva os julgamentos separadamente em cada caso RAG.

```powershell
# Três repetições para observar instabilidade; demora mais.
.\.venv\Scripts\python.exe -m evals.suite --repeats 3

# Outro nome base para os três relatórios.
.\.venv\Scripts\python.exe -m evals.suite --output evals/RELATORIO-PERSONALIZADO.md
```

## Onde editar os cenários

- `evals/datasets/cases.json`: 30 cenários originais de atendimento.
- `evals/datasets/regression_cases.json`: seis casos adicionais de problemas encontrados nas conversas.
- `evals/datasets/rag_cases.json`: onze perguntas com passagens de referência e padrões esperados na resposta.
- `tests/`: testes de engenharia com dados controlados.

Quando mudar uma política, confira as referências do dataset, reindexe e rode a suíte novamente. Não altere uma expectativa apenas para transformar um erro real em aprovação.

## O que a aprovação não garante

Cada relatório de grupo contém os testes individuais e, ao final, a avaliação agregada com suas métricas. No modo offline, os grupos de LLM são marcados como não executados. Execute o comando habitual da suíte para criar uma nova rodada dentro de `runs/`.

O código verifica regras, dados, fontes, passagens de referência e padrões de texto, e pode aplicar o juiz semântico descrito acima. Se o juiz usa o mesmo modelo do gerador, a avaliação não é independente. Mesmo com outro modelo, é necessário calibrar suas notas com uma amostra revisada por pessoas. Citações podem existir sem sustentar uma interpretação, e o juiz também pode errar. A revisão humana continua necessária e está explicitamente pendente no relatório.
