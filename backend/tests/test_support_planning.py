from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi import HTTPException

from app.models import User
from app.modules.support import planning_service
from app.modules.support.schemas import (
    SupportPlanArchive,
    SupportPlanItemCreate,
    SupportPlanItemUpdate,
    SupportPlanUpdateCreate,
)


@pytest.fixture()
def analyst(db_session):
    user = User(name="Analista", email="analista@local.test", password_hash="x", role="operator", active=True)
    db_session.add(user)
    db_session.flush()
    return user


def _create(db, user, **kwargs):
    data = {"kind": "task", "title": "Revisar fila", **kwargs}
    return planning_service.create_item(db, user, SupportPlanItemCreate(**data))


def _progress(db, user, item, **kwargs):
    return planning_service.add_update(db, user, item.id, SupportPlanUpdateCreate(version=item.version, **kwargs))


def test_create_stores_author_and_assignees(db_session, admin_user, analyst):
    item = _create(db_session, admin_user, assignee_ids=[admin_user.id, analyst.id, analyst.id])

    assert item.version == 1
    assert item.status == "planned"
    assert item.created_by_id == admin_user.id
    assert item.assignee_ids == [admin_user.id, analyst.id]


def test_create_rejects_inactive_or_unknown_assignee(db_session, admin_user, analyst):
    analyst.active = False
    db_session.flush()
    with pytest.raises(HTTPException) as excinfo:
        _create(db_session, admin_user, assignee_ids=[analyst.id])
    assert excinfo.value.status_code == 400
    with pytest.raises(HTTPException):
        _create(db_session, admin_user, assignee_ids=[9999])


def test_new_item_cannot_start_done(db_session, admin_user):
    with pytest.raises(HTTPException) as excinfo:
        _create(db_session, admin_user, status="done")
    assert excinfo.value.status_code == 400


def test_task_parent_must_be_a_project(db_session, admin_user):
    project = _create(db_session, admin_user, kind="project", title="Projeto")
    other_task = _create(db_session, admin_user, title="Outra")

    child = _create(db_session, admin_user, parent_id=project.id)
    assert child.parent_id == project.id
    with pytest.raises(HTTPException):
        _create(db_session, admin_user, parent_id=other_task.id)
    with pytest.raises(HTTPException):
        _create(db_session, admin_user, kind="project", parent_id=project.id)


def test_update_detects_stale_version(db_session, admin_user):
    item = _create(db_session, admin_user)
    planning_service.update_item(db_session, item.id, SupportPlanItemUpdate(version=1, title="Novo título"))

    with pytest.raises(HTTPException) as excinfo:
        planning_service.update_item(db_session, item.id, SupportPlanItemUpdate(version=1, title="Outro"))
    assert excinfo.value.status_code == 409
    assert item.title == "Novo título"
    assert item.version == 2


def test_update_can_clear_due_date_and_parent(db_session, admin_user):
    project = _create(db_session, admin_user, kind="project", title="Projeto")
    item = _create(db_session, admin_user, parent_id=project.id, due_date=date(2026, 11, 1))

    planning_service.update_item(
        db_session, item.id, SupportPlanItemUpdate(version=1, clear_due_date=True, clear_parent=True)
    )

    assert item.due_date is None
    assert item.parent_id is None


def test_done_requires_result_and_reopen_clears_completion(db_session, admin_user):
    item = _create(db_session, admin_user)

    with pytest.raises(HTTPException) as excinfo:
        _progress(db_session, admin_user, item, status="done")
    assert excinfo.value.status_code == 400

    _progress(db_session, admin_user, item, status="done", text="Feito", result="Fila reorganizada")
    assert item.status == "done"
    assert item.result == "Fila reorganizada"
    assert item.completed_at is not None

    _progress(db_session, admin_user, item, status="in_progress", text="Reaberto")
    assert item.status == "in_progress"
    assert item.completed_at is None


def test_blocking_or_canceling_requires_a_reason(db_session, admin_user):
    item = _create(db_session, admin_user)
    for status in ("blocked", "canceled"):
        with pytest.raises(HTTPException) as excinfo:
            _progress(db_session, admin_user, item, status=status)
        assert excinfo.value.status_code == 400


def test_update_without_text_or_status_is_rejected(db_session, admin_user):
    item = _create(db_session, admin_user)
    with pytest.raises(HTTPException):
        _progress(db_session, admin_user, item, text="  ")


def test_progress_ignores_canceled_and_archived_tasks(db_session, admin_user):
    project = _create(db_session, admin_user, kind="project", title="Projeto")
    first = _create(db_session, admin_user, parent_id=project.id, title="A")
    _create(db_session, admin_user, parent_id=project.id, title="B")
    canceled = _create(db_session, admin_user, parent_id=project.id, title="C")
    archived = _create(db_session, admin_user, parent_id=project.id, title="D")
    _progress(db_session, admin_user, first, status="done", result="ok")
    _progress(db_session, admin_user, canceled, status="canceled", text="Não vale mais")
    planning_service.set_archived(db_session, archived.id, SupportPlanArchive(version=1))

    detail = planning_service.item_detail(db_session, project.id)

    assert (detail["tasks_total"], detail["tasks_done"]) == (2, 1)
    assert sorted(child["title"] for child in detail["children"]) == ["A", "B", "C"]


