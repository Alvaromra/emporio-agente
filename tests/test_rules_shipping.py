from emporio.rules.shipping import requires_special_freight, shipping_quote


def test_campo_grande_acima_de_500_tem_frete_gratis():
    quote = shipping_quote("Campo Grande", 50_001)
    assert quote.is_local and quote.fee_cents == 0


def test_campo_grande_com_exatamente_500_paga_taxa():
    assert shipping_quote("campo grande", 50_000).fee_cents == 3_500


def test_outra_cidade_nao_inventa_valor():
    quote = shipping_quote("Dourados", 300_000)
    assert not quote.is_local
    assert quote.fee_cents is None
    assert any("SEDEX" in line for line in quote.lines)


def test_bateria_acustica_exige_frete_especial():
    assert requires_special_freight("Bateria Acústica Yamaha Kit 1 Studio")
    quote = shipping_quote("Três Lagoas", 443_900, ["Bateria Acústica Yamaha Kit 1 Studio"])
    assert any("frete especial" in line for line in quote.lines)
    assert not requires_special_freight("Yamaha C40 Nylon Natural")
