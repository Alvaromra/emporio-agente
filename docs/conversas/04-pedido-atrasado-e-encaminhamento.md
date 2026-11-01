# Situação não trivial: pedido atrasado, fora do expediente

Sábado às 15h, com a loja fechada. O pedido está com a entrega 245 dias atrasada: o agente reconhece o atraso sem inventar motivo, gera um protocolo e diz quando a equipe volta.

*Horário simulado: 2026-10-31 às 15:00, em Campo Grande.*

> E-mails e telefones aparecem como marcadores (`[EMAIL_1]`, `[TELEFONE_1]`) porque o
> histórico nunca guarda o dado pessoal: o cliente viu o próprio contato na tela, mas
> o modelo e o banco só conhecem o marcador. As linhas com 🔧 mostram as ferramentas
> que o agente consultou antes de responder.

**Cliente:** cadê meu pedido 8? meu telefone é [TELEFONE_1]

> 🔧 `consultar_pedido({"numero_pedido": 8, "email_ou_telefone": "[TELEFONE_1]"})`

**Tom:** Oi, Ana! Vi aqui que seu pedido do Kala KA-C Concert Mogno já foi enviado, mas sinto muito que ele esteja com esse atraso. 

O código de rastreio é BRJL5544332BR e você pode consultar no site dos Correios ou da Jadlog. Como a previsão já passou, você quer que eu encaminhe seu caso para nossa equipe resolver? Eles voltam na terça-feira, 03/11, às 09:00. 😟

**Cliente:** sim, pode encaminhar por favor

> 🔧 `encaminhar_para_atendente({"resumo": "Pedido 8 (Kala KA-C Concert Mogno) enviado em 15/02/2026, com previsão de entrega vencida há 245 dias. Cliente solicita verificação do atraso.", "motivo": "atraso_pedido", "numero_pedido": 8})`

**Tom:** Pronto, Ana! Já encaminhei seu caso para a nossa equipe com o protocolo **EM20261031-0001**.

Como a loja está fechada agora, eles vão analisar tudo e te dar um retorno em até 24 horas úteis, a partir de terça-feira, 03/11, às 09:00. Posso te ajudar com algo mais? 🤝
