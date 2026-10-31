# Suposições documentadas

O enunciado orienta: diante de ambiguidade, assumir uma interpretação razoável,
documentar e seguir em frente. Cada suposição abaixo indica onde ela é aplicada no
código, para que possa ser revista com a loja.

## Dados operacionais (CSVs)

| # | Situação | Suposição adotada | Onde |
|---|---|---|---|
| D1 | Os CSVs têm pedidos até março/2026, mas o agente roda em outra data. | Os CSVs são um retrato do sistema. Regras que dependem de data usam o "agora" real no fuso de Campo Grande, ou `EMPORIO_NOW` quando definido (testes e avaliações). | `clock.py` |
| D2 | Produto com `status` não ativo, mas com estoque (130 e 136). | O status prevalece. Só é vendável o que está `active` e com estoque > 0. | `v_catalog.is_sellable` |
| D3 | Promoções não têm datas de vigência. | `is_active` é a única fonte de vigência. Se houver mais de uma ativa para o mesmo produto, vale a de maior desconto (não são cumulativas, manual 6.2). | `v_catalog` |
| D4 | Promoção ativa em produto sem estoque. | Não é anunciada enquanto o produto estiver indisponível. | `v_catalog` |
| D5 | O preço promocional não está nos dados. | É calculado sobre o preço de tabela e arredondado ao centavo. Vale também para filtros do tipo "até R$ 1.000". | `v_catalog.final_price_cents` |
| D6 | O total de alguns pedidos difere da soma dos itens (pedidos 3 e 20). | O total registrado é o correto. `order_items` não guarda o preço unitário da época, então a diferença pode ser desconto ou reajuste. O agente nunca recalcula. | `transform._orders` |
| D7 | Nome, descrição e specs se contradizem em 7 produtos. | Nome e specs prevalecem. A descrição contraditória é preservada para auditoria, mas não chega ao agente. | `transform.description_conflicts` |
| D8 | Nome com abreviação truncada (produto 84, "Cedr"). | Corrigido por uma tabela explícita de correções, aplicada só se o erro ainda existir na origem. | `transform.NAME_CORRECTIONS` |
| D9 | Dois cadastros com o mesmo e-mail (11 e 43). | A identidade é verificada contra o dono de um pedido específico (pedido + e-mail ou telefone), nunca pelo e-mail isolado. | `privacy.py` e ferramentas de pedido |
| D10 | Cliente pode informar o telefone sem DDD. | Assume-se o DDD da loja (67). | `privacy.normalize_phone` |
| D11 | Pedidos em aberto há meses (8 a 16). | São tratados como atrasados ou parados: o agente informa o status registrado, sinaliza o atraso e oferece encaminhar para a equipe. | `report.operational_alerts` |
| D12 | Os arquivos originais tinham nomes longos e o PDF tinha acento no nome. | Foram apenas renomeados; o conteúdo é idêntico e o SHA-256 de cada arquivo fica registrado no banco e no relatório. | `data/raw/` |

## Manual de políticas (PDF)

As regras que geram números (prazos, parcelas, descontos, horários) estão em
`src/emporio/rules/`, com testes. Onde o manual é ambíguo ou se contradiz:

| # | Situação | Suposição adotada | Onde |
|---|---|---|---|
| M1 | A tabela da seção 3 diz "parcela mínima de R$ 100", mas a 3.1 define faixas (até 3x, 4x a 6x, 7x a 12x). A 3.1 diz ainda que até 3x não há mínimo, "exceto abaixo de R$ 50,00". | Vale a 3.1, por ser mais específica; a tabela descreve o caso de 12x. Em 2x e 3x a parcela mínima é R$ 50; em 1x não há mínimo. | `rules/payments.py` |
| M2 | O desconto do PIX não diz como arredondar. | 5% sobre o preço de tabela, arredondado ao centavo. Não se aplica a preços promocionais (6.2). | `rules/payments.py` |
| M3 | "Combinação de formas de pagamento para compras acima de R$ 2.000,00." | "Acima" é estritamente maior: exatamente R$ 2.000,00 não permite combinar. | `rules/payments.py` |
| M4 | "Frete grátis para pedidos acima de R$ 500,00" na "região metropolitana de Campo Grande", sem lista de cidades. | "Acima" é estritamente maior. Até a loja informar a lista, só o município de Campo Grande é tratado como local. | `rules/shipping.py` |
| M5 | "Domingo e Feriados: Fechado", sem listar os feriados. | Feriados nacionais, o estadual de MS (11/10) e os municipais de Campo Grande (13/06 e 26/08, a confirmar). Carnaval e Corpus Christi são pontos facultativos e contam como dias normais. Horários estendidos em datas especiais não são previstos; o agente avisa que podem ocorrer. | `rules/calendar.py` |
| M6 | O prazo de arrependimento conta do recebimento, mas os dados não têm a data real de entrega. | Usa-se a previsão de entrega (`estimated_delivery`) dos pedidos entregues. Pedidos do sistema são tratados como compras online, já que têm rastreio. | `rules/returns.py` |
| M7 | A troca por preferência vale "em até 7 dias", sem dizer a partir de quando. | A partir do recebimento, como no arrependimento. | `rules/returns.py` |
| M8 | Troca por defeito conta da compra (30 dias); garantia legal conta do recebimento (90 dias). | Os dois marcos são respeitados como estão no manual: `order_date` para a troca e recebimento para a garantia. | `rules/returns.py` |
| M9 | Dois números de WhatsApp: (67) 3341-4444 (capa e dados da empresa) e (67) 3321-4500 (seção 7). | Informa-se (67) 3341-4444, que aparece duas vezes, inclusive nos dados cadastrais. O outro número não é divulgado até a loja confirmar. | `rules/store.py` |
| M10 | O e-mail aparece como `contato@emporiodamusica.com.br` na capa e com acento (`empóriodamusica`) na tabela. | Usa-se a versão sem acento; domínio com acento é provável erro de digitação. | `rules/store.py` |
| M11 | Os dados de itens não indicam personalização, "venda final" nem boquilhas, que não são elegíveis para troca (4.4). | O agente não tem como verificar isso e informa essas exceções como condição, sem afirmar que o item se enquadra ou não. | `rules/returns.py` |

Contradições encontradas nos próprios pedidos (parcelas abaixo do mínimo, PIX sem
desconto) estão no [relatório de qualidade](relatorio_qualidade_dados.md).
