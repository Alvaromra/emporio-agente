# Empório da Música: agente de atendimento

Protótipo de um agente de mensagens de texto que atende clientes da Empório da Música
(loja de instrumentos musicais em Campo Grande/MS), respondendo dúvidas recorrentes sobre
produtos, preços, disponibilidade, pedidos e políticas da loja.

> Projeto desenvolvido para o desafio técnico de AI Engineer da Artefact.
> Status: **em construção**. Este README cresce a cada etapa.

## Visão geral da arquitetura

O agente segue uma abordagem **híbrida**:

- **Dados estruturados** (catálogo, estoque, promoções, pedidos) são consultados por
  ferramentas com SQL parametrizado sobre um SQLite gerado a partir dos CSVs.
- **Texto não estruturado** (manual de políticas) é consultado via RAG.
- **Regras de negócio** (parcelamento, desconto no PIX, prazos de devolução, horário de
  funcionamento) são código determinístico e testado.
- O **LLM** (família Gemma) orquestra: entende a mensagem, escolhe a ferramenta e redige a
  resposta com a persona da loja. Ele não calcula nem inventa dados.

As justificativas completas de cada decisão estarão na seção *Decisões técnicas*.

## Roadmap

| Etapa | Conteúdo | Status |
|---|---|---|
| 01 | Estrutura do projeto, configuração e relógio da loja | ✅ |
| 02 | ETL: limpeza, carga em SQLite e relatório de qualidade | ✅ |
| 03 | Regras de negócio determinísticas | ✅ |
| 04 | Ferramentas de catálogo e pedidos | ✅ |
| 05 | RAG sobre o manual de políticas | ✅ |
| 06 | Provedores de LLM (Gemini API e Ollama) | ✅ |
| 07 | Agente: persona, loop de function calling e guardrails | ✅ |
| 08 | Persistência do histórico de conversa | ✅ |
| 09 | Interface web, API e CLI | ✅ |
| 10 | Documentação final, conversas de exemplo e avaliações | ⏳ |

## Como rodar

Requisitos: Python 3.11 ou superior.

```bash
# Linux/macOS
python -m venv .venv
source .venv/bin/activate

# Windows (PowerShell)
py -m venv .venv
.venv\Scripts\Activate.ps1

# Instalação (modo editável, com ferramentas de desenvolvimento)
pip install -e ".[dev]"

# Configuração (opcional nesta etapa)
cp .env.example .env

# Gera data/processed/store.db e docs/relatorio_qualidade_dados.md
python -m emporio.etl

# Chama as ferramentas do agente diretamente, sem LLM
python -m emporio.tools
python -m emporio.tools buscar_produtos '{"categoria": "violão", "preco_max": 1000}'

# Testa o modelo (exige GEMINI_API_KEY no .env, ou Ollama configurado)
python -m emporio.llm --ping
python -m emporio.llm "quanto custa o Takamine GD20?"

# Interface web: abra http://localhost:8000 (API documentada em /docs)
python -m emporio.web

# Conversa com o agente no terminal (--trace mostra as ferramentas chamadas)
python -m emporio.agent --trace

# Conversas salvas: listar, mostrar, exportar, apagar, aplicar a retenção
python -m emporio.memory
python -m emporio.memory --mostrar ID
python -m emporio.memory --encaminhamentos

# Consulta o manual de políticas e mede a qualidade da recuperação
python -m emporio.rag "me arrependi, posso devolver?"
python -m emporio.rag --eval

# Testes
pytest
```

## Dados: preparação, qualidade e LGPD

A loja forneceu os dados em CSV. Antes de qualquer LLM entrar em cena, um ETL
(`src/emporio/etl/`) transforma esses arquivos num SQLite limpo e validado. A análise
dos dados mostrou que eles têm inconsistências deliberadas (descrições que falam de outro
instrumento, produtos "em breve" com estoque, promoções vencidas, totais divergentes).
Por isso o tratamento dos dados é parte central da solução, e não um detalhe.

**Dois tipos de problema, dois tratamentos.** Violações de contrato (coluna ausente,
número ilegível, chave estrangeira quebrada) interrompem o ETL com uma mensagem clara e
nada é gravado. Inconsistências de negócio são carregadas com uma decisão de tratamento
explícita e registradas na tabela `data_quality_issues`.

