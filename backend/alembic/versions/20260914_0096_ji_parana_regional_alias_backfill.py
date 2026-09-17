"""normaliza grafia de UNI - JI-PARANA para UNI - JI PARANA (mesma regional)

Revision ID: 20260914_0096
Revises: 20260912_0095
Create Date: 2026-09-14 00:00:00

Backfill de dado, não de schema. Achado da auditoria de frontend de 2026-09-14: 36 registros
gravados com a grafia "UNI - JI-PARANA" (hífen) em `operations_responsible_assignments`
(atribuição manual de responsável/regional), propagados para `management_operational_members` via
`refresh_operational_members()` - mesma filial real do IXC (id_filial 6, ver REGIONAL_CODE_MAP em
app/services/regional.py), nunca normalizada porque chegava como texto livre, não como código
numérico. `normalize_regional()` já ganhou um alias explícito (`REGIONAL_NAME_ALIASES`) para a
divergência não voltar a acontecer em dado novo - esta migration só corrige o que já estava
gravado.

- `operations_responsible_assignments`: UPDATE direto. Nenhum (responsible_name, regional) já
  existe com a grafia canônica para os mesmos 36 nomes (checado manualmente antes desta migration),
  então o UPDATE não colide com `uq_operations_responsible_assignment_identity`.
- `management_operational_members`: 24 dos 36 nomes já tinham uma linha própria com a grafia
  canônica (criada antes por uma rodada de `refresh_operational_members` a partir do histórico de
  O.S., que já normalizava - só a atribuição manual estava com hífen). Um UPDATE direto colidiria
  com `uq_management_member_name_regional`, então para esses 24 a linha com hífen é MESCLADA na
  linha canônica (preenche só os campos que a canônica ainda não tinha) e depois removida - as duas
  linhas são o mesmo par responsável/regional duplicado pela grafia, não pessoas diferentes; nenhum
  outro registro do banco referencia `management_operational_members.id` por FK (checado), então a
  remoção da linha duplicada é segura. Os 12 nomes restantes (sem linha canônica pré-existente)
  recebem UPDATE direto, como no primeiro caso.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260914_0096"
down_revision = "20260912_0095"
branch_labels = None
depends_on = None

OLD_REGIONAL = "UNI - JI-PARANA"
NEW_REGIONAL = "UNI - JI PARANA"

MERGEABLE_FIELDS = ("collaborator_id", "ixc_employee_id", "supervisor_user_id", "team_model_id")


def upgrade() -> None:
    bind = op.get_bind()

    bind.execute(
        sa.text("UPDATE operations_responsible_assignments SET regional = :new WHERE regional = :old"),
        {"new": NEW_REGIONAL, "old": OLD_REGIONAL},
    )

    members = sa.table(
        "management_operational_members",
        sa.column("id", sa.Integer),
        sa.column("responsible_name", sa.String),
        sa.column("regional", sa.String),
        sa.column("collaborator_id", sa.Integer),
        sa.column("ixc_employee_id", sa.Integer),
        sa.column("supervisor_user_id", sa.Integer),
        sa.column("team_model_id", sa.Integer),
        sa.column("last_order_at", sa.DateTime(timezone=True)),
    )

    old_rows = bind.execute(sa.select(members).where(members.c.regional == OLD_REGIONAL)).mappings().all()

    for old_row in old_rows:
        canonical = (
            bind.execute(
                sa.select(members).where(
                    members.c.responsible_name == old_row["responsible_name"],
                    members.c.regional == NEW_REGIONAL,
                )
            )
            .mappings()
            .first()
        )

        if canonical is None:
            # Sem duplicata para este nome - so corrige a grafia da propria linha.
            bind.execute(sa.update(members).where(members.c.id == old_row["id"]).values(regional=NEW_REGIONAL))
            continue

        # Duplicata real (mesmo responsavel, mesma regional, grafia diferente): preenche na linha
        # canonica so os campos que ela ainda nao tinha, sem sobrescrever nada ja preenchido.
        merged_values = {
            field: old_row[field]
            for field in MERGEABLE_FIELDS
            if canonical[field] is None and old_row[field] is not None
        }
        if old_row["last_order_at"] is not None and (
            canonical["last_order_at"] is None or old_row["last_order_at"] > canonical["last_order_at"]
        ):
            merged_values["last_order_at"] = old_row["last_order_at"]

        if merged_values:
            bind.execute(sa.update(members).where(members.c.id == canonical["id"]).values(**merged_values))

        bind.execute(sa.delete(members).where(members.c.id == old_row["id"]))


def downgrade() -> None:
    # Backfill de dado, nao muda schema - a mesclagem de duplicatas nao tem volta deterministica
    # (as linhas com hifen removidas nao podem ser reconstruidas), entao nao ha downgrade de dado.
    pass
