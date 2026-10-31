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
| 03 | Regras de negócio determinísticas | ⏳ |
| 04 | Ferramentas de catálogo e pedidos | ⏳ |
| 05 | RAG sobre o manual de políticas | ⏳ |
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