**Relatório de qualidade.** Cada execução gera
[`docs/relatorio_qualidade_dados.md`](docs/relatorio_qualidade_dados.md) com todos os
achados, a decisão tomada para cada um e alertas operacionais (como pedidos com entrega
atrasada). O catálogo de verificações em `etl/checks.py` é a fonte do relatório, então a
documentação não fica defasada em relação ao código. As interpretações adotadas estão em
[`docs/suposicoes.md`](docs/suposicoes.md).

**Decisões de modelagem.**

- Dinheiro em centavos inteiros, nunca `float`.
- A visão `v_catalog` concentra as regras de vitrine: o que é vendável, qual promoção vale,
  qual o preço final e qual descrição é segura para mostrar. As ferramentas do agente
  consultam essa visão, não as tabelas brutas.
- O banco é gerado num arquivo temporário e só então substitui o anterior, para que uma
  falha no meio nunca deixe o agente com dados pela metade.
- Apenas biblioteca padrão (`csv`, `sqlite3`). São menos de 200 linhas de dados; validar
  linha a linha dá mensagens de erro precisas sem dependências pesadas.

**LGPD.** O banco operacional não guarda nome completo, e-mail nem telefone dos clientes.
Guarda o primeiro nome (para a saudação), a cidade (regras de frete) e uma impressão
digital HMAC-SHA256 do e-mail e do telefone. Isso basta para conferir a identidade de quem
pergunta por um pedido, mas não permite extrair contatos do banco. É a aplicação dos
princípios de minimização e pseudonimização da LGPD. O segredo do HMAC vem de
`EMPORIO_PII_PEPPER`.

## Regras de negócio

O agente nunca calcula nada "de cabeça". Tudo o que gera um número ou um prazo está em
`src/emporio/rules/`, em funções puras e testadas, com cada constante apontando a seção do
manual de onde veio:

| Módulo | O que resolve | Manual |
|---|---|---|
| `payments.py` | Preço no PIX (5%, não acumula com promoção), número máximo de parcelas sem juros por faixa, pagamento combinado | 3, 3.1, 6.2 |
| `returns.py` | Arrependimento (7 dias), troca por defeito (30 dias), troca por preferência, garantia legal (90 dias) e do fabricante | 4, 8 |
| `store.py` | Loja aberta agora, quando reabre, dados de contato | 1.2, 2 |
| `calendar.py` | Feriados (inclusive Páscoa móvel) e dias úteis | 2 |
| `shipping.py` | Frete local (grátis acima de R$ 500), modalidades e prazos para outras cidades | 5 |

As funções recebem a data como parâmetro em vez de consultar o relógio. Isso permite
testar cenários como "sábado às 13h, com Finados na segunda" sem depender do dia em que os
testes rodam.

**Por que não deixar o LLM interpretar o manual?** Um modelo pode explicar uma política,
mas contar dias corridos, dividir parcelas e respeitar faixas de valor mínimo são tarefas em
que ele erra de forma silenciosa e plausível. Nesses casos, um erro vira propaganda enganosa
(manual 7.1). O RAG da etapa 05 continua útil para *explicar* políticas e responder dúvidas
abertas; os números vêm daqui.

As regras também são aplicadas aos pedidos históricos no ETL, o que revelou parcelamentos
abaixo do mínimo e pedidos PIX sem o desconto. As ambiguidades do manual e a interpretação
adotada estão em [`docs/suposicoes.md`](docs/suposicoes.md).

**Limitação conhecida:** as regras foram transcritas da versão 2.1 do manual. Se o manual
mudar, `rules/` precisa ser atualizado junto.

## Ferramentas do agente

O agente responde sobre dados da loja exclusivamente por meio de ferramentas
(`src/emporio/tools/`). Cada uma é uma função Python descrita por um JSON Schema neutro,
que a etapa 06 converte para o formato de cada provedor de LLM.

