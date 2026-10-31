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

Suposições sobre contradições do manual serão adicionadas junto com as regras de
negócio (etapa 03) e o RAG (etapa 05).
