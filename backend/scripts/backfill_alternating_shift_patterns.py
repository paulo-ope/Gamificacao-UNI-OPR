"""Aplica retroativamente a escala 12x36 (dia sim, dia não) aos colaboradores de modelo de equipe
elegível (ver `ALTERNATING_SHIFT_ELIGIBLE_TEAM_MODEL_NAMES`) que ainda não têm nenhuma escala
configurada - achado real 2026-08-24: `refresh_operational_members` só aplica o padrão default no
momento em que o `team_model_id` é atribuído pela primeira vez; quem já tinha o modelo configurado
antes dessa lógica existir nunca recebeu o default, e sem uma `shift_anchor_date` o sistema trata
todo dia como dia de trabalho - o dia de folga da escala aparece como "produção zero abaixo da
meta", pedindo justificativa todo santo dia.

Usa a MESMA função de sugestão já usada pela tela ("sistema sugere, supervisor confirma" -
`cases.suggest_shift_pattern`), só que tentando algumas datas de referência um pouco mais antigas
quando a mais recente cai num hiato curto (ex.: atraso de sincronização do IXC) que travaria a
sugestão sem necessidade - ver `BACKOFF_DAYS` abaixo. Quem continuar inconclusivo mesmo assim fica
de fora, sem nenhuma alteração (pode ser afastamento real, precisa de revisão humana).

Uso (dentro do container do backend - roda como módulo, com "-m", pra "/app" entrar no
sys.path e "import app.main" funcionar; rodar o arquivo direto com "python scripts/arquivo.py"
NÃO funciona, dá ModuleNotFoundError):

    # 1. Sempre rode em modo dry-run primeiro e leia a lista antes de aplicar:
    docker exec opr-gamification-backend python -m scripts.backfill_alternating_shift_patterns

    # 2. Só quando estiver de acordo com o que seria aplicado:
    docker exec opr-gamification-backend python -m scripts.backfill_alternating_shift_patterns --apply

Recomendado: faça um backup do banco antes de rodar com --apply (`pg_dump`) - é uma escrita real em
produção, ainda que reversível (dá pra zerar os 4 campos de escala e os casos resolvidos manualmente
depois, se precisar desfazer)."""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta

import app.main  # noqa: F401 - registra todos os mappers antes de qualquer query
from app.db.session import SessionLocal
from app.modules.management import cases as cases_engine
from app.modules.management.models import ALTERNATING_SHIFT_ELIGIBLE_TEAM_MODEL_NAMES, ManagementOperationalMember
from app.modules.operations.models import OperationTeamModel
from sqlalchemy import select

# Quantos dias pra tras da data real de hoje tentar, na ordem, ate achar uma janela sem o hiato
# recente que trava a sugestao (ver docstring do modulo). 0 = tenta primeiro com "hoje" mesmo.
BACKOFF_DAYS = [0, 3, 5, 7, 10, 14]


def find_eligible_members_without_schedule(db) -> list[ManagementOperationalMember]:
    eligible_ids = [
        model.id
        for model in db.scalars(
            select(OperationTeamModel).where(OperationTeamModel.name.in_(ALTERNATING_SHIFT_ELIGIBLE_TEAM_MODEL_NAMES))
        ).all()
    ]
    return db.scalars(
        select(ManagementOperationalMember).where(
            ManagementOperationalMember.team_model_id.in_(eligible_ids),
            ManagementOperationalMember.is_active.is_(True),
            ManagementOperationalMember.shift_pattern.is_(None),
        )
    ).all()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Grava as mudanças e recalcula os casos pendentes. Sem essa flag, só mostra o que seria feito.",
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        members = find_eligible_members_without_schedule(db)
        print(f"{len(members)} colaborador(es) elegível(is) sem escala configurada.\n")

        today = date.today()
        resolved: list[tuple[ManagementOperationalMember, object]] = []
        stuck: list[str] = []
        for member in members:
            suggestion = None
            for back in BACKOFF_DAYS:
                candidate = cases_engine.suggest_shift_pattern(db, member, today=today - timedelta(days=back))
                if candidate.suggested_pattern == "alternating":
                    suggestion = candidate
                    break
            if suggestion:
                resolved.append((member, suggestion))
                print(
                    f"  [OK] {member.responsible_name:35s} {member.regional:30s} "
                    f"conf={suggestion.confidence:.0%} ancora={suggestion.suggested_anchor_date}"
                )
            else:
                stuck.append(member.responsible_name)
                print(f"  [--] {member.responsible_name:35s} {member.regional:30s} inconclusivo, mantido como esta")

        print(f"\n{len(resolved)} seriam configurados, {len(stuck)} continuam inconclusivos (revisão manual).")

        if not args.apply:
            print("\nModo dry-run (nada foi gravado). Rode de novo com --apply para aplicar.")
            return 0

        for member, suggestion in resolved:
            member.shift_pattern = "alternating"
            member.shift_cycle_days_on = suggestion.suggested_cycle_days_on
            member.shift_cycle_days_off = suggestion.suggested_cycle_days_off
            member.shift_anchor_date = suggestion.suggested_anchor_date
        db.commit()
        print(f"\n{len(resolved)} colaborador(es) atualizados.")

        refresh_result = cases_engine.refresh_pending_cases(db)
        db.commit()
        print(
            "Recalculo de casos pendentes: "
            f"{refresh_result['daily_refreshed']} diário(s) recalculado(s), "
            f"{refresh_result['daily_resolved']} resolvido(s) automaticamente "
            f"(agora reconhecidos como dia de folga)."
        )
        return 0


if __name__ == "__main__":
    sys.exit(main())