| Ferramenta | Quando o modelo usa |
|---|---|
| `buscar_produtos` | "Quais violões até R$ 1.000?", "tem ukulele elétrico?" |
| `detalhar_produto` | "Quanto custa o Takamine GD20?" (preço, promoção, PIX, parcelas, specs) |
| `listar_promocoes` | "Tem alguma promoção?", "a Black Friday já começou?" |
| `consultar_pedido` | "Qual o status do meu pedido 8?" |
| `avaliar_troca_devolucao` | "Me arrependi, posso devolver?" |
| `status_da_loja` | "Vocês estão abertos?", endereço, telefone |
| `consultar_frete` | "Quanto é o frete para Dourados?" |

**Decisões de projeto.**

- **Valores prontos.** As ferramentas devolvem preços e datas já formatados ("R$ 2.089,05",
  "01/11/2025"). O modelo só repete; nunca soma, desconta ou conta dias.
- **Orientações junto com os fatos.** Quando um dado exige cuidado (pedido atrasado, total
  divergente, produto esgotado), a ferramenta devolve `orientacoes_ao_agente` dizendo como
  comunicar. Os achados do ETL chegam à conversa sem que o modelo precise conhecê-los.
- **Busca determinística, não semântica.** Com 65 produtos, uma busca por tokens tolerante a
  acentos, plurais e erros de digitação ("takamini gd 20" encontra o GD20) é mais precisa e
  explicável do que embeddings. Filtros de preço são SQL, não similaridade. Quando um nome é
  ambíguo ("Martin"), a ferramenta devolve os candidatos para o agente perguntar.
- **Escopo.** Pedidos de acessórios (palhetas, cabos, pedais...) e categorias sem produtos
  (sopros, cordas orquestrais) são sinalizados pela ferramenta, para o agente não inventar
  itens.
- **Erros viram dados.** Uma falha retorna `{"erro": "..."}` em vez de exceção, para o
  agente repassar ao modelo e ele reagir (pedir outro dado, tentar outra ferramenta).

**Segurança dos pedidos (LGPD).** Consultar um pedido exige o número e o e-mail ou telefone
do dono daquele pedido, comparados por HMAC em tempo constante. A mensagem de falha é
idêntica para pedido inexistente e contato errado, para não revelar quais números existem.
Depois de 3 falhas, a conversa só consulta pedidos via atendente. Se o e-mail do cliente é
compartilhado com outro cadastro, só o telefone é aceito. A resposta traz apenas o primeiro
nome do cliente, e as ferramentas abrem o banco em modo somente leitura.

## RAG sobre o manual de políticas

