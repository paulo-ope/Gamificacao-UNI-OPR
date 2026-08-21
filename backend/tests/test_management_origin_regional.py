"""Regional de origem do colaborador (Collaborator.regional) exposta em Gestão Integrada, distinta
da regional operacional onde a produção foi apurada - pedido do usuário em 2026-08-21: quem faz
atendimento cross-regional ocasional não deve "perder" os números na regional visitada, mas
precisa ser identificável na regional de origem pra perguntas tipo "quantos colaboradores temos
na Regional X"."""
from __future__ import annotations

from app.models import Collaborator, User
from app.modules.management import services as management_services
from app.modules.management.models import ManagementOperationalMember


def test_member_out_exposes_the_collaborator_origin_regional(db_session):
    collaborator = Collaborator(name="Joao Cross", role="Tecnico", regional="UNI JARU", active=True, is_registered=True)
    db_session.add(collaborator)
    db_session.flush()
    member = ManagementOperationalMember(
        responsible_name="Joao Cross",
        regional="UNI ARIQUEMES",  # regional operacional - onde ele fechou O.S. este mês
        collaborator_id=collaborator.id,
        status="validated_operation",
        is_active=True,
    )
    db_session.add(member)
    db_session.flush()

    result = management_services.member_out(member)

    assert result.regional == "UNI ARIQUEMES"
    assert result.collaborator_regional == "UNI JARU"


def test_member_out_has_no_origin_regional_without_a_linked_collaborator(db_session):
    member = ManagementOperationalMember(responsible_name="Sem Cadastro", regional="UNI JARU", status="pending_validation", is_active=True)
    db_session.add(member)
    db_session.flush()

    result = management_services.member_out(member)

    assert result.collaborator_regional is None


def test_visible_member_filters_by_origin_regional_keeps_cross_regional_rows_out_of_scope(db_session):
    home_collaborator = Collaborator(name="Maria Base Jaru", role="Tecnico", regional="UNI JARU", active=True, is_registered=True)
    other_collaborator = Collaborator(name="Pedro Base Ariquemes", role="Tecnico", regional="UNI ARIQUEMES", active=True, is_registered=True)
    db_session.add_all([home_collaborator, other_collaborator])
    db_session.flush()
    # Maria é de Jaru mas atendeu Ariquemes esse mês (linha operacional cross-regional).
    db_session.add_all([
        ManagementOperationalMember(responsible_name="Maria Base Jaru", regional="UNI ARIQUEMES", collaborator_id=home_collaborator.id, status="validated_operation", is_active=True),
        ManagementOperationalMember(responsible_name="Pedro Base Ariquemes", regional="UNI ARIQUEMES", collaborator_id=other_collaborator.id, status="validated_operation", is_active=True),
    ])
    db_session.commit()

    filters = management_services.visible_member_filters(collaborator_regional="UNI JARU")
    from sqlalchemy import select

    rows = db_session.scalars(select(ManagementOperationalMember).where(*filters)).all()

    assert [row.responsible_name for row in rows] == ["Maria Base Jaru"]
