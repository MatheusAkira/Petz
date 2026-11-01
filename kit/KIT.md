# Premissas e revisão do kit

Pet Aurora não é uma loja real. Todos os produtos, preços, pedidos e clientes foram criados para esta demonstração. Não há CPFs numéricos válidos: os documentos são rotulados `CPF-FICTICIO-NNN`. E-mails usam `example.invalid`.

Oito políticas cobrem troca/devolução, reembolso, frete, cancelamento, assinatura, retirada, privacidade e atendimento. Cada arquivo contém entre 150 e 400 palavras, conferidas por `python -m kit.validate`. Os textos foram produzidos com IA e confrontados com RN01–RN04 durante a implementação; a revisão humana final do candidato continua necessária.

A conferência de coerência adotou:

- RN01: 7 dias por arrependimento, 30 por defeito; entrega é dia zero; limites incluídos. Ração/areia abertas somente por defeito. Entrega futura não gera elegibilidade.
- RN02: meio original; Pix até 5 dias úteis; cartão até 2 faturas. Não há cálculo de feriados nem transação de reembolso.
- RN03: valor estritamente superior a 149 no Sul/Sudeste e 249 nas outras regiões; frete não compõe o subtotal.
- RN04: Pago e Em separação permitem solicitar cancelamento; Enviado/Entregue seguem devolução; Cancelado é terminal.
- As políticas secundárias referenciam essas condições sem criar exceções. Assinatura a cada 30/60 dias, retirada até 3 dias após confirmação e atendimento comercial fictício são escolhas deste kit.

Pedidos: 1001/1004/1007/1010 pertencem ao cliente-1; 1002/1005/1008 ao cliente-2; 1003/1006/1009 ao cliente-3. Em 29/10/2026, as entregas de 1004, 1005 e 1009 ocorreram há 4, 19 e 39 dias. Datas fixas permitem resultados reprodutíveis. Cada pedido possui um item; múltiplos itens exigiriam seleção explícita, que não foi implementada.

O catálogo possui 50 SKUs, nomes próximos Plus/Premium, cães e gatos, ração/areia e outros itens. Todo múltiplo de sete tem estoque zero. Não se atribui efeito terapêutico a produtos. O validador checa unicidade, preços/estoques, contagens e referências dos pedidos; testes de contrato verificam regras que não cabem no validador curto.

Temas deliberadamente ausentes: **garantia estendida e programa de fidelidade**. Também não há preço de frete pago, integração com transportadora, endereços de lojas ou agenda de próximas cobranças. Ausência deve gerar abstenção ou orientação ao atendimento, nunca informação inventada.

O kit é pequeno por intenção. Não foram simulados impostos, descontos de assinatura, múltiplos meios de pagamento, devolução parcial, fretes reais nem autenticação externa.
