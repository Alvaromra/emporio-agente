"""Limpeza, normalização e detecção de inconsistências.

Convenções de saída:
- Dinheiro em centavos inteiros (nunca float): R$ 599,90 -> 59990.
- Datas em ISO 8601 (AAAA-MM-DD).
- Booleanos como 0/1 (SQLite).
- Specs como JSON canônico (chaves ordenadas), independentemente da formatação original.
"""

from __future__ import annotations

import json
import re
import statistics
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from emporio.etl.checks import Issue, issue
from emporio.etl.extract import ContractError, Row
from emporio.money import format_brl
from emporio.privacy import fingerprint, first_name, normalize_email, normalize_phone
from emporio.rules.payments import (
    PIX_DISCOUNT_PERCENT,
    installment_plan,
    is_installment_allowed,
    minimum_installment_cents,
)
from emporio.text import fold, slugify

PRODUCT_STATUSES = {"active", "discontinued", "coming_soon"}
ORDER_STATUSES = {"pending", "confirmed", "shipped", "delivered", "cancelled"}
PAYMENT_TYPES = {"pix", "debit", "credit", "boleto"}
TRACKING_PATTERN = re.compile(r"BR[A-Z0-9]{9}BR")
EMAIL_PATTERN = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
STORE_CITY = "campo grande"

# Correções pontuais e auditáveis: id -> (nome com erro, nome corrigido, motivo).
# Só são aplicadas se o nome na origem ainda for o nome com erro.
NAME_CORRECTIONS: dict[int, tuple[str, str, str]] = {
    84: (
        "Giannini GN-15 Nylon Cedr Natural",
        "Giannini GN-15 Nylon Cedro Natural",
        "abreviação truncada 'Cedr'; specs indicam tampo em Cedro",
    ),
}

# Marcas conhecidas (as compostas primeiro). Usadas para detectar descrições
# que falam de outro instrumento.
BRANDS = (
    "Music Man", "Yamaha", "Tagima", "Giannini", "Rozini", "Shelby", "Crafter", "Martin",
    "Taylor", "Takamine", "Kalani", "Kala", "Ohana", "Gibson", "Fender", "Ibanez", "PRS",
    "Pearl", "Tama", "Nord", "Roland", "Korg",
)  # fmt: skip
# Linhas de modelo que identificam a marca mesmo quando ela não é citada.
MODEL_LINES = {
    "jazz bass": "Fender", "precision": "Fender", "stratocaster": "Fender",
    "telecaster": "Fender", "les paul": "Gibson", "stingray": "Music Man",
    "stage custom": "Yamaha", "export": "Pearl", "supernatural": "Roland",
    "nord stage": "Nord",
}  # fmt: skip
# Specs numéricas comparáveis com a descrição: chave -> substantivo em português.
NUMERIC_SPECS = {"strings": "cordas", "keys": "teclas"}
# Madeiras de corpo/cascos, com sinônimos em português -> nome canônico.
WOODS = {
    "alder": "alder", "amieiro": "alder", "ash": "ash", "freixo": "ash",
    "basswood": "basswood", "mahogany": "mahogany", "mogno": "mahogany",
    "maple": "maple", "bordo": "maple", "birch": "birch", "betula": "birch",
    "poplar": "poplar", "choupo": "poplar", "walnut": "walnut", "nogueira": "walnut",
}  # fmt: skip
WOOD_SPECS = ("body", "shells")
PRICE_OUTLIER_RATIO = Decimal("0.2")


@dataclass
class CleanData:
    categories: list[dict] = field(default_factory=list)
    products: list[dict] = field(default_factory=list)
    promotions: list[dict] = field(default_factory=list)
    customers: list[dict] = field(default_factory=list)
    orders: list[dict] = field(default_factory=list)
    order_items: list[dict] = field(default_factory=list)
    policy_chunks: list[dict] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)


# --------------------------------------------------------------------------- parsing


def _fail(table: str, key: object, column: str, value: str, reason: str) -> ContractError:
    return ContractError(f"{table}[{key}].{column} = {value!r}: {reason}")