Perguntas abertas sobre regras da loja ("como funciona a garantia?", "vocês aceitam
boleto?") são respondidas pela ferramenta `buscar_politicas`, que recupera trechos do
manual e os entrega ao modelo com a orientação de responder somente com base neles.

**Extração e divisão.** O PDF é lido com `pypdf` (puro Python) e dividido pelas seções
numeradas do próprio manual (1, 1.1, 4.2...), resultando em 25 trechos. Dividir por seção,
em vez de fatias de tamanho fixo, garante que uma regra nunca seja cortada ao meio e permite
citar a seção exata. Cada trecho carrega o título da seção-mãe como contexto. Cabeçalhos e
rodapés de página são removidos, e seções que atravessam páginas ficam inteiras. Itens
numerados dentro de uma seção ("1. Saudação") não são confundidos com títulos, porque só
conta como título o que avança a numeração.

**Correções antes de indexar.** O manual tem dois erros (e-mail com acento no domínio e um
número de WhatsApp divergente). Eles são corrigidos por uma errata explícita no código, e
cada correção aparece no relatório de qualidade. O modelo nunca vê a versão com erro.

**Recuperação lexical (BM25), não vetorial.** São 25 trechos de vocabulário estreito e
previsível. BM25 é determinístico, roda sem rede e sem modelo de embeddings, e sua
qualidade é medida. A distância entre a fala do cliente ("me arrependi", "chegou quebrado")
e o vocabulário do manual ("arrependimento", "defeito", "avaria") é coberta por um dicionário
de sinônimos pequeno e auditável, com peso menor que os termos originais.

**Avaliação.** `evals/politicas.jsonl` tem 28 perguntas escritas como um cliente escreveria,
cada uma com as seções que deveriam ser recuperadas. Resultado atual:

| Métrica | Valor |
|---|---|
| hit@1 (seção correta em primeiro) | 26/28 (93%) |
| hit@3 (seção correta entre as 3 primeiras) | 28/28 (100%) |
| MRR | 0,96 |

Como a ferramenta devolve os 3 primeiros trechos, o hit@3 é a métrica que importa para a
resposta. Uma ressalva honesta: o conjunto de avaliação e o dicionário de sinônimos foram
escritos juntos, então esses números medem regressão (se uma mudança piora a busca), não
generalização. Com mais tempo, o próximo passo seria um conjunto maior, escrito por outra
pessoa ou tirado de conversas reais, e comparar BM25 com busca vetorial e híbrida nele.

**Roteamento entre RAG e ferramentas.** O manual explica a regra; as ferramentas aplicam a
regra ao caso concreto. Quando um trecho recuperado trata de algo calculável (parcelas,
prazos de devolução, frete, loja aberta agora), a ferramenta acrescenta uma orientação para
o modelo usar a ferramenta de cálculo correspondente. Trechos internos (tom de voz, fluxo
de atendimento) vêm marcados para serem seguidos, não recitados ao cliente.

## Modelo e provedor

O agente usa a família **Gemma 4** (Google), por dois caminhos atrás da mesma interface
(`src/emporio/llm/`), escolhidos por `EMPORIO_LLM_PROVIDER`:

| Provedor | Modelo padrão | Quando usar |
|---|---|---|
| `gemini` (padrão) | `gemma-4-26b-a4b-it` via Gemini API | Avaliação e demonstração: basta uma chave gratuita, sem GPU |
| `ollama` | `gemma4:e4b` local | Sem internet, sem cotas, ou sem enviar dados de clientes a terceiros |

**Por que Gemma 4.** Tem function calling nativo, treinado no modelo e não emulado por
prompt, que é a base de um agente com ferramentas. Os pesos são abertos (Apache 2.0), então o
mesmo modelo que roda na API pode rodar na infraestrutura da loja. O `gemma2:9b`, testado no
início, foi descartado por não ter function calling nativo.

**Por que o 26B A4B como padrão.** É um modelo MoE: tem qualidade de modelo grande, mas ativa
cerca de 4B parâmetros por token, o que o torna rápido. Relatos públicos indicam que a
confiabilidade de chamadas de ferramenta das variantes menores (E2B/E4B) é inferior; por
isso a variante local fica como alternativa, e a qualidade de cada uma será comparada nas
avaliações da etapa 10.

**Sem framework de agentes.** A interface é fina: tipos neutros de mensagem (`Message`,
`ToolCall`) e um método `complete()` por provedor. Cada provedor converte o histórico e as
ferramentas para o seu formato. Isso evita camadas de adaptação que, no caso do Gemma 4, são
uma fonte conhecida de bugs no formato das chamadas de ferramenta. O provedor Ollama ainda
reconhece o formato nativo do Gemma 4 (`<|tool_call>call:...`) quando ele vaza no texto.

**Detalhes que importam.**

- O SDK do Google não executa ferramentas sozinho (`automatic_function_calling` desligado): o
  agente controla o loop, aplica limites e registra cada chamada.
- O raciocínio interno do modelo (partes `thought`) é descartado e nunca chega ao cliente.
- A mensagem original do modelo é reenviada como veio, preservando metadados que a API usa
  entre turnos.
- Erros 429 e 5xx são repetidos automaticamente com espera exponencial; falhas viram
  mensagens claras (chave inválida, cota esgotada, Ollama desligado, modelo não baixado).
- Temperatura 0,3: num atendimento, consistência e fidelidade às ferramentas valem mais do
  que variedade.

**LGPD e provedor.** Pelos termos da Gemini API, o conteúdo enviado no tier gratuito pode ser
usado pelo Google para melhorar produtos e lido por revisores humanos, e o Google orienta não
enviar dados pessoais nesse tier. Para um protótipo com dados fictícios isso é aceitável. Em
produção, com clientes reais, o caminho seria o tier pago (em que os dados não são usados
para treino) ou o Ollama local. Como mitigação adicional, a etapa 07 substitui e-mails e
telefones por marcadores antes de enviar a mensagem ao modelo.

## O agente

`src/emporio/agent/` junta as peças: persona, loop de ferramentas, guardrails e proteção de
dados pessoais.

**Persona.** O assistente se chama **Tom** (tom musical e tom de voz). O manual (7.1) define
o estilo: "informal mas profissional", como "um amigo que entende de música". O prompt pede
respostas curtas, de conversa, com pouca formatação, e chama o cliente pelo primeiro nome
quando ele é conhecido (7.2). O prompt é montado a cada mensagem com a data, a hora e a
situação da loja em Campo Grande. Fora do expediente, o agente continua atendendo e avisa
quando a equipe volta (7.1).

**Estratégia de prompt.** O prompt é curto e organizado em blocos: jeito de falar, regra de
ouro, qual ferramenta usar, dados pessoais, escopo e segurança. A regra de ouro concentra o
que mais importa: preço, estoque, prazo, pedido ou regra só depois de consultar uma
ferramenta, repetindo os valores como vieram. O resto do conhecimento de domínio não está no
prompt: está nas descrições das ferramentas e nas orientações que elas devolvem junto com os
dados (seção *Ferramentas do agente*).

**Loop de ferramentas.** A cada mensagem, o modelo pode pedir ferramentas; o agente executa,
devolve os resultados e chama o modelo de novo, até a resposta final ou o limite de 6
rodadas. Erros de ferramenta voltam ao modelo como dados, para ele reagir. O histórico
enviado é limitado às últimas 12 trocas, sempre cortado numa mensagem do cliente, para nunca
separar uma chamada de ferramenta da sua resposta.

**Guardrails.**

- **Valores com fonte.** Todo valor em R$ da resposta precisa ter vindo de uma ferramenta ou
  do próprio cliente (manual 7.1: nunca informar preço sem consultar o sistema). Se o modelo
  citar um valor sem fonte, ele recebe uma instrução interna para corrigir; se insistir, a
  resposta é trocada por uma mensagem segura que oferece a equipe.
- **Limpeza.** Marcações internas do modelo que escapam no texto são removidas.
- **Respostas de segurança** para resposta vazia e para excesso de rodadas.
- **Escopo e injeção de prompt** são tratados no prompt: recusa simpática a temas fora da
  loja, nenhuma indicação de outras lojas, e instruções do usuário ou de resultados de
  ferramentas não mudam as regras.

**Dados pessoais fora do modelo.** Antes de a mensagem ir ao LLM, e-mails e telefones viram
marcadores (`[EMAIL_1]`, `[TELEFONE_1]`). O modelo chama as ferramentas com os marcadores, e
o agente os troca pelos valores reais só na execução. O provedor de LLM nunca recebe o
contato, e o registro de ferramentas chamadas guarda apenas os marcadores. CPF e números de
cartão (validados pelo algoritmo de Luhn) não são necessários no atendimento: são removidos
de forma irreversível, e o agente orienta o cliente a não enviá-los.

**Encaminhamento.** Reclamações, atrasos e pedidos para falar com uma pessoa geram um
protocolo (`encaminhar_para_atendente`) com o prazo de retorno do manual (24 horas úteis).
Nesta etapa os protocolos ficam em memória; a etapa 08 os persiste.

## Persistência do histórico

O enunciado pede persistência "se fizer sentido para a experiência do usuário". Fez, por
quatro motivos:

1. **Continuidade.** O cliente informa o pedido numa mensagem e pergunta sobre troca na
   seguinte; a conversa também sobrevive a um reinício do servidor (`--sessao ID` na CLI).
2. **Encaminhamento.** Quando o agente gera um protocolo, a equipe precisa ver a conversa
   que levou até ele. Os protocolos ficam no mesmo banco, ligados à conversa.
3. **Auditoria.** Cada chamada de ferramenta fica registrada com os argumentos, o que
   permite entender por que o agente respondeu o que respondeu.
4. **Exemplos e avaliação.** As conversas de exemplo deste repositório são exportadas do
   banco (`python -m emporio.memory --exportar`), e não reescritas à mão.

**Onde.** SQLite em `data/runtime/app.db`, separado do banco da loja, porque o ETL recria o
`store.db` do zero. A pasta é ignorada pelo git. Uma conexão por operação e o modo WAL
deixam o banco seguro para a interface web, que atende várias conversas ao mesmo tempo.

**O que é guardado, e o que não é.**

| Guardado | Não guardado |
|---|---|
| Mensagens como o modelo as viu: e-mails e telefones já trocados por marcadores | O cofre que liga marcador e valor real (fica só em memória) |
| Chamadas de ferramenta com os argumentos marcados | CPF e cartão (removidos antes de tudo) |
| Respostas reprovadas pelo guardrail, marcadas como internas (para auditoria) | Metadados internos do provedor de LLM |
| Protocolos de encaminhamento e seus resumos | |

A consequência é deliberada: ao retomar uma conversa depois de um reinício, os marcadores
não podem mais ser convertidos de volta, e o cliente informa o contato de novo se quiser
consultar um pedido. É o preço de nunca gravar o dado pessoal.

**Retenção e exclusão.** Conversas sem atividade há mais de 90 dias (`EMPORIO_RETENTION_DAYS`)
são apagadas por `python -m emporio.memory --purgar`, pensado para rodar num agendador. A
exclusão a pedido do cliente, prevista no manual (seção 9), é `--apagar ID`.

## Interface e API

O agente tem três formas de uso, todas sobre o mesmo `Agent`:

| Interface | Comando | Para quê |
|---|---|---|
| Web | `python -m emporio.web` | Atendimento ao cliente, no navegador do computador ou do celular |
| API HTTP | mesma do item acima, em `/docs` | Integrar outro canal (ex.: WhatsApp) sem tocar no agente |
| Terminal | `python -m emporio.agent --trace` | Desenvolvimento e depuração |

**Web leve.** A página é um único arquivo HTML com CSS e JavaScript próprios, sem framework
nem etapa de build: o servidor Python é tudo o que precisa rodar. Ela mostra se a loja está
aberta agora, sugere perguntas iniciais, lembra a conversa ao recarregar a página e tem modo
claro e escuro. A identidade visual usa o verde do Pantanal e o amarelo do ipê, árvore-símbolo
do Centro-Oeste, com seis cordas de violão no cabeçalho, que também viram o indicador de
"digitando".

**Modo "Mostrar consultas".** Um interruptor exibe, abaixo de cada resposta, as ferramentas que
o agente chamou, com os argumentos e o tempo. Serve à equipe da loja e a quem avalia o projeto:
dá para ver que um preço veio de `detalhar_produto`, e não da imaginação do modelo.

**Cuidados.** As respostas do modelo passam por um renderizador de Markdown mínimo que escapa
todo HTML antes de aplicar negrito e listas, para que nada do que o modelo ou o cliente
escrever vire código na página. Mensagens têm limite de 1.000 caracteres. Duas mensagens
simultâneas na mesma conversa são serializadas por uma trava. Se a chave da Gemini API
faltar, o servidor sobe mesmo assim e a página explica o problema. O rodapé lembra o cliente
de não enviar CPF ou cartão e oferece "Apagar conversa", que remove a conversa dos registros
(manual, seção 9).

**Na rede local.** `python -m emporio.web --host 0.0.0.0` deixa a página acessível por outros
aparelhos da mesma rede, como um celular, pelo IP do computador na porta 8000.

## Estrutura

```
data/raw/          dados originais fornecidos pela loja (não são alterados)
data/processed/    artefatos gerados (ignorados pelo git)
src/emporio/       código do agente
tests/             testes automatizados
docs/              relatórios e suposições documentadas
```

Os arquivos em `data/raw/` foram apenas renomeados para nomes curtos
(ex.: `desafio_tecnico_ai_eng_-_products.csv` virou `products.csv`, e o PDF perdeu o
acento do nome para evitar problemas de codificação entre sistemas operacionais).
O conteúdo é idêntico ao original.

## Uso de assistentes de código

Este projeto é desenvolvido com apoio do Claude (Anthropic). O fluxo de trabalho e a
divisão de responsabilidades serão detalhados nesta seção ao final do projeto.