def test_overdue_only_counts_open_items(db_session, admin_user):
    past = date.today() - timedelta(days=30)
    late = _create(db_session, admin_user, title="Atrasada", due_date=past)
    done = _create(db_session, admin_user, title="Feita", due_date=past)
    _progress(db_session, admin_user, done, status="done", result="ok")

    page = planning_service.list_items(db_session, only_overdue=True)

    assert [item["id"] for item in page["items"]] == [late.id]
    assert planning_service.summary(db_session)["overdue"] == 1


def test_list_filters_by_assignee_kind_search_and_status(db_session, admin_user, analyst):
    mine = _create(db_session, admin_user, title="Treinar equipe", assignee_ids=[admin_user.id])
    _create(db_session, admin_user, title="Mapear bairros", assignee_ids=[analyst.id])
    _create(db_session, admin_user, kind="project", title="Projeto novo")

    assert [i["id"] for i in planning_service.list_items(db_session, assignee_id=admin_user.id)["items"]] == [mine.id]
    assert planning_service.list_items(db_session, kind="project")["total"] == 1
    assert planning_service.list_items(db_session, search="bairros")["total"] == 1
    assert planning_service.list_items(db_session, statuses=["blocked"])["total"] == 0


def test_list_orders_blocked_first_and_hides_archived_by_default(db_session, admin_user):
    planned = _create(db_session, admin_user, title="Planejada")
    blocked = _create(db_session, admin_user, title="Travada")
    _progress(db_session, admin_user, blocked, status="blocked", text="Falta acesso")
    gone = _create(db_session, admin_user, title="Arquivada")
    planning_service.set_archived(db_session, gone.id, SupportPlanArchive(version=1))

    ids = [item["id"] for item in planning_service.list_items(db_session)["items"]]
    assert ids == [blocked.id, planned.id]
    assert planning_service.list_items(db_session, include_archived=True)["total"] == 3


def test_detail_has_timeline_newest_first(db_session, admin_user):
    item = _create(db_session, admin_user)
    _progress(db_session, admin_user, item, text="Primeiro")
    _progress(db_session, admin_user, item, text="Segundo", status="in_progress")

    detail = planning_service.item_detail(db_session, item.id)

    assert [u["text"] for u in detail["updates"]] == ["Segundo", "Primeiro"]
    assert detail["updates"][0]["status_from"] == "planned"
    assert detail["updates"][0]["status_to"] == "in_progress"
    assert detail["updates_count"] == 2


def test_archived_item_rejects_progress(db_session, admin_user):
    item = _create(db_session, admin_user)
    planning_service.set_archived(db_session, item.id, SupportPlanArchive(version=1))
    with pytest.raises(HTTPException):
        _progress(db_session, admin_user, item, text="x")


def test_people_lists_only_active_users_with_write_permission(db_session, admin_user, analyst):
    viewer = User(name="Leitor", email="leitor@local.test", password_hash="x", role="collaborator", active=True)
    inactive = User(name="Inativo", email="inativo@local.test", password_hash="x", role="operator", active=False)
    db_session.add_all([viewer, inactive])
    db_session.flush()

    names = [person["name"] for person in planning_service.people(db_session)]

    assert "Leitor" not in names and "Inativo" not in names
    assert {"Admin", "Analista"} <= set(names)


def test_unknown_item_is_404(db_session):
    with pytest.raises(HTTPException) as excinfo:
        planning_service.item_detail(db_session, 12345)
    assert excinfo.value.status_code == 404


def test_writing_requires_plan_permission(db_session, admin_user):
    from app.core.security import require_permission

    viewer = User(name="Leitor", email="leitor2@local.test", password_hash="x", role="collaborator", active=True)
    db_session.add(viewer)
    db_session.flush()
    dependency = require_permission("support:plan_write")

    with pytest.raises(HTTPException) as excinfo:
        dependency(viewer)
    assert excinfo.value.status_code == 403
    assert dependency(admin_user) is admin_user


# ---------------------------------------------------------------------------
# Projeto > Resultado-chave > Ação, com check-in na ação (pedido do usuário, 2026-10-28)
# ---------------------------------------------------------------------------
from app.modules.support.schemas import SupportPlanCheckInCreate  # noqa: E402


def _check_in(db, user, item, **kwargs):
    data = {"version": item.version, "text": "Avançou", "progress": 40, "health": "on_track", **kwargs}
    return planning_service.add_check_in(db, user, item.id, SupportPlanCheckInCreate(**data))


def _okr(db, user):
    project = _create(db, user, kind="project", title="OKR - Suporte")
    key_result = _create(db, user, kind="key_result", title="KR 1", parent_id=project.id)
    action = _create(db, user, kind="action", title="Ação 1", parent_id=key_result.id)
    return project, key_result, action


