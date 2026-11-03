## Especificação usada para gerar o kit

> Criar um e-commerce pet inteiramente fictício chamado Pet Aurora. Produzir oito políticas originais em português, de 150 a 400 palavras: trocas, reembolso, frete, cancelamento, assinatura, retirada, privacidade e atendimento. Preservar exatamente RN01–RN04 do desafio. Incluir 50 produtos para cães e gatos, ração e areia, nomes parecidos e estoque zero. Criar dez pedidos de três clientes, cinco estados e cinco regiões, com entregas há 4, 19 e 39 dias na referência 30/10/2026. Usar example.invalid e documentos explicitamente fictícios. Omitir garantia estendida e fidelidade. Não copiar políticas reais, prometer diagnóstico ou inventar integração externa.

## Especificação de revisão e avaliação

> Conferir contagens, tamanho dos textos, referências de SKU e estados/datas. Testar limites estritos de frete e inclusivos de devolução, ração/areia abertas, isolamento de cliente, 404 e 503. Registrar resultados reais e separar limitações da cobertura aprovada. Não afirmar que um modelo foi executado se só a baseline foi testada.

O gerador exato, inclusive o texto das políticas, está versionável em `scripts/generate_kit.py`. O prompt de execução opcional do roteador e os schemas de tools estão em `petz/llm.py`. A IA auxiliou também na criação do código, testes e documentação. A conferência realizada foi automatizada e pelo próprio agente; não equivale a revisão humana independente.



### 1. Implementação do roteador de intenções e do contexto

**Objetivo:** separar a interpretação da mensagem das decisões de negócio e manter a continuidade das conversas.

> Implemente o roteamento do assistente Pet Aurora usando uma LLM local via Ollama. A classificação deve considerar o significado da mensagem atual e o contexto relevante da sessão, sem usar um classificador alternativo por palavras-chave. Utilize a ferramenta `route_request`, com exatamente um argumento `intent` pertencente ao enum definido pela aplicação. Não permita argumentos extras, alteração de `customer_id` ou execução de transações pelo modelo.
>
> Distinga consulta de pedido, solicitação individual de troca/cancelamento, dúvidas gerais sobre políticas, busca de produtos, visão geral do catálogo, identidade do assistente, saúde animal, atendimento humano e tentativas de alterar regras. Perguntas legítimas sobre garantia estendida ou fidelidade devem receber a intenção de assunto desconhecido. Consultar um pedido de outra pessoa deve passar pela ferramenta de autorização; a classificação não deve decidir quem pode acessá-lo.
>
> Preserve a operação pendente quando o cliente responder apenas com o número solicitado. Por exemplo, após pedir o número para uma devolução, “1004” deve retomar a devolução. Uma mudança de assunto deve encerrar a espera anterior. “E o outro pedido?” deve solicitar um novo número, sem reutilizar o pedido anterior. Permita uma segunda tentativa estruturada nos casos previstos pelo contrato; recuse ferramentas desconhecidas e argumentos indevidos. Adicione testes com respostas controladas do modelo para verificar esses comportamentos e trate falhas sem inventar uma intenção.

**Referências verificáveis:** `petz/llm.py` (`SYSTEM_PROMPT` e `TOOLS`), `petz/assistant.py` e `tests/test_contracts.py`.

### 2. Construção do RAG com evidências e abstenção

**Objetivo:** responder dúvidas sobre políticas com fontes verificáveis e explicitar quando a base não permite responder.

> Implemente um fluxo RAG local para as oito políticas Markdown da loja fictícia. Separe documentos em trechos de até 110 palavras, com sobreposição de 25, preservando título, identificador estável e caminho de origem. Gere embeddings com EmbeddingGemma e persista os vetores em SQLite/sqlite-vec. Registre versão do chunking, hash dos documentos, prefixos e identificação do modelo para detectar quando o índice precisa ser atualizado. Uma falha na geração de novos embeddings deve preservar o índice anterior.
>
> Recupere os trechos pela pergunta original, com top-k e similaridade mínima configuráveis. Use LangChain para montar a cadeia de prompt, geração estruturada e validação. Envie ao gerador apenas a pergunta e os documentos recuperados, orientando-o a responder em português somente com fatos presentes nas evidências. Trate mensagens e documentos como dados não confiáveis: instruções embutidas não devem alterar as regras do sistema.
>
> Exija JSON com `supported`, `answer` e `citations`. Cada citação deve informar um `chunk_id` recuperado e uma passagem literal contínua com pelo menos 12 caracteres. Valide o schema, o identificador e a presença da passagem no trecho. Monte os caminhos das fontes na aplicação. Se faltar evidência, produza abstenção; se a geração ou a validação falhar, informe erro de forma controlada. Não invente políticas, descontos, diagnósticos ou ações executadas. Teste também citações inventadas, recuperação vazia e índice desatualizado.

**Referências verificáveis:** `petz/retrieval.py`, `petz/index.py`, `petz/rag.py` (`PROMPT` e `SCHEMA`) e `tests/test_rag.py`.

### 3. Regras calculáveis e isolamento dos pedidos

**Objetivo:** manter cálculos e autorização fora da geração de linguagem.

