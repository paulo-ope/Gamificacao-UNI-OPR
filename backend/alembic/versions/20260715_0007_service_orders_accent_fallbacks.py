"""accent fixes for service_orders fallback/default values (diagnosis, customer_name, status)

The import pipeline and the ORM/schema defaults used to fall back to unaccented placeholder
text ("Nao informado", "Concluida") whenever a spreadsheet row was missing that field. The
source now writes the accented versions, but existing rows already carry the old text forever
unless rewritten here. Both spellings normalize identically wherever these fields are compared
(scoring_detail.normalize() strips accents), so this is purely a display fix - safe for
whatever regional/scoring logic reads these columns.

Revision ID: 20260715_0007
Revises: 20260715_0006
Create Date: 2026-07-15 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20260715_0007"
down_revision = "20260715_0006"
branch_labels = None
depends_on = None


def _table_names() -> set[str]:
    return set(inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    if "service_orders" not in _table_names():
        return

    bind.execute(sa.text("UPDATE service_orders SET diagnosis = 'Não informado' WHERE diagnosis = 'Nao informado'"))
    bind.execute(sa.text("UPDATE service_orders SET customer_name = 'Não informado' WHERE customer_name = 'Nao informado'"))
    bind.execute(sa.text("UPDATE service_orders SET status = 'Concluída' WHERE status = 'Concluida'"))


def downgrade() -> None:
    # Cosmetic text fix only - not worth reversing.
    pass
