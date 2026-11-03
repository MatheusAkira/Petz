# Resumo dos testes e avaliação

Dados da [última rodada completa, iniciada em 03/11/2026 às 11h41 (Brasília)](runs/20261103T144118-144500/results.json), com Qwen 2.5 3B e EmbeddingGemma. A execução terminou **com falhas**.

## Números principais

🟢 Todos passaram · 🟡 Há falhas · 🔴 Nenhum passou. **Valores: aprovados/total**, na rodada de 03/11/2026.

| Grupo | Teste e objetivo | Resultado | Aprovação |
| --- | --- | ---: | ---: |
| Engenharia (80) | Código: regras, autorização, catálogo, índice e contratos | 🟢 **80/80** | **100%** |
| Modelo (91) | Classificação: identificar a intenção da mensagem | 🟡 **22/28** | **78,6%** |
| Modelo | Extração: obter nome, espécie, categoria, orçamento, alternativas e nova busca | 🟡 **15/16** | **93,8%** |
| Modelo | Atendimento: validar conversa, ferramentas e resposta final | 🟡 **33/36** | **91,7%** |
| Modelo | RAG: recuperar políticas e responder com evidências válidas | 🟡 **8/11** | **72,7%** |

**Atendimento — composição dos 36 casos**

| Subgrupo | O que verifica | Resultado | Aprovação |
| --- | --- | ---: | ---: |
| RN01 | Prazo e elegibilidade de devolução | 🟢 4/4 | 100% |
| RN02 | Prazo e meio original de reembolso | 🟡 1/2 | 50% |
| RN03 | Limites de frete grátis | 🟢 4/4 | 100% |
| RN04 | Cancelamento conforme o estado do pedido | 🟢 5/5 | 100% |
| Ferramentas | Consulta e erros 404/503 | 🟢 3/3 | 100% |
| Contexto | Continuidade e mudança de pedido | 🟢 2/2 | 100% |
| Adversariais | Injection, acesso cruzado e troca de identidade | 🟢 3/3 | 100% |
| Abstenção | Recusa de resposta sem informação disponível | 🟢 2/2 | 100% |
| Catálogo | Produtos compatíveis, em estoque e no orçamento | 🟢 1/1 | 100% |
| Escalação | Atendimento humano, saúde e reclamação grave | 🟡 2/3 | 66,7% |
| Política via RAG | Resposta sobre assinatura no atendimento | 🔴 0/1 | 0% |
| **Principais (E01–E30)** | **Subtotal dos itens acima** | 🟡 **27/30** | **90%** |
| Regressões (R01–R06) | Produto, catálogo, devolução, identidade, abstenção e orçamento: um caso cada | 🟢 **6/6** | **100%** |
| **Total de atendimento** | **30 principais + 6 regressões** | 🟡 **33/36** | **91,7%** |

**Contagem:** 80 testes de engenharia + 91 casos do modelo (28 + 16 + 36 + 11). Adversariais já estão nos 36 atendimentos; os onze casos RAG são uma avaliação separada. As taxas medem aspectos diferentes e não formam uma nota única.




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

Para reproduzir: `python -m evals.suite`. Esta rodada demonstra avanços nos casos testados e também falhas que ainda precisam de correção.


