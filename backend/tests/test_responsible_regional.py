"""Resolução de responsável x regional (extraído de management/services.py em 2026-08-21, ver
generic-riding-petal.md) - cadastro manual tem prioridade sobre histórico de O.S. para o MESMO
par (responsible_name, regional); pares só vistos no histórico entram como "order_history"."""

from datetime import datetime, timezone

from app.modules.operations.models import OperationOrder, OperationResponsibleAssignment
from app.modules.operations.responsible_regional import resolve_responsible_regional_candidates


def _order(responsible: str, regional: str, order_code: str, ixc_id: int | None = None) -> OperationOrder:
    return OperationOrder(
        source="ixc",
        source_order_id=order_code,
        order_code=order_code,
        regional=regional,
        os_type="Suporte",
        os_subject="Fibra",
        responsible=responsible,
        responsible_ixc_id=ixc_id,
        opened_at=datetime(2026, 7, 20, tzinfo=timezone.utc),
        closed_at=datetime(2026, 7, 20, 15, 0, tzinfo=timezone.utc),
        raw_payload={},
    )


def test_assignment_wins_over_order_history_for_the_same_pair(db_session):
    db_session.add(OperationResponsibleAssignment(responsible_name="Joao Campo", regional="UNI JARU"))
    db_session.add(_order("Joao Campo", "UNI JARU", "OS-1", ixc_id=123))
    db_session.flush()

    candidates = resolve_responsible_regional_candidates(db_session)
    assert len(candidates) == 1
    assert candidates[0].source == "assignment"
    assert candidates[0].ixc_employee_id == 123  # dado do histórico ainda enriquece o candidato manual


def test_order_history_only_pair_becomes_a_separate_candidate(db_session):
    """Pessoa com cadastro manual numa regional E histórico de O.S. em OUTRA regional - os dois
    pares coexistem como candidatos distintos (uma pessoa pode ter mais de uma linha)."""
    db_session.add(OperationResponsibleAssignment(responsible_name="Joao Campo", regional="UNI JARU"))
    db_session.add(_order("Joao Campo", "UNI - ROLIM DE MOURA", "OS-1"))
    db_session.flush()

    candidates = {(c.responsible_name, c.regional): c.source for c in resolve_responsible_regional_candidates(db_session)}
    assert candidates == {
        ("Joao Campo", "UNI JARU"): "assignment",
        ("Joao Campo", "UNI - ROLIM DE MOURA"): "order_history",
    }


def test_no_candidates_when_no_data(db_session):
    assert resolve_responsible_regional_candidates(db_session) == []
