"""Catálogo de verificações de qualidade.

Cada verificação declara a severidade e, principalmente, a decisão de
tratamento. O relatório de qualidade é gerado a partir daqui, então a
documentação nunca fica defasada em relação ao código.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Severity(StrEnum):
    ALTA = "alta"
    MEDIA = "média"
    BAIXA = "baixa"

    @property
    def rank(self) -> int:
        return {"alta": 0, "média": 1, "baixa": 2}[self.value]


@dataclass(frozen=True)
class Check:
    code: str
    severity: Severity
    title: str
    treatment: str


@dataclass(frozen=True)
class Issue:
    check: Check
    entity: str
    entity_id: str
    detail: str


_CHECKS = [
    Check(
        "product.description_brand_mismatch", Severity.ALTA,
        "Descrição cita marca diferente da marca do nome",
        "Nome e specs são a fonte da verdade. A descrição é marcada como não confiável "
        "e não é usada pelo agente.",
    ),
    Check(
        "product.description_spec_conflict", Severity.ALTA,
        "Descrição contradiz as specs (cordas, teclas ou madeira)",
        "Mesmo tratamento: prevalecem as specs; a descrição não é usada.",
    ),
    Check(
        "product.unsellable_with_stock", Severity.MEDIA,
        "Produto fora de linha ou em pré-lançamento com estoque positivo",
        "O status prevalece sobre o estoque: o produto não é ofertado.",
    ),
    Check(
        "product.active_out_of_stock", Severity.BAIXA,
        "Produto ativo sem estoque",
        "Informar indisponibilidade e sugerir alternativas semelhantes (manual 7.3).",
    ),
    Check(
        "product.price_outlier", Severity.BAIXA,
        "Preço abaixo de 20% da mediana da categoria",
        "Preço mantido (o sistema é a fonte oficial); sinalizado para revisão da equipe.",
    ),
    Check(
        "product.name_corrected", Severity.BAIXA,
        "Nome corrigido pela tabela explícita de correções",
        "Correção versionada no código, aplicada só se o nome original ainda estiver errado.",
    ),
    Check(
        "category.empty", Severity.MEDIA,
        "Categoria sem nenhum produto cadastrado",
        "O agente informa que não há itens dessa categoria no momento, sem inventar produtos.",
    ),
    Check(
        "promotion.multiple_active", Severity.ALTA,
        "Mais de uma promoção ativa para o mesmo produto",
        "Promoções não são cumulativas (manual 6.2): vale a de maior desconto.",
    ),
    Check(
        "promotion.active_on_unsellable", Severity.MEDIA,
        "Promoção ativa para produto que não pode ser vendido",
        "A promoção não é anunciada enquanto o produto não estiver disponível.",
    ),
    Check(
        "order.total_mismatch", Severity.MEDIA,
        "Total do pedido difere da soma de quantidade × preço atual",
        "O agente informa o total registrado e nunca recalcula: order_items não guarda o "
        "preço unitário da época, então a diferença pode ser desconto ou reajuste.",
    ),
    Check(
        "order.item_not_released", Severity.MEDIA,
        "Pedido contém produto fora de linha ou em pré-lançamento",
        "Histórico preservado. Em pedidos em aberto, o agente não promete prazo e "
        "encaminha para a equipe.",
    ),
    Check(
        "order.installment_below_minimum", Severity.MEDIA,
        "Parcelamento com parcela abaixo do mínimo da faixa (manual 3.1)",
        "Histórico preservado. O agente aplica a regra vigente apenas em novas simulações "
        "e não comenta condições de pedidos passados.",
    ),
    Check(
        "order.pix_discount_missing", Severity.BAIXA,
        "Pedido pago via PIX com total igual ao preço de tabela, sem o desconto de 5%",
        "O agente informa o total registrado e não afirma se houve desconto: ele pode ter "
        "sido aplicado no pagamento sem constar no total.",
    ),
    Check(
        "order.tracking_invalid", Severity.ALTA,
        "Código de rastreamento fora do padrão BR + 9 caracteres + BR (manual 5.3)",
        "O código não é repassado ao cliente; o caso é encaminhado para a equipe.",
    ),
    Check(
        "order.tracking_status_mismatch", Severity.MEDIA,
        "Rastreamento incompatível com o status do pedido",
        "O status prevalece; o agente não menciona rastreamento incoerente.",
    ),
    Check(
        "order.delivery_before_order", Severity.ALTA,
        "Previsão de entrega anterior à data do pedido",
        "A previsão não é informada ao cliente.",
    ),
    Check(
        "order.local_with_carrier_tracking", Severity.BAIXA,
        "Cliente de Campo Grande com código de rastreio de transportadora",
        "O manual (5.1) prevê motoboy próprio na região. O agente informa o código "
        "existente sem afirmar qual transportadora fez a entrega.",
    ),
    Check(
        "order_item.duplicate_line", Severity.BAIXA,
        "Mesmo produto repetido em linhas diferentes do pedido",
        "Linhas consolidadas somando as quantidades.",
    ),
    Check(
        "customer.shared_email", Severity.ALTA,
        "Mesmo e-mail em mais de um cadastro",
        "A verificação de identidade é sempre feita contra o dono de um pedido específico, "
        "nunca pelo e-mail isolado. Assim um cadastro não expõe pedidos do outro.",
    ),
    Check(
        "customer.shared_phone", Severity.ALTA,
        "Mesmo telefone em mais de um cadastro",
        "Mesmo tratamento do e-mail compartilhado.",
    ),
    Check(
        "customer.invalid_contact", Severity.MEDIA,
        "E-mail ou telefone em formato inválido",
        "Cadastro carregado; a verificação por esse contato tende a falhar e o agente "
        "oferece o canal humano.",
    ),
]  # fmt: skip

CHECKS: dict[str, Check] = {check.code: check for check in _CHECKS}


def issue(code: str, entity: str, entity_id: object, detail: str) -> Issue:
    return Issue(check=CHECKS[code], entity=entity, entity_id=str(entity_id), detail=detail)
