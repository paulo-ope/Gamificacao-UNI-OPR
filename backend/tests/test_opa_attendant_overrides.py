from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from app.modules.support.models import SupportOpaAttendance, SupportOpaAttendantOverride
from app.modules.support.opa_attendant_overrides import (
    create_override,
    delete_override,
    list_overrides,
    load_active_overrides,
    resolve_attendant_type,
    update_override,
)
from app.modules.support.opa_ingestion import import_opa_attendances
from app.modules.support.router import opa_attendant_summary
from tests.test_opa_ingestion import FakeOpaClient, _record


# --- resolve_attendant_type (função pura) -----------------------------------


def test_resolve_attendant_type_prioritizes_override_over_opa_tipo():
    overrides = {"A-1": "virtual_agent"}
    assert resolve_attendant_type("A-1", "user", overrides) == "bot"


def test_resolve_attendant_type_falls_back_to_opa_tipo_without_override():
    assert resolve_attendant_type("A-1", "user", {}) == "user"
    assert resolve_attendant_type("A-1", "bot", {}) == "bot"


def test_resolve_attendant_type_returns_none_when_nothing_known():
    assert resolve_attendant_type("A-1", None, {}) is None
    assert resolve_attendant_type(None, None, {}) is None


def test_resolve_attendant_type_ignores_inactive_or_unknown_classification():
    # `overrides` já vem filtrado por `active=True` de `load_active_overrides` —
    # aqui testamos que uma classificação desconhecida (não mapeada) não quebra
    # nem é tratada como bot por engano.
    assert resolve_attendant_type("A-1", "user", {"A-1": "algo_nao_mapeado"}) == "user"


# --- CRUD --------------------------------------------------------------------


def test_create_override_persists_and_is_returned_by_list(db_session):
    created = create_override(
        db_session, attendant_id="A-1", attendant_name="Theo", classification="virtual_agent", active=True, created_by=None
    )
    db_session.flush()

    assert created.id is not None
    items = list_overrides(db_session)
    assert len(items) == 1
    assert items[0].attendant_id == "A-1"
    assert items[0].attendant_name == "Theo"


def test_create_override_rejects_duplicate_attendant_id(db_session):
    create_override(db_session, attendant_id="A-1", attendant_name=None, classification="virtual_agent", active=True, created_by=None)
    db_session.flush()

    with pytest.raises(ValueError):
        create_override(db_session, attendant_id="A-1", attendant_name=None, classification="virtual_agent", active=True, created_by=None)


def test_create_override_rejects_blank_attendant_id(db_session):
    with pytest.raises(ValueError):
        create_override(db_session, attendant_id="   ", attendant_name=None, classification="virtual_agent", active=True, created_by=None)


def test_create_override_rejects_unknown_classification(db_session):
    with pytest.raises(ValueError):
        create_override(db_session, attendant_id="A-1", attendant_name=None, classification="humano_de_mentira", active=True, created_by=None)


def test_update_override_can_deactivate(db_session):
    created = create_override(db_session, attendant_id="A-1", attendant_name=None, classification="virtual_agent", active=True, created_by=None)
    db_session.flush()

    updated = update_override(db_session, created.id, {"active": False})
    assert updated.active is False
    assert load_active_overrides(db_session) == {}


def test_delete_override_removes_row(db_session):
    created = create_override(db_session, attendant_id="A-1", attendant_name=None, classification="virtual_agent", active=True, created_by=None)
    db_session.flush()

    assert delete_override(db_session, created.id) is True
    assert db_session.scalar(select(SupportOpaAttendantOverride)) is None


def test_delete_override_returns_false_when_not_found(db_session):
    assert delete_override(db_session, 999) is False


# --- Integração com a ingestão -----------------------------------------------


def test_bot_with_opa_tipo_continues_working_without_override(db_session):
    """Caso de regressão: atendente com `tipo="bot"` na dimensão do OPA continua
    classificado como bot mesmo sem nenhum override cadastrado."""
    record = _record(
        id="OPA-BOT-REG",
        atendente={"id": "BOT-1", "nome": "Bot"},
        data_abertura="2026-08-26T10:00:00+00:00",
        data_encerramento="2026-08-26T10:30:00+00:00",
        tmr_seconds=None,
    )
    messages = [
        {"id_user": "U-1", "data": "2026-08-26T10:00:00+00:00"},
        {"id_atend": "BOT-1", "data": "2026-08-26T10:00:05+00:00"},
    ]
    client = FakeOpaClient(
        [record],
        users=[{"_id": "BOT-1", "nome": "Bot", "tipo": "bot"}],
        messages={"OPA-BOT-REG": messages},
    )

    import_opa_attendances(db_session, client, date_from=date(2026, 8, 26), date_to=date(2026, 8, 26), imported_by=None)

    attendance = db_session.scalar(select(SupportOpaAttendance).where(SupportOpaAttendance.source_id == "OPA-BOT-REG"))
    assert attendance.handled_by_bot is True
    assert attendance.reached_human is False
    assert attendance.tmr_seconds is None
    assert attendance.tmr_all_responses_seconds == 5


