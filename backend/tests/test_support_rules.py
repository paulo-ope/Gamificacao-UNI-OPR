from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from app.modules.support import dashboard_macros, feedback_service, ranking_service, support_rules
from app.modules.support.models import SupportOpaAttendance, SupportOpaDimension
from app.modules.support.support_rules import FeedbackGoals, IndicatorGoals, RankingRules, SupportRules


def test_defaults_match_the_values_that_used_to_be_hardcoded():
    rules = support_rules.DEFAULT_RULES
    assert (rules.ranking.rating.good_min, rules.ranking.rating.good_points, rules.ranking.rating.bad_max, rules.ranking.rating.bad_points) == (4.0, 5, 3.9, -3)
    assert [(step.max_seconds, step.points) for step in rules.ranking.tmr_steps] == [(60, 5), (120, 3), (180, 1)]
    assert (rules.ranking.tmr_penalty.after_seconds, rules.ranking.tmr_penalty.block_seconds, rules.ranking.tmr_penalty.points) == (180, 180, -2)
    assert (rules.ranking.calls.block, rules.ranking.calls.block_points, rules.ranking.calls.week_penalty) == (12, 20, -10)
    assert rules.indicator_goals.csat == dashboard_macros.CSAT_TARGET
    assert rules.indicator_goals.tmr_seconds == dashboard_macros.TMR_TARGET_SECONDS
    assert rules.indicator_goals.tma_seconds == dashboard_macros.TMA_TARGET_SECONDS
    assert rules.indicator_goals.resolutivity_percent == dashboard_macros.RESOLUTIVITY_TARGET_PERCENT
    assert rules.indicator_goals.attention_margin_percent / 100 == dashboard_macros.ATTENTION_MARGIN
    default_goals = {key: target for key, _, _, target, _, _, _ in feedback_service.GOALS}
    assert feedback_service.goals_with(FeedbackGoals()) == feedback_service.GOALS
    assert default_goals["operational"] == 38 and default_goals["tmr"] == 140.0


def test_invalid_rules_are_rejected():
    with pytest.raises(ValidationError):  # faixa negativa acima da positiva
        RankingRules.model_validate({"rating": {"good_min": 3.0, "bad_max": 4.0}})
    with pytest.raises(ValidationError):  # faixas de TMR fora de ordem
        RankingRules.model_validate({"tmr_steps": [{"max_seconds": 120, "points": 3}, {"max_seconds": 60, "points": 5}]})
    with pytest.raises(ValidationError):  # penalidade começando antes da última faixa
        RankingRules.model_validate({"tmr_penalty": {"after_seconds": 100, "block_seconds": 60, "points": -1}})
    with pytest.raises(ValidationError):  # bloco de ligações zero
        RankingRules.model_validate({"calls": {"block": 0}})
    with pytest.raises(ValidationError):  # meta zero
        FeedbackGoals.model_validate({"operational": 0})
    with pytest.raises(ValidationError):  # nota acima de 5
        IndicatorGoals.model_validate({"csat": 6})


def test_load_returns_defaults_until_something_is_saved(db_session):
    assert support_rules.load_current(db_session) == support_rules.DEFAULT_RULES
    assert support_rules.last_change(db_session) == (None, None)


def test_save_creates_versions_and_same_day_save_replaces(db_session):
    first = SupportRules(feedback_goals=FeedbackGoals(operational=40))
    support_rules.save(db_session, first, saved_by="Ana", today=date(2026, 10, 16))
    db_session.commit()
    second = SupportRules(feedback_goals=FeedbackGoals(operational=45))
    support_rules.save(db_session, second, saved_by="Bia", today=date(2026, 10, 16))  # mesmo dia: substitui
    db_session.commit()

    assert support_rules.load_current(db_session).feedback_goals.operational == 45
    assert support_rules.last_change(db_session) == (date(2026, 10, 16), "Bia")
    assert len(support_rules._read_history(db_session)) == 1


