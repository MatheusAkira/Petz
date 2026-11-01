# Resultados e análise de falhas

## Avaliação semântica automática e mapa de métricas

Foi adicionado um juiz LLM na etapa de geração RAG, com rubrica explícita para fidelidade, correção factual, completude, relevância e utilidade. Todas as métricas anteriores continuam disponíveis e agora têm etapa, método e limitação indicados no relatório. O juiz recebe as referências e os contextos recuperados separadamente; notas e evidências passam por validação de schema, escala e correspondência das passagens. Notas são consultivas e não alteram a aprovação dos checks determinísticos. A revisão humana e a calibração permanecem pendentes.

As respostas da rodada `20261031T162654-229700` foram avaliadas sem repetir a geração, em uma nova rodada terminada em `semantic-20261031T171401`. Foram nove julgamentos válidos, um erro do juiz por evidência não encontrada e um caso sem resposta validada para julgar. A primeira tentativa com schema anterior foi interrompida e preservada como tal; não é o relatório principal.

O juiz disponível é o próprio `qwen2.5:3b`, portanto os resultados não são independentes. Médias estimadas, em escala 0–1: fidelidade 0,7500 em sete respostas factuais; correção factual 0,5833, completude 0,5278, relevância 0,9167 e utilidade 0,6111 em nove casos. Abstenções padronizadas não têm fidelidade aplicável: a nota original foi preservada no JSON e excluída somente dessa média. As notas podem estar erradas e precisam de comparação com julgamentos humanos antes de servirem como critério de aprovação.

Os testes do código passaram em 69 métodos, incluindo schema do juiz, notas fora da escala, dimensões faltantes, evidências inventadas, médias sem casos não aplicáveis, configuração independente do juiz e apresentação das etapas. Novas execuções completas incluem o juiz por padrão; `--no-semantic` desativa a etapa e `--judge-saved` permite avaliar apenas respostas salvas. Modelo e timeout do juiz são configurados em `JUDGE_MODEL` e `JUDGE_TIMEOUT`, pelo cliente centralizado.

## Suíte completa com relatório Markdown

O comando `python -m evals.suite` foi implementado e executado integralmente. A rodada `20261030T195408-563800` está arquivada em `evals/runs/`, com JSON detalhado e Markdown. O relatório principal é `evals/RELATORIO.md`; as instruções estão em `evals/docs/COMO_EXECUTAR.md`.

Resultados automáticos desta rodada:

- Kit válido e **58/58 testes de engenharia aprovados**.
- **24/36 cenários de atendimento aprovados**, incluindo as seis regressões novas.
- **8/11 cenários de RAG aprovados** nos checks de recuperação, passagens, resposta e citações.
- Fonte/passagem relevante recuperada em **8/9 perguntas positivas (88,89%)**; precisão média dos chunks retornados de **62,96%**. MRR, recall de chunks, nDCG e cobertura média das passagens foram 0,8889 nesta amostra de um chunk de referência relevante por pergunta.

As falhas de atendimento incluem desvios de devolução/cancelamento para consulta de status, formato inválido de classificação, abstenção em pergunta coberta e bloqueio de citação. Alguns controles adversariais foram seguros, mas falharam na rota exigida: encaminhamento humano em vez de segurança e recusa de acesso 403 em vez de bloqueio prévio pelo classificador. Esses casos não devem ser interpretados automaticamente como vazamento ou concessão de benefício.

As três falhas de RAG foram: resposta de cancelamento sem o fluxo de devolução esperado; citação não literal em assinatura, recusada pela validação; e horário de atendimento não recuperado acima do limiar, levando a abstenção. A revisão semântica humana continua pendente. Os padrões textuais não provam correção ou completude de todas as afirmações e podem exigir adjudicação de paráfrases.

O comando retornou código 1 por haver checks reprovados, preservando todos os resultados. Os casos não foram alterados para elevar a aprovação. Há um modo `--offline`, sem chamadas ao Ollama, e `--repeats` para observar estabilidade; esta rodada usou uma repetição, sem estimativa estatística de generalização. Os datasets foram preparados com auxílio de IA e não representam um conjunto independente revisado por especialista.
