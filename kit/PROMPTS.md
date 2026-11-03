## Especificação usada para gerar o kit

> Criar um e-commerce pet inteiramente fictício chamado Pet Aurora. Produzir oito políticas originais em português, de 150 a 400 palavras: trocas, reembolso, frete, cancelamento, assinatura, retirada, privacidade e atendimento. Preservar exatamente RN01–RN04 do desafio. Incluir 50 produtos para cães e gatos, ração e areia, nomes parecidos e estoque zero. Criar dez pedidos de três clientes, cinco estados e cinco regiões, com entregas há 4, 19 e 39 dias na referência 30/10/2026. Usar example.invalid e documentos explicitamente fictícios. Omitir garantia estendida e fidelidade. Não copiar políticas reais, prometer diagnóstico ou inventar integração externa.

## Especificação de revisão e avaliação

> Conferir contagens, tamanho dos textos, referências de SKU e estados/datas. Testar limites estritos de frete e inclusivos de devolução, ração/areia abertas, isolamento de cliente, 404 e 503. Registrar resultados reais e separar limitações da cobertura aprovada. Não afirmar que um modelo foi executado se só a baseline foi testada.

O gerador exato, inclusive o texto das políticas, está versionável em `scripts/generate_kit.py`. O prompt de execução opcional do roteador e os schemas de tools estão em `petz/llm.py`. A IA auxiliou também na criação do código, testes e documentação. A conferência realizada foi automatizada e pelo próprio agente; não equivale a revisão humana independente.
