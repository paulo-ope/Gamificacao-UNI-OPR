"""Recalcula o TMA ativo e o TMR agrupado (regra do OPA) de um período, sem esperar o backfill noturno.

O backfill das madrugadas processa os atendimentos mais recentes primeiro, com teto diário. Este comando fecha
um período específico na hora (1 chamada ao OPA por atendimento, ~0,1 s cada). Roda com o MESMO lock da
importação normal, então nunca escreve na mesma linha que uma sincronização em andamento.

Uso (na pasta do projeto, com o backend no ar):

    docker compose exec backend python -m app.modules.support.recompute_active_metrics \
        --date-from 2026-10-01 --date-to 2026-10-14 --limit 12000

Pode ser interrompido e rodado de novo: só pega quem ainda não foi calculado.
"""

from __future__ import annotations

import argparse
from datetime import date

from app.db.session import SessionLocal
from app.services.opa_client import get_opa_client

from .opa_ingestion import _support_opa_import_lock, pending_active_metrics_count, run_active_metrics_recompute


def main() -> None:
    parser = argparse.ArgumentParser(description="Recalcula o TMA ativo e o TMR agrupado de um periodo.")
    parser.add_argument("--date-from", type=date.fromisoformat, required=True)
    parser.add_argument("--date-to", type=date.fromisoformat, required=True)
    parser.add_argument("--limit", type=int, default=5000, help="maximo de atendimentos nesta rodada (padrao 5000)")
    parser.add_argument("--delay", type=float, default=0.05, help="pausa entre chamadas ao OPA, em segundos")
    args = parser.parse_args()

    with SessionLocal() as db:
        print(f"pendentes (todos os periodos) antes: {pending_active_metrics_count(db)}", flush=True)
        with _support_opa_import_lock(db):
            result = run_active_metrics_recompute(
                db,
                get_opa_client(),
                date_from=args.date_from,
                date_to=args.date_to,
                limit=args.limit,
                delay_seconds=args.delay,
            )
        print(f"resultado: {result}", flush=True)
        print(f"pendentes (todos os periodos) depois: {pending_active_metrics_count(db)}", flush=True)


if __name__ == "__main__":
    main()
