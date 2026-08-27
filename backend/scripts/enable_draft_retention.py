"""Liga a poda de rascunhos superados da Gamificacao (achado A1 da auditoria financeira
2026-08-26, retomado na auditoria de performance 2026-08-27).

Idempotente - roda de novo sem problema. So grava as duas AppSettings; a exclusao em si so
acontece na proxima vez que `recalculate_current_period` rodar (ciclo do sincronizador do IXC,
a cada ~20 min) e chamar `prune_superseded_drafts`, nunca na execucao deste script.

Uso: python scripts/enable_draft_retention.py [--keep N]
"""
from __future__ import annotations

import argparse

from app.db.session import SessionLocal
from app.services.calculation import (
    DRAFT_RETENTION_ENABLED_SETTING,
    DRAFT_RETENTION_KEEP_SETTING,
    upsert_setting,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep", type=int, default=3, help="rascunhos mais recentes mantidos por periodo (padrao 3)")
    args = parser.parse_args()

    with SessionLocal() as db:
        upsert_setting(
            db,
            DRAFT_RETENTION_ENABLED_SETTING,
            "true",
            description="Liga a poda automatica de rascunhos superados de fechamento (achado A1 da auditoria 2026-08-26).",
        )
        upsert_setting(
            db,
            DRAFT_RETENTION_KEEP_SETTING,
            str(args.keep),
            description="Quantos rascunhos mais recentes por periodo a poda automatica mantem.",
        )
        db.commit()
    print(f"gamification_draft_retention_enabled=true, gamification_draft_retention_keep={args.keep}")


if __name__ == "__main__":
    main()
