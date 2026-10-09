"""Contrato de resposta da TV do SGP Suporte (`GET /support/tv/snapshot`).

Mesmas regras do resto do módulo: tempos sempre em segundos (unidade no nome do campo), `None`
significa "não sabemos" (nunca 0) e toda média com cobertura parcial traz o denominador.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class SupportTvCoverage(BaseModel):
    count: int
    total: int
    percentage: float | None = None


class SupportTvTmr(BaseModel):
    """TMR geral (conta resposta de bot) contra a meta operacional."""

    current_seconds: float | None = None
    previous_seconds: float | None = None
    target_seconds: int
    # ok = dentro da meta; above = acima da meta; no_data = sem atendimento com TMR no dia.
    status: Literal["ok", "above", "no_data"]
    coverage: SupportTvCoverage


class SupportTvKpis(BaseModel):
    total_today: int
    previous_day_total: int
    closed_today: int
    closure_rate: float | None = None
    # Sem encerramento e abertos nas últimas 24 h - não depende da virada do dia.
    open_now: int
    tmr_all_responses: SupportTvTmr
    average_tmr_human_seconds: float | None = None
    previous_average_tmr_human_seconds: float | None = None
    average_first_response_seconds: float | None = None
    average_rating: float | None = None
    previous_average_rating: float | None = None


class SupportTvHourlyPoint(BaseModel):
    hour: int
    # None nas horas que ainda não chegaram (hoje é parcial) - nunca 0.
    today: int | None = None
    baseline_average: float | None = None


class SupportTvHourly(BaseModel):
    current_hour: int
    # Quantas semanas anteriores (mesmo dia da semana) tinham dado e entraram na média.
    baseline_weeks_used: int
    points: list[SupportTvHourlyPoint]


class SupportTvCount(BaseModel):
    label: str
    total: int


class SupportTvBotHuman(BaseModel):
    classified_attendances: int
    unclassified_attendances: int
    with_bot: int
    with_bot_percentage: float | None = None
    reached_human: int
    reached_human_percentage: float | None = None
    bot_to_human_handoff: int
    bot_to_human_handoff_percentage: float | None = None


class SupportTvAttendant(BaseModel):
    attendant_id: str
    name: str
    total: int
    closed: int
    # TMR geral do atendente no dia (inclui resposta de bot) - mesmo critério do TMR principal da TV.
    average_tmr_seconds: float | None = None
    average_rating: float | None = None


class SupportTvBurst(BaseModel):
    window: str
    observed: int
    expected: float | None = None
    ratio: float | None = None
    active: bool
    # same_weekday = comparado ao mesmo dia da semana nas últimas semanas; none = sem histórico.
    basis: str


class SupportTvPace(BaseModel):
    """Ritmo de HOJE: protocolos operacionais até agora contra o esperado até esta hora."""

    observed_today: int
    expected_so_far: float | None = None
    ratio: float | None = None
    status: Literal["normal", "attention", "critical", "no_baseline"]


class SupportTvCityAlert(BaseModel):
    city: str
    today_count: int
    expected: float
    deviation_pct: float | None = None


class SupportTvRadar(BaseModel):
    """Radar de incidente: SÓ protocolos operacionais (assunto 90 do IXC), SÓ de hoje. Cada parte falha
    sozinha: `None` significa que aquela fonte não respondeu, nunca "tudo normal"."""

    scope: Literal["operational"] = "operational"
    baseline_weeks_used: int = 0
    pace: SupportTvPace | None = None
    bursts: list[SupportTvBurst] | None = None
    cities_at_risk: list[SupportTvCityAlert] | None = None


class SupportTvN1(BaseModel):
    operational: int
    financial: int
    total: int
    previous_total: int


class SupportTvSync(BaseModel):
    last_success_at: datetime | None = None
    consecutive_failures: int = 0


class SupportTvDepartmentFilter(BaseModel):
    """Departamentos que a TV está considerando. Lista vazia = todos."""

    department_ids: list[str] = Field(default_factory=list)
    department_names: list[str] = Field(default_factory=list)


class SupportTvDepartmentOption(BaseModel):
    id: str
    name: str


class SupportTvConfig(BaseModel):
    department_ids: list[str] = Field(default_factory=list)
    available_departments: list[SupportTvDepartmentOption] = Field(default_factory=list)
    tmr_target_seconds: int


class SupportTvConfigUpdate(BaseModel):
    department_ids: list[str] = Field(default_factory=list, max_length=50)


class SupportTvPresenceState(BaseModel):
    code: str
    label: str
    total: int


class SupportTvPresenceAgent(BaseModel):
    name: str
    state_code: str
    state_label: str
    # Aproximação: segundos desde a última atualização do usuário no OPA. None = sem data.
    seconds_in_state: int | None = None


class SupportTvPresence(BaseModel):
    """Status dos atendentes (campo `online` do usuário no OPA). `ringing_available=false` diz que a
    API NÃO informa ligação tocando - a tela não deve sugerir que sabe."""

    generated_at: datetime
    scope: Literal["departments", "all"]
    total: int
    available_percentage: float | None = None
    states: list[SupportTvPresenceState] = Field(default_factory=list)
    # Quem está em ligação, ocupado, em pausa ou ausente (os que pedem atenção), com há quanto tempo.
    agents: list[SupportTvPresenceAgent] = Field(default_factory=list)
    agents_total: int = 0
    unmapped_codes: list[str] = Field(default_factory=list)
    ringing_available: bool = False


class SupportTvSnapshot(BaseModel):
    generated_at: datetime
    # Dia local de operação (America/Porto_Velho) a que "hoje" se refere.
    local_date: date
    department_filter: SupportTvDepartmentFilter = Field(default_factory=SupportTvDepartmentFilter)
    kpis: SupportTvKpis | None = None
    hourly: SupportTvHourly | None = None
    top_reasons: list[SupportTvCount] | None = None
    channels: list[SupportTvCount] | None = None
    bot_human: SupportTvBotHuman | None = None
    attendants: list[SupportTvAttendant] | None = None
    radar: SupportTvRadar
    n1: SupportTvN1 | None = None
    sync: SupportTvSync
    # Blocos que não puderam ser calculados (ex.: "radar.bursts"), para a tela avisar.
    unavailable: list[str] = Field(default_factory=list)