def test_ranking_rules_for_month_use_the_version_in_force_at_month_end(db_session):
    old = SupportRules(ranking=RankingRules.model_validate({"calls": {"block": 12, "block_points": 20, "week_penalty": -10}}))
    new = SupportRules(ranking=RankingRules.model_validate({"calls": {"block": 10, "block_points": 30, "week_penalty": -5}}))
    support_rules.save(db_session, old, saved_by="Ana", today=date(2026, 8, 20))
    support_rules.save(db_session, new, saved_by="Ana", today=date(2026, 10, 3))
    db_session.commit()

    # Julho fechou antes da 1ª alteração: padrão. Agosto e setembro: versão de 20/08. Outubro: a de 03/10.
    assert support_rules.ranking_rules_for_month(db_session, date(2026, 7, 31)).calls.block_points == 20
    assert support_rules.ranking_rules_for_month(db_session, date(2026, 9, 30)).calls.block == 12
    assert support_rules.ranking_rules_for_month(db_session, date(2026, 10, 31)).calls.block == 10
    assert support_rules.ranking_rules_for_month(db_session, date(2026, 10, 31)).calls.block_points == 30


def test_corrupted_setting_falls_back_to_defaults(db_session):
    from app.services.calculation import upsert_setting

    upsert_setting(db_session, support_rules.SETTING_KEY, "isto não é json")
    db_session.commit()
    assert support_rules.load_current(db_session) == support_rules.DEFAULT_RULES


def test_rule_lines_follow_the_saved_values():
    rules = RankingRules.model_validate({"calls": {"block": 10, "block_points": 30, "week_penalty": -5}})
    calls = next(item for item in ranking_service.rule_lines(rules) if item["key"] == "calls")
    assert calls["lines"][0] == "A cada 10 ligações no mês: +30 pontos (40 ligações = +120 pontos)"
    assert calls["lines"][1] == "Cada semana completa com menos de 10 ligações: -5 pontos"
    default_text = ranking_service.rule_lines(support_rules.DEFAULT_RULES.ranking)
    assert next(item for item in default_text if item["key"] == "rating")["lines"][0] == "Nota a partir de 4,0: +5 pontos"


def test_custom_ranking_rules_change_the_points():
    rules = RankingRules.model_validate(
        {"rating": {"good_min": 4.5, "good_points": 10, "bad_max": 4.0, "bad_points": -5}, "tmr_steps": [{"max_seconds": 30, "points": 8}], "tmr_penalty": {"after_seconds": 90, "block_seconds": 30, "points": -1}}
    )
    assert ranking_service.rating_points(4.5, rules) == 10 and ranking_service.rating_points(4.2, rules) == 0 and ranking_service.rating_points(4.0, rules) == -5
    assert ranking_service.tmr_points(30, rules) == 8
    assert ranking_service.tmr_points(60, rules) == 0  # entre a última faixa e o início da penalidade
    assert ranking_service.tmr_points(100, rules) == -1 and ranking_service.tmr_points(121, rules) == -2


def test_closed_month_keeps_its_old_rules_after_a_change(db_session):
    db_session.add(SupportOpaDimension(dimension_type="user", source_id="a", name="Maycon Batista"))
    for n in range(12):
        db_session.add(
            SupportOpaAttendance(
                source_id=f"M{n}", attendant_id="a", first_human_attendant_id="a", channel="pabx", status="F",
                opened_at=datetime(2026, 9, 10, 15, tzinfo=timezone.utc), closed_at=datetime(2026, 9, 10, 16, tzinfo=timezone.utc),
                reached_human=True, rating=4.5,
            )
        )
    db_session.commit()
    today = date(2026, 10, 16)

    def points():
        row = ranking_service.monthly_ranking(db_session, month=date(2026, 9, 1), reference=today)["rows"][0]
        return row["rating"]["points"]

    assert points() == 5  # regra padrão: nota >= 4,0 vale +5
    changed = SupportRules(ranking=RankingRules.model_validate({"rating": {"good_min": 4.0, "good_points": 50, "bad_max": 3.9, "bad_points": -3}}))
    support_rules.save(db_session, changed, saved_by="Ana", today=date(2026, 10, 5))  # vale a partir de outubro
    db_session.commit()

    assert points() == 5  # setembro já fechado: continua com a regra da época
    october = ranking_service.monthly_ranking(db_session, month=date(2026, 10, 1), reference=today)
    assert october["rules"][0]["lines"][0] == "Nota a partir de 4,0: +50 pontos"