def test_attendant_without_opa_tipo_classified_as_bot_via_manual_override(db_session):
    """Objetivo principal da tarefa: atendente que o OPA NUNCA marcou como bot
    (nem aparece na dimensão de usuários) passa a ser classificado como bot porque
    foi cadastrado manualmente como `virtual_agent`."""
    create_override(db_session, attendant_id="VIRTUAL-1", attendant_name="Theo", classification="virtual_agent", active=True, created_by=None)
    db_session.flush()

    record = _record(
        id="OPA-OVERRIDE-1",
        atendente={"id": "VIRTUAL-1", "nome": "Theo"},
        data_abertura="2026-08-26T10:00:00+00:00",
        data_encerramento="2026-08-26T10:30:00+00:00",
        tmr_seconds=None,
    )
    messages = [
        {"id_user": "U-1", "data": "2026-08-26T10:00:00+00:00"},
        {"id_atend": "VIRTUAL-1", "data": "2026-08-26T10:00:05+00:00"},
    ]
    # Sem `users=[...]`: VIRTUAL-1 nunca existiu na dimensão sincronizada do OPA.
    client = FakeOpaClient([record], messages={"OPA-OVERRIDE-1": messages})

    import_opa_attendances(db_session, client, date_from=date(2026, 8, 26), date_to=date(2026, 8, 26), imported_by=None)

    attendance = db_session.scalar(select(SupportOpaAttendance).where(SupportOpaAttendance.source_id == "OPA-OVERRIDE-1"))
    assert attendance.handled_by_bot is True
    assert attendance.reached_human is False
    # TMR humano nulo (não há resposta humana) — TMR geral preenchido (bot respondeu).
    assert attendance.tmr_seconds is None
    assert attendance.tmr_all_responses_seconds == 5


def test_manual_override_takes_priority_over_opa_dimension_tipo(db_session):
    """Override manual vence mesmo quando o OPA classifica o mesmo attendant_id
    como humano (`tipo="user"`) — cenário citado no objetivo 3."""
    create_override(db_session, attendant_id="A-1", attendant_name=None, classification="virtual_agent", active=True, created_by=None)
    db_session.flush()

    record = _record(
        id="OPA-OVERRIDE-2",
        atendente={"id": "A-1", "nome": "Atendente Um"},
        data_abertura="2026-08-26T10:00:00+00:00",
        data_encerramento="2026-08-26T10:30:00+00:00",
        tmr_seconds=None,
    )
    messages = [
        {"id_user": "U-1", "data": "2026-08-26T10:00:00+00:00"},
        {"id_atend": "A-1", "data": "2026-08-26T10:00:05+00:00"},
    ]
    client = FakeOpaClient(
        [record],
        users=[{"_id": "A-1", "nome": "Atendente Um", "tipo": "user"}],
        messages={"OPA-OVERRIDE-2": messages},
    )

    import_opa_attendances(db_session, client, date_from=date(2026, 8, 26), date_to=date(2026, 8, 26), imported_by=None)

    attendance = db_session.scalar(select(SupportOpaAttendance).where(SupportOpaAttendance.source_id == "OPA-OVERRIDE-2"))
    # Sem o override, A-1 (tipo="user") contaria como humano: tmr_seconds=5,
    # handled_by_bot=False. Com o override, vira bot.
    assert attendance.handled_by_bot is True
    assert attendance.reached_human is False
    assert attendance.tmr_seconds is None
    assert attendance.tmr_all_responses_seconds == 5


def test_attendant_summary_marks_manually_overridden_attendant_as_bot(db_session, admin_user):
    """Prova, via `attendant_summary` (o que o painel individual consome), que um
    attendant_id cadastrado como agente virtual aparece com `attendant_type="bot"`
    — é esse campo que o frontend usa pra priorizar TMR geral."""
    create_override(db_session, attendant_id="VIRTUAL-2", attendant_name="Theo", classification="virtual_agent", active=True, created_by=None)
    db_session.flush()

    record = _record(
        id="OPA-PAINEL-1",
        atendente={"id": "VIRTUAL-2", "nome": "Theo"},
        data_abertura="2026-08-26T10:00:00+00:00",
        data_encerramento="2026-08-26T10:30:00+00:00",
        tmr_seconds=None,
    )
    messages = [
        {"id_user": "U-1", "data": "2026-08-26T10:00:00+00:00"},
        {"id_atend": "VIRTUAL-2", "data": "2026-08-26T10:00:05+00:00"},
    ]
    client = FakeOpaClient([record], messages={"OPA-PAINEL-1": messages})
    import_opa_attendances(db_session, client, date_from=date(2026, 8, 26), date_to=date(2026, 8, 26), imported_by=None)

    summary = opa_attendant_summary(
        "VIRTUAL-2",
        date_from=date(2026, 8, 26),
        date_to=date(2026, 8, 26),
        date_basis="opened_at",
        status=None,
        channel=None,
        department_id=None,
        reason_id=None,
        customer=None,
        search=None,
        db=db_session,
        user=admin_user,
    )

    assert summary["attendant_type"] == "bot"
    assert summary["average_tmr_all_responses_seconds"] == 5
    assert summary["average_tmr_seconds"] is None


def test_attendant_summary_not_shown_as_unknown_once_registered_as_virtual_agent(db_session, admin_user):
    """Critério de aceite: atendente cadastrado como agente virtual não aparece
    mais como desconhecido — mesmo sem nunca ter aparecido em nenhum atendimento
    importado (só existe no cadastro manual)."""
    create_override(db_session, attendant_id="VIRTUAL-3", attendant_name="Theo Novo", classification="virtual_agent", active=True, created_by=None)
    db_session.flush()

    summary = opa_attendant_summary(
        "VIRTUAL-3",
        date_from=date(2026, 8, 1),
        date_to=date(2026, 8, 31),
        date_basis="opened_at",
        status=None,
        channel=None,
        department_id=None,
        reason_id=None,
        customer=None,
        search=None,
        db=db_session,
        user=admin_user,
    )

    assert summary is not None
    assert summary["attendant_type"] == "bot"
