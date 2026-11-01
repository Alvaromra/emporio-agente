# Uso de assistentes de código

## Ferramenta

Usei o **Claude** (Anthropic), pela interface do claude.ai, dentro de um Projeto com o
enunciado, os CSVs e o manual da loja. O Claude tinha um ambiente Linux onde rodava código,
testes e capturas de tela da interface antes de me entregar cada etapa. Esse ambiente não
tinha acesso à Gemini API nem ao Ollama, então todos os testes com o modelo real foram
feitos por mim, na minha máquina.

## Divisão de responsabilidades

| Eu | Claude |
|---|---|
| Defini as escolhas iniciais: RAG, família Gemma (Google), interface própria, Python | Analisou os dados e o manual antes de qualquer código e propôs ajustes às minhas escolhas |
| Aprovei cada etapa antes da implementação | Implementou cada etapa com testes e validou o patch sobre o estado anterior do repositório |
| Testei com o modelo real e apontei o que não estava bom | Corrigiu a partir da saída real que eu enviava |
| Revisei os diffs, rodei testes, fiz cada commit e push | Pesquisou fatos externos (versões do Gemma 4, termos da Gemini API) e redigiu a documentação |

## Fluxo de trabalho

1. **Análise antes do código.** O Claude analisou os CSVs e o manual e encontrou
   inconsistências deliberadas: descrições que falam de outro instrumento, produtos "em breve"
   com estoque, uma promoção inativa justamente no Takamine GD20 do enunciado, totais de pedido
   divergentes e contradições no próprio manual. A partir disso, propôs trocar o RAG puro por
   uma abordagem híbrida (ferramentas com SQL para os dados, RAG só para o manual). Aceitei
   porque TODO: escreva com suas palavras por que a proposta fez sentido.
2. **Dez etapas, dez commits.** O projeto foi planejado como uma sequência de commits, para
   que o histórico mostrasse a construção.
3. **Patches revisados.** A partir da etapa 03, cada etapa chegou como um patch. Eu aplicava
   com `git apply`, revisava o diff, rodava `pytest` e só então fazia o commit, com a minha
   autoria.
4. **Teste com o modelo real em cada etapa que envolve o LLM.** Rodei `python -m emporio.llm`
   e `python -m emporio.agent --trace` com o Gemma 4 e mandei a saída para análise.

## Onde intervim

- **Autoria dos commits.** As duas primeiras etapas vieram como repositório pronto, com autor
  provisório, e um comando de exemplo continha um e-mail fictício que acabei usando. Percebi no
  GitHub que um commit aparecia como de outro usuário. Apaguei o repositório, corrigi a autoria
  e mudamos o processo: a partir dali, eu aplicava os patches e fazia os commits.
- **Regra de push.** Questionei se enviar vários commits num mesmo push violava a regra de "não
  fazer force-push de tudo em um único commit". Confirmamos que não, desde que os commits
  continuem separados.
- **Teste real do agente (etapa 07).** Rodei o roteiro de conversas com o Gemma 4. O agente
  acertou os casos difíceis, mas a saída mostrou quatro problemas: ele dizia "Pode sim!" sobre
  a devolução antes de verificar o pedido, listava 8 opções sem dizer que existiam 12, citava
  números de seção do manual para o cliente, e as setas do teclado não funcionavam no terminal.
  Eles viraram um commit próprio de correção (`fix(agent)`), e testei de novo antes de
  commitar.
- **Primeira avaliação ponta a ponta (etapa 10).** Rodei os 15 cenários com o modelo real e
  dois falharam. Um era um erro real do agente: ao informar um preço promocional, ele omitia o
  preço original e o percentual, o que o manual (6.2) proíbe. O outro era a cota do tier
  gratuito (16 mil tokens de entrada por minuto), que o SDK não respeitava. As duas correções
  viraram um commit próprio, e a segunda execução passou nos 15 cenários.
- TODO: inclua decisões que você mudou ou questionou (ex.: o número de WhatsApp escolhido),
  ou apague esta linha.

## Como validei o que foi gerado

- Conferi o relatório de qualidade dos dados contra os CSVs originais.
- Rodei os testes a cada etapa (200 no final) e mantive o CI no GitHub Actions.
- Chamei as ferramentas manualmente (`python -m emporio.tools`) para ver exatamente o que o
  agente recebe.
- Testei o agente com o modelo real no terminal e na interface web.
- Rodei a avaliação ponta a ponta (`python -m emporio.evals`) e gerei as conversas de exemplo
  com o modelo real, sem edição.

TODO: acrescente o que você revisou com mais atenção no código.

## Avaliação

TODO: o que funcionou bem, onde a IA errou ou exigiu correção, e o que você faria diferente.
