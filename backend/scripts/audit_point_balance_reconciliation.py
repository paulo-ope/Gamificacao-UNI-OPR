"""Relatorio de conciliacao do saldo de pontos (Etapa 0 da auditoria financeira 2026-08-26).

SOMENTE LEITURA - nao cria, nao altera e nao apaga nenhum registro. Nenhum `commit` acontece
aqui, e a sessao e aberta so pra consultar.

Por que existe (ver docs/auditoria-gamificacao-financeira-2026-08-26.md, achado C4): existem hoje
1.377 lancamentos `manual_adjustment` com `created_by = NULL`, criados por scripts fora da API,
que compensam debitos de garantia cobrados no fechamento errado. O saldo liquido pendente e
POSITIVO e sera somado automaticamente ao proximo fechamento marcado como pago
(`apply_pending_entries_for_paid_run`). Antes de pagar qualquer coisa, um humano precisa conferir
credito a credito se ele tem contrapartida real.

O que o relatorio responde, por lancamento pendente:

  COMPENSADO           credito casa com um debito ja aplicado E existe um re-lancamento vivo do
                       mesmo par de O.S -> a cobranca so mudou de mes, o efeito liquido fecha.
  SEM_CONTRAPARTIDA    credito casa com um debito ja aplicado, mas NAO existe re-lancamento vivo
                       -> a pessoa recebe o credito e nunca mais e cobrada por essa garantia.
  DEBITO_ESTORNADO     o debito referenciado foi estornado E ainda assim o credito foi criado
                       -> devolucao em dobro do mesmo evento.
  DEBITO_NAO_APLICADO  o debito referenciado ainda esta pendente (nunca foi cobrado) e ja existe
                       credito compensando -> credito sem cobranca correspondente.
  DEBITO_NAO_ENCONTRADO / SEM_REFERENCIA   nao da pra rastrear a origem do credito.

Uso (dentro do container do backend, como modulo):

    docker exec opr-gamification-backend python -m scripts.audit_point_balance_reconciliation

Saidas em CSV no stdout, em tres blocos separados por uma linha `## <nome>`:
`lancamentos`, `por_colaborador` e `divergencia_por_fechamento`. Redirecione pra arquivo:

    docker exec opr-gamification-backend python -m scripts.audit_point_balance_reconciliation \
        > conciliacao-saldo.csv
"""
from __future__ import annotations

import csv
import re
import sys
from collections import defaultdict
from decimal import Decimal

import app.main  # noqa: F401 - registra todos os mappers antes de qualquer query
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import CalculationRun, Collaborator, CollaboratorScore, PointBalanceEntry
from app.services.calculation import get_point_value

# "credito para compensar o debito #733 (garantia O.S IXC-... / original IXC-...)"
REFERENCED_DEBIT_RE = re.compile(r"d[eé]bito\s*#(\d+)", re.IGNORECASE)


def _cents(value: float | None) -> Decimal:
    """Pontos/reais como Decimal, pra que a soma do relatorio nao herde o erro de float que a
    auditoria aponta no achado M5 - o relatorio precisa ser exato mesmo enquanto o banco nao e."""
    return Decimal(str(round(float(value or 0.0), 2)))


def _pair_key(entry: PointBalanceEntry) -> tuple[str, str] | None:
    if entry.original_os_code and entry.related_os_code:
        return (entry.original_os_code, entry.related_os_code)
    return None


def _classify(
    credit: PointBalanceEntry,
    debit: PointBalanceEntry | None,
    live_reissue: PointBalanceEntry | None,
) -> str:
    if debit is None:
        return "DEBITO_NAO_ENCONTRADO"
    if debit.status == "reverted":
        return "DEBITO_ESTORNADO"
    if debit.status == "pending":
        return "DEBITO_NAO_APLICADO"
    # debit.status == "applied"
    return "COMPENSADO" if live_reissue is not None else "SEM_CONTRAPARTIDA"


