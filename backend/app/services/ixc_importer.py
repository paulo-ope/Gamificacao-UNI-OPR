from __future__ import annotations

import calendar
import contextlib
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import Collaborator, ImportRun, ScoringSubjectRule, ServiceOrder
from app.services.calculation_closure import find_paid_run_for_service_order_context
from app.services.ixc_client import (
    IxcClient,
    fetch_assuntos,
    fetch_clientes_by_ids,
    fetch_diagnosticos,
    fetch_funcionarios,
    fetch_logins_by_ids,
    fetch_service_orders,
    fetch_setores,
)
from app.services.point_balance import detect_post_payment_warranty_debits
from app.services.regional import normalize_regional_grouped as normalize_regional
from app.services.upvalue_importer import (
    ImportRowValidationError,
    UNKNOWN_VALUE,
    add_import_audit,
    build_import_result,
    find_existing_service_order,
    get_or_create_collaborator,
    normalize_text,
    reference_date_for_payload,
    values_differ,
)

# Campos que a API sempre traz (diferente da planilha, onde uma coluna pode não existir) -
# usado no mesmo mecanismo de diffing por "campo fornecido" que o importador UpValue já usa.
IXC_PROVIDED_FIELDS = [
    "os_code",
    "contract_id",
    "customer_login",
    "customer_name",
    "collaborator",
    "regional",
    "os_type",
    "os_subject",
    "diagnosis",
    "status",
    "sla_status",
    "sla_hours",
    "closing_time_hours",
    "opened_at",
    "closed_at",
    "is_warranty",
    "is_recurrence",
    "has_reschedule",
    "has_pending",
]

ZERO_DATE_SENTINELS = {"0000-00-00 00:00:00", "0000-00-00", ""}

# Chave arbitrária e fixa para o lock consultivo do Postgres que serializa importações do IXC (ver
# `_ixc_import_lock`). Só precisa ser única dentro do banco - não colide com nada mais no sistema.
IXC_IMPORT_LOCK_KEY = 913_275_001
IXC_IMPORT_LOCK_MAX_WAIT_SECONDS = 60.0
IXC_IMPORT_LOCK_POLL_INTERVAL_SECONDS = 1.0


class IxcImportLockTimeoutError(RuntimeError):
    """Outra importação do IXC (sincronização periódica ou retroativa) já está em andamento."""