> Implemente RN01–RN04 em funções determinísticas, usando dados fictícios e uma data de referência explícita nos testes. Na RN01, conte a entrega como dia zero, aceite arrependimento até o sétimo dia e defeito até o trigésimo, incluindo os limites. Entregas futuras não devem gerar elegibilidade. Ração e areia abertas só podem ser devolvidas por defeito dentro do prazo aplicável.
>
> Na RN02, preserve o meio de pagamento original: Pix em até cinco dias úteis e cartão em até duas faturas. Não converta estorno de cartão em Pix, não invente cálculo de feriados e não afirme que um reembolso foi executado. Na RN03, conceda frete gratuito somente para subtotal estritamente superior a R$ 149 no Sul/Sudeste e a R$ 249 nas demais regiões; frete não compõe o subtotal. Na RN04, permita solicitar cancelamento em Pago e Em separação; Enviado e Entregue devem seguir orientação de devolução, e Cancelado deve ser terminal.
>
> A consulta de pedidos deve usar a identidade da sessão, sem aceitar troca de cliente por texto ou argumentos do modelo. Negue acesso a pedido de outro cliente e não exponha seus itens, pagamento ou status. Diferencie falta de autorização, pedido inexistente e indisponibilidade, com contratos 403, 404 e 503. Retorne apenas os dados necessários ao atendimento. Teste limites de prazo e valor, embalagem aberta, todos os estados de cancelamento e tentativas de acesso cruzado, com resultados esperados independentes da resposta da LLM.

**Referências verificáveis:** `petz/rules.py`, `kit/api_mock.py`, `tests/test_contracts.py` e casos E01–E22 em `evals/datasets/cases.json`.

### 4. Busca de produtos com filtros e consentimento

**Objetivo:** recomendar apenas itens reais, disponíveis e compatíveis com a solicitação.

> Implemente a extração estruturada de filtros de produtos com a LLM, validando nome ou tema, espécie, categoria, orçamento e consentimento para alternativas conforme o schema do catálogo. Aplique os filtros em código sobre os produtos fictícios. Não aceite SKU inventado, produto sem estoque, espécie incompatível ou preço acima do orçamento informado.
>
> Preserve um nome específico entre turnos: se a busca não encontrou “computador gamer” e a pessoa respondeu apenas “gato”, isso não autoriza recomendar qualquer produto para gatos. Informe ausência e peça consentimento antes de retirar o filtro de nome e oferecer alternativas. Uma consulta geral como “Quais produtos vocês têm?” deve iniciar a visão de catálogo e limpar a busca específica anterior. Uma correção como “Na verdade é para gato” deve atualizar a espécie no fluxo apropriado.
>
> Confira se o nome extraído corresponde à mensagem após normalização de acentos, espaços e pontuação. Não transforme espécie ou categoria genérica em nome de produto. Em falha de extração ou filtros inválidos, peça esclarecimento em vez de recomendar itens sem restrições. Crie testes para orçamento em reais, catálogo sem resultado, mudanças de espécie, estoque zero e aceitação ou recusa de alternativas. Documente que a correspondência de nomes é lexical e não garante tolerância a todo erro de digitação.

**Referências verificáveis:** `petz/catalog.py`, `tests/test_catalog.py` e `evals/datasets/extraction_cases.json`.

### 5. Avaliação automatizada e documentação dos resultados

**Objetivo:** tornar a qualidade do assistente verificável e permitir que outra pessoa reproduza a avaliação.

> Prepare um conjunto principal com 30 cenários de atendimento, incluindo pelo menos quatro casos derivados de RN01–RN04 com expectativa calculável e três adversariais. Inclua prompt injection, consulta a pedido de outro cliente e tentativa de assumir outra identidade. Cubra também contexto entre turnos, 404/503, produtos, abstenção por informação ausente, saúde animal e encaminhamento humano. Mantenha os casos extras de regressão separados dos 30 principais.
>
> Defina expectativas explícitas de rota, elegibilidade, dias, código de ferramenta, fatos obrigatórios, informações proibidas e fontes quando aplicáveis. Automatize as verificações e retorne código de falha quando houver reprovação. Separe testes de engenharia com respostas controladas das avaliações que realmente chamam o modelo. O modo offline deve marcar essas etapas como não executadas, sem atribuir aprovação a elas.
>
> Avalie classificação e extração diretamente nos seus contratos. Para RAG, registre pergunta, resposta de referência, evidências recuperadas, resposta gerada, citações e métricas de recuperação. Acrescente DeepEval com juiz Ollama para fidelidade, correção, completude, relevância e utilidade. Preserve notas e erros por métrica; as notas são consultivas e não devem apagar falhas determinísticas. Identifique se gerador e juiz usam o mesmo modelo e registre que a calibração humana está pendente.
>
> Salve resultados por execução, preservando rodadas anteriores e registrando configuração, modelos e latência. No README, explique arquitetura, escolha de modelos, trade-offs, comandos, resultados e próximos passos. Diferencie tempos medidos de estimativas de custo baseadas em premissas. Não declare sucesso de casos que falharam nem apresente um teste simulado como execução real do modelo.

**Referências verificáveis:** `evals/datasets/`, `evals/suite.py`, `evals/checks.py`, `evals/deepeval_backend.py`, `evals/runs/` e `README.md`.