def build_report(db) -> tuple[list[dict], list[dict], list[dict], float]:
    point_value = get_point_value(db)

    entries = list(db.scalars(select(PointBalanceEntry).order_by(PointBalanceEntry.id.asc())))
    by_id = {entry.id: entry for entry in entries}
    collaborator_names = {
        collaborator.id: collaborator.name
        for collaborator in db.scalars(select(Collaborator))
    }

    # Re-lancamentos VIVOS (pendentes) por par de O.S - e assim que se descobre se a cobranca que o
    # credito estornou voltou a existir em outro mes ou simplesmente sumiu.
    live_debits_by_pair: dict[tuple[str, str], list[PointBalanceEntry]] = defaultdict(list)
    for entry in entries:
        if entry.entry_type != "post_payment_warranty_debit" or entry.status != "pending":
            continue
        key = _pair_key(entry)
        if key:
            live_debits_by_pair[key].append(entry)

    rows: list[dict] = []
    for entry in entries:
        if entry.status != "pending" or entry.requires_review:
            continue

        debit: PointBalanceEntry | None = None
        live_reissue: PointBalanceEntry | None = None
        classification: str

        if entry.entry_type == "manual_adjustment":
            match = REFERENCED_DEBIT_RE.search(entry.reason or "")
            if not match:
                classification = "SEM_REFERENCIA"
            else:
                debit = by_id.get(int(match.group(1)))
                pair = _pair_key(debit) if debit else None
                if pair:
                    live_reissue = next(
                        (item for item in live_debits_by_pair.get(pair, []) if item.id != (debit.id if debit else None)),
                        None,
                    )
                classification = _classify(entry, debit, live_reissue)
        elif entry.entry_type == "post_payment_warranty_debit":
            classification = "DEBITO_A_COBRAR"
        else:
            classification = "SALDO_REMANESCENTE"

        rows.append(
            {
                "lancamento_id": entry.id,
                "tipo": entry.entry_type,
                "classificacao": classification,
                "colaborador_id": entry.collaborator_id,
                "colaborador": collaborator_names.get(entry.collaborator_id, "?"),
                "pontos": f"{_cents(entry.points)}",
                "valor_reais": f"{_cents(float(_cents(entry.points)) * point_value)}",
                "os_original": entry.original_os_code or "",
                "os_retorno": entry.related_os_code or "",
                "alvo": (
                    f"{entry.target_reference_month:02d}/{entry.target_reference_year}"
                    if entry.target_reference_month and entry.target_reference_year
                    else ""
                ),
                "debito_referenciado_id": debit.id if debit else "",
                "debito_referenciado_status": debit.status if debit else "",
                "debito_referenciado_pontos": f"{_cents(debit.points)}" if debit else "",
                "debito_referenciado_fechamento": debit.applied_calculation_run_id if debit else "",
                "relancamento_vivo_id": live_reissue.id if live_reissue else "",
                "criado_por": entry.created_by if entry.created_by is not None else "SEM AUTOR",
                "criado_em": entry.created_at.isoformat() if entry.created_at else "",
                "motivo": (entry.reason or "").replace("\n", " | "),
            }
        )

    # Resumo por colaborador: o que efetivamente entra no proximo fechamento pago.
    per_collaborator: dict[int, dict] = {}
    for row in rows:
        item = per_collaborator.setdefault(
            row["colaborador_id"],
            {
                "colaborador_id": row["colaborador_id"],
                "colaborador": row["colaborador"],
                "lancamentos": 0,
                "creditos_pontos": Decimal("0"),
                "debitos_pontos": Decimal("0"),
                "saldo_pontos": Decimal("0"),
                "compensado": 0,
                "sem_contrapartida": 0,
                "debito_estornado": 0,
                "debito_nao_aplicado": 0,
                "nao_rastreavel": 0,
            },
        )
        points = Decimal(row["pontos"])
        item["lancamentos"] += 1
        item["saldo_pontos"] += points
        if points > 0:
            item["creditos_pontos"] += points
        else:
            item["debitos_pontos"] += points
        if row["classificacao"] == "COMPENSADO":
            item["compensado"] += 1
        elif row["classificacao"] == "SEM_CONTRAPARTIDA":
            item["sem_contrapartida"] += 1
        elif row["classificacao"] == "DEBITO_ESTORNADO":
            item["debito_estornado"] += 1
        elif row["classificacao"] == "DEBITO_NAO_APLICADO":
            item["debito_nao_aplicado"] += 1
        elif row["classificacao"] in {"DEBITO_NAO_ENCONTRADO", "SEM_REFERENCIA"}:
            item["nao_rastreavel"] += 1

    collaborator_rows = []
    for item in sorted(per_collaborator.values(), key=lambda entry: -entry["saldo_pontos"]):
        collaborator_rows.append(
            {
                **{key: str(value) for key, value in item.items()},
                "impacto_reais": f"{_cents(float(item['saldo_pontos']) * point_value)}",
            }
        )

    # Divergencia por fechamento: soma das linhas de collaborator_scores x total gravado no
    # result_summary (achado C1). E o numero que decide qual fonte a folha usou.
    divergence_rows = []
    for run in db.scalars(
        select(CalculationRun)
        .where(CalculationRun.status.in_(["paid", "approved", "review"]))
        .order_by(CalculationRun.id.asc())
    ):
        scores = list(db.scalars(select(CollaboratorScore).where(CollaboratorScore.calculation_run_id == run.id)))
        if not scores:
            continue
        rows_total = sum(_cents(score.estimated_payment) for score in scores)
        rows_points = sum(_cents(score.final_points) for score in scores)
        summary = run.result_summary if isinstance(run.result_summary, dict) else {}
        summary_total = _cents(summary.get("estimated_payment"))
        summary_points = _cents(summary.get("final_points"))
        divergence_rows.append(
            {
                "fechamento_id": run.id,
                "competencia": f"{run.reference_month:02d}/{run.reference_year}",
                "regional": run.regional or "(agregado)",
                "status": run.status,
                "valor_linhas_banco": f"{rows_total}",
                "valor_result_summary": f"{summary_total}",
                "diferenca_reais": f"{rows_total - summary_total}",
                "pontos_linhas_banco": f"{rows_points}",
                "pontos_result_summary": f"{summary_points}",
                "diferenca_pontos": f"{rows_points - summary_points}",
                "colaboradores": len(scores),
            }
        )

    return rows, collaborator_rows, divergence_rows, point_value


