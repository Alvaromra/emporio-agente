"""Regras de negócio determinísticas, derivadas do manual de políticas.

Princípio do projeto: o LLM conversa e decide qual ferramenta usar; o código calcula.
Prazos, parcelas, descontos e horários saem daqui, testados, e nunca da "intuição"
do modelo. Cada constante cita a seção do manual de onde veio.
"""

POLICY_VERSION = "Manual de Políticas e Procedimentos v2.1 (junho de 2025)"
