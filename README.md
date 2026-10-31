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
| 02 | ETL: limpeza, carga em SQLite e relatório de qualidade | ⏳ |
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

# Testes
pytest
```

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
