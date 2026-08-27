"""indices das consultas financeiras da Gamificacao (auditoria 2026-08-26, achado A3)

Revision ID: 20260826_0077
Revises: 20260826_0076
Create Date: 2026-08-26 00:00:00

Todas as consultas de periodo do modulo filtram por `service_orders.closed_at`/`opened_at`, e
nenhuma das duas tinha indice. Medido na base real (75.177 O.S.):

    Seq Scan on service_orders (cost=0.00..4174.76 rows=1) (actual rows=6989)
      Rows Removed by Filter: 68188

Alem da varredura completa, o planejador estimava 1 linha onde havia 6.989 - erro de 7.000x que
envenena o plano de qualquer join sobre essa relacao.

`collaborator_scores` (225.121 linhas) tambem nao tinha indice em `calculation_run_id` nem em
`collaborator_id`, e e carregada por `selectinload` em praticamente toda tela do modulo.
`point_balance_entries` era varrida inteira a cada par candidato em `_existing_entry` e
`_original_already_debited`.

Migration puramente ADITIVA: so cria indices, nao altera nenhuma coluna, nenhum dado e nenhuma
regra de negocio. Usa CONCURRENTLY no PostgreSQL (fora de transacao) para nao travar as tabelas
durante a criacao - `service_orders` e `collaborator_scores` estao em uso continuo pela
sincronizacao do IXC.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260826_0077"
down_revision = "20260826_0076"
branch_labels = None
depends_on = None


INDEXES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    # Consultas de periodo: scoring_detail.period_orders, period_orders_for_aggregation,
    # recurrence_penalties, point_balance.detect_post_payment_warranty_debits e dashboard.
    ("ix_service_orders_closed_at", "service_orders", ("closed_at",)),
    ("ix_service_orders_opened_at", "service_orders", ("opened_at",)),
    # leadership_bonus.pending_unregistered_for_run e todo filtro por colaborador.
    ("ix_service_orders_collaborator_id", "service_orders", ("collaborator_id",)),
    # selectinload(CalculationRun.scores) e ensure_no_overlapping_paid_period.
    ("ix_collaborator_scores_calculation_run_id", "collaborator_scores", ("calculation_run_id",)),
    ("ix_collaborator_scores_collaborator_id", "collaborator_scores", ("collaborator_id",)),
    # find_paid_run_for_period / find_run_for_period / _load_saved_run.
    (
        "ix_calculation_runs_period_status",
        "calculation_runs",
        ("reference_year", "reference_month", "status"),
    ),
    # Guardas de duplicidade do ledger de saldo.
    ("ix_point_balance_entries_original_service_order_id", "point_balance_entries", ("original_service_order_id",)),
    ("ix_point_balance_entries_original_os_code", "point_balance_entries", ("original_os_code",)),
    ("ix_point_balance_entries_related_os_code", "point_balance_entries", ("related_os_code",)),
    # Filtro por data na trilha de auditoria.
    ("ix_audit_logs_created_at", "audit_logs", ("created_at",)),
)


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if _is_postgres():
        # CONCURRENTLY nao pode rodar dentro de transacao - `autocommit_block` sai dela.
        with op.get_context().autocommit_block():
            for name, table, columns in INDEXES:
                op.execute(
                    sa.text(
                        f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} "
                        f"ON {table} ({', '.join(columns)})"
                    )
                )
        return

    for name, table, columns in INDEXES:
        op.create_index(name, table, list(columns), unique=False)


def downgrade() -> None:
    if _is_postgres():
        with op.get_context().autocommit_block():
            for name, _table, _columns in reversed(INDEXES):
                op.execute(sa.text(f"DROP INDEX CONCURRENTLY IF EXISTS {name}"))
        return

    for name, table, _columns in reversed(INDEXES):
        op.drop_index(name, table_name=table)