def _int(table: str, key: object, column: str, value: str) -> int:
    try:
        return int(value)
    except ValueError:
        raise _fail(table, key, column, value, "inteiro esperado") from None


def _cents(table: str, key: object, column: str, value: str) -> int:
    try:
        amount = Decimal(value)
    except InvalidOperation:
        raise _fail(table, key, column, value, "valor monetário esperado") from None
    return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _date(table: str, key: object, column: str, value: str, *, optional: bool = False):
    if not value and optional:
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise _fail(table, key, column, value, "data AAAA-MM-DD esperada") from None


def _choice(table: str, key: object, column: str, value: str, allowed: set[str]) -> str:
    normalized = value.lower()
    if normalized not in allowed:
        raise _fail(table, key, column, value, f"esperado um de {sorted(allowed)}")
    return normalized


# --------------------------------------------------------------------------- produtos


def _contains(folded_text: str, term: str) -> bool:
    return re.search(rf"\b{re.escape(fold(term))}\b", folded_text) is not None


def brands_in(text: str) -> set[str]:
    folded = fold(text)
    found = {brand for brand in BRANDS if _contains(folded, brand)}
    found |= {brand for model, brand in MODEL_LINES.items() if _contains(folded, model)}
    return found


def description_conflicts(name: str, description: str, specs: dict) -> list[tuple[str, str]]:
    """Retorna (código do check, detalhe) para cada contradição encontrada."""
    conflicts: list[tuple[str, str]] = []
    folded = fold(description)

    name_brands = brands_in(name)
    foreign = brands_in(description) - name_brands
    if name_brands and foreign:
        conflicts.append(
            (
                "product.description_brand_mismatch",
                f"nome indica {sorted(name_brands)}, descrição cita {sorted(foreign)}",
            )
        )

    for key, noun in NUMERIC_SPECS.items():
        spec_value = str(specs.get(key, ""))
        if not spec_value.isdigit():
            continue
        mentioned = set(re.findall(rf"\b(\d+)\s+{noun}\b", folded))
        if mentioned and spec_value not in mentioned:
            conflicts.append(
                (
                    "product.description_spec_conflict",
                    f"specs: {key}={spec_value}; descrição: {', '.join(sorted(mentioned))} {noun}",
                )
            )

    described_woods = {canon for word, canon in WOODS.items() if _contains(folded, word)}
    for key in WOOD_SPECS:
        if key not in specs or not described_woods:
            continue
        spec_woods = {
            WOODS.get(part.strip(), part.strip()) for part in re.split(r"[/,]", fold(specs[key]))
        }
        if not described_woods & spec_woods:
            conflicts.append(
                (
                    "product.description_spec_conflict",
                    f"specs: {key}={specs[key]}; descrição cita {sorted(described_woods)}",
                )
            )
    return conflicts


