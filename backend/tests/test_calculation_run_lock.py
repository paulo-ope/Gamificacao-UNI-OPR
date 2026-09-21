"""P0-4 da auditoria técnica de 2026-09-15 (`docs/auditoria-tecnica-geral-2026-09-15.md`):
`/calculation-runs/calculate` (e o recálculo automático em `recalculate_current_period`) não
tinham NENHUMA proteção contra duas execuções do mesmo ciclo (mesmo mês/ano/regional) em
paralelo - sem lock, sem `UniqueConstraint`. A correção adiciona `CalculationRunLock`
(`app/models.py`), cuja garantia é o `UniqueConstraint(lock_key)` do banco, e
`calculation_closure.py::calculation_cycle_lock`/`acquire_calculation_lock`/
`release_calculation_lock`, usados em ambos os pontos de entrada
(`calculation_runs.py::calculate` e `calculation.py::recalculate_current_period`).

Os testes que provam a exclusão mútua de verdade (marcados "THREAD REAL" abaixo) usam DUAS
conexões genuinamente independentes - um arquivo SQLite temporário (não `:memory:`/`StaticPool`,
que dão a MESMA conexão física para toda sessão do teste) - porque a garantia que queremos provar
é do BANCO (`UniqueConstraint`), não de algo em memória do processo Python. Chamar a função duas
vezes em sequência na mesma sessão NÃO prova isso: as duas nunca disputam a mesma linha ao mesmo
tempo.
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models import (
    AppSetting,
    CalculationRun,
    CalculationRunLock,
    Collaborator,
    HealthRule,
    ScoringGroup,
    ScoringSubjectRule,
    ServiceOrder,
)
from app.services.calculation import calculate_scores
from app.services.calculation_closure import (
    CALCULATION_LOCK_STALE_AFTER,
    acquire_calculation_lock,
    calculation_cycle_lock,
    now_utc,
    release_calculation_lock,
)


def _seed_minimal_period(db_session, make_collaborator, *, month=6, year=2026, regional="UNI SUL"):
    """Dados mínimos para `calculate_scores` produzir 1 colaborador com pontuação - mesma receita
    já usada em `test_calculation_closure.py`."""
    collaborator = make_collaborator(name="Tecnico Trava", regional=regional, registered=True)
    group = ScoringGroup(name="Manutencao", default_points=10.0, active=True)
    db_session.add(group)
    db_session.flush()
    db_session.add(ScoringSubjectRule(group_id=group.id, os_type="Manutencao", os_subject="Reparo", use_group_default=True, active=True))
    db_session.add(AppSetting(key="point_value", value="2.00"))
    db_session.add(HealthRule(name="Boa", min_sla=0, max_recurrence_rate=100, multiplier=1.0, active=True))
    db_session.add(
        ServiceOrder(
            os_code=f"OS-LOCK-{month}-{year}",
            contract_id="C-1",
            customer_login="cli.lock",
            customer_name="Cliente Trava",
            collaborator_id=collaborator.id,
            regional=regional,
            os_type="Manutencao",
            os_subject="Reparo",
            diagnosis="Falha",
            status="Concluida",
            sla_status="Dentro do prazo",
            opened_at=datetime(year, month, 5, tzinfo=timezone.utc),
            closed_at=datetime(year, month, 5, tzinfo=timezone.utc),
        )
    )
    db_session.commit()
    return collaborator


# --- Unidade: acquire/release/steal (sessão única, sem race real) -------------------------------


def test_different_cycles_never_share_a_lock_key(db_session):
    """E: mês diferente, regional diferente e mesmo mês/regional (chave repetida só depois de
    liberada) nunca colidem entre si."""
    key_a = acquire_calculation_lock(db_session, 6, 2026, "UNI SUL")
    key_b = acquire_calculation_lock(db_session, 7, 2026, "UNI SUL")
    key_c = acquire_calculation_lock(db_session, 6, 2026, "UNI NORTE")
    key_d = acquire_calculation_lock(db_session, 6, 2026, None)
    assert len({key_a, key_b, key_c, key_d}) == 4

    release_calculation_lock(db_session, key_a)
    # depois de liberada, a MESMA chave pode ser adquirida de novo sem esperar o timeout de stale.
    key_a_again = acquire_calculation_lock(db_session, 6, 2026, "UNI SUL")
    assert key_a_again == key_a

    for key in (key_a_again, key_b, key_c, key_d):
        release_calculation_lock(db_session, key)


def test_a_fresh_lock_blocks_a_second_acquire_for_the_same_cycle(db_session, admin_user):
    db_session.add(
        CalculationRunLock(
            lock_key="2026-06:UNI SUL", reference_month=6, reference_year=2026,
            regional="UNI SUL", locked_at=now_utc(), locked_by=admin_user.id,
        )
    )
    db_session.commit()

    with pytest.raises(HTTPException) as excinfo:
        acquire_calculation_lock(db_session, 6, 2026, "UNI SUL")
    assert excinfo.value.status_code == 409
    assert db_session.query(CalculationRunLock).count() == 1, "a tentativa rejeitada nao pode ter criado uma segunda linha"


def test_a_stale_lock_is_stolen_instead_of_blocking_forever(db_session, admin_user):
    """G (variante crash): um processo derrubado no meio do calculo (kill -9, OOM) nunca chama
    `release_calculation_lock` - sem o roubo de trava velha, o ciclo ficaria travado para sempre."""
    stale_at = now_utc() - CALCULATION_LOCK_STALE_AFTER - timedelta(minutes=1)
    db_session.add(
        CalculationRunLock(
            lock_key="2026-06:UNI SUL", reference_month=6, reference_year=2026,
            regional="UNI SUL", locked_at=stale_at, locked_by=admin_user.id,
        )
    )
    db_session.commit()

    lock_key = acquire_calculation_lock(db_session, 6, 2026, "UNI SUL")
    assert lock_key == "2026-06:UNI SUL"
    assert db_session.query(CalculationRunLock).count() == 1
    release_calculation_lock(db_session, lock_key)


def test_exception_inside_the_locked_block_still_releases_the_lock(db_session, make_collaborator, monkeypatch):
    """G: uma falha no meio do cálculo (bug num passo qualquer) não pode deixar a trava presa -
    senão o PRÓXIMO recálculo legítimo do mesmo ciclo ficaria bloqueado por um erro que já
    aconteceu e nunca mais vai se repetir."""
    _seed_minimal_period(db_session, make_collaborator)

    def _boom(*args, **kwargs):
        raise RuntimeError("falha simulada no meio do calculo")

    monkeypatch.setattr("app.services.calculation.calculate_regional_health", _boom)

    with pytest.raises(RuntimeError):
        with calculation_cycle_lock(db_session, 6, 2026, "UNI SUL", user=None):
            calculate_scores(db_session, reference_month=6, reference_year=2026, regional="UNI SUL", allow_paid_revision=True)

    assert db_session.query(CalculationRunLock).count() == 0, "a trava tem que ter sido liberada mesmo com excecao no meio do calculo"

    # nao ficou preso: o mesmo ciclo pode ser travado de novo imediatamente, sem esperar o timeout.
    lock_key = acquire_calculation_lock(db_session, 6, 2026, "UNI SUL")
    release_calculation_lock(db_session, lock_key)


# --- HTTP: comportamento observável ponta a ponta -----------------------------------------------


def test_sequential_recalculation_of_the_same_cycle_is_never_blocked_by_a_previous_call(client, db_session, make_collaborator):
    """A: duas chamadas SEQUENCIAIS (uma só depois da outra terminar) continuam permitidas - é o
    comportamento já existente e aceito (cada recálculo cria um novo rascunho; a limpeza de
    rascunhos antigos é outra funcionalidade, `prune_superseded_drafts`, desligada por padrão). A
    trava só bloqueia SOBREPOSIÇÃO, nunca repetição sequencial."""
    _seed_minimal_period(db_session, make_collaborator)
    payload = {"reference_month": 6, "reference_year": 2026, "regional": "UNI SUL", "create_revision": True}

    first = client.post("/api/calculation-runs/calculate", json=payload)
    assert first.status_code == 200, first.text
    second = client.post("/api/calculation-runs/calculate", json=payload)
    assert second.status_code == 200, second.text

    assert first.json()["id"] != second.json()["id"]
    assert db_session.query(CalculationRunLock).count() == 0, "a trava do primeiro calculo tem que ter sido liberada"


def test_lock_does_not_interfere_with_the_existing_paid_period_rule(client, db_session, make_collaborator):
    """F: a regra de reprocessamento já existente (período pago não pode ser recalculado sem
    revisão explícita, `ensure_period_not_closed`) continua funcionando exatamente como antes - a
    nova trava não pode mascarar essa mensagem nem ficar presa depois do primeiro cálculo."""
    _seed_minimal_period(db_session, make_collaborator)
    payload = {"reference_month": 6, "reference_year": 2026, "regional": "UNI SUL", "create_revision": True}

    first = client.post("/api/calculation-runs/calculate", json=payload)
    assert first.status_code == 200, first.text
    run_id = first.json()["id"]
    for status in ["review", "approved", "paid"]:
        resp = client.patch(f"/api/calculation-runs/{run_id}/status", json={"status": status})
        assert resp.status_code == 200, resp.text

    blocked = client.post(
        "/api/calculation-runs/calculate",
        json={"reference_month": 6, "reference_year": 2026, "regional": "UNI SUL"},
    )
    assert blocked.status_code == 409
    assert "pago" in blocked.json()["detail"].lower(), "tem que ser a mensagem da regra de periodo pago, nao a da trava nova"
    assert db_session.query(CalculationRunLock).count() == 0, "a trava do primeiro calculo (que teve sucesso) tem que ter sido liberada"


# --- THREAD REAL: prova de exclusão mútua entre conexões genuinamente independentes --------------


def _two_independent_sqlite_sessions(tmp_path):
    db_path = tmp_path / "calculation_lock_race.sqlite3"
    url = f"sqlite:///{db_path}"
    engine_a = create_engine(url, connect_args={"timeout": 30})
    engine_b = create_engine(url, connect_args={"timeout": 30})
    Base.metadata.create_all(engine_a)
    session_a = sessionmaker(bind=engine_a, expire_on_commit=False)()
    session_b = sessionmaker(bind=engine_b, expire_on_commit=False)()
    return engine_a, engine_b, session_a, session_b


def test_thread_real_concurrent_lock_acquisition_only_one_side_wins(tmp_path):
    """H + B + C: duas THREADS reais, cada uma com sua PRÓPRIA conexão (arquivo SQLite
    compartilhado, não `StaticPool`), tentando adquirir a MESMA trava ao mesmo tempo via uma
    barreira. Prova que a garantia é do BANCO (`UniqueConstraint`), não de uma variável em memória
    do processo: só uma pode vencer, a outra tem que ser rejeitada com 409 imediatamente."""
    engine_a, engine_b, session_a, session_b = _two_independent_sqlite_sessions(tmp_path)
    barrier = threading.Barrier(2)
    results: dict[str, tuple] = {}

    def attempt(name: str, session) -> None:
        barrier.wait(timeout=5)
        try:
            lock_key = acquire_calculation_lock(session, 6, 2026, "UNI SUL")
            results[name] = ("ok", lock_key)
        except HTTPException as exc:
            results[name] = ("conflict", exc.status_code)

    threads = [threading.Thread(target=attempt, args=("a", session_a)), threading.Thread(target=attempt, args=("b", session_b))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)

    assert set(results) == {"a", "b"}, f"as duas threads precisam terminar: {results}"
    statuses = sorted(outcome[0] for outcome in results.values())
    assert statuses == ["conflict", "ok"], results
    assert next(outcome[1] for outcome in results.values() if outcome[0] == "conflict") == 409

    session_a.close()
    session_b.close()
    verify = sessionmaker(bind=engine_a, expire_on_commit=False)()
    assert verify.query(CalculationRunLock).count() == 1, "so uma linha de trava pode existir apos a disputa"
    verify.close()
    engine_a.dispose()
    engine_b.dispose()


def test_thread_real_concurrent_calculate_scores_creates_exactly_one_run(tmp_path):
    """B + C + D: o mesmo cenário acima, mas rodando o fluxo INTEIRO (`calculation_cycle_lock` +
    `calculate_scores` + commit, o que o router realmente faz) em vez de só a trava - prova que a
    segunda tentativa concorrente é rejeitada ANTES de fazer qualquer trabalho (nunca chega a
    calcular pontuação nem a aplicar efeito derivado nenhum), então só existe UM `CalculationRun`
    e um único conjunto de pontuação ao final."""
    engine_a, engine_b, session_a, session_b = _two_independent_sqlite_sessions(tmp_path)

    seed = sessionmaker(bind=engine_a, expire_on_commit=False)()
    collaborator = Collaborator(name="Tecnico Race", role="Tecnico", regional="UNI SUL", active=True, is_registered=True)
    seed.add(collaborator)
    seed.flush()
    group = ScoringGroup(name="Manutencao", default_points=10.0, active=True)
    seed.add(group)
    seed.flush()
    seed.add(ScoringSubjectRule(group_id=group.id, os_type="Manutencao", os_subject="Reparo", use_group_default=True, active=True))
    seed.add(AppSetting(key="point_value", value="2.00"))
    seed.add(HealthRule(name="Boa", min_sla=0, max_recurrence_rate=100, multiplier=1.0, active=True))
    seed.add(
        ServiceOrder(
            os_code="OS-RACE-1", contract_id="C-1", customer_login="cli.race", customer_name="Cliente Race",
            collaborator_id=collaborator.id, regional="UNI SUL", os_type="Manutencao", os_subject="Reparo",
            diagnosis="Falha", status="Concluida", sla_status="Dentro do prazo",
            opened_at=datetime(2026, 6, 5, tzinfo=timezone.utc), closed_at=datetime(2026, 6, 5, tzinfo=timezone.utc),
        )
    )
    seed.commit()
    seed.close()

    barrier = threading.Barrier(2)
    results: dict[str, tuple] = {}

    def attempt(name: str, session) -> None:
        barrier.wait(timeout=5)
        try:
            with calculation_cycle_lock(session, 6, 2026, "UNI SUL", user=None):
                run = calculate_scores(
                    session,
                    reference_month=6,
                    reference_year=2026,
                    regional="UNI SUL",
                    allow_paid_revision=True,
                )
                session.commit()
                results[name] = ("ok", run.id)
        except HTTPException as exc:
            session.rollback()
            results[name] = ("conflict", exc.status_code)
        except Exception as exc:  # pragma: no cover - só apareceria com um bug real na trava
            session.rollback()
            results[name] = ("error", repr(exc))

    threads = [threading.Thread(target=attempt, args=("a", session_a)), threading.Thread(target=attempt, args=("b", session_b))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert set(results) == {"a", "b"}, f"as duas threads precisam terminar: {results}"
    statuses = sorted(outcome[0] for outcome in results.values())
    assert statuses == ["conflict", "ok"], results
    assert next(outcome[1] for outcome in results.values() if outcome[0] == "conflict") == 409

    session_a.close()
    session_b.close()
    verify = sessionmaker(bind=engine_a, expire_on_commit=False)()
    runs = verify.execute(
        select(CalculationRun).where(CalculationRun.reference_month == 6, CalculationRun.reference_year == 2026, CalculationRun.regional == "UNI SUL")
    ).scalars().all()
    assert len(runs) == 1, "a dupla concorrente so pode ter produzido UM CalculationRun"
    assert verify.query(CalculationRunLock).count() == 0, "a trava tem que ter sido liberada apos o vencedor commitar"
    verify.close()
    engine_a.dispose()
    engine_b.dispose()
