# Privacidade e dados pessoais

O assistente usa somente os dados necessários para responder à solicitação. A identidade do cliente vem da sessão confiável, definida na inicialização do ambiente de demonstração. Declarar outro identificador no texto não altera essa identidade. Cada consulta a pedidos verifica a titularidade antes de retornar detalhes. Não mostramos nome, endereço, e-mail, documento, itens ou situação de pedido pertencente a outra pessoa.

Os dados deste projeto são sintéticos; os e-mails usam o domínio reservado example.invalid e os documentos têm rótulos explícitos de teste. O catálogo não contém dados pessoais.

Os logs persistidos contêm eventos estruturados com rota, fontes, tempo e códigos de resultado, sem armazenar a mensagem original, identificador do cliente ou número do pedido. Essa minimização evita depender apenas de expressões regulares para mascarar dados. Conversas ficam apenas em memória durante a sessão e podem ser apagadas encerrando o processo.

O protótipo não comprova conformidade jurídica completa com a LGPD e não substitui revisão especializada. Solicitações de acesso, correção ou exclusão de dados devem ser encaminhadas ao atendimento humano. Nunca informe senha, código temporário ou dados bancários completos ao assistente.