def _products(rows: list[Row], categories: dict[int, str], issues: list[Issue]) -> list[dict]:
    products: list[dict] = []
    for row in rows:
        pid = _int("products", "?", "product_id", row["product_id"])
        name = row["name"]
        if pid in NAME_CORRECTIONS and name == NAME_CORRECTIONS[pid][0]:
            _, corrected, reason = NAME_CORRECTIONS[pid]
            issues.append(
                issue(
                    "product.name_corrected",
                    "products",
                    pid,
                    f"{name!r} -> {corrected!r} ({reason})",
                )
            )
            name = corrected

        category_id = _int("products", pid, "category_id", row["category_id"])
        if category_id not in categories:
            raise _fail("products", pid, "category_id", row["category_id"], "categoria inexistente")

        try:
            specs = json.loads(row["specs"])
        except json.JSONDecodeError:
            raise _fail("products", pid, "specs", row["specs"], "JSON inválido") from None
        if not isinstance(specs, dict):
            raise _fail("products", pid, "specs", row["specs"], "objeto JSON esperado")
        specs = {str(k): str(v).strip() for k, v in specs.items()}

        price = _cents("products", pid, "price_brl", row["price_brl"])
        stock = _int("products", pid, "stock_quantity", row["stock_quantity"])
        if price <= 0 or stock < 0:
            raise _fail("products", pid, "price/stock", f"{price}/{stock}", "valor negativo")
        status = _choice("products", pid, "status", row["status"], PRODUCT_STATUSES)

        conflicts = description_conflicts(name, row["description"], specs)
        for code, detail in conflicts:
            issues.append(issue(code, "products", pid, f"{name}: {detail}"))
        reliable = not conflicts

        if status != "active" and stock > 0:
            issues.append(
                issue(
                    "product.unsellable_with_stock",
                    "products",
                    pid,
                    f"{name}: status={status}, estoque={stock}",
                )
            )
        if status == "active" and stock == 0:
            issues.append(issue("product.active_out_of_stock", "products", pid, name))

        searchable = [name, categories[category_id], *specs.values()]
        if reliable:
            searchable.append(row["description"])

        products.append(
            {
                "product_id": pid,
                "name": name,
                "category_id": category_id,
                "price_cents": price,
                "stock_quantity": stock,
                "status": status,
                "description": row["description"],
                "description_reliable": int(reliable),
                "specs_json": json.dumps(specs, ensure_ascii=False, sort_keys=True),
                "created_at": _date("products", pid, "created_at", row["created_at"]),
                "search_text": fold(" ".join(searchable)),
            }
        )

    by_category: dict[int, list[dict]] = {}
    for product in products:
        by_category.setdefault(product["category_id"], []).append(product)
    for members in by_category.values():
        if len(members) < 3:
            continue
        median = Decimal(statistics.median(p["price_cents"] for p in members))
        for p in members:
            if p["price_cents"] < median * PRICE_OUTLIER_RATIO:
                detail = (
                    f"{p['name']}: {format_brl(p['price_cents'])} "
                    f"vs. mediana {format_brl(int(median))}"
                )
                issues.append(issue("product.price_outlier", "products", p["product_id"], detail))
    return products


# --------------------------------------------------------------------------- demais tabelas


def _categories(rows: list[Row]) -> list[dict]:
    return [
        {
            "category_id": _int("categories", "?", "category_id", row["category_id"]),
            "name": row["name"],
            "slug": slugify(row["name"]),
            "description": row["description"],
        }
        for row in rows
    ]


def _promotions(rows: list[Row], products: dict[int, dict], issues: list[Issue]) -> list[dict]:
    promotions: list[dict] = []
    for row in rows:
        promo_id = _int("promotions", "?", "promotion_id", row["promotion_id"])
        product_id = _int("promotions", promo_id, "product_id", row["product_id"])
        if product_id not in products:
            raise _fail(
                "promotions", promo_id, "product_id", row["product_id"], "produto inexistente"
            )
        discount = _int("promotions", promo_id, "discount_percent", row["discount_percent"])
        if not 0 < discount < 100:
            raise _fail(
                "promotions", promo_id, "discount_percent", row["discount_percent"], "fora de 1..99"
            )
        active = _choice("promotions", promo_id, "is_active", row["is_active"], {"0", "1"})
        promotions.append(
            {
                "promotion_id": promo_id,
                "product_id": product_id,
                "discount_percent": discount,
                "label": row["description"],
                "is_active": int(active),
            }
        )

    active_by_product: dict[int, list[dict]] = {}
    for promo in promotions:
        if promo["is_active"]:
            active_by_product.setdefault(promo["product_id"], []).append(promo)
    for product_id, active in active_by_product.items():
        product = products[product_id]
        if len(active) > 1:
            labels = ", ".join(f"{p['label']} ({p['discount_percent']}%)" for p in active)
            issues.append(
                issue(
                    "promotion.multiple_active",
                    "products",
                    product_id,
                    f"{product['name']}: {labels}",
                )
            )
        if product["status"] != "active" or product["stock_quantity"] == 0:
            for promo in active:
                issues.append(
                    issue(
                        "promotion.active_on_unsellable",
                        "promotions",
                        promo["promotion_id"],
                        f"{product['name']} ({product['status']}, "
                        f"estoque {product['stock_quantity']})",
                    )
                )
    return promotions


