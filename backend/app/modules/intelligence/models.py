"""UNI Intelligence - fundação (F0+F1): motor de monitores que detecta, persiste e da ciclo de
vida a alertas/incidentes operacionais, sem depender de nenhum canal externo (Slack ainda não
existe no projeto) e sem chamar LLM nesta fase (ver docs/plano-plataforma-inteligencia-operacional.md).

Módulo transversal (não vive dentro de `operations`) porque consome dados de operações, rede e
suporte hoje, e de outros domínios no futuro - mesmo racional que já separou `support` de
`operations` (ver docs/auditoria-evolucao-opa-suite-2026-08-16.md)."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class IntelligenceMonitorRun(Base):
    """Uma execução de um monitor. Existe para resolver, de forma definitiva, a diferença entre
    "não houve alerta" e "o monitor não rodou" - problema operacional já vivido antes desta
    plataforma (ver item J do estudo de arquitetura). Uma run nasce RUNNING antes de qualquer
    avaliação de resultado e é sempre finalizada no `finally` do scheduler, com sucesso ou erro -
    nunca fica pendurada, exceto se o processo cair no meio, caso em que o próprio scheduler a
    encontra na inicialização seguinte e a marca INTERRUPTED (ver scheduler.py)."""

    __tablename__ = "intelligence_monitor_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    monitor_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    # RUNNING | COMPLETED | COMPLETED_WITH_WARNINGS | FAILED | INTERRUPTED
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="RUNNING", index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    alerts_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    alerts_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    alerts_resolved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Métricas livres por monitor (ex.: quantos clusters avaliados, quantas regionais cobertas) -
    # não normalizado em coluna porque cada monitor mede coisas diferentes.
    stats_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        Index("ix_intelligence_monitor_runs_key_started", "monitor_key", "started_at"),
        Index("ix_intelligence_monitor_runs_key_status", "monitor_key", "status"),
    )


class IntelligenceAlert(Base):
    """Entidade única para alerta e incidente (diferenciados só por `kind`) - lifecycle, dedupe,
    severidade, escopo e notificação são idênticos para os dois; um incidente é um alerta com
    evidência de correlação mais rica. Duas tabelas duplicariam toda a máquina de estados (ver
    item E do estudo de arquitetura, docs/plano-plataforma-inteligencia-operacional.md).

    `dedupe_key` é o mecanismo central de nao renascer a cada ciclo (ver alerts.py): cada monitor
    calcula uma chave estável para a mesma ocorrência real; se já existe alerta ativo com essa
    chave, o monitor atualiza em vez de criar.

    `source_type`/`source_key` existem desde o primeiro dia mesmo sem uma engine de publishers
    ainda (F0+F1 não a constrói) - é o que permite, no futuro, controlar quem pode publicar o quê
    (monitor, IA, usuário) sem precisar alterar esta tabela."""

    __tablename__ = "intelligence_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # ALERT | INCIDENT
    kind: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    alert_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    monitor_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    dedupe_key: Mapped[str] = mapped_column(String(300), nullable=False, index=True)

    # Materializados para índice/filtro direto; o detalhe completo de escopo vive em scope_json
    # (pode incluir cidade, setor, modelo de equipe etc., conforme o monitor).
    regional: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    scope_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # dedupe_key: correção pós-Lote A (ver migration 20260816_0066). NÃO é unique() na coluna: um
    # alerta RESOLVED/DISMISSED não pode ocupar a chave para sempre - reincidência (item 7 dos
    # testes obrigatórios) precisa poder criar uma linha NOVA com a mesma dedupe_key depois que a
    # anterior foi encerrada. A unicidade real é aplicada em `alerts.py`, restrita aos alertas
    # ATIVOS (_active_alerts_for_monitor) - o scheduler é sequencial (um monitor por vez, nunca
    # duas execuções do mesmo monitor em paralelo), então não há corrida real a proteger no banco
    # nesta fase. Debt documentado para F2+: se o scheduler virar multi-worker, adicionar índice
    # único parcial (WHERE status NOT IN (...)) por dialeto.

    # LOW | MEDIUM | HIGH | CRITICAL
    severity: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # Confiabilidade herdada da Fase 1 do FilterContractV1 (docs/proposta-filter-contract-v1.md):
    # nenhum alerta sem a incerteza que o acompanha. `coverage_json` guarda, por exemplo, a
    # cobertura de coordenadas usada para sustentar (ou não) uma conclusão geográfica.
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    coverage_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    warnings_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    source_last_sync: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # NEW | INVESTIGATING | CONFIRMED | IN_PROGRESS | RECOVERING | RESOLVED | DISMISSED | EXPIRED
    # Nesta fase só NEW/CONFIRMED/RESOLVED/DISMISSED são de fato produzidos pelos monitores; os
    # demais valores ficam disponíveis para as fases seguintes (ver item I do estudo).
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="NEW", index=True)

    first_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    acknowledged_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Ciclos consecutivos em que o monitor rodou e não redetectou este dedupe_key. Zera a cada
    # redetecção; ao atingir `resolve_after_misses` (configurável por monitor) o alerta vira
    # RESOLVED automaticamente (ver alerts.py). Auto-resolve deliberadamente conservador: um único
    # ciclo sem detecção nunca é suficiente.
    misses_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # SYSTEM | MONITOR | AI | USER - de onde este alerta se origina. Hoje só MONITOR é produzido;
    # os demais valores existem para não obrigar migração quando IA (F4) ou ação manual (item
    # "publishers" do processo aprovado) entrarem.
    source_type: Mapped[str] = mapped_column(String(20), nullable=False, default="MONITOR")
    source_key: Mapped[str | None] = mapped_column(String(120), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    events: Mapped[list["IntelligenceAlertEvent"]] = relationship(
        back_populates="alert",
        cascade="all, delete-orphan",
        order_by="IntelligenceAlertEvent.created_at",
    )

    __table_args__ = (
        Index("ix_intelligence_alerts_status_severity", "status", "severity"),
        Index("ix_intelligence_alerts_monitor_status", "monitor_key", "status"),
    )


class IntelligenceAlertEvent(Base):
    """Timeline append-only de um alerta - dá o histórico de evolução ("acompanhar evolução de um
    evento", pedido explícito da visão) e é o que permite provar, depois, por que um alerta
    escalou ou foi resolvido. Nunca é editado ou apagado, só inserido."""

    __tablename__ = "intelligence_alert_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alert_id: Mapped[int] = mapped_column(ForeignKey("intelligence_alerts.id", ondelete="CASCADE"), nullable=False, index=True)
    # DETECTED | UPDATED | SEVERITY_CHANGED | STATUS_CHANGED | RESOLVED | DISMISSED
    # preparado (não usado ainda): AI_ANALYZED | ACKNOWLEDGED | NOTIFIED | CONFIDENCE_CHANGED
    event_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    # None = evento gerado pelo sistema (monitor); preenchido só quando uma ação humana gerar o evento.
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    alert: Mapped["IntelligenceAlert"] = relationship(back_populates="events")
