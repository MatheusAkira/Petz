# Resumo dos testes e avaliação

Dados da [última rodada completa, iniciada em 03/11/2026 às 11h41 (Brasília)](runs/20261103T144118-144500/results.json), com Qwen 2.5 3B e EmbeddingGemma. A execução terminou **com falhas**.

## Números principais

| Grupo | Etapa / subgrupo | Aprovados / total | Aprovação |
| --- | --- | --- | --- |
| **Engenharia — 80 testes** | Código, contratos e integrações | **80 / 80** | **100%** |
| **Modelo — 91 casos** | Classificação de intenção | 22 / 28 | 78,6% |
| Modelo | Extração de filtros | 15 / 16 | 93,8% |
| Modelo | Atendimento completo: 30 principais + 6 regressões | **33 / 36** | **91,7%** |
| Modelo | Recuperação e geração RAG isoladas | 8 / 11 | 72,7% |

**Detalhamento dos 36 atendimentos** — as linhas abaixo já estão incluídas no total de atendimento:

| Conjunto | Subgrupo | Aprovados / total | Aprovação |
| --- | --- | --- | --- |
| Principais | RN01 — devolução | 4 / 4 | 100% |
| Principais | RN02 — reembolso | 1 / 2 | 50% |
| Principais | RN03 — frete | 4 / 4 | 100% |
| Principais | RN04 — cancelamento | 5 / 5 | 100% |
| Principais | Ferramentas e erros de consulta | 3 / 3 | 100% |
| Principais | Contexto entre turnos | 2 / 2 | 100% |
| Principais | Adversariais: injection, acesso cruzado e identidade | 3 / 3 | 100% |
| Principais | Abstenção por ausência de informação | 2 / 2 | 100% |
| Principais | Catálogo | 1 / 1 | 100% |
| Principais | Escalação: humano, saúde e reclamação grave | 2 / 3 | 66,7% |
| Principais | Política de assinatura via RAG no atendimento | 0 / 1 | 0% |
| **Subtotal principais** | **Casos E01–E30** | **27 / 30** | **90%** |
| Regressões | Produto, catálogo, devolução, identidade, abstenção e orçamento (um caso cada) | 6 / 6 | 100% |
| **Total atendimento** | **Principais + regressões** | **33 / 36** | **91,7%** |

O caso de política via RAG acima pertence ao atendimento completo; os onze casos de RAG isolado são outro conjunto. Os três adversariais não são casos extras. Os grupos medem aspectos diferentes e não devem ser somados em uma nota única.


O atendimento reúne 30 casos principais e seis regressões. As etapas medem aspectos diferentes e não devem ser somadas em uma taxa única de qualidade.

Nos 36 cenários, com 45 turnos, a latência total teve **mediana de 8,55 s**, **média de 15,66 s** e **P95 de 42,24 s**. São tempos de conversas de teste completas, sem digitação e sem o juiz da etapa RAG; não representam latência por mensagem nem benchmark com concorrência.

## Impressões e falhas

A engenharia passou nos 80 testes e o atendimento aprovou 33 dos 36 cenários. Os três adversariais passaram: pedido de outro cliente bloqueado com 403, prompt injection direcionado à segurança e tentativa de assumir outra identidade também bloqueada. Isso confirma os casos conhecidos; exemplos deles estão no prompt e ainda é necessário avaliar ataques independentes.

A classificação continua sendo uma fragilidade: seis casos divergiram da referência (I04, I14, I16, I20, I21 e I27). Na extração, somente F11 falhou, no campo `new_search`, que indica uma nova busca.

Os três atendimentos reprovados foram:

- **E06 — reembolso do cartão em Pix:** erro no RAG, sem os fatos e a fonte esperados.
- **E27 — pedido de atendente humano:** erro no RAG em vez de encaminhamento humano.
- **E30 — assinatura:** abstenção indevida, embora exista política sobre o assunto.

No RAG isolado, houve três falhas: cancelamento sem a orientação esperada de devolução; citação inválida em assinatura, bloqueada pela validação; e recuperação insuficiente sobre horários, levando à abstenção. Validar citações ajuda a bloquear saídas inválidas, mas não resolve sozinho completude e recuperação.

## Avaliação semântica

O DeepEval avaliou 10 dos 11 casos RAG; assinatura ficou sem julgamento por não haver resposta validada. Médias em escala de 0 a 1, considerando somente notas disponíveis:

| Dimensão | Média | Casos aplicáveis avaliados |
| --- | --- | --- |
| Fidelidade | 0,5587 | 7 |
| Correção | 0,4400 | 10 |
| Completude | 0,4800 | 10 |
| Relevância | 0,2833 | 10 |
| Utilidade | 0,3500 | 10 |

As notas são consultivas e não alteram os checks determinísticos. O juiz usa o mesmo modelo do gerador e não foi calibrado por revisão humana. Há inconsistências que exigem revisão: para Pix, a nota de fidelidade foi zero, embora a justificativa afirme alinhamento ao contexto. Portanto, essas médias não devem ser usadas isoladamente para declarar qualidade ou segurança.

## Pontos de melhoria

1. Corrigir a classificação, principalmente a distinção entre atendimento humano, políticas e operações de pedidos.
2. Resolver os casos de reembolso e assinatura e melhorar recuperação, completude e validação das respostas RAG.
3. Ampliar regressões com paráfrases, conversas longas, mudanças de assunto e ataques independentes dos exemplos do prompt.
4. Comparar modelos maiores ou APIs com o mesmo conjunto e calibrar um juiz independente com revisão humana.
5. Criar uma interface de chat, testar usabilidade e evoluir autenticação e integrações reais.
6. Medir desempenho com concorrência, modelos frios/quentes e custo operacional no ambiente de destino.

Para reproduzir: `python -m evals.suite`. O modo `--offline` verifica engenharia e kit, mas não executa as avaliações reais do modelo. Esta rodada demonstra avanços nos casos testados e também falhas que ainda precisam de correção.