def _customers(
    rows: list[Row], pepper: str, issues: list[Issue]
) -> tuple[list[dict], dict[int, str]]:
    customers: list[dict] = []
    cities: dict[int, str] = {}
    by_email: dict[str, list[int]] = {}
    by_phone: dict[str, list[int]] = {}
    for row in rows:
        cid = _int("customers", "?", "customer_id", row["customer_id"])
        email, phone = normalize_email(row["email"]), normalize_phone(row["phone"])
        problems = []
        if not EMAIL_PATTERN.fullmatch(email):
            problems.append("e-mail")
        if len(phone) not in (10, 11):
            problems.append("telefone")
        if problems:
            issues.append(issue("customer.invalid_contact", "customers", cid, " e ".join(problems)))
        by_email.setdefault(email, []).append(cid)
        by_phone.setdefault(phone, []).append(cid)
        cities[cid] = row["city"]
        customers.append(
            {
                "customer_id": cid,
                "first_name": first_name(row["name"]),
                "city": row["city"],
                "email_fp": fingerprint("email", email, pepper),
                "phone_fp": fingerprint("phone", phone, pepper),
            }
        )
    # Os detalhes nunca exibem o contato em si, só quais cadastros colidem.
    for code, groups in (("customer.shared_email", by_email), ("customer.shared_phone", by_phone)):
        for ids in groups.values():
            if len(ids) > 1:
                ids_text = ",".join(map(str, sorted(ids)))
                issues.append(issue(code, "customers", ids_text, f"cadastros {ids_text}"))
    return customers, cities


def _payment(order_id: int, value: str) -> tuple[str, int]:
    match = re.fullmatch(r"(pix|debit|boleto|credit)(?:_(\d{1,2})x)?", value.lower())
    if not match:
        raise _fail("orders", order_id, "payment_method", value, "formato desconhecido")
    payment_type, installments = match.group(1), int(match.group(2) or 1)
    if not 1 <= installments <= 12 or (payment_type != "credit" and installments != 1):
        raise _fail("orders", order_id, "payment_method", value, "parcelamento inválido")
    return payment_type, installments


def _order_items(
    rows: list[Row], orders: set[int], products: set[int], issues: list[Issue]
) -> list[dict]:
    merged: dict[tuple[int, int], int] = {}
    for row in rows:
        order_id = _int("order_items", "?", "order_id", row["order_id"])
        product_id = _int("order_items", order_id, "product_id", row["product_id"])
        quantity = _int("order_items", order_id, "quantity", row["quantity"])
        if order_id not in orders:
            raise _fail("order_items", order_id, "order_id", row["order_id"], "pedido inexistente")
        if product_id not in products:
            raise _fail(
                "order_items", order_id, "product_id", row["product_id"], "produto inexistente"
            )
        if quantity <= 0:
            raise _fail("order_items", order_id, "quantity", row["quantity"], "deve ser > 0")
        key = (order_id, product_id)
        if key in merged:
            issues.append(
                issue("order_item.duplicate_line", "orders", order_id, f"produto {product_id}")
            )
        merged[key] = merged.get(key, 0) + quantity
    return [{"order_id": o, "product_id": p, "quantity": q} for (o, p), q in sorted(merged.items())]


