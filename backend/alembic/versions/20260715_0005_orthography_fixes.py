"""accent fixes for seeded names/descriptions

seed.py only creates these rows if they don't already exist (matched by name), so simply
fixing the spelling in seed.py has no effect on databases that were already seeded - the old
unaccented rows just keep existing forever, and rerunning the (now-accented) seed would create
duplicate rows instead of fixing the old ones. This migration renames the already-seeded rows
in place so existing environments pick up the corrected spelling without duplicating anything.

Revision ID: 20260715_0005
Revises: 20260710_0004
Create Date: 2026-07-15 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20260715_0005"
down_revision = "20260710_0004"
branch_labels = None
depends_on = None

SCORING_GROUP_RENAMES = [
    ("Manutencao", "Manutenção", "Precificacao padrao para manutencoes operacionais.", "Precificação padrão para manutenções operacionais."),
    (
        "Ativacao / Mudanca de Endereco / Retorno",
        "Ativação / Mudança de Endereço / Retorno",
        "Precificacao padrao para ativacao, mudanca de endereco e retorno.",
        "Precificação padrão para ativação, mudança de endereço e retorno.",
    ),
    ("Mudanca de Tecnologia", "Mudança de Tecnologia", "Precificacao padrao para mudancas de tecnologia.", "Precificação padrão para mudanças de tecnologia."),
    ("Recolhimento", "Recolhimento", "Precificacao padrao para recolhimentos.", "Precificação padrão para recolhimentos."),
]

RECURRENCE_RULE_RENAMES = [
    (
        "Reincidencia de Manutencao",
        "Reincidência de Manutenção",
        "Manutencao",
        "Manutenção",
        "Regra padrao: nova manutencao do mesmo vinculo dentro da janela caracteriza reincidencia.",
        "Regra padrão: nova manutenção do mesmo vínculo dentro da janela caracteriza reincidência.",
    ),
    (
        "Reincidencia de Ativacao",
        "Reincidência de Ativação",
        "Ativacao",
        "Ativação",
        "Regra padrao: manutencao apos ativacao dentro da janela caracteriza retorno operacional.",
        "Regra padrão: manutenção após ativação dentro da janela caracteriza retorno operacional.",
    ),
    (
        "Alteracao de Endereco nao reincide",
        "Alteração de Endereço não reincide",
        "Mud. de Endereco",
        "Mud. de Endereço",
        "Regra padrao: alteracao de endereco recorrente e tratada como demanda diferente.",
        "Regra padrão: alteração de endereço recorrente é tratada como demanda diferente.",
    ),
    (
        "Mudanca de Tecnologia nao reincide",
        "Mudança de Tecnologia não reincide",
        "Mud. de Tecnologia",
        "Mud. de Tecnologia",
        "Regra padrao: mudanca de tecnologia recorrente e tratada como demanda diferente.",
        "Regra padrão: mudança de tecnologia recorrente é tratada como demanda diferente.",
    ),
]

HEALTH_RULE_RENAMES = [
    ("Atencao", "Atenção"),
    ("Critica", "Crítica"),
]

DIAGNOSIS_RULE_DESCRIPTION_RENAMES = [
    ("Resolvido", "Diagnostico conclusivo sem penalidade.", "Diagnóstico conclusivo sem penalidade."),
]

APP_SETTING_DESCRIPTION_RENAMES = [
    ("point_value", "Valor monetario pago por ponto final.", "Valor monetário pago por ponto final."),
    ("recurrence_window_days", "Janela em dias para reconhecer reincidencia operacional.", "Janela em dias para reconhecer reincidência operacional."),
    ("recurrence_identity_fields", "Campos usados para vincular O.S do mesmo cliente na reincidencia.", "Campos usados para vincular O.S do mesmo cliente na reincidência."),
    ("warranty_scores", "Define se garantia resolvida tambem gera pontuacao.", "Define se garantia resolvida também gera pontuação."),
    ("warranty_reduction_percentage", "Percentual de reducao quando garantia pontua com reducao.", "Percentual de redução quando garantia pontua com redução."),
    ("recurrence_action", "Regra de reincidencia: annul_original, subtract_original, no_penalty ou requires_review.", "Regra de reincidência: annul_original, subtract_original, no_penalty ou requires_review."),
    ("recurrence_penalty_points", "Desconto fixo quando reincidencia usa subtract_original.", "Desconto fixo quando reincidência usa subtract_original."),
    ("deleted_default_scoring_groups", "Grupos padrao removidos manualmente para o seed automatico nao recriar.", "Grupos padrão removidos manualmente para o seed automático não recriar."),
]


def _table_names() -> set[str]:
    return set(inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    tables = _table_names()

    if "scoring_groups" in tables:
        for old_name, new_name, old_desc, new_desc in SCORING_GROUP_RENAMES:
            if old_name != new_name:
                bind.execute(
                    sa.text("UPDATE scoring_groups SET name = :new_name WHERE name = :old_name"),
                    {"new_name": new_name, "old_name": old_name},
                )
            bind.execute(
                sa.text("UPDATE scoring_groups SET description = :new_desc WHERE description = :old_desc"),
                {"new_desc": new_desc, "old_desc": old_desc},
            )

    if "recurrence_classification_rules" in tables:
        for old_name, new_name, old_type, new_type, old_desc, new_desc in RECURRENCE_RULE_RENAMES:
            bind.execute(
                sa.text("UPDATE recurrence_classification_rules SET name = :new_name WHERE name = :old_name"),
                {"new_name": new_name, "old_name": old_name},
            )
            bind.execute(
                sa.text(
                    "UPDATE recurrence_classification_rules SET original_os_type_pattern = :new_type "
                    "WHERE original_os_type_pattern = :old_type"
                ),
                {"new_type": new_type, "old_type": old_type},
            )
            bind.execute(
                sa.text(
                    "UPDATE recurrence_classification_rules SET return_os_type_pattern = :new_type "
                    "WHERE return_os_type_pattern = :old_type"
                ),
                {"new_type": new_type, "old_type": old_type},
            )
            bind.execute(
                sa.text("UPDATE recurrence_classification_rules SET description = :new_desc WHERE description = :old_desc"),
                {"new_desc": new_desc, "old_desc": old_desc},
            )

    if "health_rules" in tables:
        for old_name, new_name in HEALTH_RULE_RENAMES:
            bind.execute(
                sa.text("UPDATE health_rules SET name = :new_name WHERE name = :old_name"),
                {"new_name": new_name, "old_name": old_name},
            )

    if "diagnosis_penalty_rules" in tables:
        for diagnosis_name, old_desc, new_desc in DIAGNOSIS_RULE_DESCRIPTION_RENAMES:
            bind.execute(
                sa.text(
                    "UPDATE diagnosis_penalty_rules SET description = :new_desc "
                    "WHERE diagnosis_name = :diagnosis_name AND description = :old_desc"
                ),
                {"new_desc": new_desc, "diagnosis_name": diagnosis_name, "old_desc": old_desc},
            )

    if "app_settings" in tables:
        for key, old_desc, new_desc in APP_SETTING_DESCRIPTION_RENAMES:
            bind.execute(
                sa.text("UPDATE app_settings SET description = :new_desc WHERE key = :key AND description = :old_desc"),
                {"new_desc": new_desc, "key": key, "old_desc": old_desc},
            )


def downgrade() -> None:
    # Cosmetic text fix only - not worth reversing.
    pass
