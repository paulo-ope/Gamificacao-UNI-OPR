"""Recupera O.S. fechadas que estao em `operations_orders` mas nunca entraram em `service_orders`.

Por que existe: a projeção periodica so seleciona O.S. cuja atualizacao no IXC seja posterior a marca
d'agua. Uma O.S. que chega em `operations_orders` depois de a marca d'agua ja ter passado da data dela
nunca e selecionada, e fica de fora da pontuacao e da auditoria (outubro/2026: 113 O.S.). O ciclo
automatico agora reconcilia os ultimos dias sozinho; este comando cobre periodos mais antigos.

Por padrao e SIMULACAO (somente leitura, nada e gravado). `--apply` cria as O.S. faltantes, com as
mesmas travas do sync: periodo pago bloqueia, colaborador inativo/inexistente nao e criado.

Uso (dentro do container do backend, como modulo; datas no fuso America/Porto_Velho, `--to` inclusive):

    python -m scripts.reconcile_missing_service_orders --from 2026-10-01 --to 2026-10-31
    python -m scripts.reconcile_missing_service_orders --from 2026-10-01 --to 2026-10-31 --apply
    python -m scripts.reconcile_missing_service_orders --from 2026-10-01 --to 2026-10-31 --apply --recalculate

`--recalculate` recalcula a apuracao do periodo corrente depois de criar; sem ele o proximo
recalculo automatico (ou manual) incorpora as O.S. novas.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, time, timedelta

import app.main  # noqa: F401 - registra todos os mappers antes de qualquer query

from app.db.session import SessionLocal
from app.modules.operations.period import OPERATIONS_TIMEZONE
from app.services.calculation import recalculate_current_period
from app.services.operations_sync import reconcile_missing_service_orders_from_operations


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"data invalida (use AAAA-MM-DD): {value}") from exc


def _local_start(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=OPERATIONS_TIMEZONE)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--from", dest="date_from", type=_parse_date, required=True, help="primeiro dia (AAAA-MM-DD)")
    parser.add_argument("--to", dest="date_to", type=_parse_date, required=True, help="ultimo dia, inclusive (AAAA-MM-DD)")
    parser.add_argument("--apply", action="store_true", help="cria as O.S. faltantes (padrao: simulacao)")
    parser.add_argument("--recalculate", action="store_true", help="com --apply, recalcula o periodo corrente ao final")
    parser.add_argument("--batch-size", type=int, default=25)
    args = parser.parse_args(argv)

    if args.date_to < args.date_from:
        parser.error("--to nao pode ser anterior a --from")
    if args.recalculate and not args.apply:
        parser.error("--recalculate so faz sentido com --apply")

    with SessionLocal() as db:
        result = reconcile_missing_service_orders_from_operations(
            db,
            date_from=_local_start(args.date_from),
            date_to=_local_start(args.date_to + timedelta(days=1)),
            dry_run=not args.apply,
            batch_size=args.batch_size,
            imported_by=None,
            only_missing=True,
        )
        if not args.apply:
            db.rollback()

        print("Modo:", "APLICADO" if args.apply else "SIMULACAO (nada foi gravado)")
        for key in (
            "analyzed_count",
            "ready_to_create",
            "created_count",
            "blocked_paid_period",
            "invalid_collaborator",
            "error_count",
        ):
            print(f"{key}: {result[key]}")
        codes = result["created_os_codes"] if args.apply else result["ready_os_codes"]
        print("O.S.:", ", ".join(codes) if codes else "(nenhuma)")
        for error in result["errors"][:20]:
            print("erro:", error)

        if args.apply and args.recalculate and result["created_count"]:
            recalculate_current_period(db, execution_note="Recálculo após reconciliação manual de O.S. faltantes.")
            print("Apuração do período corrente recalculada.")
    return 1 if result["error_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
