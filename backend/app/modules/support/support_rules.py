"""Regras editáveis do Suporte (pedido do usuário, 2026-10-16), na aba Configuração > Regras.

Três conjuntos, todos com valor padrão igual ao que antes estava fixo no código:

- `ranking`: pontos do Ranking mensal (avaliação, faixas de TMR e penalidade, ligações);
- `feedback_goals`: as 8 metas individuais da aba Feedback;
- `indicator_goals`: metas dos Indicadores do Suporte e a margem de "Atenção" (vale também no Feedback).

Guardado como JSON em `app_settings` (sem tabela nova), em VERSÕES com a data em que passaram a valer. O
ranking de um mês FECHADO usa a versão em vigor no último dia daquele mês (mudar a regra hoje não mexe nos meses
passados); o mês em andamento e o resto do sistema usam a versão mais recente. Meses anteriores à primeira
alteração usam os valores padrão.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from pydantic import BaseModel, Field, ValidationError, model_validator
from sqlalchemy.orm import Session

from app.services.calculation import get_setting, upsert_setting

SETTING_KEY = "support_rules_history"
SETTING_DESCRIPTION = "Regras do Suporte (Ranking e metas), em versões por data de vigência."
MAX_VERSIONS = 60


class RatingRule(BaseModel):
    good_min: float = Field(4.5, ge=0, le=5)
    good_points: int = Field(10, ge=-1000, le=1000)
    bad_max: float = Field(3.99, ge=0, le=5)
    bad_points: int = Field(-10, ge=-1000, le=1000)

    @model_validator(mode="after")
    def _ordered(self) -> "RatingRule":
        if self.bad_max >= self.good_min:
            raise ValueError("A nota da faixa negativa deve ser menor que a da faixa positiva.")
        return self


class TmrStep(BaseModel):
    max_seconds: float = Field(gt=0, le=7200)
    points: int = Field(ge=-1000, le=1000)


class TmrPenalty(BaseModel):
    after_seconds: float = Field(120.0, gt=0, le=7200)
    block_seconds: float = Field(180.0, ge=1, le=7200)
    points: int = Field(-10, ge=-1000, le=1000)
    # Penalidade única (não bateu a meta); desligada, repete `points` a cada `block_seconds` excedidos.
    flat: bool = True


class CallsRule(BaseModel):
    """Ligações por SEMANA (dom-sáb): cada uma vale `call_points` até o teto `week_target`; cada ligação que faltou
    para a meta desconta `missing_penalty`. Semana parcial nas pontas do mês tem meta e teto proporcionais aos dias."""

    week_target: int = Field(12, ge=1, le=1000)
    call_points: int = Field(1, ge=-1000, le=1000)
    missing_penalty: int = Field(-1, ge=-1000, le=1000)


def _default_tmr_steps() -> list[TmrStep]:
    return [TmrStep(max_seconds=120, points=10)]


class RankingRules(BaseModel):
    rating: RatingRule = Field(default_factory=RatingRule)
    tmr_steps: list[TmrStep] = Field(default_factory=_default_tmr_steps, min_length=1, max_length=6)
    tmr_penalty: TmrPenalty = Field(default_factory=TmrPenalty)
    calls: CallsRule = Field(default_factory=CallsRule)

    @model_validator(mode="after")
    def _steps_ordered(self) -> "RankingRules":
        limits = [step.max_seconds for step in self.tmr_steps]
        if limits != sorted(set(limits)):
            raise ValueError("As faixas de TMR devem estar em ordem crescente, sem repetir o limite.")
        if self.tmr_penalty.after_seconds < limits[-1]:
            raise ValueError("A penalidade do TMR deve começar a partir do limite da última faixa.")
        return self


class FeedbackGoals(BaseModel):
    """Metas individuais da aba Feedback. Registros, atendimentos e ligações são SEMANAIS; avaliação e tempos não."""

    operational: float = Field(38, gt=0, le=100000)
    financial: float = Field(38, gt=0, le=100000)
    field: float = Field(25, gt=0, le=100000)
    opa_attendances: float = Field(96, gt=0, le=100000)
    calls: float = Field(12, gt=0, le=100000)
    rating: float = Field(4.50, gt=0, le=5)
    tma_seconds: float = Field(3600.0, gt=0, le=86400)
    tmr_seconds: float = Field(120.0, gt=0, le=86400)


class IndicatorGoals(BaseModel):
    """Metas dos Indicadores do Suporte; a margem de Atenção também vale para o Feedback."""

    csat: float = Field(4.5, gt=0, le=5)
    tmr_seconds: float = Field(120.0, gt=0, le=86400)
    tma_seconds: float = Field(3600.0, gt=0, le=86400)
    resolutivity_percent: float = Field(80.0, gt=0, le=100)
    attention_margin_percent: float = Field(10.0, ge=0, le=100)


class SupportRules(BaseModel):
    ranking: RankingRules = Field(default_factory=RankingRules)
    feedback_goals: FeedbackGoals = Field(default_factory=FeedbackGoals)
    indicator_goals: IndicatorGoals = Field(default_factory=IndicatorGoals)


DEFAULT_RULES = SupportRules()


def _read_history(db: Session) -> list[dict[str, Any]]:
    try:
        raw = json.loads(get_setting(db, SETTING_KEY, "[]"))
    except ValueError:
        return []
    return raw if isinstance(raw, list) else []


def _parse(version: dict[str, Any]) -> SupportRules:
    try:
        return SupportRules.model_validate(version.get("rules") or {})
    except ValidationError:
        return DEFAULT_RULES


def load_current(db: Session) -> SupportRules:
    """Versão mais recente (ou o padrão, se nunca foi alterada)."""
    history = _read_history(db)
    return _parse(history[-1]) if history else DEFAULT_RULES


def ranking_rules_for_month(db: Session, month_end: date) -> RankingRules:
    """Regras do Ranking em vigor no último dia do mês: a versão mais recente com vigência até essa data;
    antes da primeira alteração, o padrão. Para o mês em andamento, é a versão atual."""
    chosen = DEFAULT_RULES
    for version in _read_history(db):
        try:
            effective = date.fromisoformat(str(version.get("effective_from")))
        except ValueError:
            continue
        if effective <= month_end:
            chosen = _parse(version)
    return chosen.ranking


def last_change(db: Session) -> tuple[date | None, str | None]:
    history = _read_history(db)
    if not history:
        return None, None
    last = history[-1]
    try:
        effective = date.fromisoformat(str(last.get("effective_from")))
    except ValueError:
        effective = None
    return effective, last.get("saved_by")


def save(db: Session, rules: SupportRules, *, saved_by: str, today: date) -> None:
    """Grava uma nova versão a valer de `today`. Duas gravações no mesmo dia ficam numa versão só (a última)."""
    history = _read_history(db)
    version = {"effective_from": today.isoformat(), "saved_by": saved_by, "rules": rules.model_dump()}
    if history and history[-1].get("effective_from") == version["effective_from"]:
        history[-1] = version
    else:
        history.append(version)
    upsert_setting(db, SETTING_KEY, json.dumps(history[-MAX_VERSIONS:], ensure_ascii=False), SETTING_DESCRIPTION)
