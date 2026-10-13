"""Lista das O.S. "fora do prazo" do quadro por regional (`GET /operations/in-progress/orders?overdue_only=true`).

O contrato que importa: a lista soma exatamente o `overdue_backlog` que o quadro mostrou, com o
mesmo recorte de filtros - senão o número clicado e a lista abrem divergentes.
"""

from __future__ import annotations

from datetime import timedelta

from app.modules.operations.models import OperationOrder
from app.modules.operations.period import current_month_bounds

MATRIX = "/api/operations/overview/regional-matrix"
ORDERS = "/api/operations/in-progress/orders"


def _open(source_order_id: str, opened_at, *, sla_status: str, **overrides) -> OperationOrder:
    defaults = dict(
        source="ixc",
        source_order_id=source_order_id,
        order_code=source_order_id.upper(),
        sector="Suporte Externo Fibra",
        regional="UNI - NORTE",
        status="Aberta",
        status_code="A",
        is_closed=False,
        sla_status=sla_status,
        opened_at=opened_at,
        closed_at=None,
        raw_payload={},
    )
    defaults.update(overrides)
    return OperationOrder(**defaults)


def test_overdue_only_lists_exactly_the_orders_counted_in_the_matrix(client, db_session):
    from tests.test_operations_regional_matrix import _utc_at

    _, date_to = current_month_bounds()
    old_day = max(date_to - timedelta(days=40), date_to.replace(month=1, day=1))
    db_session.add_all(
        [
            # Atrasada aberta fora do período: o estoque ignora período, então entra.
            _open("od-late-old", _utc_at(old_day, 8), sla_status="out_of_time"),
            _open("od-late-new", _utc_at(date_to, 8), sla_status="out_of_time", responsible="Técnico X"),
            # Filial granular que o quadro agrupa dentro de Rolim de Moura.
            _open("od-late-grouped", _utc_at(date_to, 8), sla_status="out_of_time", regional="UNI - SAO FELIPE DOESTE"),
            _open("od-late-rolim", _utc_at(date_to, 8), sla_status="out_of_time", regional="UNI - ROLIM DE MOURA"),
            _open("od-on-time", _utc_at(date_to, 9), sla_status="on_time"),
            # Rótulo que não é regional agrupada: o quadro lista como linha própria.
            _open("od-late-unknown", _utc_at(date_to, 8), sla_status="out_of_time", regional="NAO IDENTIFICADO"),
            _open("od-other-regional", _utc_at(date_to, 9), sla_status="out_of_time", regional="UNI - SUL"),
            # Fechada e atrasada não é estoque.
            _open("od-closed", _utc_at(date_to, 9), sla_status="out_of_time", is_closed=True, closed_at=_utc_at(date_to, 11)),
        ]
    )
    db_session.flush()
    period = {"date_from": date_to.isoformat(), "date_to": date_to.isoformat()}

    matrix = client.get(MATRIX, params=period).json()
    listing = client.get(ORDERS, params={"overdue_only": "true", "page_size": 50})

    assert listing.status_code == 200
    payload = listing.json()
    assert payload["total"] == matrix["total"]["overdue_backlog"] == 6
    assert {item["source_order_id"] for item in payload["items"]} == {
        "od-late-old", "od-late-new", "od-late-grouped", "od-late-rolim", "od-other-regional", "od-late-unknown",
    }

    # Clicar na linha "Rolim de Moura" do quadro (que já soma São Felipe) abre as duas O.S.
    rolim = client.get(ORDERS, params={"overdue_only": "true", "regional_groups": "UNI - ROLIM DE MOURA"}).json()
    rolim_row = next(row for row in matrix["items"] if row["regional"] == "UNI - ROLIM DE MOURA")
    assert rolim["total"] == rolim_row["overdue_backlog"] == 2
    # Linha cujo rótulo não é regional agrupada: antes abria vazia.
    unknown = client.get(ORDERS, params={"overdue_only": "true", "regional_label": "NAO IDENTIFICADO"}).json()
    unknown_row = next(row for row in matrix["items"] if row["regional"] == "NAO IDENTIFICADO")
    assert unknown["total"] == unknown_row["overdue_backlog"] == 1
    # O rótulo agrupado também funciona (São Felipe soma dentro de Rolim de Moura).
    grouped = client.get(ORDERS, params={"overdue_only": "true", "regional_label": "UNI - ROLIM DE MOURA"}).json()
    assert grouped["total"] == rolim_row["overdue_backlog"] == 2
    # O filtro de executor não reduz a lista, igual ao quadro (`_backlog_filters`).
    by_responsible = client.get(ORDERS, params={"overdue_only": "true", "regional_groups": "UNI - ROLIM DE MOURA", "responsibles": "Técnico X"}).json()
    assert by_responsible["total"] == 2
