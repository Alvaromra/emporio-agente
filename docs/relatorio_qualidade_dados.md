# Relatório de qualidade dos dados

> Gerado automaticamente por `python -m emporio.etl`. Não edite à mão.
> Data de referência: 2026-10-31

## Resumo

| Tabela | Registros carregados |
|---|---|
| `categories` | 9 |
| `products` | 65 |
| `promotions` | 25 |
| `customers` | 50 |
| `orders` | 20 |
| `order_items` | 22 |

- Produtos vendáveis (ativos e com estoque): **61** de 65.
- Promoções ativas: **4** de 25.
- Produtos com descrição não confiável: **7**.
- Achados de qualidade: **41** em 13 tipos.

## Achados e tratamento

| Severidade | Achado | Ocorrências | Registros | Tratamento |
|---|---|---|---|---|
| alta | Mesmo e-mail em mais de um cadastro | 1 | customers 11,43 | A verificação de identidade é sempre feita contra o dono de um pedido específico, nunca pelo e-mail isolado. Assim um cadastro não expõe pedidos do outro. |
| alta | Descrição cita marca diferente da marca do nome | 7 | products 135, 136, 137, 139, 140, 142, 144 | Nome e specs são a fonte da verdade. A descrição é marcada como não confiável e não é usada pelo agente. |
| alta | Descrição contradiz as specs (cordas, teclas ou madeira) | 5 | products 135, 137, 139, 140, 142 | Mesmo tratamento: prevalecem as specs; a descrição não é usada. |
| média | Categoria sem nenhum produto cadastrado | 3 | categories 6, 7, 8 | O agente informa que não há itens dessa categoria no momento, sem inventar produtos. |
| média | Parcelamento com parcela abaixo do mínimo da faixa (manual 3.1) | 3 | orders 9, 16, 18 | Histórico preservado. O agente aplica a regra vigente apenas em novas simulações e não comenta condições de pedidos passados. |
| média | Pedido contém produto fora de linha ou em pré-lançamento | 2 | orders 3, 14 | Histórico preservado. Em pedidos em aberto, o agente não promete prazo e encaminha para a equipe. |
| média | Total do pedido difere da soma de quantidade × preço atual | 2 | orders 3, 20 | O agente informa o total registrado e nunca recalcula: order_items não guarda o preço unitário da época, então a diferença pode ser desconto ou reajuste. |
| média | Produto fora de linha ou em pré-lançamento com estoque positivo | 2 | products 130, 136 | O status prevalece sobre o estoque: o produto não é ofertado. |
| baixa | Cliente de Campo Grande com código de rastreio de transportadora | 7 | orders 1, 2, 3, 4, 5, 7, 8 | O manual (5.1) prevê motoboy próprio na região. O agente informa o código existente sem afirmar qual transportadora fez a entrega. |
| baixa | Pedido pago via PIX com total igual ao preço de tabela, sem o desconto de 5% | 5 | orders 1, 5, 10, 13, 17 | O agente informa o total registrado e não afirma se houve desconto: ele pode ter sido aplicado no pagamento sem constar no total. |
| baixa | Produto ativo sem estoque | 1 | products 96 | Informar indisponibilidade e sugerir alternativas semelhantes (manual 7.3). |
| baixa | Nome corrigido pela tabela explícita de correções | 1 | products 84 | Correção versionada no código, aplicada só se o nome original ainda estiver errado. |
| baixa | Preço abaixo de 20% da mediana da categoria | 2 | products 136, 142 | Preço mantido (o sistema é a fonte oficial); sinalizado para revisão da equipe. |

## Detalhes

### Mesmo e-mail em mais de um cadastro

Código: `customer.shared_email`

- customers 11,43: cadastros 11,43

### Descrição cita marca diferente da marca do nome

Código: `product.description_brand_mismatch`

- products 135: Music Man Bass 1X Electric Bass: nome indica ['Music Man'], descrição cita ['Fender']
- products 136: Ibanez Bass 2X Electric Bass: nome indica ['Ibanez'], descrição cita ['Fender']
- products 137: Yamaha Bass 3X Electric Bass: nome indica ['Yamaha'], descrição cita ['Ibanez']
- products 139: Bateria Acústica Yamaha Kit 1 Studio: nome indica ['Yamaha'], descrição cita ['Pearl']
- products 140: Bateria Acústica Pearl Kit 2 Studio: nome indica ['Pearl'], descrição cita ['Tama']
- products 142: Teclado Sintetizador Korg Synth 1 Pro: nome indica ['Korg'], descrição cita ['Roland']
- products 144: Teclado Sintetizador Roland Synth 3 Pro: nome indica ['Roland'], descrição cita ['Yamaha']

### Descrição contradiz as specs (cordas, teclas ou madeira)

Código: `product.description_spec_conflict`

- products 135: Music Man Bass 1X Electric Bass: specs: body=Ash; descrição cita ['alder']
- products 137: Yamaha Bass 3X Electric Bass: specs: strings=4; descrição: 5 cordas
- products 139: Bateria Acústica Yamaha Kit 1 Studio: specs: shells=Maple; descrição cita ['mahogany', 'poplar']
- products 140: Bateria Acústica Pearl Kit 2 Studio: specs: shells=Maple; descrição cita ['birch']
- products 142: Teclado Sintetizador Korg Synth 1 Pro: specs: keys=61; descrição: 88 teclas

### Categoria sem nenhum produto cadastrado

Código: `category.empty`

