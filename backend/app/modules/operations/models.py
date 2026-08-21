from __future__ import annotations

from datetime import date, datetime, time, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class OperationImportRun(Base):
    __tablename__ = "operations_import_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date_from: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    date_to: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="running", index=True)
    fetched_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unchanged_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    errors: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    imported_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OperationBackfillJob(Base):
    __tablename__ = "operations_backfill_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date_from: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    date_to: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    next_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    sector_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending", index=True)
    total_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fetched_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unchanged_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    errors: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    requested_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OperationOpenBacklogJob(Base):
    """Job assíncrono da varredura de backlog aberto (todos os setores, sem recorte de data) - mesmo
    espírito de OperationBackfillJob (status/progresso/erros pesquisáveis por polling), mas o
    progresso é medido por setor processado, não por dia, já que o backlog aberto não é uma consulta
    por período."""

    __tablename__ = "operations_open_backlog_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sector_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending", index=True)
    total_sectors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed_sectors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fetched_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unchanged_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    errors: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    requested_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OperationSavedFilter(Base):
    __tablename__ = "operations_saved_filters"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_operations_saved_filters_user_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    filters: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    visibility: Mapped[str] = mapped_column(String(20), nullable=False, default="personal", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class OperationOrder(Base):
    __tablename__ = "operations_orders"
    __table_args__ = (
        UniqueConstraint("source", "source_order_id", name="uq_operations_orders_source_id"),
        Index("ix_operations_orders_opened_closed", "opened_at", "closed_at"),
        Index("ix_operations_orders_dimensions", "regional", "os_type", "os_subject"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="ixc", index=True)
    source_order_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    order_code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    protocol: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    contract_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    customer_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    customer_login: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    customer_name: Mapped[str | None] = mapped_column(String(220), nullable=True)
    company_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    regional: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    state: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    city: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    # Confirmados contra uma amostra real de 104k+ O.S. já importadas (raw_payload->>'bairro'/
    # 'latitude'/'longitude', ver ixc_ingestion.py) - diferente de rua/número/CEP, que só existem
    # embutidos na string única de `endereco` (ver OperationOrderOut.address_is_structured em
    # schemas.py), estes três SÃO campos separados na origem e valeu a pena materializar.
    neighborhood: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    contract_type: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    person_type: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    os_type: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    os_subject: Mapped[str | None] = mapped_column(String(220), nullable=True, index=True)
    diagnosis: Mapped[str | None] = mapped_column(String(220), nullable=True, index=True)
    department: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    sector: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    priority: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    creator: Mapped[str | None] = mapped_column(String(180), nullable=True, index=True)
    responsible: Mapped[str | None] = mapped_column(String(180), nullable=True, index=True)
    # id_tecnico bruto do IXC (su_rh_funcionarios), guardado alem do nome pra permitir casar o
    # colaborador com precisao (ver Collaborator.ixc_employee_id) sem depender so de nome.
    responsible_ixc_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    project: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    pop: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    status_code: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    status: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    is_closed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    is_internal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    sla_status: Mapped[str] = mapped_column(String(40), nullable=False, default="unidentified", index=True)
    sla_target_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    elapsed_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    assumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    displacement_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    execution_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    normalization_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    last_imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class OperationTeamModel(Base):
    __tablename__ = "operations_team_models"
    __table_args__ = (UniqueConstraint("name", name="uq_operations_team_models_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    daily_target: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    median_from_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    good_from_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    below_target_color: Mapped[str] = mapped_column(String(7), nullable=False, default="#fee2e2")
    median_color: Mapped[str] = mapped_column(String(7), nullable=False, default="#fef3c7")
    good_color: Mapped[str] = mapped_column(String(7), nullable=False, default="#dcfce7")
    excellent_color: Mapped[str] = mapped_column(String(7), nullable=False, default="#dbeafe")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    target_rules: Mapped[list["OperationTeamTargetRule"]] = relationship(
        back_populates="team_model",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="OperationTeamTargetRule.period_type",
    )
    target_rule_versions: Mapped[list["OperationTeamTargetVersion"]] = relationship(
        back_populates="team_model",
        cascade="all, delete-orphan",
    )


class OperationTeamTargetRule(Base):
    __tablename__ = "operations_team_target_rules"
    __table_args__ = (
        UniqueConstraint("team_model_id", "period_type", name="uq_operations_team_target_rule_period"),
        Index("ix_operations_team_target_rule_model_period", "team_model_id", "period_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_model_id: Mapped[int] = mapped_column(
        ForeignKey("operations_team_models.id", ondelete="CASCADE"), nullable=False, index=True
    )
    period_type: Mapped[str] = mapped_column(String(20), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    median_from_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    good_from_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    target_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    team_model: Mapped[OperationTeamModel] = relationship(back_populates="target_rules")


class OperationTeamTargetVersion(Base):
    """Histórico append-only de `OperationTeamTargetRule` - essa tabela nunca é editada nem tem
    linha apagada (só fecha `valid_to` e abre uma nova). Criada porque `OperationTeamTargetRule`
    é destrutiva (`_replace_target_rules`, operations/router.py, apaga e recria as regras a cada
    edição, sem deixar rastro) e não há como saber hoje qual era a meta vigente numa data
    passada. Só tem dado a partir do dia em que este recurso entrou em produção (mais o backfill
    de uma migration, que assume a configuração atual válida desde a criação da regra) - sem
    retroatividade para mudanças que já aconteceram antes disso."""

    __tablename__ = "operations_team_target_versions"
    __table_args__ = (
        Index("ix_operations_team_target_versions_lookup", "team_model_name", "period_type", "valid_from"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_model_id: Mapped[int] = mapped_column(
        ForeignKey("operations_team_models.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Snapshot do nome - as consultas de análise de O.S. já resolvem modelo de equipe por NOME
    # (ai/queries.py:_group_label), não por id; evita um join extra em toda consulta de meta.
    team_model_name: Mapped[str] = mapped_column(String(120), nullable=False)
    period_type: Mapped[str] = mapped_column(String(20), nullable=False)
    target_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    median_from_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    good_from_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    team_model: Mapped[OperationTeamModel] = relationship(back_populates="target_rule_versions")


class OperationSubjectTypeMapping(Base):
    __tablename__ = "operations_subject_type_mappings"
    __table_args__ = (UniqueConstraint("subject", name="uq_operations_subject_type_mapping_subject"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subject: Mapped[str] = mapped_column(String(220), nullable=False, unique=True, index=True)
    os_type: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class OperationResponsibleAssignment(Base):
    __tablename__ = "operations_responsible_assignments"
    __table_args__ = (
        UniqueConstraint("responsible_name", "regional", name="uq_operations_responsible_assignment_identity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    responsible_name: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    regional: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    team_model_id: Mapped[int | None] = mapped_column(
        ForeignKey("operations_team_models.id", ondelete="SET NULL"), nullable=True, index=True
    )
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class OperationIxcCollaborator(Base):
    __tablename__ = "operations_ixc_collaborators"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_employee_id: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class OperationResponsibleDirectorySetting(Base):
    __tablename__ = "operations_responsible_directory_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="orders")
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class OperationBacklogSnapshot(Base):
    """Fotografia diária do backlog (O.S. ainda abertas) por regional/modelo de equipe/setor - não
    existe nenhum histórico auditado de antes desta tabela existir (achado confirmado durante o
    desenho deste recurso: o sistema não guardava snapshot nem log de mudança de status de O.S.).
    Captura feita 1x por dia por `capture_backlog_snapshot` (backlog_snapshot.py), a partir da
    data em que o job entrar em produção - sem retroatividade possível.

    `sector` foi adicionado um dia depois da primeira versão desta tabela - achado real: sem ele,
    a série histórica de backlog não conseguia ser filtrada por setor (ex.: "contém Ex"), porque
    esse dado nunca tinha sido capturado. As poucas linhas gravadas no dia anterior a esta mudança
    não têm granularidade de setor (ficam com o valor de fallback "Não identificado").

    `city` segue o mesmo padrão de `sector`: adicionada depois, pra permitir concentração
    geográfica (ex.: "quais cidades mais geram backlog") sem precisar de uma tabela nova. Linhas
    gravadas antes desta coluna existir também ficam com o fallback "Não identificado"."""

    __tablename__ = "operations_backlog_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "snapshot_date", "regional", "team_model", "sector", "city", name="uq_operations_backlog_snapshot_identity"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    regional: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    # "Não identificado" quando a O.S. não tem responsável mapeado a um modelo de equipe - nunca
    # NULL, pro agrupamento não precisar tratar ausência como caso especial.
    team_model: Mapped[str] = mapped_column(String(120), nullable=False)
    sector: Mapped[str] = mapped_column(String(160), nullable=False, server_default="Não identificado")
    city: Mapped[str] = mapped_column(String(160), nullable=False, server_default="Não identificado")
    backlog_count: Mapped[int] = mapped_column(Integer, nullable=False)
    backlog_atrasado_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class OperationLoginStatusSnapshot(Base):
    """Fotografia periódica (várias vezes por dia, não 1x/dia como o backlog) do status de conexão
    de cada login do IXC (`radusuarios.online`) - append-only, nunca upsertada, pra permitir montar
    a série "esse login ficou fora de 'online' nos últimos N dias" e cruzar com lat/long pra achar
    clusters geográficos de queda (ex.: rompimento de fibra num trecho). Sem esta tabela o IXC só
    devolve o status atual (achado confirmado consultando `radusuarios` direto: não existe endpoint
    de histórico de status por login, só accounting RADIUS em `radacct`, que não cobre logins fibra
    monitorados por sinal óptico - a maioria dos casos com `online` diferente de 'S').

    `online` guarda o valor bruto do IXC ('S', 'N', 'SS' = sem sinal, ou vazio), sem normalizar pra
    boolean - achado real: 'SS' é quase 40% dos logins fibra numa amostra de produção e é
    justamente o estado que se quer detectar, então perder essa distinção reduzindo pra
    True/False descartaria o sinal mais relevante da feature.

    `latitude`/`longitude` são gravados a cada captura (não só uma vez) porque o cadastro do login
    pode ganhar coordenada depois de já existir - guardar por captura evita ter que voltar no IXC
    pra saber "quando essa coordenada passou a existir"."""

    __tablename__ = "operations_login_status_snapshots"
    __table_args__ = (
        Index("ix_operations_login_status_snapshots_login_captured", "login_id", "captured_at"),
        Index(
            "ix_operations_login_status_snapshots_online_geo",
            "online",
            "latitude",
            "longitude",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    login_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    login: Mapped[str] = mapped_column(String(160), nullable=False)
    online: Mapped[str] = mapped_column(String(10), nullable=False, default="")
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Passthrough direto de `ultima_conexao_final` do IXC (achado real da auditoria de
    # 2026-08-21) - fica NULL enquanto o login está online AGORA (reflete o estado/sessão atual,
    # é zerado pelo próprio IXC ao reconectar). NÃO é "a última vez que este login já caiu
    # historicamente" - pra isso, usar o histórico append-only desta mesma tabela
    # (OperationLoginStatusSnapshot, filtrando captured_at) ou `recent_events` de
    # `opr_get_login_detail`.
    last_disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OperationLoginCurrentStatus(Base):
    """Estado ATUAL de cada login (1 linha por login, sempre upsertada) - existe ao lado de
    `OperationLoginStatusSnapshot` (histórico append-only) porque a detecção de cluster geográfico
    precisa saber "quem mudou pra desconectado nos últimos N minutos" toda vez que alguém abre a
    tela, e calcular isso escaneando o histórico inteiro não escala (achado real: com ~11M linhas
    de histórico acumuladas em poucas horas de teste, essa consulta levava 11s sozinha, porque
    `DISTINCT ON` com filtro de data não consegue usar um índice pra pular direto pro registro mais
    recente de cada login). Aqui a resposta já vem pronta: `status_changed_at` é atualizado só
    quando `online` muda de valor (ver `upsert_login_current_status`), então a consulta de
    clusterização vira um filtro simples e indexado em vez de uma varredura."""

    __tablename__ = "operations_login_current_status"
    __table_args__ = (
        Index("ix_operations_login_current_status_online_changed", "online", "status_changed_at"),
        Index("ix_operations_login_current_status_regional", "regional"),
    )

    login_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    login: Mapped[str] = mapped_column(String(160), nullable=False)
    online: Mapped[str] = mapped_column(String(10), nullable=False, default="")
    # Mesma normalização de `app.services.regional.normalize_regional` (radusuarios.id_filial),
    # usada pela Operação Analítica para O.S. - pedido do usuário em 2026-08-14 pra poder filtrar
    # status de login por regional (ex.: "quais logins de Machadinho D'Oeste estão offline"), o que
    # nao era possivel so com lat/long.
    regional: Mapped[str | None] = mapped_column(String(80), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Ver docstring equivalente em OperationLoginStatusSnapshot.last_disconnected_at acima - mesma
    # semântica (passthrough de ultima_conexao_final, NULL enquanto online, não é histórico).
    last_disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Só muda quando `online` muda de valor em relação à captura anterior - NÃO é "última vez que
    # vimos esse login" (isso é `captured_at`). É o campo que a detecção de transição usa.
    status_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class OperationOnuSignalCurrent(Base):
    """Estado ATUAL de telemetria óptica/ONU por login (1 linha por login, sempre upsertada) -
    tabela `radpop_radio_cliente_fibra` do IXC (achada por sondagem manual contra a API real em
    2026-08-14, não documentada publicamente; é a fonte da aba "Cliente Fibra (ONU)" da tela de
    login) - sinal RX/TX em dBm, serial/MAC da ONU, transmissor (OLT) e causa da última queda
    (ex.: "Link Loss"), telemetria que o simples `online`/'SS' de `OperationLoginCurrentStatus`
    não tem.

    Só cobre os logins já presentes em `OperationLoginCurrentStatus` (não a base inteira de ~90 mil
    ONUs do IXC) - decisão deliberada para não sobrecarregar a API do IXC com uma varredura
    periódica completa (ver `operations/onu_signal_snapshot.py`)."""

    __tablename__ = "operations_onu_signal_current"
    __table_args__ = (
        Index("ix_operations_onu_signal_current_drop_cause", "last_drop_cause"),
        Index("ix_operations_onu_signal_current_transmitter", "transmitter_id"),
    )

    login_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    contract_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    signal_rx_dbm: Mapped[float | None] = mapped_column(Float, nullable=True)
    signal_tx_dbm: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_drop_cause: Mapped[str | None] = mapped_column(String(120), nullable=True)
    onu_serial: Mapped[str | None] = mapped_column(String(60), nullable=True)
    onu_model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    transmitter_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # Nome resolvido de `radpop_radio.descricao` (tabela de cadastro de OLT/transmissor do IXC,
    # achada por sondagem manual em 2026-08-17 - `transmitter_id` sozinho é um ID numérico bruto,
    # sem significado nenhum pra quem lê). Resolvido em `onu_signal_snapshot.py` a cada captura,
    # sem tabela de lookup própria - mesmo padrão já usado pra resolver `id_tecnico` em nome de
    # responsável na importação de O.S. (ver `operations/ixc_ingestion.py`).
    transmitter_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    voltage: Mapped[float | None] = mapped_column(Float, nullable=True)
    signal_measured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pon_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    pon_no: Mapped[str | None] = mapped_column(String(20), nullable=True)
    slot_no: Mapped[str | None] = mapped_column(String(20), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class OperationOnuSignalSnapshot(Base):
    """Histórico APPEND-ONLY de telemetria óptica/ONU (uma linha por captura, nunca upsertada) -
    complementa `OperationOnuSignalCurrent` (que só guarda o valor mais recente por login) para
    permitir responder "o sinal do login/serial X estava em Y na data Z, e hoje está em W" (pedido
    do usuário em 2026-08-17). Mesmo padrão de `OperationLoginStatusSnapshot`: a captura já busca
    esse dado no IXC a cada ciclo (ver `onu_signal_snapshot.capture_onu_signal_snapshot`) - esta
    tabela só grava a mesma linha de novo em vez de sobrescrever, sem chamada adicional ao IXC.

    Cobertura parcial por desenho: só é gravada quando o login está na "fila de diagnóstico"
    daquele ciclo (offline, transição recente, ou nunca capturado - ver
    `_onu_signal_watchlist_login_ids`), não a cada ciclo para todo login monitorado. Um login
    saudável e estável por dias não gera pontos novos nesse intervalo - a série reflete os
    momentos em que houve motivo pra medir, não uma amostragem uniforme no tempo."""

    __tablename__ = "operations_onu_signal_snapshots"
    __table_args__ = (
        Index("ix_operations_onu_signal_snapshots_login_captured", "login_id", "captured_at"),
        Index("ix_operations_onu_signal_snapshots_serial_captured", "onu_serial", "captured_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    login_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    contract_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    signal_rx_dbm: Mapped[float | None] = mapped_column(Float, nullable=True)
    signal_tx_dbm: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_drop_cause: Mapped[str | None] = mapped_column(String(120), nullable=True)
    onu_serial: Mapped[str | None] = mapped_column(String(60), nullable=True)
    onu_model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    transmitter_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    transmitter_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    voltage: Mapped[float | None] = mapped_column(Float, nullable=True)
    signal_measured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pon_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    pon_no: Mapped[str | None] = mapped_column(String(20), nullable=True)
    slot_no: Mapped[str | None] = mapped_column(String(20), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True, default=utc_now)


class OperationBranchCapacity(Base):
    """Capacidade mensal de produção configurada POR FILIAL (`regional` - já é a identidade
    granular por `id_filial` do IXC, ver `app/services/regional.py`), com 3 faixas positivas:
    Boa, Ótima e Excelente. Indicador GERENCIAL agregado da filial inteira - paralelo e
    independente das metas por Modelo de Equipe (`OperationTeamModel`), que continuam pintando
    cada célula do calendário por colaborador/dia como sempre pintaram. Não existe faixa "abaixo"
    aqui de propósito: abaixo de `good_threshold` a filial simplesmente não bateu nenhuma faixa
    (ver `services.branch_capacity_summary`), não precisa de cor própria configurável.

    Uma linha por filial (`regional` é único) - sem linha configurada, a filial não aparece no
    indicador de capacidade (não tem como calcular percentual sem faixas definidas)."""

    __tablename__ = "operations_branch_capacity"
    __table_args__ = (UniqueConstraint("regional", name="uq_operations_branch_capacity_regional"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    regional: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    good_threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=2500)
    great_threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=3000)
    excellent_threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=3500)
    good_color: Mapped[str] = mapped_column(String(7), nullable=False, default="#dcfce7")
    great_color: Mapped[str] = mapped_column(String(7), nullable=False, default="#dbeafe")
    excellent_color: Mapped[str] = mapped_column(String(7), nullable=False, default="#ede9fe")
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)
