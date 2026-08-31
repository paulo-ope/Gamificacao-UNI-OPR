from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.modules.support.models import SupportOpaAttendance, SupportOpaDimension
from app.modules.support.opa_ingestion import backfill_attendant_names
from app.modules.support.router import OpaExtraFilters, opa_breakdowns
from scripts.fix_opa_attendant_names import diagnose, main


def _attendance(source_id: str, attendant_id: str | None, attendant_name: str | None) -> SupportOpaAttendance:
    return SupportOpaAttendance(
        source_id=source_id,
        protocol=f"P-{source_id}",
        attendant_id=attendant_id,
        attendant_name=attendant_name,
        opened_at=datetime(2026, 8, 1, 10, tzinfo=timezone.utc),
        closed_at=datetime(2026, 8, 1, 11, tzinfo=timezone.utc),
        raw_payload={},
    )


def _user_dimension(source_id: str, name: str | None) -> SupportOpaDimension:
    return SupportOpaDimension(
        dimension_type="user",
        source_id=source_id,
        name=name,
        payload_json={"_id": source_id, "nome": name, "tipo": "user"},
    )


def _name_of(db_session, source_id: str) -> str | None:
    return db_session.scalar(
        select(SupportOpaAttendance.attendant_name).where(SupportOpaAttendance.source_id == source_id)
    )


def test_apply_corrige_nome_vazio(db_session):
    db_session.add_all([_attendance("A", "ID-1", None), _user_dimension("ID-1", "Ana Souza")])
    db_session.flush()

    assert backfill_attendant_names(db_session) == 1
    assert _name_of(db_session, "A") == "Ana Souza"


def test_apply_corrige_nome_igual_ao_id(db_session):
    """O caso da VM: a API mandou o id no campo de nome, entao o fallback da
    ingestao nunca entrou (ele so cobre campo vazio)."""
    db_session.add_all([_attendance("B", "ID-2", "ID-2"), _user_dimension("ID-2", "Bruno Lima")])
    db_session.flush()

    assert backfill_attendant_names(db_session) == 1
    assert _name_of(db_session, "B") == "Bruno Lima"


def test_apply_nao_sobrescreve_nome_humano_valido(db_session):
    db_session.add_all([_attendance("C", "ID-3", "Carla Dias"), _user_dimension("ID-3", "Nome Diferente")])
    db_session.flush()

    assert backfill_attendant_names(db_session) == 0
    assert _name_of(db_session, "C") == "Carla Dias"


def test_apply_deixa_pendente_quando_nao_ha_dimensao(db_session):
    """Sem dimensao que traduza o id, o nome NAO e inventado -- o registro fica
    pendente e aparece no diagnostico."""
    db_session.add(_attendance("D", "ID-SEM-DIM", ""))
    db_session.flush()

    assert backfill_attendant_names(db_session) == 0
    assert _name_of(db_session, "D") == ""
    assert diagnose(db_session)["pendentes_sem_dimensao"] == 1


def test_apply_ignora_dimensao_cujo_nome_e_o_proprio_id(db_session):
    """Trocar id por id nao corrige nada e quebraria a idempotencia: o registro
    voltaria a contar como corrigivel em toda execucao."""
    db_session.add_all([_attendance("E", "ID-4", "ID-4"), _user_dimension("ID-4", "ID-4")])
    db_session.flush()

    assert backfill_attendant_names(db_session) == 0
    assert diagnose(db_session)["corrigiveis"] == 0


def test_apply_e_idempotente(db_session):
    db_session.add_all(
        [
            _attendance("F1", "ID-5", "ID-5"),
            _attendance("F2", "ID-5", None),
            _user_dimension("ID-5", "Fernanda Reis"),
        ]
    )
    db_session.flush()

    assert backfill_attendant_names(db_session) == 2
    # Segunda passada nao encontra mais nada: a condicao deixou de casar.
    assert backfill_attendant_names(db_session) == 0
    assert _name_of(db_session, "F1") == "Fernanda Reis"
    assert _name_of(db_session, "F2") == "Fernanda Reis"


def test_apply_nao_altera_attendant_id_nem_raw_payload(db_session):
    row = _attendance("G", "ID-6", "ID-6")
    row.raw_payload = {"id_atendente": "ID-6", "protocolo": "P-G"}
    db_session.add_all([row, _user_dimension("ID-6", "Gabriel Nunes")])
    db_session.flush()

    backfill_attendant_names(db_session)
    db_session.refresh(row)

    assert row.attendant_name == "Gabriel Nunes"
    assert row.attendant_id == "ID-6"
    assert row.raw_payload == {"id_atendente": "ID-6", "protocolo": "P-G"}


