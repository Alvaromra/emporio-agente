# Situação não trivial: devolução por arrependimento

O agente não promete a devolução antes de verificar o pedido. A identidade é confirmada pelo e-mail, que o modelo só vê como marcador, e o prazo é calculado pelas regras da loja.

*Horário simulado: 2026-10-31 às 10:30, em Campo Grande.*

> E-mails e telefones aparecem como marcadores (`[EMAIL_1]`, `[TELEFONE_1]`) porque o
> histórico nunca guarda o dado pessoal: o cliente viu o próprio contato na tela, mas
> o modelo e o banco só conhecem o marcador. As linhas com 🔧 mostram as ferramentas
> que o agente consultou antes de responder.

**Cliente:** Me arrependi da minha compra, posso devolver meu pedido?

> 🔧 `buscar_politicas({"pergunta": "prazo de devolução por arrependimento"})`

**Tom:** Entendo perfeitamente. Em compras online, você tem até 7 dias corridos após o recebimento para solicitar a devolução por arrependimento, desde que o instrumento esteja na embalagem original e sem sinais de uso.

Para eu verificar se o seu pedido se encaixa nessas condições, poderia me informar o número do pedido e o e-mail ou telefone usado na compra? 🎸

**Cliente:** pedido 1, meu email é [EMAIL_1]

> 🔧 `avaliar_troca_devolucao({"motivo": "arrependimento", "numero_pedido": 1, "email_ou_telefone": "[EMAIL_1]"})`

**Tom:** Pedro, verifiquei aqui e, pelo sistema, o prazo de 7 dias para devolução por arrependimento desse pedido já expirou.

Se o motivo for algum defeito de fabricação, a gente pode avaliar a troca ou a garantia. Quer que eu te encaminhe para um de nossos atendentes para analisar melhor o seu caso? 🤝

**Cliente:** e se o violão tiver algum defeito?

> 🔧 `avaliar_troca_devolucao({"motivo": "defeito", "numero_pedido": 1, "email_ou_telefone": "[EMAIL_1]"})`

**Tom:** Se o violão tiver um defeito de fabricação, o caso passa a ser tratado pela garantia. Como o prazo de troca direta na loja já passou, o ideal é acionar a garantia do fabricante, que geralmente dura de 6 meses a 2 anos.

A gente pode tentar intermediar esse processo para você. Quer que eu te encaminhe para um atendente para conversarem sobre isso? 🎸
