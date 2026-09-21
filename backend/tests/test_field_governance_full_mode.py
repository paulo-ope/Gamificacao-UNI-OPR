"""P0-3 da auditoria técnica de 2026-09-15 (`docs/auditoria-tecnica-geral-2026-09-15.md`):
`response_mode="full"` (o padrão em toda rota de O.S./busca/detalhe) devolvia `None` ("sem
filtro") quando `fields` não vinha explícito - desligar um campo em `AiFieldPermission`
(`selectable`/`detail_available` = False) não tinha efeito nenhum na chamada mais comum. A
correção faz "full" sempre recortar por `policy.field_allowed_or_uncatalogued`, sobre TODO o
campo do schema (incluindo `@computed_field`, que `model_fields` sozinho não lista).

Achado real ao escrever estes testes: o teste já existente
(`test_ai_governance_fase2.py::test_disabling_field_in_governance_removes_it_from_selectable_output`)
só checava que um `fields=[...]` EXPLÍCITO com o campo desligado é rejeitado (422) - nunca checou
se o campo continuava vazando no modo padrão sem `fields`, que é exatamente o P0-3.
"""
from __future__ import annotations

from datetime import datetime, time, timezone

from app.modules.ai_governance.gate import enforce_ai_endpoint_for_user
from app.modules.ai_governance.models import AiFieldPermission
from app.modules.ai_governance.policy import bump_policy_version, resolve_effective_policy
from app.modules.ai.router import resolve_ai_order_details_output_fields, resolve_ai_search_output_fields
from app.modules.operations.models import OperationOrder
from app.modules.operations.period import OPERATIONS_TIMEZONE, current_month_bounds


def _utc_at(day, hour=12):
    return datetime.combine(day, time(hour=hour), tzinfo=OPERATIONS_TIMEZONE).astimezone(timezone.utc)


def _make_order(db_session, *, source_order_id, order_code, opened_at, **overrides):
    defaults = dict(
        source="ixc",
        source_order_id=source_order_id,
        order_code=order_code,
        regional="UNI - JI PARANA",
        state="RO",
        city="Ji-Paraná",
        os_type="Manutenção",
        os_subject="Reparo",
        sector="Suporte Externo Fibra",
        creator="Atendente A",
        responsible="Técnico A",
        status="Em execução",
        status_code="EX",
        is_closed=False,
        sla_status="on_time",
        opened_at=opened_at,
        raw_payload={"mensagem": "Relato de abertura"},
    )
    defaults.update(overrides)
    order = OperationOrder(**defaults)
    db_session.add(order)
    db_session.flush()
    return order


def _disable_field(db_session, *, entity: str, field: str, capability: str):
    permission = db_session.query(AiFieldPermission).filter_by(entity=entity, field=field).one()
    setattr(permission, capability, False)
    db_session.commit()
    bump_policy_version(db_session)


# --- REST: /operations/orders (listagem) e /operations/orders/{id} (detalhe) ------------------


def test_disabled_field_is_removed_from_the_order_list_default_response(client, db_session):
    """Modo padrão da tela (sem `fields`, `response_mode=full` implícito) - o achado central do
    P0-3: antes desta correção, `responsible` continuava aparecendo mesmo desligado."""
    date_from, date_to = current_month_bounds()
    _make_order(db_session, source_order_id="P0-3-LIST", order_code="IXC-P0-3-LIST", opened_at=_utc_at(date_from, 9))
    _disable_field(db_session, entity="operations_orders", field="responsible", capability="selectable")

    response = client.get(f"/api/operations/orders?date_from={date_from.isoformat()}&date_to={date_to.isoformat()}")

    assert response.status_code == 200
    items = response.json()["items"]
    assert items, "precisa ter pelo menos 1 item pra o teste fazer sentido"
    assert "responsible" not in items[0]
    # Campo não desligado continua aparecendo - não virou "esconde tudo".
    assert items[0]["order_code"] == "IXC-P0-3-LIST"


def test_disabled_field_is_removed_from_the_order_detail_default_response(client, db_session):
    date_from, _ = current_month_bounds()
    _make_order(db_session, source_order_id="P0-3-DETAIL", order_code="IXC-P0-3-DETAIL", opened_at=_utc_at(date_from, 9))
    _disable_field(db_session, entity="operations_orders", field="responsible", capability="detail_available")

    response = client.get("/api/operations/orders/P0-3-DETAIL")

    assert response.status_code == 200
    payload = response.json()
    assert "responsible" not in payload
    assert payload["order_code"] == "IXC-P0-3-DETAIL"


