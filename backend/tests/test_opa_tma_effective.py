"""TMA EFETIVO do OPA: da 1ª mensagem do atendente humano até a mensagem de conclusão.

Validado em 2026-10-12 contra os 203 atendimentos da Jennyfer exportados do OPA (04-10/10): 8m55s
calculado (n=156) contra 9m04s no painel. `tma_seconds` (duração total) não muda - o TMA efetivo é
uma coluna ao lado, nunca no lugar.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.modules.support.models import SupportOpaAttendance, SupportOpaDimension
from app.modules.support.opa_ingestion import _effective_tma_seconds, run_tmr_history_backfill
from tests.test_opa_ingestion import FakeOpaClient

HUMANS = {"agente-1"}
CONCLUSION = "Seu atendimento foi concluído com sucesso! ✅\nSe precisar de qualquer coisa, é só nos chamar."


def _at(minute: int, second: int = 0) -> str:
    return f"2026-10-04T17:{minute:02d}:{second:02d}+00:00"


def test_effective_tma_runs_from_first_human_message_to_the_conclusion_message():
    messages = [
        {"tipo": "assistant", "data": _at(0)},  # log interno do Theo: não conta
        {"id_user": "cliente", "data": _at(1)},
        {"id_atend": "bot-1", "data": _at(2), "mensagem": "Olá! Sou o assistente virtual."},
        {"id_atend": "agente-1", "data": _at(10), "mensagem": "Oi, vou te ajudar."},
        {"id_atend": "agente-1", "data": _at(17), "mensagem": CONCLUSION},
        # O fechamento no OPA vem depois (pesquisa de satisfação, timeout): não entra no tempo.
        {"id_atend": "bot-1", "data": _at(40), "mensagem": "Como foi o atendimento?"},
    ]

    assert _effective_tma_seconds(messages, HUMANS) == 7 * 60


def test_effective_tma_recognizes_the_conclusion_message_ignoring_case_and_accents():
    messages = [
        {"id_atend": "agente-1", "data": _at(0), "mensagem": "Boa tarde"},
        {"id_atend": "agente-1", "data": _at(5), "mensagem": "SEU ATENDIMENTO FOI CONCLUIDO COM SUCESSO!"},
        {"id_atend": "agente-1", "data": _at(9), "mensagem": "Obrigado pelo contato."},
    ]

    assert _effective_tma_seconds(messages, HUMANS) == 5 * 60


def test_effective_tma_falls_back_to_the_last_human_message_without_a_conclusion_message():
    messages = [
        {"id_atend": "agente-1", "data": _at(3), "mensagem": "Oi"},
        {"id_user": "cliente", "data": _at(4)},
        {"id_atend": "agente-1", "data": _at(9), "mensagem": "Pronto, resolvido."},
        {"id_atend": "bot-1", "data": _at(30), "mensagem": "Pesquisa"},
    ]

    assert _effective_tma_seconds(messages, HUMANS) == 6 * 60


def test_effective_tma_is_none_without_any_human_message():
    messages = [
        {"id_user": "cliente", "data": _at(1)},
        {"id_atend": "bot-1", "data": _at(2), "mensagem": "Resolvido pelo bot."},
    ]

    assert _effective_tma_seconds(messages, HUMANS) is None
    assert _effective_tma_seconds([], HUMANS) is None


def test_effective_tma_ignores_human_messages_without_a_parseable_timestamp():
    messages = [
        {"id_atend": "agente-1", "mensagem": "sem data"},
        {"id_atend": "agente-1", "data": _at(2), "mensagem": "Oi"},
        {"id_atend": "agente-1", "data": _at(4), "mensagem": "Tchau"},
    ]

    assert _effective_tma_seconds(messages, HUMANS) == 2 * 60


def _closed(source_id: str, closed_hour: int, **overrides) -> SupportOpaAttendance:
    base = dict(
        source_id=source_id,
        opened_at=datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc),
        closed_at=datetime(2026, 10, 4, closed_hour, 0, tzinfo=timezone.utc),
        tma_seconds=3 * 3600,
        tmr_all_responses_seconds=30,
        reached_human=True,
        raw_payload={},
    )
    base.update(overrides)
    return SupportOpaAttendance(**base)


def _human_agent(db_session) -> None:
    db_session.add(SupportOpaDimension(dimension_type="user", source_id="agente-1", name="Agente", payload_json={"tipo": "user"}))


def test_backfill_fills_effective_tma_for_human_attendances_and_keeps_total_duration(db_session):
    _human_agent(db_session)
    db_session.add_all(
        [
            _closed("com-humano", 16),
            _closed("so-bot", 17, reached_human=False),
            _closed("ja-calculado", 18, tma_effective_seconds=60),
        ]
    )
    db_session.flush()
    client = FakeOpaClient(
        [],
        messages={
            "com-humano": [
                {"id_atend": "agente-1", "data": _at(0), "mensagem": "Oi"},
                {"id_atend": "agente-1", "data": _at(9), "mensagem": CONCLUSION},
            ],
        },
    )

    result = run_tmr_history_backfill(db_session, client, limit=10)

    assert result["processed"] == 1
    db_session.expire_all()
    rows = {row.source_id: row for row in db_session.query(SupportOpaAttendance)}
    assert rows["com-humano"].tma_effective_seconds == 9 * 60
    assert rows["com-humano"].tma_seconds == 3 * 3600
    assert rows["so-bot"].tma_effective_seconds is None
    assert rows["ja-calculado"].tma_effective_seconds == 60


def test_backfill_processes_the_most_recent_pending_effective_tma_first(db_session):
    _human_agent(db_session)
    db_session.add_all(
        [_closed("velho", 13), _closed("meio", 15), _closed("recente", 20)]
    )
    db_session.flush()
    messages = {
        key: [
            {"id_atend": "agente-1", "data": _at(0), "mensagem": "Oi"},
            {"id_atend": "agente-1", "data": _at(4), "mensagem": "Tchau"},
        ]
        for key in ("velho", "meio", "recente")
    }

    # Lote de 4: metade (2) vai para o TMA efetivo, e a fila de TMR (vazia aqui) não consome mais.
    run_tmr_history_backfill(db_session, FakeOpaClient([], messages=messages), limit=4)

    db_session.expire_all()
    done = {row.source_id for row in db_session.query(SupportOpaAttendance) if row.tma_effective_seconds is not None}
    assert done == {"recente", "meio"}


def test_overview_exposes_effective_tma_next_to_total_duration_with_explicit_coverage(db_session):
    from datetime import date

    from app.modules.support import opa_overview_service
    from app.modules.support.opa_filters import OpaAttendanceFilters

    db_session.add_all(
        [
            _closed("a", 16, tma_effective_seconds=600),
            _closed("b", 17, tma_effective_seconds=1200),
            _closed("c", 18),  # humano, mas ainda sem TMA efetivo (histórico não reprocessado)
            _closed("d", 19, reached_human=False),  # só bot: nunca entra na média
        ]
    )
    db_session.flush()
    filters = OpaAttendanceFilters(date_from=date(2026, 10, 4), date_to=date(2026, 10, 4))

    metrics = opa_overview_service.overview_metrics(db_session, filters)
    expanded = opa_overview_service.expanded_overview(db_session, filters)

    assert metrics["average_tma_effective_seconds"] == 900.0
    assert metrics["average_duration_seconds"] == 3 * 3600  # a duração total não mudou
    assert metrics["tma_effective_coverage"] == {"count": 2, "total": 4, "percentage": 50.0}
    assert expanded["average_tma_effective_seconds"]["current"] == 900.0
    assert expanded["tma_effective_coverage"]["count"] == 2


# ---- TMR EFETIVO (aproximação do TMR do OPA) -------------------------------------------------

from app.modules.support.opa_ingestion import _effective_tmr_seconds  # noqa: E402


def _client(minute: int, second: int = 0) -> dict:
    return {"id_user": "cliente", "data": _at(minute, second), "mensagem": "pergunta"}


def test_effective_tmr_ignores_the_bot_only_phase_and_averages_gaps_after_the_human_arrives():
    messages = [
        # Fase só com o bot: o cliente espera 10 min por um humano - NÃO entra no TMR efetivo.
        _client(0),
        {"tipo": "assistant", "data": _at(1)},
        {"id_atend": "agente-1", "data": _at(10), "mensagem": "Olá, sou o atendente."},
        # Depois da entrada do humano: respostas em 30 s e 90 s.
        _client(11, 0),
        {"id_atend": "agente-1", "data": _at(11, 30), "mensagem": "Já verifico."},
        _client(15, 0),
        {"id_atend": "agente-1", "data": _at(16, 30), "mensagem": "Pronto."},
    ]

    assert _effective_tmr_seconds(messages, HUMANS) == 60


def test_effective_tmr_measures_from_the_last_client_message_before_the_reply():
    messages = [
        {"id_atend": "agente-1", "data": _at(0), "mensagem": "Oi"},
        _client(5, 0),
        _client(5, 40),  # a pergunta final do cliente chega 40 s antes da resposta
        {"id_atend": "agente-1", "data": _at(6, 0), "mensagem": "Respondido."},
    ]

    assert _effective_tmr_seconds(messages, HUMANS) == 20


def test_effective_tmr_counts_a_bot_reply_after_the_human_has_joined():
    messages = [
        {"id_atend": "agente-1", "data": _at(0), "mensagem": "Oi"},
        _client(2, 0),
        {"tipo": "assistant", "data": _at(2, 30)},
    ]

    assert _effective_tmr_seconds(messages, HUMANS) == 30


def test_effective_tmr_discards_gaps_above_one_hour_and_is_none_when_nothing_is_measurable():
    only_long_gap = [
        {"id_atend": "agente-1", "data": _at(0), "mensagem": "Oi"},
        {"id_user": "cliente", "data": "2026-10-04T18:00:00+00:00"},
        {"id_atend": "agente-1", "data": "2026-10-04T19:30:00+00:00", "mensagem": "Desculpe a demora."},
    ]
    no_human = [_client(0), {"id_atend": "bot-1", "data": _at(1), "mensagem": "Bot"}]
    no_client_after_human = [{"id_atend": "agente-1", "data": _at(0), "mensagem": "Oi"}]

    assert _effective_tmr_seconds(only_long_gap, HUMANS) is None
    assert _effective_tmr_seconds(no_human, HUMANS) is None
    assert _effective_tmr_seconds(no_client_after_human, HUMANS) is None


def test_backfill_fills_effective_tmr_together_with_effective_tma(db_session):
    _human_agent(db_session)
    db_session.add(_closed("com-humano", 16))
    db_session.flush()
    client = FakeOpaClient(
        [],
        messages={
            "com-humano": [
                {"id_atend": "agente-1", "data": _at(0), "mensagem": "Oi"},
                _client(2, 0),
                {"id_atend": "agente-1", "data": _at(2, 45), "mensagem": CONCLUSION},
            ]
        },
    )

    run_tmr_history_backfill(db_session, client, limit=10)

    db_session.expire_all()
    row = db_session.query(SupportOpaAttendance).filter_by(source_id="com-humano").one()
    assert row.tma_effective_seconds == 165
    assert row.tmr_effective_seconds == 45
    assert row.tmr_seconds is not None or row.tmr_all_responses_seconds is not None  # as métricas antigas seguem


def test_overview_exposes_effective_tmr_with_coverage_over_closed_attendances(db_session):
    from datetime import date

    from app.modules.support import opa_overview_service
    from app.modules.support.opa_filters import OpaAttendanceFilters

    db_session.add_all(
        [
            _closed("a", 16, tmr_effective_seconds=30),
            _closed("b", 17, tmr_effective_seconds=90),
            _closed("c", 18),
        ]
    )
    db_session.flush()
    filters = OpaAttendanceFilters(date_from=date(2026, 10, 4), date_to=date(2026, 10, 4))

    metrics = opa_overview_service.overview_metrics(db_session, filters)
    expanded = opa_overview_service.expanded_overview(db_session, filters)

    assert metrics["average_tmr_effective_seconds"] == 60.0
    assert metrics["tmr_effective_coverage"] == {"count": 2, "total": 3, "percentage": (2 / 3) * 100}
    assert expanded["average_tmr_effective_seconds"]["current"] == 60.0


# ---- TMR HUMANO (só humano, a partir da entrada dele) ----------------------------------------

from app.modules.support.opa_ingestion import _human_tmr_after_entry_seconds  # noqa: E402


def test_human_tmr_ignores_the_wait_for_the_human_and_the_bot_replies():
    messages = [
        # Fase só com o bot e espera de 12 min pelo humano: fica fora do TMR humano.
        _client(0),
        {"tipo": "assistant", "data": _at(1)},
        {"id_atend": "agente-1", "data": _at(12), "mensagem": "Olá, sou o atendente."},
        # Depois da entrada: o bot responde rápido (10 s), mas só a resposta HUMANA fecha o intervalo.
        _client(13, 0),
        {"tipo": "assistant", "data": _at(13, 10)},
        {"id_atend": "agente-1", "data": _at(13, 50), "mensagem": "Já verifico."},
        _client(20, 0),
        {"id_atend": "agente-1", "data": _at(21, 30), "mensagem": "Pronto."},
    ]

    assert _human_tmr_after_entry_seconds(messages, HUMANS) == 70  # (50 s + 90 s) / 2


def test_human_tmr_measures_from_the_first_client_message_of_a_burst():
    messages = [
        {"id_atend": "agente-1", "data": _at(0), "mensagem": "Oi"},
        _client(5, 0),
        _client(5, 40),
        {"id_atend": "agente-1", "data": _at(6, 0), "mensagem": "Respondido."},
    ]

    assert _human_tmr_after_entry_seconds(messages, HUMANS) == 60


def test_human_tmr_is_none_without_human_or_without_a_measurable_reply():
    no_human = [_client(0), {"id_atend": "bot-1", "data": _at(1), "mensagem": "Bot"}]
    human_only_talks = [{"id_atend": "agente-1", "data": _at(0), "mensagem": "Oi"}]

    assert _human_tmr_after_entry_seconds(no_human, HUMANS) is None
    assert _human_tmr_after_entry_seconds(human_only_talks, HUMANS) is None


def test_backfill_fills_human_tmr_and_keeps_the_general_tmr_unchanged(db_session):
    _human_agent(db_session)
    db_session.add(_closed("com-humano", 16))
    db_session.flush()
    messages = [
        _client(0, 0),
        {"tipo": "assistant", "data": _at(0, 20)},  # TMR geral conta o bot: 20 s
        {"id_atend": "agente-1", "data": _at(10, 0), "mensagem": "Olá"},
        _client(11, 0),
        {"id_atend": "agente-1", "data": _at(11, 45), "mensagem": CONCLUSION},
    ]

    run_tmr_history_backfill(db_session, FakeOpaClient([], messages={"com-humano": messages}), limit=10)

    db_session.expire_all()
    row = db_session.query(SupportOpaAttendance).filter_by(source_id="com-humano").one()
    assert row.tmr_human_live_seconds == 45
    assert row.tmr_all_responses_seconds is not None and row.tmr_all_responses_seconds != 45


# ---- ESPERA PELO HUMANO ("1ª resposta humana") -----------------------------------------------

from app.modules.support.opa_ingestion import _human_wait_seconds  # noqa: E402


def test_human_wait_runs_from_the_last_bot_message_to_the_first_human_message():
    messages = [
        _client(0),
        {"tipo": "assistant", "data": _at(1), "mensagem": "Entendi, vou ajudar."},  # conversa com o bot
        _client(30),
        {"tipo": "assistant", "data": _at(31), "mensagem": "Por favor, aguarde um atendente disponível!"},
        _client(35),  # o cliente insiste na fila: não muda a referência (é o bot que transfere)
        {"id_atend": "agente-1", "data": _at(41), "mensagem": "Olá, sou o atendente."},
        {"id_atend": "agente-1", "data": _at(45), "mensagem": "Já verifico."},
    ]

    assert _human_wait_seconds(messages, HUMANS) == 10 * 60  # 31 -> 41, sem os 30 min com o bot


def test_human_wait_falls_back_to_the_last_client_message_without_any_bot_message():
    messages = [_client(10, 0), _client(12, 0), {"id_atend": "agente-1", "data": _at(12, 45), "mensagem": "Oi"}]

    assert _human_wait_seconds(messages, HUMANS) == 45


def test_human_wait_is_none_without_human_or_without_any_earlier_message():
    no_human = [_client(0), {"tipo": "assistant", "data": _at(1)}]
    human_first = [{"id_atend": "agente-1", "data": _at(0), "mensagem": "Oi"}]

    assert _human_wait_seconds(no_human, HUMANS) is None
    assert _human_wait_seconds(human_first, HUMANS) is None


def test_backfill_fills_human_wait_and_the_overview_averages_it_with_coverage(db_session):
    from datetime import date

    from app.modules.support import opa_overview_service
    from app.modules.support.opa_filters import OpaAttendanceFilters

    _human_agent(db_session)
    db_session.add_all([_closed("a", 16), _closed("b", 17, human_wait_seconds=300), _closed("c", 18, human_wait_seconds=None)])
    db_session.flush()
    messages = {
        "a": [
            _client(0),
            {"tipo": "assistant", "data": _at(1), "mensagem": "Aguarde um atendente."},
            {"id_atend": "agente-1", "data": _at(4), "mensagem": "Oi"},
        ]
    }

    run_tmr_history_backfill(db_session, FakeOpaClient([], messages=messages), limit=10)

    db_session.expire_all()
    assert db_session.query(SupportOpaAttendance).filter_by(source_id="a").one().human_wait_seconds == 180
    metrics = opa_overview_service.overview_metrics(
        db_session, OpaAttendanceFilters(date_from=date(2026, 10, 4), date_to=date(2026, 10, 4))
    )
    assert metrics["average_human_wait_seconds"] == 240.0  # (180 + 300) / 2
    assert metrics["human_wait_coverage"]["count"] == 2 and metrics["human_wait_coverage"]["total"] == 3