def _dump(title: str, rows: list[dict]) -> None:
    print(f"## {title}")
    if not rows:
        print("(vazio)")
        print()
        return
    writer = csv.DictWriter(sys.stdout, fieldnames=list(rows[0].keys()), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    print()


def main() -> None:
    db = SessionLocal()
    try:
        rows, collaborator_rows, divergence_rows, point_value = build_report(db)
    finally:
        db.close()

    totals = defaultdict(Decimal)
    counts: defaultdict[str, int] = defaultdict(int)
    for row in rows:
        totals[row["classificacao"]] += Decimal(row["pontos"])
        counts[row["classificacao"]] += 1

    print(f"# Conciliacao do saldo de pontos - valor do ponto R$ {point_value:.2f}")
    print(f"# Lancamentos pendentes analisados: {len(rows)} | colaboradores afetados: {len(collaborator_rows)}")
    saldo = sum(Decimal(row["pontos"]) for row in rows)
    print(f"# Saldo liquido pendente: {saldo} pontos = R$ {_cents(float(saldo) * point_value)}")
    print("#")
    print("# classificacao,lancamentos,pontos,valor_reais")
    for classification in sorted(counts, key=lambda key: -abs(totals[key])):
        points = totals[classification]
        print(f"# {classification},{counts[classification]},{points},{_cents(float(points) * point_value)}")
    print()

    _dump("lancamentos", rows)
    _dump("por_colaborador", collaborator_rows)
    _dump("divergencia_por_fechamento", divergence_rows)


if __name__ == "__main__":
    main()