def test_computed_field_still_appears_in_full_mode_when_allowed(client, db_session):
    """Guarda de regressão da própria correção: `service_description` é `@computed_field`
    (Pydantic) - `model_fields` sozinho não o lista, só `model_computed_fields`. Uma versão
    ingênua da correção (usando só `model_fields`) faria este campo sumir do modo "full" mesmo
    autorizado - confirmado ao escrever este teste (falhou antes do ajuste)."""
    date_from, _ = current_month_bounds()
    _make_order(
        db_session, source_order_id="P0-3-COMPUTED", order_code="IXC-P0-3-COMPUTED", opened_at=_utc_at(date_from, 9),
        raw_payload={"mensagem": "Relato normal do atendimento"},
    )

    response = client.get("/api/operations/orders/P0-3-COMPUTED")

    assert response.status_code == 200
    assert response.json()["service_description"] == "Relato normal do atendimento"


def test_disabling_computed_field_removes_it_from_full_mode_too(client, db_session):
    date_from, _ = current_month_bounds()
    _make_order(
        db_session, source_order_id="P0-3-COMPUTED-OFF", order_code="IXC-P0-3-COMPUTED-OFF", opened_at=_utc_at(date_from, 9),
        raw_payload={"mensagem": "Não deveria aparecer"},
    )
    _disable_field(db_session, entity="operations_orders", field="service_description", capability="detail_available")

    response = client.get("/api/operations/orders/P0-3-COMPUTED-OFF")

    assert response.status_code == 200
    assert "service_description" not in response.json()


# --- Camada de IA (funções puras, usadas por /api/ai/* e pelas tools MCP) ----------------------


def test_resolve_ai_search_output_fields_excludes_disabled_field_in_full_mode(db_session, admin_user):
    _disable_field(db_session, entity="operations_orders", field="service_address", capability="selectable")
    policy = resolve_effective_policy(db_session, admin_user)

    output_fields = resolve_ai_search_output_fields(policy, "full", None)

    assert output_fields is not None, "nunca deve voltar a ser None - é o próprio bug do P0-3"
    assert "service_address" not in output_fields
    # Campo calculado (não catalogado) continua sempre disponível.
    assert "distance_km" in output_fields
    assert "order_code" in output_fields


def test_resolve_ai_order_details_output_fields_excludes_disabled_field_in_full_mode(db_session, admin_user):
    _disable_field(db_session, entity="operations_orders", field="responsible", capability="detail_available")
    policy = resolve_effective_policy(db_session, admin_user)

    output_fields = resolve_ai_order_details_output_fields(policy, "full", None)

    assert output_fields is not None
    assert "responsible" not in output_fields
    assert "order_code" in output_fields
    # Campo calculado do detalhe continua presente quando autorizado.
    assert "service_description" in output_fields


def test_unrestricted_policy_full_mode_matches_the_old_unfiltered_behaviour(db_session, admin_user):
    """Sem nenhum campo desligado, o modo "full" precisa continuar devolvendo, na prática, quase
    tudo que `_build_search_item`/`OperationOrderDetailOut` sempre devolveram - a correção não
    pode reduzir silenciosamente o que um perfil sem restrição nenhuma já via.

    Achado colateral ao escrever este teste (fora do escopo do P0-3, registrado à parte em
    docs/STATUS.md): `pop` está em `AI_SEARCH_GOVERNED_FIELDS` (ai/queries.py) mas NUNCA foi
    adicionado a `OperationOrderOut` (operations/schemas.py) - `field_registry.py` deriva
    "selectable" da presença em `OperationOrderOut.model_fields`, então `pop` já estava
    catalogado como NÃO selecionável mesmo pra um perfil sem restrição nenhuma. Antes desta
    correção isso não importava (o modo "full" ignorava a política); agora `pop` some do modo
    "full" de `opr_search_orders` também - é a governança passando a valer de verdade sobre um
    gap pré-existente do catálogo, não uma regressão desta correção."""
    from app.modules.ai.queries import AI_SEARCH_ITEM_FIELDS

    policy = resolve_effective_policy(db_session, admin_user)

    search_fields = set(resolve_ai_search_output_fields(policy, "full", None))
    assert AI_SEARCH_ITEM_FIELDS - search_fields == {"pop"}, (
        "só 'pop' deve ficar de fora (gap conhecido do catálogo) - qualquer outra ausência é uma regressão real"
    )

    detail_fields = resolve_ai_order_details_output_fields(policy, "full", None)
    from app.modules.operations.schemas import OperationOrderDetailOut

    assert set(detail_fields) == set(OperationOrderDetailOut.model_fields) | set(OperationOrderDetailOut.model_computed_fields)
