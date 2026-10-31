"""ETL: dos CSVs da loja para um SQLite limpo, validado e pronto para o agente.

Duas categorias de problema são tratadas de forma diferente:

- Violação de contrato (coluna ausente, número ilegível, chave estrangeira
  quebrada): o ETL para com uma mensagem clara. Carregar dados assim esconderia
  bugs.
- Inconsistência de negócio (descrição que contradiz as specs, total de pedido
  divergente, produto "em breve" com estoque): o dado é carregado com uma
  decisão explícita de tratamento e o achado vai para o relatório de qualidade.
"""

from emporio.etl.pipeline import PipelineResult, run_pipeline

__all__ = ["PipelineResult", "run_pipeline"]