def test_key_result_and_action_need_the_right_parent(db_session, admin_user):
    project, key_result, action = _okr(db_session, admin_user)
    task = _create(db_session, admin_user, title="Tarefa solta")

    with pytest.raises(HTTPException):
        _create(db_session, admin_user, kind="key_result", title="Sem projeto")
    with pytest.raises(HTTPException):
        _create(db_session, admin_user, kind="key_result", title="Pai errado", parent_id=task.id)
    with pytest.raises(HTTPException):
        _create(db_session, admin_user, kind="action", title="Sem KR")
    with pytest.raises(HTTPException):
        _create(db_session, admin_user, kind="action", title="Direto no projeto", parent_id=project.id)
    with pytest.raises(HTTPException):
        _create(db_session, admin_user, kind="project", title="Projeto filho", parent_id=key_result.id)
    with pytest.raises(HTTPException) as excinfo:
        planning_service.update_item(db_session, action.id, SupportPlanItemUpdate(version=1, clear_parent=True))
    assert excinfo.value.status_code == 400


def test_check_in_records_progress_health_and_starts_the_action(db_session, admin_user):
    _, _, action = _okr(db_session, admin_user)

    item, _ = _check_in(db_session, admin_user, action, text="Fechei o desenho", progress=40, health="at_risk")

    assert (item.status, item.progress, item.health, item.version) == ("in_progress", 40, "at_risk", 2)
    assert item.last_check_in_at is not None
    entry = planning_service.item_detail(db_session, action.id)["updates"][0]
    assert (entry["is_check_in"], entry["progress"], entry["health"], entry["text"]) == (True, 40, "at_risk", "Fechei o desenho")
    assert (entry["status_from"], entry["status_to"]) == ("planned", "in_progress")


def test_check_in_is_only_for_open_actions_with_text_and_current_version(db_session, admin_user):
    project, key_result, action = _okr(db_session, admin_user)

    for wrong in (project, key_result):
        with pytest.raises(HTTPException):
            _check_in(db_session, admin_user, wrong)
    with pytest.raises(HTTPException):
        _check_in(db_session, admin_user, action, text="   ")
    with pytest.raises(HTTPException) as stale:
        _check_in(db_session, admin_user, action, version=9)
    assert stale.value.status_code == 409
    _progress(db_session, admin_user, action, status="done", result="Feito")
    with pytest.raises(HTTPException):
        _check_in(db_session, admin_user, action)
    reopened, _ = _progress(db_session, admin_user, action, status="in_progress")
    archived, _ = planning_service.set_archived(db_session, reopened.id, SupportPlanArchive(version=reopened.version))
    with pytest.raises(HTTPException):
        _check_in(db_session, admin_user, archived)


def test_progress_rolls_up_from_actions_to_key_results_and_project(db_session, admin_user):
    project, key_result, action = _okr(db_session, admin_user)
    second = _create(db_session, admin_user, kind="action", title="Ação 2", parent_id=key_result.id)
    other_kr = _create(db_session, admin_user, kind="key_result", title="KR 2", parent_id=project.id)
    task = _create(db_session, admin_user, title="Tarefa", parent_id=project.id)
    canceled = _create(db_session, admin_user, kind="action", title="Cancelada", parent_id=key_result.id)
    _progress(db_session, admin_user, canceled, status="canceled", text="Não vale")
    _check_in(db_session, admin_user, action, progress=50)
    _progress(db_session, admin_user, second, status="done", result="Ok")
    _progress(db_session, admin_user, task, status="done", result="Ok")

    progress = planning_service.progress_by_item(db_session)

    assert progress[action.id] == 50 and progress[second.id] == 100
    assert progress[key_result.id] == 75  # média de 50 e 100; a cancelada não entra
    assert progress[other_kr.id] == 0  # sem ações: vale o próprio avanço
    assert progress[project.id] == 58  # média de KR1 (75), KR2 (0) e a tarefa concluída (100)
    assert progress[task.id] is None


def test_board_list_and_summary_leave_out_key_results_and_actions(db_session, admin_user):
    project, key_result, action = _okr(db_session, admin_user)

    default = planning_service.list_items(db_session)
    only_actions = planning_service.list_items(db_session, kind="action")

    assert [item["id"] for item in default["items"]] == [project.id]
    assert [item["id"] for item in only_actions["items"]] == [action.id]
    assert planning_service.summary(db_session)["open"] == 1


def test_detail_of_project_and_key_result_lists_children_with_progress(db_session, admin_user):
    project, key_result, action = _okr(db_session, admin_user)
    _check_in(db_session, admin_user, action, progress=30, health="off_track")

    project_children = planning_service.item_detail(db_session, project.id)["children"]
    kr_detail = planning_service.item_detail(db_session, key_result.id)

    assert [(child["kind"], child["title"], child["progress"], child["children_total"]) for child in project_children] == [("key_result", "KR 1", 30, 1)]
    assert kr_detail["parent_title"] == "OKR - Suporte" and kr_detail["progress"] == 30
    action_child = kr_detail["children"][0]
    assert (action_child["kind"], action_child["progress"], action_child["health"]) == ("action", 30, "off_track")
