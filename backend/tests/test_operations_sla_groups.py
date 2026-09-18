from __future__ import annotations

from types import SimpleNamespace

from app.core.security import get_current_user
from app.main import app
from app.modules.operations.models import OperationSlaGroup, OperationSlaSubjectGroup


def test_sla_group_can_be_created_renamed_and_deleted(client, db_session):
    created = client.post(
        "/api/operations/sla-groups",
        json={"card_label": "SLA de Produtividade", "name": "Produtividade Geral"},
    )
    assert created.status_code == 201
    body = created.json()
    group_id = body["id"]
    assert body["card_label"] == "SLA de Produtividade"
    assert body["name"] == "Produtividade Geral"
    assert body["subjects"] == []

    renamed = client.patch(f"/api/operations/sla-groups/{group_id}", json={"name": "Produtividade Interna"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Produtividade Interna"
    assert renamed.json()["card_label"] == "SLA de Produtividade"

    deleted = client.delete(f"/api/operations/sla-groups/{group_id}")
    assert deleted.status_code == 204
    assert db_session.get(OperationSlaGroup, group_id) is None


def test_sla_group_rejects_duplicate_name(client):
    first = client.post("/api/operations/sla-groups", json={"card_label": "SLA de Ativação", "name": "Único"})
    assert first.status_code == 201

    duplicate = client.post("/api/operations/sla-groups", json={"card_label": "SLA de Suporte", "name": "Único"})
    assert duplicate.status_code == 409


def test_replacing_sla_group_subjects_moves_subject_between_groups(client, db_session):
    """Um assunto só pode estar em UM grupo por vez - atribuir a um grupo novo precisa
    remover a atribuição antiga automaticamente, não duplicar a linha."""
    origin = client.post("/api/operations/sla-groups", json={"card_label": "SLA de Ativação", "name": "Origem"})
    destination = client.post("/api/operations/sla-groups", json={"card_label": "SLA de Ativação", "name": "Destino"})
    origin_id = origin.json()["id"]
    destination_id = destination.json()["id"]

    set_origin = client.put(f"/api/operations/sla-groups/{origin_id}/subjects", json={"subjects": ["Instalação Fibra Urbana"]})
    assert set_origin.status_code == 200
    assert set_origin.json()["subjects"] == ["Instalação Fibra Urbana"]

    set_destination = client.put(
        f"/api/operations/sla-groups/{destination_id}/subjects", json={"subjects": ["Instalação Fibra Urbana"]}
    )
    assert set_destination.status_code == 200
    assert set_destination.json()["subjects"] == ["Instalação Fibra Urbana"]

    # Saiu do grupo de origem - não fica em dois grupos ao mesmo tempo.
    origin_after = client.get("/api/operations/sla-groups")
    origin_row = next(item for item in origin_after.json() if item["id"] == origin_id)
    assert origin_row["subjects"] == []

    rows = list(db_session.query(OperationSlaSubjectGroup).filter(OperationSlaSubjectGroup.subject == "Instalação Fibra Urbana"))
    assert len(rows) == 1
    assert rows[0].group_id == destination_id


def test_sla_group_delete_unassigns_its_subjects_instead_of_orphaning_rows(client, db_session):
    created = client.post("/api/operations/sla-groups", json={"card_label": "SLA de Suporte", "name": "Temporário"})
    group_id = created.json()["id"]
    client.put(f"/api/operations/sla-groups/{group_id}/subjects", json={"subjects": ["Suporte Externo Rádio"]})

    deleted = client.delete(f"/api/operations/sla-groups/{group_id}")
    assert deleted.status_code == 204

    remaining = list(db_session.query(OperationSlaSubjectGroup).filter(OperationSlaSubjectGroup.subject == "Suporte Externo Rádio"))
    assert remaining == []


def test_sla_groups_management_requires_its_own_permission(client):
    limited_user = SimpleNamespace(
        role="viewer",
        managed_regional=None,
        managed_regionals=[],
        access_profiles=[
            SimpleNamespace(
                active=True,
                # "operations:read" é exigido a nível de ROUTER (todo o módulo Operação Analítica,
                # ver `router = APIRouter(..., dependencies=[Depends(require_permission("operations:read"))])`
                # em operations/router.py) - sem ele, qualquer rota do módulo devolve 403 antes de
                # chegar na permissão específica da rota. "operations:view_sla" é a permissão
                # ESPECÍFICA de leitura dos grupos; sem "operations:manage_sla_groups", só a
                # escrita deve ser bloqueada.
                permissions=[
                    SimpleNamespace(permission="operations:read"),
                    SimpleNamespace(permission="operations:view_sla"),
                ],
            )
        ],
    )
    app.dependency_overrides[get_current_user] = lambda: limited_user
    try:
        create = client.post("/api/operations/sla-groups", json={"card_label": "X", "name": "Y"})
        listing = client.get("/api/operations/sla-groups")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert create.status_code == 403
    # Leitura exige só operations:read (nível de router) + operations:view_sla - sem
    # operations:manage_sla_groups, que este usuário não tem.
    assert listing.status_code == 200


def test_sla_catalog_subjects_reports_order_count_and_current_group(client, db_session):
    from datetime import datetime, timezone

    from app.modules.operations.models import OperationOrder

    db_session.add(
        OperationOrder(
            source="ixc",
            source_order_id="cat-1",
            order_code="IXC-CAT-1",
            regional="UNI - JI PARANA",
            sector="Suporte Externo Fibra",
            os_type="Ativação",
            os_subject="Instalação Fibra Urbana",
            responsible="Técnico 1",
            status="Finalizada",
            status_code="F",
            is_closed=True,
            sla_status="on_time",
            opened_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
            closed_at=datetime(2026, 9, 1, 2, tzinfo=timezone.utc),
            raw_payload={},
        )
    )
    db_session.flush()

    catalog = client.get("/api/operations/sla-groups/catalog-subjects")
    assert catalog.status_code == 200
    row = next(item for item in catalog.json() if item["subject"] == "Instalação Fibra Urbana")
    assert row["order_count"] == 1
    assert row["group_id"] is None