def test_dry_run_nao_altera_dados(db_session, monkeypatch):
    """`main()` sem `--apply` precisa terminar sem gravar nada. A sessao do
    script e trocada pela do teste pra que o efeito seja observavel aqui."""
    db_session.add_all([_attendance("H", "ID-7", "ID-7"), _user_dimension("ID-7", "Helena Prado")])
    db_session.flush()

    monkeypatch.setattr("scripts.fix_opa_attendant_names.SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)

    assert main([]) == 0
    assert _name_of(db_session, "H") == "ID-7"

    assert main(["--dry-run"]) == 0
    assert _name_of(db_session, "H") == "ID-7"


def test_main_apply_corrige_e_zera_pendencia(db_session, monkeypatch):
    db_session.add_all([_attendance("I", "ID-8", "ID-8"), _user_dimension("ID-8", "Igor Salles")])
    db_session.flush()

    monkeypatch.setattr("scripts.fix_opa_attendant_names.SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)
    monkeypatch.setattr(db_session, "commit", db_session.flush)

    assert main(["--apply"]) == 0
    assert _name_of(db_session, "I") == "Igor Salles"
    assert diagnose(db_session)["corrigiveis"] == 0


def test_diagnostico_conta_cada_situacao_separadamente(db_session):
    db_session.add_all(
        [
            _attendance("J1", "ID-9", "ID-9"),          # nome == id, corrigivel
            _attendance("J2", "ID-9", None),            # vazio, corrigivel
            _attendance("J3", "ID-SEM", ""),            # vazio, sem dimensao
            _attendance("J4", "ID-10", "Nome Bom"),     # ok
            _user_dimension("ID-9", "Joana Reis"),
            _user_dimension("ID-10", "Nome Bom"),
        ]
    )
    db_session.flush()

    dados = diagnose(db_session)

    assert dados["total_atendimentos"] == 4
    assert dados["com_attendant_id"] == 4
    assert dados["nome_igual_ao_id"] == 1
    assert dados["nome_vazio"] == 2
    assert dados["dimensoes_user"] == 2
    assert dados["corrigiveis"] == 2
    assert dados["pendentes_sem_dimensao"] == 1


def test_ranking_por_atendente_passa_a_mostrar_nome_apos_correcao(db_session, admin_user):
    """Fecha o ciclo: o breakdown agrupa por `attendant_name` cru, entao antes da
    correcao o ranking exibia o id na tela."""
    db_session.add_all(
        [
            _attendance("K1", "ID-11", "ID-11"),
            _attendance("K2", "ID-11", "ID-11"),
            _user_dimension("ID-11", "Karina Melo"),
        ]
    )
    db_session.flush()

    def _labels():
        body = opa_breakdowns(
            dimension="attendant",
            sort_by="total",
            sort_dir="desc",
            limit=20,
            search=None,
            date_from=None,
            date_to=None,
            date_basis="opened_at",
            status=None,
            channel=None,
            attendant_id=None,
            attendant=None,
            department_id=None,
            department=None,
            reason_id=None,
            reason=None,
            protocol=None,
            customer=None,
            extra=OpaExtraFilters(),
            db=db_session,
            user=admin_user,
        )
        return [item["label"] for item in body["items"]]

    assert _labels() == ["ID-11"]

    backfill_attendant_names(db_session)
    db_session.expire_all()

    assert _labels() == ["Karina Melo"]


def test_painel_individual_prefere_dimensao_quando_nome_gravado_e_o_id(db_session):
    """`resolve_attendant_identity` usava `attendance_name or dimension_name`: o id
    gravado como nome e "truthy" e vencia o nome bom da dimensao, entao o drawer
    mostrava hash mesmo com a dimensao sincronizada."""
    from app.modules.support.opa_attendant_service import resolve_attendant_identity

    db_session.add_all([_attendance("L", "ID-12", "ID-12"), _user_dimension("ID-12", "Lucas Vieira")])
    db_session.flush()

    identidade = resolve_attendant_identity(db_session, "ID-12")

    assert identidade is not None
    assert identidade["attendant_name"] == "Lucas Vieira"
    assert identidade["attendant_id"] == "ID-12"


def test_painel_individual_mantem_nome_humano_ja_gravado(db_session):
    from app.modules.support.opa_attendant_service import resolve_attendant_identity

    db_session.add_all([_attendance("M", "ID-13", "Marina Alves"), _user_dimension("ID-13", "Nome Antigo")])
    db_session.flush()

    identidade = resolve_attendant_identity(db_session, "ID-13")

    assert identidade["attendant_name"] == "Marina Alves"
