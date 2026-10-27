from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SupportOpaImportRun(Base):
    __tablename__ = "support_opa_import_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, default="opa", index=True)
    entity: Mapped[str] = mapped_column(String(80), nullable=False, default="attendance", index=True)
    mode: Mapped[str] = mapped_column(String(40), nullable=False, default="manual", index=True)
    date_from: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    date_to: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="running", index=True)
    page_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    pages_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_skip: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fetched_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unchanged_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    errors: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    checkpoint_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    imported_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SupportOpaImportMonth(Base):
    """Rastreio de "este mês calendário já foi totalmente importado" - não existe
    endpoint no OPA Suite que informe um total esperado por mês, então "completo"
    é definido operacionalmente: uma `SupportOpaImportRun` cujo [date_from, date_to]
    cobre o mês inteiro terminou com status completed/completed_with_warnings (ver
    `opa_ingestion._maybe_mark_month_complete`). Usado pelo painel de meses da tela
    de Suporte e pelo backfill automático de madrugada (`opa_scheduler.run_opa_backfill_once`)
    pra saber quais meses recentes ainda faltam."""

    __tablename__ = "support_opa_import_months"
    __table_args__ = (UniqueConstraint("year_month", name="uq_support_opa_import_months_year_month"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    year_month: Mapped[str] = mapped_column(String(7), nullable=False, index=True)  # "2026-07"
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="missing", index=True)
    attendance_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_run_id: Mapped[int | None] = mapped_column(ForeignKey("support_opa_import_runs.id", ondelete="SET NULL"), nullable=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class SupportOpaAttendanceRaw(Base):
    __tablename__ = "support_opa_attendances_raw"
    __table_args__ = (
        UniqueConstraint("source_id", name="uq_support_opa_attendances_raw_source_id"),
        Index("ix_support_opa_raw_opened_closed", "opened_at", "closed_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class SupportOpaDimension(Base):
    __tablename__ = "support_opa_dimensions"
    __table_args__ = (
        UniqueConstraint("dimension_type", "source_id", name="uq_support_opa_dimensions_type_source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dimension_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(String(220), nullable=True, index=True)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class SupportOpaAttendantOverride(Base):
    """Cadastro manual de classificação de atendente do OPA Suite — hoje usado só
    pra forçar `attendant_type="bot"` (via `classification="virtual_agent"`) quando
    a dimensão sincronizada da API (`SupportOpaDimension.payload_json.tipo`) não
    reflete isso, seja porque o OPA nunca mandou `tipo="bot"` pra aquele atendente,
    seja porque o atendente nem chegou a ser sincronizado como dimensão. Tem
    prioridade sobre `payload_json.tipo` — ver `opa_attendant_overrides.resolve_attendant_type`.
    """

    __tablename__ = "support_opa_attendant_overrides"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attendant_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    attendant_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    classification: Mapped[str] = mapped_column(String(40), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class SupportOpaSavedFilter(Base):
    """Recorte de filtros salvo da tela /suporte.

    `scope` separa dois usos que o usuario pediu explicitamente como coisas
    diferentes:
      - "personal": so aparece para quem criou, mas sincroniza entre dispositivos
        (diferente do atalho de localStorage, que morre com o navegador).
      - "global": aparece para todo mundo que enxerga o modulo, para recortes
        oficiais da operacao.
    Editar/apagar um filtro global exige a mesma permissao de gestao do modulo -
    ver o router; qualquer usuario pode criar e apagar os proprios "personal".

    `filters_json` guarda o recorte cru (mesmas chaves da querystring da tela).
    Deliberadamente sem FK para colunas de filtro: se uma etiqueta/atendente sumir
    do OPA, o filtro salvo continua abrindo e simplesmente nao casa nada, em vez de
    quebrar a tela inteira.
    """

    __tablename__ = "support_opa_saved_filters"
    __table_args__ = (
        Index("ix_support_opa_saved_filters_scope_owner", "scope", "owner_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    scope: Mapped[str] = mapped_column(String(20), nullable=False, default="personal")
    filters_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class SupportIxcTicketSavedFilter(Base):
    """Recorte de filtros salvo do Atendimento IXC (item 10 do plano de evolução analítica,
    2026-09-17: "filtros mais fácil de utilizar e poder salvar visão e ela ser padrão ou não").

    Diferente de `SupportOpaSavedFilter`, é SEMPRE pessoal (decisão do usuário: cada um define a
    própria visão, sem escopo "global" aqui) - por isso `owner_id` não é nullable. `is_default`
    marca a visão que a tela aplica sozinha ao abrir; só uma pode ser padrão por dono ao mesmo
    tempo (garantido no service/router, não em constraint de banco - trocar o padrão é
    "desmarcar a anterior e marcar a nova", não uma operação atômica de banco que valha a pena
    modelar como unique index parcial).

    `filters_json` guarda só `subject_ids`/`sector_ids` (as duas dimensões que
    `IxcTicketFiltersBar` controla hoje) - não o período nem o foco de drill-down (regional/
    cidade/bairro), que vivem no estado interno do painel único, não neste recorte."""

    __tablename__ = "support_ixc_ticket_saved_filters"
    __table_args__ = (
        Index("ix_support_ixc_ticket_saved_filters_owner", "owner_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    filters_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class SupportIxcTicketRaw(Base):
    """Payload bruto do atendimento IXC (`su_ticket`), mesmo padrão de auditoria de
    `SupportOpaAttendanceRaw` - guarda o registro cru pra reprocessamento e conferência,
    independente do que `SupportIxcTicket` extrai/normaliza hoje."""

    __tablename__ = "support_ixc_tickets_raw"
    __table_args__ = (
        UniqueConstraint("source_id", name="uq_support_ixc_tickets_raw_source_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class SupportIxcTicket(Base):
    """Atendimento REAL do IXC (tabela `su_ticket`) - o protocolo que o time abre na aba
    Atendimentos do IXC e que dispara a abertura de O.S.; nenhuma O.S. é aberta diretamente,
    sempre passa por um atendimento primeiro (confirmado ao vivo contra a API em 2026-09-11,
    ver docs/STATUS.md). Diferente de `SupportOpaAttendance`, que é o atendimento por CHAT do
    OPA Suite - as duas fontes convivem no módulo Suporte por decisão explícita do usuário
    (exceção deliberada à separação OPA/IXC do plano original, ver
    docs/plano-integracao-opa-suite.md item 4), cada linha marcada com a origem no campo
    implícito da própria tabela.

    Usado como indicador ANTECIPADO/preditivo de incidente, complementando a O.S. (que continua
    sendo a confirmação e o tratamento operacional) - certas anormalidades aparecem primeiro no
    volume de atendimento e só depois viram O.S. (ver docs/STATUS.md, exemplo real: Rolim de
    Moura). `su_oss_chamado.id_ticket` referencia de volta este registro - ver
    `OperationOrder.ticket_id` em modules/operations/models.py.

    `regional` vem direto do próprio ticket (`id_filial`, normalizado via
    `app/services/regional.normalize_regional`) - não precisa herdar de outra tabela.
    `city`/`neighborhood`/`locality_type` vêm do cadastro do CLIENTE (`cliente.cidade`/`bairro`/
    `tipo_localidade`), nunca do campo `endereco` do próprio ticket, que é texto livre não
    parseável com segurança ("LOGRADOURO, NUMERO - BAIRRO CIDADE UF - CEP")."""

    __tablename__ = "support_ixc_tickets"
    __table_args__ = (
        UniqueConstraint("source_id", name="uq_support_ixc_tickets_source_id"),
        Index("ix_support_ixc_tickets_regional_created", "regional", "created_at"),
        Index("ix_support_ixc_tickets_city_neighborhood", "city", "neighborhood"),
        # Fase 0 do plano de evolução analítica (2026-09-14): motivo/cliente cruzados com data são
        # a base de duas heurísticas novas - reincidência (COUNT por customer_id numa janela de
        # tempo) e o baseline hora-do-dia/dia-da-semana por motivo (Fase 4, burst). Sem estes
        # índices compostos, as duas viram table scan no volume real (dezenas de milhares de
        # tickets/mês).
        Index("ix_support_ixc_tickets_subject_created", "subject_id", "created_at"),
        Index("ix_support_ixc_tickets_customer_created", "customer_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    protocol: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    customer_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    customer_name: Mapped[str | None] = mapped_column(String(220), nullable=True, index=True)
    contract_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    regional: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    city: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    neighborhood: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    # Código cru do IXC (`cliente.tipo_localidade`) - valor confirmado ao vivo em amostra: "U"
    # (urbano). Valor de rural ainda não observado; não assumir enum fechado sem validar mais.
    locality_type: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    subject_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    subject_name: Mapped[str | None] = mapped_column(String(220), nullable=True, index=True)
    # `su_ticket.id_ticket_setor` - achado real 2026-09-12: resolve contra a MESMA tabela
    # `empresa_setor` que a O.S. já usa (`fetch_setores`/`empresa_setor.setor`), confirmado ao
    # vivo (id=2 -> "Pós Venda", id=3 -> "Retenção"). Pedido do usuário: filtro por setor além de
    # motivo, se existir - existe.
    sector_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    sector_name: Mapped[str | None] = mapped_column(String(220), nullable=True, index=True)
    # `su_ticket.id_usuarios` - quem abriu o protocolo (tabela `usuarios` do IXC; resolvido em
    # `SupportIxcUser`). `NULL` quando o IXC devolve 0 (protocolo criado sem operador, p. ex. por
    # integração). Pedido do usuário (2026-10-06): contar só protocolos do Suporte Interno N1.
    # Preenchido por toda importação nova; o histórico anterior só foi retroalimentado para os
    # motivos do N1 (migração `20260922_0109`).
    opened_by_user_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    status: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    sub_status: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    channel_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    workflow_process_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    priority: Mapped[str | None] = mapped_column(String(40), nullable=True)
    title: Mapped[str | None] = mapped_column(String(220), nullable=True)
    # Relato protocolado (`su_ticket.menssagem`, grafia original do IXC) - texto livre do
    # atendimento, pedido explícito do usuário (2026-09-11) pra aparecer no nó final do
    # drill-down. Pode conter PII digitada pelo cliente/atendente (nome, telefone) embutida no
    # texto - mesmo nível de acesso de hoje (`support:read`), sem mascaramento dedicado ainda;
    # se isso virar problema, replicar o padrão de `support:view_pii`/`support:view_conversation`
    # já usado pelo atendimento OPA (ver docs/plano-analise-opa-suite-atendimentos.md item 9).
    report: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    first_imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    last_imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class SupportIxcUser(Base):
    """Usuário do IXC (`usuarios`) que abriu algum protocolo - só quem aparece em
    `SupportIxcTicket.opened_by_user_id`, não o cadastro inteiro. Guarda o grupo (`id_grupo`), que é
    o que define o Suporte Interno N1 (grupos 105 e 117, confirmados pelo usuário em 2026-10-06 - ver
    `ixc_n1.N1_IXC_GROUP_IDS`). O grupo é o ATUAL do usuário no IXC, atualizado a cada importação em
    que ele aparece: quem sair desses grupos deixa de contar, inclusive no histórico."""

    __tablename__ = "support_ixc_users"
    __table_args__ = (UniqueConstraint("ixc_user_id", name="uq_support_ixc_users_ixc_user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ixc_user_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(String(220), nullable=True)
    group_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class SupportIxcTaxonomyMapping(Base):
    """Mapeamento MANUAL e versionado de motivo (`SupportIxcTicket.subject_id`) -> tema ->
    categoria - Fase 0 do plano de evolução analítica do Atendimento IXC (2026-09-14). Existe
    porque `subject_name` (o motivo cru do IXC, ~80 valores) é granular demais pra virar um filtro
    de negócio (ex.: "Wi-Fi e equipamentos", "Triagem operacional") - essa camada não é derivável
    automaticamente dos dados, precisa ser definida por alguém que conhece a operação.

    Fase 0 só cria a tabela VAZIA (nenhum motivo populado ainda) - todo `subject_id` resolve como
    `NAO_MAPEADO` até o de-para ser preenchido (ver `ixc_ticket_taxonomy.resolve_theme_for_subject`).
    Isso é deliberado: a tabela vazia já habilita o contrato (coluna/endpoint) sem inventar uma
    taxonomia às pressas.

    NÃO reaproveita nem redefine `category` (hoje exposto em `SupportIxcTicketPriorityItem` como o
    motivo dominante, `subject_name` cru) - tema/categoria são campos NOVOS e adicionais, pra não
    quebrar nenhum consumidor existente do campo antigo.

    Versionado por `effective_from`: o mapeamento vigente de um `subject_id` num dia `D` é a linha
    daquele `subject_id` com o MAIOR `effective_from <= D` - permite corrigir um de-para no futuro
    sem apagar qual mapeamento estava valendo quando uma métrica antiga foi calculada (`version` é
    só um contador informativo de quantas vezes aquele subject_id já foi remapeado, não é a chave
    de vigência)."""

    __tablename__ = "support_ixc_taxonomy_mappings"
    __table_args__ = (
        Index("ix_support_ixc_taxonomy_subject_effective", "subject_id", "effective_from"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subject_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    theme_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    theme_label: Mapped[str] = mapped_column(String(160), nullable=False)
    category_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    category_label: Mapped[str] = mapped_column(String(160), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    # Peso-base (0-100) do TEMA no indicador de risco (ICC) - pedido do usuário (2026-09-15):
    # "prior relativo", não decisão final de incidente. `ixc_ticket_text_signal.py` ajusta este
    # peso pra CIMA/BAIXO por palavra-chave da descrição (`SupportIxcTicket.report`) - motivos
    # genéricos como "Registro de Atendimento Operacional" nascem com peso baixo de propósito e
    # dependem do texto pra escalar (evita "todo registro genérico virar falso sinal de
    # incidente", achado explícito do usuário). Calibração visual inicial, não regra validada
    # (mesmo aviso de `ixc_ticket_overview.CRITICAL_DEVIATION_PCT`).
    risk_weight: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class SupportIxcHourlyBaseline(Base):
    """Baseline pré-computado de atendimentos esperados por hora-do-dia/dia-da-semana - Fase 4 do
    plano de evolução analítica do Atendimento IXC (2026-09-15). Existe porque calcular isso ao
    vivo a cada request (média/desvio-padrão de N semanas anteriores, por hora, por regional)
    seria caro repetido - o mesmo raciocínio de `OperationBacklogSnapshot`, aqui aplicado a uma
    MÉDIA em vez de uma fotografia. Recalculado 1x/dia por `ixc_ticket_baseline.recompute_all_
    hourly_baselines` (job idempotente por dia, mesmo padrão de `backlog_snapshot.py`) - as linhas
    do dia são APAGADAS e reinseridas a cada recálculo (não é histórico incremental, é sempre "o
    baseline vigente agora", coerente com o fato de o baseline ser uma média móvel, não um fato
    pontual).

    `scope_type`/`scope_id`: `("global", None)` é a operação inteira; `("regional", <regional>)`
    é uma regional específica - o mesmo par usado como chave de agrupamento em `_scope_where`
    (ixc_ticket_context.py). `weekday` é 0=segunda...6=domingo (`date.weekday()`), `hour` é a hora
    LOCAL 0-23 (mesmo fuso dos demais horários do sistema, `America/Porto_Velho`)."""

    __tablename__ = "support_ixc_hourly_baselines"
    __table_args__ = (
        UniqueConstraint(
            "scope_type", "scope_id", "weekday", "hour", name="uq_support_ixc_hourly_baseline_scope_slot"
        ),
        Index("ix_support_ixc_hourly_baseline_scope", "scope_type", "scope_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scope_type: Mapped[str] = mapped_column(String(20), nullable=False)
    scope_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    hour: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_count: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    stddev_count: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    sample_weeks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class SupportOpaAttendance(Base):
    __tablename__ = "support_opa_attendances"
    __table_args__ = (
        UniqueConstraint("source_id", name="uq_support_opa_attendances_source_id"),
        Index("ix_support_opa_attendances_opened_closed", "opened_at", "closed_at"),
        Index("ix_support_opa_attendances_attendant_reason", "attendant_name", "reason_name"),
        Index(
            "ix_support_opa_attendances_tmr_backfill",
            "closed_at",
            "tmr_all_responses_seconds",
            "tmr_backfill_attempted_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    protocol: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    customer_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    customer_name: Mapped[str | None] = mapped_column(String(220), nullable=True)
    attendant_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    attendant_name: Mapped[str | None] = mapped_column(String(180), nullable=True, index=True)
    department_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    department_name: Mapped[str | None] = mapped_column(String(180), nullable=True, index=True)
    reason_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    reason_name: Mapped[str | None] = mapped_column(String(220), nullable=True, index=True)
    channel: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    channel_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    channel_customer: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    status: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    first_response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    tma_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tmr_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # TMR geral: mesmo cálculo do tmr_seconds, mas conta resposta de QUALQUER
    # atendente (bot ou humano) como resposta válida — pensado pra comparar
    # com painéis que não distinguem bot de humano no TMR. tmr_seconds
    # continua sendo o TMR só-humano, não foi alterado.
    tmr_all_responses_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # TMA EFETIVO (o do painel do OPA): da 1ª mensagem do atendente humano até a mensagem de
    # conclusão (ou a última mensagem humana, sem ela). `tma_seconds` continua sendo a duração
    # TOTAL (abertura -> encerramento), que inclui bot, fila e o tempo até o fechamento. NULL =
    # sem mensagem humana (atendimento só do bot) ou mensagens ainda não buscadas - nunca 0.
    # Ver opa_ingestion._effective_tma_seconds.
    tma_effective_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # TMR EFETIVO (APROXIMAÇÃO do TMR do painel do OPA, ±35% em 5 atendentes testados): média dos
    # intervalos entre a última mensagem do cliente e a resposta (humana ou do bot) depois da entrada
    # do atendente humano, descartando intervalos acima de 1 h. `tmr_seconds`/`tmr_all_responses_seconds`
    # não mudam. NULL = sem humano, sem resposta medível ou mensagens ainda não buscadas - nunca 0.
    # Ver opa_ingestion._effective_tmr_seconds.
    tmr_effective_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # TMR HUMANO "ao vivo": só respostas de atendente HUMANO e só a partir da entrada dele (mede a
    # rapidez do atendente, sem a espera pelo humano). `tmr_seconds` (legado) continua incluindo essa
    # espera e não muda. NULL = sem humano, sem resposta medível ou mensagens ainda não buscadas.
    # Ver opa_ingestion._human_tmr_after_entry_seconds.
    tmr_human_live_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # ESPERA PELO HUMANO ("1ª resposta humana"): da última mensagem do bot (a transferência) até a 1ª
    # mensagem do atendente humano; sem mensagem do bot, da última mensagem do cliente. Não inclui a
    # conversa do cliente com o bot (que o `first_response_at - opened_at` legado inclui). NULL = sem
    # humano ou mensagens ainda não buscadas. Ver opa_ingestion._human_wait_seconds.
    human_wait_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # REGRA DO OPA (2026-10-15): TMA e TMR ajustados contra o relatório por atendente do próprio OPA
    # (18 atendentes, 07/10 a 14/10, 2.603 conversas). Os painéis passam a usar estas colunas; as
    # `tma_effective_seconds`/`tmr_effective_seconds` acima ficam como histórico.
    # - `tma_active_seconds`: da 1ª mensagem humana até a conclusão (ou a última humana), somando os intervalos
    #   entre mensagens do cliente e do atendente com cada SILÊNCIO LIMITADO a 1 h (o cliente que some não
    #   infla o TMA). Erro médio contra o OPA: 15% (28% com a regra antiga).
    # - `tmr_gap_sum_seconds` e `tmr_gap_count`: soma e quantidade dos intervalos de resposta (última mensagem
    #   do cliente -> resposta de humano ou bot, depois da entrada do humano, cortando acima de 1 h). A média
    #   do painel é soma/contagem de TODAS as respostas juntas, não a média das médias por conversa (erro
    #   médio contra o OPA: 16% contra 30%).
    # NULL = sem humano, sem resposta medível ou ainda não calculado; use `active_metrics_at` para saber se
    # já foi calculado.
    tma_active_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tmr_gap_sum_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tmr_gap_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Quando as três colunas acima foram calculadas (mesmo que o resultado seja NULL: conversa só do bot).
    # O backfill noturno só reprocessa quem ainda não tem isto.
    active_metrics_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Nullable de propósito: NULL = atendimento ainda não classificado (histórico
    # anterior à Fase 2, ou mensagens indisponíveis) — nunca tratar como False.
    # Ver opa_ingestion._classify_bot_human.
    handled_by_bot: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    reached_human: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    bot_to_human_handoff: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # Resumo mínimo de handoff a partir das MESMAS mensagens já buscadas pro TMR
    # (zero chamada extra à API do OPA Suite) — existe só pra preparar uma
    # comparação futura contra o painel oficial do OPA (divergência de contagem
    # documentada em docs/roteiro-comparacao-tmr-opa-suite.md, seção 10.3), NÃO
    # altera tmr_seconds/tmr_all_responses_seconds/handled_by_bot/reached_human/
    # bot_to_human_handoff, que continuam calculados exatamente como antes.
    # NULL = mensagens indisponíveis ou atendimento sem resposta humana
    # classificável — nunca tratar como "sem handoff".
    distinct_human_attendant_ids: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    first_human_attendant_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_human_attendant_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    human_message_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bot_message_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    client_message_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Etiquetas do atendimento projetadas do `raw_payload` (`tags[].id_tag`) numa
    # string delimitada — ex.: ",id1,id2,". Existe porque etiqueta é a única
    # dimensão de filtro que o OPA só entrega dentro do JSON: filtrar direto no
    # payload (`json_array_elements`) medido em ~410 ms por query no volume real,
    # inviável numa tela que dispara ~8 agregações por carga. Sempre gravado com
    # separador nas duas pontas pra que `LIKE '%,id,%'` não case com um id que
    # apenas contenha outro como prefixo/sufixo. NULL = atendimento importado
    # antes desta coluna existir e ainda não reprojetado; string vazia com
    # separadores (",") = atendimento sem nenhuma etiqueta, que é diferente.
    tag_ids_text: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    # Última tentativa do backfill noturno de TMR histórico (ver
    # opa_ingestion.run_tmr_history_backfill) — NULL = nunca tentado. Marcado em toda
    # tentativa, sucesso ou falha, pra não bater sempre nos mesmos registros quando a
    # busca de mensagens falha (ex.: conversa muito antiga sem mensagem disponível na
    # API do OPA) — o backfill prioriza quem nunca foi tentado, depois quem foi
    # tentado há mais tempo.
    tmr_backfill_attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    first_imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    last_imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class SupportOccurrenceDetail(Base):
    """Diagnóstico e finalização de uma ocorrência (atendimento IXC do assunto 211).

    Uma linha por `su_ticket` do assunto 211, alimentada junto da importação de atendimentos
    (`occurrences_sync.py`). `diagnosis_id/name` vêm de `su_ticket.id_su_diagnostico` x tabela
    `su_diagnostico`; `finalized_at`/`finalization_report` vêm da mensagem de finalização do ticket
    (`su_mensagens` com `su_status = 'S'`). Ocorrência sem `finalized_at` está em aberto.

    Os horários seguem a convenção do restante do módulo: relógio do servidor IXC gravado como se
    fosse UTC (ver `ixc_ticket_ingestion._parse_ixc_datetime`)."""

    __tablename__ = "support_occurrence_details"
    __table_args__ = (
        UniqueConstraint("source_id", name="uq_support_occurrence_details_source_id"),
        Index("ix_support_occurrence_details_diagnosis", "diagnosis_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    diagnosis_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    diagnosis_name: Mapped[str | None] = mapped_column(String(220), nullable=True)
    ticket_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    finalization_report: Mapped[str | None] = mapped_column(Text, nullable=True)
    finalized_by_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class SupportContactGeo(Base):
    """Onde mora o cliente de um atendimento do OPA - base do Radar de Contatos do Suporte Interno.

    Uma linha por cliente do OPA (não por atendimento): `opa_customer_id` é o `_id` do cliente no OPA
    (`SupportOpaAttendance.customer_id`) e `ixc_customer_id` é o `id` do cadastro do OPA, que é o
    `id_cliente` do IXC (validado em 2026-10-20 contra os tickets do IXC). Cidade/bairro/regional vêm
    do cadastro do IXC (mesma regra de `ixc_ticket_ingestion._normalize_ticket_record`); latitude e
    longitude vêm do cadastro do OPA. `status = "not_found"` guarda quem não foi achado no IXC, para
    tentar de novo só depois de alguns dias em vez de a cada ciclo.

    Não guarda CPF, telefone nem texto de mensagem."""

    __tablename__ = "support_contact_geo"
    __table_args__ = (
        UniqueConstraint("opa_customer_id", name="uq_support_contact_geo_opa_customer"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opa_customer_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    ixc_customer_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ok")
    regional: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    neighborhood: Mapped[str | None] = mapped_column(String(160), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    resolved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class SupportPlanItem(Base):
    """Projeto ou tarefa lançado na aba Especialista/Analista do Suporte Interno.

    `kind` é "project" ou "task"; só tarefa tem `parent_id`, e o pai tem de ser projeto (a regra
    vive em `planning_service`). `assignee_ids` guarda os ids dos usuários responsáveis (um ou os
    dois). Tudo o que é lançado fica visível para quem acessa o Suporte Interno, por isso não há
    recorte por dono. `version` sobe a cada edição para barrar a gravação por cima de uma edição
    que a pessoa ainda não viu. Itens saem de cena por `archived`, nunca por exclusão."""

    __tablename__ = "support_plan_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="task", index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("support_plan_items.id", ondelete="SET NULL"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="planned", index=True)
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    assignee_ids: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_by_name: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class SupportPlanUpdate(Base):
    """Registro de andamento de um item (texto, autor e, quando houve, a mudança de status)."""

    __tablename__ = "support_plan_updates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("support_plan_items.id", ondelete="CASCADE"), nullable=False, index=True)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    author_name: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    text: Mapped[str] = mapped_column(Text, nullable=False)
    status_from: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status_to: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
