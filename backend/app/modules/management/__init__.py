"""Módulo de Gestão Integrada - a camada de governança da matriz.

Dois blocos que se alimentam:

1. **Estrutura operacional** (`services.py`): reconcilia três fontes que discordam entre si sobre
   quem pertence à operação - a configuração da Operação Analítica
   (`OperationResponsibleAssignment`), o histórico de O.S. do IXC (`OperationOrder`) e o cadastro
   da Gamificação (`Collaborator`) - num cadastro único e validado, com supervisor e modelo de
   equipe vinculados. É o pré-requisito do bloco 2: sem saber de quem é a meta e quem responde por
   ela, não há a quem cobrar.

2. **Casos de gestão** (`cases.py`): a cobrança formal de um desvio. Nasce automaticamente do
   desvio de meta do mês fechado, ou manualmente pela matriz. Ciclo:
   `pending` → supervisor justifica → `justified`/`in_progress` → matriz revisa →
   `resolved`/`rejected`. Cada passo é auditado e o histórico da discussão fica em
   `ManagementCaseComment`.

Separação de papéis (aplicada no SERVIDOR, ver `cases.case_scope_conditions`): o supervisor
justifica e comenta apenas o que é dele; só a matriz (`management:review`) abre casos manualmente,
gera o lote do mês e encerra um caso.
"""

