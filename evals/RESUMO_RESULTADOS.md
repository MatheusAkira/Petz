# Resumo dos testes e avaliação

Dados da [última rodada completa, iniciada em 03/11/2026 às 11h41 (Brasília)](runs/20261103T144118-144500/results.json), com Qwen 2.5 3B e EmbeddingGemma. A execução terminou **com falhas**.

## Números principais

| Etapa | Aprovados / total | Aprovação |
| --- | --- | --- |
| Testes de engenharia | 80 / 80 | 100% |
| Classificação de intenção | 22 / 28 | 78,6% |
| Extração de filtros | 15 / 16 | 93,8% |
| Cenários de atendimento | 33 / 36 | 91,7% |
| Recuperação e geração RAG | 8 / 11 | 72,7% |
| Adversariais (parte dos 36 atendimentos) | 3 / 3 | 100% |

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
