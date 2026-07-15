"""accent fixes for scoring groups and a recurrence rule that diverged from seed.py defaults

The previous migration (20260715_0005) only matched rows still holding the exact generic
seed.py wording. In practice this project's scoring groups were long ago renamed to more
specific names through the admin UI (e.g. "Manutencao Urbana Simples", "(Urbano)"/"(Rural)"
variants), and one recurrence rule was custom-configured differently from the seed default.
Those rows never matched the previous migration's WHERE clauses, so their accents were never
fixed. This migration targets the actual current wording directly.

Revision ID: 20260715_0006
Revises: 20260715_0005
Create Date: 2026-07-15 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20260715_0006"
down_revision = "20260715_0005"
branch_labels = None
depends_on = None

# (old name, new name, old description, new description)
SCORING_GROUP_RENAMES = [
    (
        "Manutencao Urbana Simples",
        "Manutenção Urbana Simples",
        "(Simples) Precificacao para manutencoes simples.",
        "(Simples) Precificação para manutenções simples.",
    ),
    (
        "Ativacao / Mudanca de Endereco / Retorno (Urbano)",
        "Ativação / Mudança de Endereço / Retorno (Urbano)",
        "(Urbano) Precificacao padrao para ativacao, mudanca de endereco e retorno.",
        "(Urbano) Precificação padrão para ativação, mudança de endereço e retorno.",
    ),
    (
        "Ativacao / Mudanca de Endereco / Retorno (RURAL)",
        "Ativação / Mudança de Endereço / Retorno (RURAL)",
        "(Rural) Precificacao padrao para ativacao, mudanca de endereco e retorno.",
        "(Rural) Precificação padrão para ativação, mudança de endereço e retorno.",
    ),
    (
        # also fixes "Urbano" -> "Urbana" to agree with "Manutenção" (feminine), matching the
        # sibling group "Manutenção Urbana Simples" above - not just an accent gap.
        "Manutencao Urbano Complexa",
        "Manutenção Urbana Complexa",
        None,
        None,
    ),
    (
        "Manutencao Rural",
        "Manutenção Rural",
        None,
        None,
    ),
]

# (old name, new name) - title-case + accent, to match sibling rows "Reincidência de X"
RECURRENCE_RULE_RENAMES = [
    ("Reincidencia de Alteração de endereço", "Reincidência de Alteração de Endereço"),
]


def _table_names() -> set[str]:
    return set(inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    tables = _table_names()

    if "scoring_groups" in tables:
        for old_name, new_name, old_desc, new_desc in SCORING_GROUP_RENAMES:
            bind.execute(
                sa.text("UPDATE scoring_groups SET name = :new_name WHERE name = :old_name"),
                {"new_name": new_name, "old_name": old_name},
            )
            if old_desc is not None:
                bind.execute(
                    sa.text("UPDATE scoring_groups SET description = :new_desc WHERE description = :old_desc"),
                    {"new_desc": new_desc, "old_desc": old_desc},
                )

    if "recurrence_classification_rules" in tables:
        for old_name, new_name in RECURRENCE_RULE_RENAMES:
            bind.execute(
                sa.text("UPDATE recurrence_classification_rules SET name = :new_name WHERE name = :old_name"),
                {"new_name": new_name, "old_name": old_name},
            )


def downgrade() -> None:
    # Cosmetic text fix only - not worth reversing.
    pass
