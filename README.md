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
| 06 | Provedores de LLM (Gemini API e Ollama) | ⏳ |
| 07 | Agente: persona, loop de function calling e guardrails | ⏳ |
| 08 | Persistência do histórico de conversa | ⏳ |
| 09 | Interface web, API e CLI | ⏳ |
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