def _orders(
    rows: list[Row],
    customer_cities: dict[int, str],
    item_rows: list[Row],
    products: dict[int, dict],
    issues: list[Issue],
) -> tuple[list[dict], list[dict]]:
    orders: list[dict] = []
    for row in rows:
        oid = _int("orders", "?", "order_id", row["order_id"])
        customer_id = _int("orders", oid, "customer_id", row["customer_id"])
        if customer_id not in customer_cities:
            raise _fail("orders", oid, "customer_id", row["customer_id"], "cliente inexistente")
        status = _choice("orders", oid, "status", row["status"], ORDER_STATUSES)
        payment_type, installments = _payment(oid, row["payment_method"])
        order_date = _date("orders", oid, "order_date", row["order_date"])
        estimated = _date(
            "orders", oid, "estimated_delivery", row["estimated_delivery"], optional=True
        )
        tracking = row["tracking_code"].upper() or None

        if tracking and not TRACKING_PATTERN.fullmatch(tracking):
            issues.append(issue("order.tracking_invalid", "orders", oid, tracking))
        if status in {"shipped", "delivered"} and not tracking:
            issues.append(
                issue("order.tracking_status_mismatch", "orders", oid, f"{status} sem rastreamento")
            )
        if status in {"pending", "confirmed", "cancelled"} and tracking:
            issues.append(
                issue("order.tracking_status_mismatch", "orders", oid, f"{status} com rastreamento")
            )
        if estimated and estimated < order_date:
            issues.append(
                issue(
                    "order.delivery_before_order",
                    "orders",
                    oid,
                    f"pedido {order_date}, previsão {estimated}",
                )
            )
        if tracking and fold(customer_cities[customer_id]) == STORE_CITY:
            issues.append(
                issue(
                    "order.local_with_carrier_tracking",
                    "orders",
                    oid,
                    f"cliente em {customer_cities[customer_id]}, código {tracking}",
                )
            )

        orders.append(
            {
                "order_id": oid,
                "customer_id": customer_id,
                "order_date": order_date,
                "status": status,
                "total_cents": _cents("orders", oid, "total_brl", row["total_brl"]),
                "payment_type": payment_type,
                "installments": installments,
                "tracking_code": tracking,
                "estimated_delivery": estimated,
                "notes": row["notes"] or None,
            }
        )

    items = _order_items(item_rows, {o["order_id"] for o in orders}, set(products), issues)
    items_by_order: dict[int, list[dict]] = {}
    for item in items:
        items_by_order.setdefault(item["order_id"], []).append(item)
    for order in orders:
        lines = items_by_order.get(order["order_id"], [])
        expected = sum(products[i["product_id"]]["price_cents"] * i["quantity"] for i in lines)
        if lines and expected != order["total_cents"]:
            diff = order["total_cents"] - expected
            detail = (
                f"registrado {format_brl(order['total_cents'])}, "
                f"itens a preço atual {format_brl(expected)} "
                f"(diferença {'-' if diff < 0 else '+'}{format_brl(abs(diff))})"
            )
            issues.append(issue("order.total_mismatch", "orders", order["order_id"], detail))
        if (
            order["payment_type"] == "credit"
            and order["installments"] > 1
            and not is_installment_allowed(order["total_cents"], order["installments"])
        ):
            _, parcel = installment_plan(order["total_cents"], order["installments"])
            minimum = minimum_installment_cents(order["installments"])
            detail = (
                f"{order['installments']}x de {format_brl(parcel)} sobre "
                f"{format_brl(order['total_cents'])}; mínimo da faixa: {format_brl(minimum)}"
            )
            issues.append(
                issue("order.installment_below_minimum", "orders", order["order_id"], detail)
            )
        if order["payment_type"] == "pix" and lines and order["total_cents"] == expected:
            detail = (
                f"total {format_brl(order['total_cents'])} igual ao preço de tabela, "
                f"sem os {PIX_DISCOUNT_PERCENT}% do PIX"
            )
            issues.append(issue("order.pix_discount_missing", "orders", order["order_id"], detail))
        for item in lines:
            product = products[item["product_id"]]
            if product["status"] != "active":
                detail = f"pedido {order['status']} contém {product['name']} ({product['status']})"
                issues.append(issue("order.item_not_released", "orders", order["order_id"], detail))
    return orders, items


# --------------------------------------------------------------------------- orquestração


def transform(tables: dict[str, list[Row]], pepper: str) -> CleanData:
    data = CleanData()
    data.categories = _categories(tables["categories"])
    category_names = {c["category_id"]: c["name"] for c in data.categories}
    data.products = _products(tables["products"], category_names, data.issues)
    products_by_id = {p["product_id"]: p for p in data.products}

    used_categories = {p["category_id"] for p in data.products}
    for category in data.categories:
        if category["category_id"] not in used_categories:
            data.issues.append(
                issue("category.empty", "categories", category["category_id"], category["name"])
            )

    data.promotions = _promotions(tables["promotions"], products_by_id, data.issues)
    data.customers, cities = _customers(tables["customers"], pepper, data.issues)
    data.orders, data.order_items = _orders(
        tables["orders"], cities, tables["order_items"], products_by_id, data.issues
    )
    return data