@contextlib.contextmanager
def _ixc_import_lock(db: Session):
    """Serializa importações do IXC (sincronização periódica + backfill manual podem ser disparadas ao
    mesmo tempo por processos diferentes). Sem isso, duas importações concorrentes podem: (a) cada uma
    criar um `Collaborator` duplicado para o mesmo nome novo, já que a lista de colaboradores é lida uma
    vez por rodada e não há restrição de unicidade no nome; (b) tentar criar a mesma O.S. ao mesmo tempo e
    colidir na chave única de `os_code`. Usa lock consultivo do Postgres (`pg_try_advisory_lock`) preso à
    MESMA conexão da sessão que vai rodar a importação - não é um lock em memória do processo Python, então
    funciona entre processos/workers diferentes também.
    """
    waited = 0.0
    acquired = False
    while waited <= IXC_IMPORT_LOCK_MAX_WAIT_SECONDS:
        acquired = bool(db.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": IXC_IMPORT_LOCK_KEY}).scalar())
        if acquired:
            break
        time.sleep(IXC_IMPORT_LOCK_POLL_INTERVAL_SECONDS)
        waited += IXC_IMPORT_LOCK_POLL_INTERVAL_SECONDS

    if not acquired:
        raise IxcImportLockTimeoutError(
            "Outra importação do IXC (sincronização automática ou retroativa) já está em andamento. Tente novamente em instantes."
        )

    try:
        yield
    finally:
        db.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": IXC_IMPORT_LOCK_KEY})

# Setores do IXC (su_oss_chamado.setor -> empresa_setor) que interessam à gamificação - decisão do dono
# do produto: só trabalho técnico de campo (suporte externo/fibra/rádio), não administrativo/comercial.
# "7"=Suporte Externo, "8"=Suporte Externo Rádio, "9"=Suporte Externo Fibra.
IXC_TECHNICAL_SETOR_IDS = ["7", "8", "9"]

# Marcador explícito de "ninguém classificou este assunto ainda" - usado quando nenhuma fonte (regra
# cadastrada, mapa fixo, histórico aprendido) sabe o Tipo Geral de um assunto novo. Substitui o fallback
# antigo de nome-de-setor/"NAO IDENTIFICADO", que disfarçava um assunto sem classificação como se fosse
# uma categoria real - a O.S continua sendo importada normalmente (não trava o lote), só fica visível na
# fila "Assuntos sem regra" até alguém classificar (decisão do dono do produto).
PENDING_OS_TYPE = "PENDENTE DE CLASSIFICAÇÃO"

# os_subject -> os_type "de verdade" (a categoria de serviço que a matriz de pontuação E as regras de
# reincidência esperam, ex. "Manutenção"/"Ativação"/"Recolhimento"/"Mud. de Endereço" - não existe como
# campo no IXC, ver docs/plano-integracao-ixc.md seção 0.5). Fonte: REGRAS_CONFIGURADAS_GAMIFICACAO.md
# (extração real da produção, 2026-05-29) - a mesma referência usada para criar as ScoringSubjectRule que
# faltavam (seção 0.8). Gravado aqui como constante fixa, e NÃO aprendido de dado importado, porque dado
# importado pode ser apagado (já aconteceu - ver seção 0.9) e derrubaria essa resolução silenciosamente.
KNOWN_OS_TYPE_BY_SUBJECT: dict[str, str] = {
    "Instalação Evento/Permuta Fibra Urbana": "Ativação",
    "Instalação Fibra Rural": "Ativação",
    "Instalação Fibra Urbana": "Ativação",
    "Instalação Rádio": "Ativação",
    "Retorno de Instalação Fibra Rural": "Ativação",
    "Retorno de Instalação Fibra Urbana": "Ativação",
    "Retorno de Instalação Rádio": "Ativação",
    "Viabilidade": "Informação",
    "Alteração na Rede Interna Fibra Rural": "Manutenção",
    "Alteração na Rede Interna Fibra Urbana": "Manutenção",
    "Alteração na Rede Interna Rádio": "Manutenção",
    "Ativação de Login Presencial": "Manutenção",
    "Manutenção Preventiva Operacional": "Manutenção",
    "Regulagem de Sinal": "Manutenção",
    "Reincidência de Suporte Fibra Rural": "Manutenção",
    "Reincidência de Suporte Fibra Urbana": "Manutenção",
    "Reincidência de Suporte Rádio": "Manutenção",
    "Remoção de Flashman": "Manutenção",
    "Sem Conexão (Link LOS)": "Manutenção",
    "Sem Conexão Fibra Rural": "Manutenção",
    "Sem Conexão Fibra Urbana": "Manutenção",
    "Sem Conexão Rádio": "Manutenção",
    "Suporte Externo Fibra Rural": "Manutenção",
    "Suporte Externo Fibra Urbana": "Manutenção",
    "Suporte Externo Rádio": "Manutenção",
    "Suporte Prioritário": "Manutenção",
    "Suporte Streaming/Apps": "Manutenção",
    "Troca de Equipamentos": "Manutenção",
    "Alteração de Endereço Fibra Rural": "Mud. de Endereço",
    "Alteração de Endereço Fibra Urbana": "Mud. de Endereço",
    "Alteração de Endereço Rádio": "Mud. de Endereço",
    "Retorno de Alteração de Endereço Fibra Rural": "Mud. de Endereço",
    "Retorno de Alteração de Endereço Fibra Urbana": "Mud. de Endereço",
    "Retorno de Alteração de Endereço Rádio": "Mud. de Endereço",
    "Alteração da Tecnologia para Fibra": "Mud. de Tecnologia",
    "Retorno de Alteração de Tecnologia para Fibra": "Mud. de Tecnologia",
    "Instalação Evento/Permuta Fibra Rural": "Outros",
    "Retorno de Instalação Evento/Permuta Fibra Urbana": "Outros",
    "Recuperação de Equipamento por Cobrança": "Recolhimento",
    "Remoção de Equipamentos": "Recolhimento",
}


@dataclass
class IxcLookupCache:
    """Tabelas de apoio do IXC resolvidas por id. Assunto/diagnóstico/funcionário/setor são pequenas e
    carregadas por inteiro; cliente/login são carregados sob demanda (só os ids vistos no lote atual)."""

    assuntos: dict[int, dict[str, Any]] = field(default_factory=dict)
    diagnosticos: dict[int, dict[str, Any]] = field(default_factory=dict)
    funcionarios: dict[int, dict[str, Any]] = field(default_factory=dict)
    setores: dict[int, dict[str, Any]] = field(default_factory=dict)
    clientes: dict[int, dict[str, Any]] = field(default_factory=dict)
    logins: dict[int, dict[str, Any]] = field(default_factory=dict)
    # os_subject -> os_type "de verdade" (a categoria de serviço que a matriz de pontuação espera, ex.
    # "Manutenção"/"Ativação"/"Recolhimento") - não existe como campo no IXC (nem em su_oss_assunto, nem
    # em su_oss_chamado.setor), então é aprendido do histórico já importado via planilha. Ver
    # docs/plano-integracao-ixc.md para o achado completo.
    historical_os_type_by_subject: dict[str, str] = field(default_factory=dict)
    # os_subject -> os_type direto da ScoringSubjectRule ativa mais recente - a fonte "viva", editável
    # pelo admin pela própria tela (ver `_link_subject_rule`/`update_scoring_subject_rule` em
    # api/routes/scoring.py). Prioridade MÁXIMA na resolução: assim que alguém classifica um assunto
    # pela tela, toda importação futura desse assunto já nasce corretamente classificada, sem precisar
    # de deploy de código pra atualizar `KNOWN_OS_TYPE_BY_SUBJECT`.
    subject_rule_os_type_by_subject: dict[str, str] = field(default_factory=dict)


def _to_int(value: Any) -> int | None:
    if value in (None, "", "0"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _chunked(items: list[int], size: int = 200) -> list[list[int]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def parse_ixc_datetime(value: Any) -> datetime | None:
    """Converte datas do IXC ('YYYY-MM-DD HH:MM:SS') tratando o 'zero-date' do MySQL como ausente.

    Observado na prática (ver docs/plano-integracao-ixc.md, seção 6): `data_prazo_limite` às vezes vem
    como '0000-00-00 00:00:00' em vez de vazio - se não tratar isso, viraria uma data literal do ano 0.
    """
    if value is None:
        return None
    text = str(value).strip()
    if text in ZERO_DATE_SENTINELS:
        return None
    try:
        parsed = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            parsed = datetime.strptime(text, "%Y-%m-%d")
        except ValueError:
            return None
    return parsed.replace(tzinfo=timezone.utc)


def load_historical_os_type_mapping(db: Session) -> dict[str, str]:
    """Aprende, a partir do que já foi importado via planilha, qual `os_type` corresponde a cada
    `os_subject` (ex.: "Suporte Externo Fibra Urbana" -> "Manutenção"). Confirmado empiricamente que essa
    relação é 1:1 nos dados existentes (nenhum assunto tem mais de um tipo histórico). Exclui O.S. de
    origem IXC de propósito - senão um `os_type` já errado (resolvido por `setor`) contaminaria o
    aprendizado para o mesmo assunto."""
    rows = db.execute(
        select(ServiceOrder.os_subject, ServiceOrder.os_type)
        .where(ServiceOrder.os_code.notlike("IXC-%"))
        .distinct()
    ).all()
    mapping: dict[str, str] = {}
    for os_subject, os_type in rows:
        if os_subject and os_type and os_subject not in mapping:
            mapping[os_subject] = os_type
    return mapping


def load_subject_rule_os_type_mapping(db: Session) -> dict[str, str]:
    """Carrega o Tipo Geral direto da `ScoringSubjectRule` ativa mais recente por assunto - a fonte
    editável pelo admin pela tela "Assuntos sem regra"/matriz de pontuação. Quando o mesmo os_subject
    tem mais de uma regra (não deveria, mas pode acontecer antes da reconciliação de duplicatas rodar),
    usa a mais recentemente atualizada."""
    rows = db.execute(
        select(ScoringSubjectRule.os_subject, ScoringSubjectRule.os_type, ScoringSubjectRule.updated_at)
        .where(ScoringSubjectRule.active.is_(True))
        .order_by(ScoringSubjectRule.updated_at.desc().nullslast())
    ).all()
    mapping: dict[str, str] = {}
    for os_subject, os_type, _updated_at in rows:
        if os_subject and os_type and os_subject not in mapping:
            mapping[os_subject] = os_type
    return mapping


# Tabelas de apoio (assuntos/diagnósticos/funcionários/setores) mudam raramente (um admin cadastra um
# funcionário novo, um assunto novo no IXC etc. - não a cada minuto), mas antes desta cache eram
# buscadas por INTEIRO a cada importação (backfill manual ou sincronização periódica), gerando 15 das
# 18 requisições de um ciclo típico (~1.266 registros) mesmo quando havia só 1 O.S nova pra processar
# (achado real, medido ao vivo - ver docs/plano-integracao-ixc.md). Cache em memória do processo, com
# expiração por tempo: reduz a carga no IXC sem arriscar ficar desatualizado por muito tempo.
_LOOKUP_TABLES_CACHE_TTL_SECONDS = 60 * 60  # 1 hora


@dataclass
class _CachedLookupTables:
    assuntos: dict[int, dict[str, Any]]
    diagnosticos: dict[int, dict[str, Any]]
    funcionarios: dict[int, dict[str, Any]]
    setores: dict[int, dict[str, Any]]
    fetched_at: float


_lookup_tables_cache: _CachedLookupTables | None = None


def _fetch_lookup_tables(client: IxcClient) -> _CachedLookupTables:
    assuntos: dict[int, dict[str, Any]] = {}
    for record in fetch_assuntos(client):
        rid = _to_int(record.get("id"))
        if rid is not None:
            assuntos[rid] = record
    diagnosticos: dict[int, dict[str, Any]] = {}
    for record in fetch_diagnosticos(client):
        rid = _to_int(record.get("id"))
        if rid is not None:
            diagnosticos[rid] = record
    funcionarios: dict[int, dict[str, Any]] = {}
    for record in fetch_funcionarios(client):
        rid = _to_int(record.get("id"))
        if rid is not None:
            funcionarios[rid] = record
    setores: dict[int, dict[str, Any]] = {}
    for record in fetch_setores(client):
        rid = _to_int(record.get("id"))
        if rid is not None:
            setores[rid] = record
    return _CachedLookupTables(
        assuntos=assuntos, diagnosticos=diagnosticos, funcionarios=funcionarios, setores=setores,
        fetched_at=time.monotonic(),
    )


def build_lookup_cache(client: IxcClient, db: Session | None = None) -> IxcLookupCache:
    # Seguro sem lock próprio: toda importação (backfill manual ou sincronização periódica) - a única
    # chamadora desta função - já roda dentro de `_ixc_import_lock` (lock consultivo do Postgres), então
    # nunca há duas execuções concorrentes escrevendo nesta variável de módulo ao mesmo tempo, mesmo
    # com múltiplos workers (o lock é por conexão com o banco, não em memória do processo).
    global _lookup_tables_cache
    now = time.monotonic()
    is_stale = _lookup_tables_cache is None or (now - _lookup_tables_cache.fetched_at) > _LOOKUP_TABLES_CACHE_TTL_SECONDS
    if is_stale:
        _lookup_tables_cache = _fetch_lookup_tables(client)

    tables = _lookup_tables_cache
    cache = IxcLookupCache()
    # Os dicionários são compartilhados (não copiados) entre chamadas - seguro porque nada os modifica
    # depois de montados aqui (só leitura durante o mapeamento das O.S, ver grep por `.assuntos[` etc).
    cache.assuntos = tables.assuntos
    cache.diagnosticos = tables.diagnosticos
    cache.funcionarios = tables.funcionarios
    cache.setores = tables.setores
    if db is not None:
        cache.historical_os_type_by_subject = load_historical_os_type_mapping(db)
        cache.subject_rule_os_type_by_subject = load_subject_rule_os_type_mapping(db)
    return cache


def hydrate_clientes_e_logins(client: IxcClient, cache: IxcLookupCache, records: list[dict[str, Any]]) -> None:
    """Busca em lote (não um por um) os clientes/logins referenciados no lote de O.S. atual."""
    cliente_ids = sorted({_to_int(r.get("id_cliente")) for r in records} - {None})
    login_ids = sorted({_to_int(r.get("id_login")) for r in records} - {None})

    for chunk in _chunked(list(cliente_ids)):
        for record in fetch_clientes_by_ids(client, chunk):
            rid = _to_int(record.get("id"))
            if rid is not None:
                cache.clientes[rid] = record

    for chunk in _chunked(list(login_ids)):
        for record in fetch_logins_by_ids(client, chunk):
            rid = _to_int(record.get("id"))
            if rid is not None:
                cache.logins[rid] = record


def _cliente_display_name(record: dict[str, Any] | None) -> str:
    if not record:
        return ""
    for field_name in ("razao", "nome_social", "fantasia"):
        text = normalize_text(record.get(field_name))
        if text:
            return text
    return ""


def build_service_order_payload_from_ixc(record: dict[str, Any], cache: IxcLookupCache) -> dict[str, Any]:
    ixc_id = record.get("id")
    os_code = f"IXC-{ixc_id}" if ixc_id not in (None, "") else normalize_text(record.get("protocolo"))

    regional = normalize_regional(normalize_text(record.get("id_filial")) or None)

    assunto = cache.assuntos.get(_to_int(record.get("id_assunto")) or -1)
    os_subject = normalize_text(assunto.get("assunto")) if assunto else ""
    os_subject = os_subject or UNKNOWN_VALUE

    # os_type precisa ser a categoria de serviço que a matriz de pontuação E as regras de reincidência
    # esperam (ex. "Manutenção", "Ativação"), não o departamento/setor interno do IXC - são espaços de
    # valores diferentes (achado confirmado com dado real, ver docs/plano-integracao-ixc.md secao 0.5).
    # Prioridade: 1) ScoringSubjectRule ativa (fonte editável pelo admin pela tela - assim que alguém
    # classifica um assunto, toda importação futura já nasce correta); 2) mapa fixo conhecido
    # (KNOWN_OS_TYPE_BY_SUBJECT, nao depende de dado que pode ser apagado - ver secao 0.9, isso ja
    # quebrou uma vez); 3) o que o historico no banco ainda ensinar (caso exista alguma O.S nao-IXC
    # remanescente); 4) PENDING_OS_TYPE - nunca inventa uma classificação a partir do nome do setor
    # (isso disfarçava um assunto sem classificação como se fosse uma categoria real).
    os_type = (
        cache.subject_rule_os_type_by_subject.get(os_subject)
        or KNOWN_OS_TYPE_BY_SUBJECT.get(os_subject)
        or cache.historical_os_type_by_subject.get(os_subject)
        or PENDING_OS_TYPE
    )

    diagnostico = cache.diagnosticos.get(_to_int(record.get("id_su_diagnostico")) or -1)
    diagnosis = normalize_text(diagnostico.get("descricao")) if diagnostico else ""
    diagnosis = diagnosis or "Não informado"

    funcionario = cache.funcionarios.get(_to_int(record.get("id_tecnico")) or -1)
    collaborator_name = normalize_text(funcionario.get("funcionario")) if funcionario else UNKNOWN_VALUE

    cliente = cache.clientes.get(_to_int(record.get("id_cliente")) or -1)
    customer_name = _cliente_display_name(cliente) or "Não informado"

    login = cache.logins.get(_to_int(record.get("id_login")) or -1)
    customer_login = normalize_text(login.get("login")) if login else ""
    contract_id = normalize_text(login.get("id_contrato")) if login else ""

    opened_at = parse_ixc_datetime(record.get("data_abertura"))
    closed_at = parse_ixc_datetime(record.get("data_fechamento"))

    if opened_at is None:
        raise ImportRowValidationError("missing_date", "O.S sem data de abertura")

    # Decisão do dono do produto: uma O.S ainda em andamento pode trocar de colaborador até fechar, então
    # só entra no sistema quando já está definitiva. A busca já filtra por status='F' (ver
    # `fetch_service_orders(only_finalized=True)`), mas essa checagem aqui é uma segunda trava - se por
    # algum motivo o status='F' vier sem `data_fechamento` preenchida, rejeita em vez de criar uma O.S
    # "Concluída" sem data de fechamento real.
    if closed_at is None:
        raise ImportRowValidationError("missing_date", "O.S ainda não finalizada no IXC (sem data de fechamento)")

    status = "Concluída"

    # SLA: essa instância do IXC não usa status_sla/data_prazo_limite (confirmado com dado real -
    # ver docs/plano-integracao-ixc.md secao 6). Usa a meta de horas configurada no assunto.
    sla_hours_raw = assunto.get("meta_horas_abertura") if assunto else None
    try:
        sla_hours = float(sla_hours_raw) if sla_hours_raw not in (None, "") else None
    except (TypeError, ValueError):
        sla_hours = None

    closing_time_hours = None
    if opened_at and closed_at:
        closing_time_hours = round((closed_at - opened_at).total_seconds() / 3600, 2)

    return {
        "os_code": os_code,
        "contract_id": contract_id or UNKNOWN_VALUE,
        "customer_login": customer_login or None,
        "customer_name": customer_name,
        "collaborator_name": collaborator_name,
        "regional": regional,
        "os_type": os_type,
        "os_subject": os_subject,
        "diagnosis": diagnosis,
        "status": status,
        "sla_status": "",
        "sla_hours": sla_hours,
        "closing_time_hours": closing_time_hours,
        "opened_at": opened_at,
        "closed_at": closed_at,
        # Reincidencia/garantia nao vem pronta do IXC - o motor de regras parametrizadas
        # (RecurrenceClassificationRule) e quem decide isso, nao essas duas flags (ver plano, secao 5).
        "is_warranty": False,
        "is_recurrence": False,
        "is_priority": bool(sla_hours is not None and sla_hours <= 6),
        # TODO(gap aberto): sem confirmacao de campo para reagendamento/pendencia no su_oss_chamado alem
        # de data_reagendar - ver docs/plano-integracao-ixc.md.
        "has_reschedule": bool(normalize_text(record.get("data_reagendar"))),
        "has_pending": False,
        "__provided_fields__": list(IXC_PROVIDED_FIELDS),
    }


def import_ixc_service_orders(
    db: Session,
    client: IxcClient,
    *,
    opened_after: str | None = None,
    opened_before: str | None = None,
    closed_after: str | None = None,
    closed_before: str | None = None,
    updated_after: str | None = None,
    updated_before: str | None = None,
    imported_by: int | None = None,
) -> dict[str, Any]:
    """Adaptador Fase B: busca O.S. da API do IXC e alimenta o MESMO pipeline de matching/auditoria/
    bloqueio de período pago que o importador UpValue usa - não duplica essa lógica.

    `updated_after` (filtra por `ultima_atualizacao`) é o parâmetro certo para sincronização periódica -
    pega tanto O.S. novas quanto já existentes que mudaram (ex: uma que fechou). `updated_before` deve
    SEMPRE acompanhar `updated_after` na sincronização periódica: fecha a janela num instante fixo,
    capturado antes de começar a paginar (ver `sync_ixc_service_orders`) - sem isso, uma O.S. que passa a
    satisfazer o filtro EM QUANTO a busca ainda está paginando pode cair numa página já lida (a paginação é
    por offset/página, não por cursor) e ser perdida pra sempre, já que a sincronização seguinte só olha
    pra frente a partir da marca d'água (achado real: 2 O.S. de Nova Brasilândia D'Oeste fecharam durante a
    janela de uma sincronização e nunca mais apareceram - ver docs/plano-integracao-ixc.md). `closed_after`/
    `closed_before` filtram por data de FECHAMENTO - use os dois juntos para importar retroativamente um
    período específico (ver `backfill_ixc_service_orders`); é o par certo porque a apuração agrupa O.S.
    pelo mês em que fecharam, não em que abriram (uma O.S. aberta em 31/05 e fechada em 01/06 fica de fora
    do backfill de maio se filtrar por `opened_after`/`opened_before` - achado real documentado no plano).
    `opened_after`/`opened_before` continuam disponíveis para quem precisar filtrar por abertura. O
    resultado inclui `max_updated_at` (o maior `ultima_atualizacao` visto no lote) para quem quiser avançar
    uma marca d'água de sincronização (ver `sync_ixc_service_orders`).

    Serializado por `_ixc_import_lock` - sincronização periódica e backfill manual nunca rodam ao mesmo
    tempo (evita colaborador duplicado e corrida na criação de O.S, ver seção de achados do plano).
    """
    with _ixc_import_lock(db):
        return _import_ixc_service_orders_body(
            db, client,
            opened_after=opened_after, opened_before=opened_before,
            closed_after=closed_after, closed_before=closed_before,
            updated_after=updated_after, updated_before=updated_before,
            imported_by=imported_by,
        )


def _import_ixc_service_orders_body(
    db: Session,
    client: IxcClient,
    *,
    opened_after: str | None = None,
    opened_before: str | None = None,
    closed_after: str | None = None,
    closed_before: str | None = None,
    updated_after: str | None = None,
    updated_before: str | None = None,
    imported_by: int | None = None,
) -> dict[str, Any]:
    records = list(
        fetch_service_orders(
            client,
            opened_after=opened_after,
            opened_before=opened_before,
            closed_after=closed_after,
            closed_before=closed_before,
            updated_after=updated_after,
            updated_before=updated_before,
            setor_ids=IXC_TECHNICAL_SETOR_IDS,
            only_finalized=True,
        )
    )
    max_updated_at = max(
        (normalize_text(r.get("ultima_atualizacao")) for r in records if normalize_text(r.get("ultima_atualizacao"))),
        default=None,
    )
    cache = build_lookup_cache(client, db)
    hydrate_clientes_e_logins(client, cache, records)
    collaborators_cache = list(db.scalars(select(Collaborator)))

    errors: list[dict[str, Any]] = []
    import_run = ImportRun(
        filename=(
            "ixc-api"
            f"{'-opened_after=' + opened_after if opened_after else ''}"
            f"{'-opened_before=' + opened_before if opened_before else ''}"
            f"{'-closed_after=' + closed_after if closed_after else ''}"
            f"{'-closed_before=' + closed_before if closed_before else ''}"
            f"{'-updated_after=' + updated_after if updated_after else ''}"
            f"{'-updated_before=' + updated_before if updated_before else ''}"
        ),
        file_hash=None,
        source="ixc",
        status="completed",
        total_rows=len(records),
        detected_columns=[],
        mapped_columns={},
        errors=[],
        imported_by=imported_by,
        started_at=datetime.now(timezone.utc),
        notes=None,
    )
    db.add(import_run)
    db.flush()

    touched_orders: list[ServiceOrder] = []

    for offset, record in enumerate(records, start=1):
        try:
            payload = build_service_order_payload_from_ixc(record, cache)
            provided_fields = set(payload.pop("__provided_fields__", []))
            collaborator_name = payload.pop("collaborator_name")
            existing = find_existing_service_order(db, payload)
            target_paid_run = find_paid_run_for_service_order_context(
                db,
                (existing.closed_at if existing else None) or (existing.opened_at if existing else None) or reference_date_for_payload(payload),
                existing.regional if existing else payload.get("regional"),
            )
            if not target_paid_run and (existing is None or "collaborator" in provided_fields):
                collaborator, created_collaborator = get_or_create_collaborator(
                    db, collaborator_name, payload["regional"], collaborators_cache=collaborators_cache
                )
                if created_collaborator:
                    import_run.unknown_collaborator_count += 1
                payload["collaborator_id"] = collaborator.id
                if "collaborator" in provided_fields:
                    provided_fields.add("collaborator_id")

            if existing:
                changes: list[tuple[str, Any, Any]] = []
                for field_name, value in payload.items():
                    if field_name not in provided_fields:
                        continue
                    current_value = getattr(existing, field_name)
                    if values_differ(field_name, current_value, value):
                        changes.append((field_name, current_value, value))
                if not changes:
                    import_run.skipped_count += 1
                    add_import_audit(
                        db, import_run, "skipped", os_code=existing.os_code, service_order_id=existing.id,
                        reason="sem alterações", row_number=offset, created_by=imported_by,
                    )
                elif target_paid_run:
                    import_run.paid_period_blocked_count += 1
                    reason = "A O.S pertence a um período já marcado como pago e não foi alterada. Para revisar, crie uma revisão pós-pagamento."
                    add_import_audit(
                        db, import_run, "blocked_paid_period", os_code=existing.os_code,
                        service_order_id=existing.id, reason=reason, row_number=offset, created_by=imported_by,
                    )
                    errors.append({"row": offset, "reason": reason, "data": record})
                else:
                    for field_name, old_value, new_value in changes:
                        setattr(existing, field_name, new_value)
                        add_import_audit(
                            db, import_run, "updated", os_code=existing.os_code, service_order_id=existing.id,
                            field_name=field_name, old_value=old_value, new_value=new_value,
                            row_number=offset, created_by=imported_by,
                        )
                    import_run.updated_count += 1
                    touched_orders.append(existing)
            else:
                if target_paid_run:
                    import_run.paid_period_blocked_count += 1
                    reason = "A O.S pertence a um período já marcado como pago e não foi criada. Para revisar, crie uma revisão pós-pagamento."
                    add_import_audit(
                        db, import_run, "blocked_paid_period", os_code=payload.get("os_code"),
                        reason=reason, row_number=offset, created_by=imported_by,
                    )
                    errors.append({"row": offset, "reason": reason, "data": record})
                else:
                    service_order = ServiceOrder(**payload)
                    db.add(service_order)
                    db.flush()
                    add_import_audit(
                        db, import_run, "created", os_code=service_order.os_code, service_order_id=service_order.id,
                        reason="O.S criada pela integração IXC", row_number=offset, created_by=imported_by,
                    )
                    import_run.created_count += 1
                    touched_orders.append(service_order)
            import_run.processed_rows += 1
        except ImportRowValidationError as exc:
            import_run.processed_rows += 1
            import_run.rejected_count += 1
            if exc.code == "missing_date":
                import_run.missing_date_count += 1
            add_import_audit(db, import_run, "rejected", reason=exc.reason, row_number=offset, created_by=imported_by)
            errors.append({"row": offset, "reason": exc.reason, "data": record})
        except Exception as exc:
            import_run.processed_rows += 1
            import_run.error_rows += 1
            add_import_audit(
                db, import_run, "error", reason=f"Erro inesperado: {exc}", row_number=offset, created_by=imported_by,
            )
            errors.append({"row": offset, "reason": f"Erro inesperado: {exc}", "data": record})

    import_run.imported_rows = import_run.created_count + import_run.updated_count
    import_run.ignored_rows = import_run.skipped_count + import_run.rejected_count + import_run.paid_period_blocked_count + import_run.error_rows
    import_run.errors = errors
    import_run.finished_at = datetime.now(timezone.utc)
    if import_run.error_rows or import_run.rejected_count or import_run.paid_period_blocked_count:
        import_run.status = "completed_with_warnings"
    import_run.notes = (
        "Importação concluída com alertas." if import_run.status == "completed_with_warnings" else "Importação concluída com sucesso."
    )

    if touched_orders:
        detect_post_payment_warranty_debits(db, touched_orders, triggered_by=imported_by)

    result = build_import_result(import_run)
    result["max_updated_at"] = max_updated_at
    return result


def backfill_ixc_service_orders(
    db: Session,
    client: IxcClient,
    *,
    year: int,
    month: int,
    imported_by: int | None = None,
) -> dict[str, Any]:
    """Importação retroativa de um mês específico (busca sob demanda, não faz parte do polling
    periódico). Usa `import_ixc_service_orders` com `closed_after`/`closed_before` limitando ao mês
    pedido - uma vez importado, essa faixa fica salva em `service_orders` e a sincronização periódica
    (que só olha pra frente a partir da marca d'água) nunca precisa buscar essas O.S. antigas de novo.

    Filtra por data de FECHAMENTO (não abertura): a apuração agrupa O.S. pelo mês em que fecharam, então
    uma O.S. aberta no fim do mês anterior e fechada dentro deste mês precisa ser trazida por este backfill
    - se filtrasse por abertura, ela ficaria de fora tanto do backfill deste mês quanto do mês anterior
    (achado real: 4 O.S. abertas em 30-31/05/2026 e fechadas em 01/06 ficaram ausentes do backfill de junho
    até essa mudança - ver docs/plano-integracao-ixc.md).
    """
    if not 1 <= month <= 12:
        raise ValueError("Mês inválido (use 1-12).")

    start = f"{year:04d}-{month:02d}-01 00:00:00"
    last_day = calendar.monthrange(year, month)[1]
    end = f"{year:04d}-{month:02d}-{last_day:02d} 23:59:59"

    result = import_ixc_service_orders(db, client, closed_after=start, closed_before=end, imported_by=imported_by)
    result["backfill_period"] = f"{year:04d}-{month:02d}"
    return result