- categories 6: Instrumentos de Sopro (Madeiras)
- categories 7: Instrumentos de Sopro (Metais)
- categories 8: Cordas Orquestrais

### Parcelamento com parcela abaixo do mínimo da faixa (manual 3.1)

Código: `order.installment_below_minimum`

- orders 9: 6x de R$ 58,31 sobre R$ 349,90; mínimo da faixa: R$ 80,00
- orders 16: 6x de R$ 71,65 sobre R$ 429,90; mínimo da faixa: R$ 80,00
- orders 18: 12x de R$ 38,32 sobre R$ 459,90; mínimo da faixa: R$ 100,00

### Pedido contém produto fora de linha ou em pré-lançamento

Código: `order.item_not_released`

- orders 3: pedido delivered contém Kala KA-ABP-CTG Barítono Cedar (coming_soon)
- orders 14: pedido pending contém Kala KA-ABP-CTG Barítono Cedar (coming_soon)

### Total do pedido difere da soma de quantidade × preço atual

Código: `order.total_mismatch`

- orders 3: registrado R$ 3.450,00, itens a preço atual R$ 3.498,00 (diferença -R$ 48,00)
- orders 20: registrado R$ 1.400,00, itens a preço atual R$ 1.488,00 (diferença -R$ 88,00)

### Produto fora de linha ou em pré-lançamento com estoque positivo

Código: `product.unsellable_with_stock`

- products 130: Kala KA-ABP-CTG Barítono Cedar: status=coming_soon, estoque=2
- products 136: Ibanez Bass 2X Electric Bass: status=discontinued, estoque=13

### Cliente de Campo Grande com código de rastreio de transportadora

Código: `order.local_with_carrier_tracking`

- orders 1: cliente em Campo Grande, código BRAB1234567BR
- orders 2: cliente em Campo Grande, código BRCX9876543BR
- orders 3: cliente em Campo Grande, código BRDZ4561230BR
- orders 4: cliente em Campo Grande, código BRQM7890123BR
- orders 5: cliente em Campo Grande, código BRTP3456789BR
- orders 7: cliente em Campo Grande, código BRKR1122334BR
- orders 8: cliente em Campo Grande, código BRJL5544332BR

### Pedido pago via PIX com total igual ao preço de tabela, sem o desconto de 5%

Código: `order.pix_discount_missing`

- orders 1: total R$ 11.499,00 igual ao preço de tabela, sem os 5% do PIX
- orders 5: total R$ 4.599,00 igual ao preço de tabela, sem os 5% do PIX
- orders 10: total R$ 8.732,00 igual ao preço de tabela, sem os 5% do PIX
- orders 13: total R$ 1.899,00 igual ao preço de tabela, sem os 5% do PIX
- orders 17: total R$ 689,00 igual ao preço de tabela, sem os 5% do PIX

### Produto ativo sem estoque

Código: `product.active_out_of_stock`

- products 96: Giannini GF-3D Dreadnought Sunburst

### Nome corrigido pela tabela explícita de correções

Código: `product.name_corrected`

- products 84: 'Giannini GN-15 Nylon Cedr Natural' -> 'Giannini GN-15 Nylon Cedro Natural' (abreviação truncada 'Cedr'; specs indicam tampo em Cedro)

### Preço abaixo de 20% da mediana da categoria

Código: `product.price_outlier`

- products 136: Ibanez Bass 2X Electric Bass: R$ 441,00 vs. mediana R$ 7.944,50
- products 142: Teclado Sintetizador Korg Synth 1 Pro: R$ 1.127,00 vs. mediana R$ 9.351,00

## Alertas operacionais

Pedidos em aberto com previsão vencida ou sem atualização há mais de 30 dias, na data de referência. Dependem da data e, por isso, são recalculados a cada consulta do agente, não gravados no banco.

| Pedido | Status | Data do pedido | Previsão | Situação |
|---|---|---|---|---|
| 8 | shipped | 2026-02-15 | 2026-02-28 | previsão de entrega vencida há 245 dias |
| 9 | confirmed | 2026-02-20 | - | em aberto há 253 dias |
| 10 | confirmed | 2026-02-25 | - | em aberto há 248 dias |
| 11 | confirmed | 2026-03-05 | - | em aberto há 240 dias |
| 12 | confirmed | 2026-03-10 | - | em aberto há 235 dias |
| 13 | pending | 2026-03-12 | - | em aberto há 233 dias |
| 14 | pending | 2026-03-15 | - | em aberto há 230 dias |
| 15 | pending | 2026-03-18 | - | em aberto há 227 dias |
| 16 | pending | 2026-03-22 | - | em aberto há 223 dias |

## Integridade da origem

| Arquivo | SHA-256 |
|---|---|
| `categories.csv` | `7a7901e16c8c6357a956031ada45a6fd6a4cc9bd7bc1edc05448cc55b01b0a9e` |
| `customers.csv` | `1cd724dc86eac6258913cc890abf23d3893c57a99c9325ebfb91dfad3c7b0f37` |
| `order_items.csv` | `7656eb681821d48e0c932f61d3188309b955c25446578235f2d8e69604b0f0bc` |
| `orders.csv` | `deb9c2480605d8d22117d569f0045fd156c5e9a58ffeebb847ff61b3b9512fd5` |
| `products.csv` | `78d911d96ee891abb163b6c858e895025aa530ab27d0290540f05d5098377c12` |
| `promotions.csv` | `cbe08c7e91b00437c0c00a7ef1486deba73de52d23e3f97f51a7dbd557d759e0` |
