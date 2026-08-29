from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Collaborator, User
from app.services.audit_log import record_audit_log
from app.services.documents import format_cpf_with_mask, is_valid_cpf, mask_document, normalize_document
from app.services.ixc_client import IxcApiError, IxcClient
from app.services.portal_invites import create_invite

# Fase 2C - convite inteligente por CPF integrado ao IXC (ver
# docs/portal-ciclo-vida-conta-colaborador.md). `funcionarios` é a tabela correta de colaboradores
# no IXC (RH/técnico de campo) - confirmado por sondagem manual em 2026-08-29 (~864 registros,
# filtro por `funcionarios.cpf_cnpj` retorna 1 funcionário correto). `cliente` NÃO é usada como
# fonte aqui de propósito - é o cadastro de assinante/contrato, uma entidade completamente
# diferente de quem trabalha na UNI.
FUNCIONARIOS_TABLE = "funcionarios"


@dataclass
class IxcCollaboratorMatch:
    ixc_employee_id: int
    name: str
    email: str | None
    phone: str | None
    cpf_masked: str | None
    active: bool
    department_id: int | None
    sector_id: int | None
    local_collaborator_id: int | None
    local_collaborator_name: str | None
    local_match_kind: str | None  # "ixc_employee_id" | "cpf" | "name" | None
    # Só existe dentro do processo desta chamada - nunca serializado na resposta HTTP
    # (`IxcCpfLookupOut` não tem este campo). Necessário pra Fase seguinte (criar convite)
    # revalidar o mesmo colaborador sem reconsultar o IXC uma segunda vez por chamada.
    normalized_cpf: str


def _normalize_name(name: str) -> str:
    return " ".join(name.strip().split()).casefold()


def _safe_int(value: Any) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _parse_active(value: Any) -> bool:
    if value is None:
        return True
    return str(value).strip().upper() in ("S", "1", "TRUE", "SIM", "ATIVO")


def find_local_collaborator(db: Session, *, ixc_employee_id: int, normalized_cpf: str, name: str) -> tuple[Collaborator | None, str | None]:
    """Ordem de prioridade exigida (ver seção 2 do documento de planejamento - vínculo nunca é
    automático, mas a ORDEM de sugestão importa): `ixc_employee_id` já vinculado é o sinal mais
    forte (alguém já confirmou esse vínculo antes); CPF é o segundo mais forte (identifica a
    pessoa); nome normalizado é só uma pista fraca (nomes colidem), sempre tratado como sugestão."""
    by_ixc_id = db.scalar(select(Collaborator).where(Collaborator.ixc_employee_id == ixc_employee_id))
    if by_ixc_id:
        return by_ixc_id, "ixc_employee_id"

    by_cpf = db.scalar(select(Collaborator).where(Collaborator.cpf == normalized_cpf))
    if by_cpf:
        return by_cpf, "cpf"

    if name:
        target = _normalize_name(name)
        # Tabela pequena (~800 colaboradores) e ação disparada manualmente por um admin, não em
        # lote - varredura em Python é simples e não há indício de que valha a pena outra
        # estratégia (ver docs/manual_desenvolvimento_senior.md seção 5.3, medir antes de otimizar).
        for candidate in db.scalars(select(Collaborator)).all():
            if _normalize_name(candidate.name) == target:
                return candidate, "name"

    return None, None


def _fetch_funcionarios_by_cpf(client: IxcClient, normalized_cpf: str) -> list[dict[str, Any]]:
    """Achado real em 2026-08-29 (CPF de teste `70240110250`, dígito verificador válido, não
    encontrado apesar de existir no IXC): `funcionarios.cpf_cnpj` nesta instalação guarda o
    documento COM MÁSCARA (`702.401.102-50`), não só dígitos - um filtro `=` com o valor
    normalizado nunca bate com o registro real, mesmo ele existindo. Tenta primeiro com máscara
    (formato confirmado contra a API real); só tenta dígitos puros depois, como resguardo pra um
    registro legado que porventura tenha sido gravado sem máscara - nunca o contrário, pra não
    pagar uma segunda chamada no caso comum. `OP: IN` com os dois formatos numa única chamada foi
    tentado e descartado: o webservice desta instalação devolve uma página de erro
    (`RESPOSTA_INVALIDA`) pra `IN` com valores contendo pontuação."""
    masked_cpf = format_cpf_with_mask(normalized_cpf)
    if masked_cpf:
        page = client.list(FUNCIONARIOS_TABLE, grid_param=[{"TB": "funcionarios.cpf_cnpj", "OP": "=", "P": masked_cpf}], page=1, rp=5)
        if page.records:
            return page.records
    page = client.list(FUNCIONARIOS_TABLE, grid_param=[{"TB": "funcionarios.cpf_cnpj", "OP": "=", "P": normalized_cpf}], page=1, rp=5)
    return page.records


def _mask_phone_for_confirmation(phone: str | None) -> str | None:
    """Mascaramento parcial pro autoatendimento (Fase 2D - colaborador confirma o PRÓPRIO
    telefone antes de solicitar acesso, pedido do usuário em 2026-08-29): mostra DDD + últimos 4
    dígitos, o suficiente pra a pessoa reconhecer "é o meu número" sem expor o telefone inteiro a
    quem só adivinhou um CPF de dígito verificador válido (rota pública, sem autenticação)."""
    digits = "".join(char for char in (phone or "") if char.isdigit())
    if len(digits) < 8:
        return None
    last4 = digits[-4:]
    ddd = digits[:2] if len(digits) >= 10 else None
    return f"({ddd}) ****-{last4}" if ddd else f"****-{last4}"


def find_funcionario_identity_by_cpf(client: IxcClient, normalized_cpf: str) -> dict[str, Any] | None:
    """Busca crua (nome + telefone em claro), sem auditoria - quem chama decide o contexto de
    auditoria (autoatendimento público x admin). Reaproveitada tanto pelo autoatendimento (Fase
    2D) quanto por `submit_access_request`, que revalida o CPF contra o IXC de novo no momento do
    envio em vez de confiar no que o cliente devolveu na etapa de confirmação (mesmo princípio de
    "nunca confia no cliente pra dado que o servidor pode verificar" já usado em
    `create_invite_from_ixc`).

    `ixc_employee_id` (2026-08-29): nunca serializado em resposta pública (`PortalAccessRequestCpfLookupOut`
    não tem esse campo) - existe só pra `submit_access_request` poder aplicar a mesma prioridade de
    correspondência de `find_local_collaborator` (ixc_employee_id > CPF > nome) que o fluxo do
    admin já usa em `lookup_collaborator_by_cpf`."""
    records = _fetch_funcionarios_by_cpf(client, normalized_cpf)
    if len(records) != 1:
        return None
    record = records[0]
    name = str(record.get("funcionario") or "").strip()
    phone = (str(record.get("fone_celular") or "").strip()) or None
    if not name:
        return None
    return {"name": name, "phone": phone, "ixc_employee_id": _safe_int(record.get("id"))}


def lookup_own_identity_by_cpf(db: Session, client: IxcClient, cpf: str) -> dict[str, Any]:
    """Fase 2D - autoatendimento: o próprio colaborador digita o CPF pra confirmar nome e telefone
    antes de solicitar acesso (pedido do usuário em 2026-08-29). Pública, sem autenticação -
    devolve só nome e telefone PARCIALMENTE mascarado, nunca e-mail (e-mail é sempre digitado por
    quem solicita, nunca herdado do IXC - decisão explícita do usuário) e nunca dado interno
    (`ixc_employee_id`, departamento, setor, vínculo local - isso é informação só do admin,
    ver `lookup_collaborator_by_cpf`)."""
    normalized_cpf = normalize_document(cpf)
    if not normalized_cpf or not is_valid_cpf(normalized_cpf):
        raise HTTPException(status_code=422, detail="CPF inválido. Confira os números e tente novamente.")
    cpf_masked = mask_document(normalized_cpf)

    try:
        identity = find_funcionario_identity_by_cpf(client, normalized_cpf)
    except IxcApiError as exc:
        record_audit_log(db, None, "ixc_collaborator.self_lookup_failed", "ixc_collaborator", None, None, {"cpf_masked": cpf_masked, "error": "ixc_api_error"})
        db.commit()
        raise HTTPException(status_code=502, detail="Não foi possível consultar o IXC agora. Tente novamente em alguns instantes.") from exc

    if not identity:
        record_audit_log(db, None, "ixc_collaborator.self_lookup_not_found", "ixc_collaborator", None, None, {"cpf_masked": cpf_masked})
        db.commit()
        raise HTTPException(status_code=404, detail="Nenhum funcionário encontrado no IXC para este CPF.")

    record_audit_log(db, None, "ixc_collaborator.self_lookup_found", "ixc_collaborator", None, None, {"cpf_masked": cpf_masked})
    db.commit()

    return {"name": identity["name"], "phone_masked": _mask_phone_for_confirmation(identity["phone"])}


def lookup_collaborator_by_cpf(db: Session, admin_user: User, client: IxcClient, cpf: str) -> IxcCollaboratorMatch:
    """Toda consulta EFETIVAMENTE feita ao IXC é auditada aqui dentro (achado/não achado/múltiplos),
    commitada na hora - mesmo quando termina em erro, porque a auditoria da tentativa de consulta
    precisa sobreviver independente do desfecho (`get_db` não faz rollback automático, só fecha a
    sessão; sem commit explícito aqui, a linha de auditoria de uma consulta que falhou seria
    perdida). CPF mascarado sempre, nunca em claro (seção 9 do documento de planejamento)."""
    normalized_cpf = normalize_document(cpf)
    if not normalized_cpf or not is_valid_cpf(normalized_cpf):
        raise HTTPException(status_code=422, detail="CPF inválido. Confira os números e tente novamente.")
    cpf_masked = mask_document(normalized_cpf)

    try:
        records = _fetch_funcionarios_by_cpf(client, normalized_cpf)
    except IxcApiError as exc:
        record_audit_log(db, admin_user, "ixc_collaborator.lookup_failed", "ixc_collaborator", None, None, {"cpf_masked": cpf_masked, "error": "ixc_api_error"})
        db.commit()
        raise HTTPException(status_code=502, detail="Não foi possível consultar o IXC agora. Tente novamente em alguns instantes.") from exc

    if not records:
        record_audit_log(db, admin_user, "ixc_collaborator.lookup_not_found", "ixc_collaborator", None, None, {"cpf_masked": cpf_masked})
        db.commit()
        raise HTTPException(status_code=404, detail="Nenhum funcionário encontrado no IXC para este CPF.")
    if len(records) > 1:
        # Nunca deveria acontecer (CPF é único), mas se acontecer o sistema NUNCA decide sozinho
        # qual dos registros é o certo - exige revisão manual fora deste fluxo.
        record_audit_log(
            db, admin_user, "ixc_collaborator.lookup_ambiguous", "ixc_collaborator", None, None,
            {"cpf_masked": cpf_masked, "matches": len(records)},
        )
        db.commit()
        raise HTTPException(
            status_code=409,
            detail="Mais de um funcionário foi encontrado no IXC para este CPF. Revise manualmente antes de convidar.",
        )

    record = records[0]
    ixc_employee_id = _safe_int(record.get("id"))
    if ixc_employee_id is None:
        record_audit_log(db, admin_user, "ixc_collaborator.lookup_failed", "ixc_collaborator", None, None, {"cpf_masked": cpf_masked, "error": "missing_id"})
        db.commit()
        raise HTTPException(status_code=502, detail="Resposta inesperada do IXC para este funcionário (sem id).")

    name = str(record.get("funcionario") or "").strip()
    email = (str(record.get("email") or "").strip()) or None
    phone = (str(record.get("fone_celular") or "").strip()) or None
    active = _parse_active(record.get("ativo"))
    department_id = _safe_int(record.get("id_departamento"))
    sector_id = _safe_int(record.get("id_setor_padrao"))

    local, match_kind = find_local_collaborator(db, ixc_employee_id=ixc_employee_id, normalized_cpf=normalized_cpf, name=name)

    record_audit_log(
        db, admin_user, "ixc_collaborator.lookup_found", "ixc_collaborator", ixc_employee_id, None,
        {"cpf_masked": cpf_masked, "local_match_kind": match_kind},
    )
    db.commit()

    return IxcCollaboratorMatch(
        ixc_employee_id=ixc_employee_id,
        name=name,
        email=email,
        phone=phone,
        cpf_masked=cpf_masked,
        active=active,
        department_id=department_id,
        sector_id=sector_id,
        local_collaborator_id=local.id if local else None,
        local_collaborator_name=local.name if local else None,
        local_match_kind=match_kind,
        normalized_cpf=normalized_cpf,
    )


def enrich_collaborator_from_ixc(collaborator: Collaborator, match: IxcCollaboratorMatch) -> None:
    """Preenche só o que está VAZIO localmente - nunca sobrescreve um valor já cadastrado
    silenciosamente. CPF e `ixc_employee_id` divergentes são bloqueados (409 na rota) em vez de
    corrigidos sozinhos - o mesmo princípio do primeiro acesso da Fase 1 (CPF já cadastrado
    CONFIRMA, nunca sobrescreve), estendido aqui pra `ixc_employee_id` porque esse campo também é
    usado por outros módulos (Operação Analítica) pra casar colaborador com técnico de O.S. -
    trocá-lo por engano reatribuiria esse histórico inteiro pra outra pessoa."""
    if collaborator.ixc_employee_id is None:
        collaborator.ixc_employee_id = match.ixc_employee_id
    elif collaborator.ixc_employee_id != match.ixc_employee_id:
        raise HTTPException(
            status_code=409,
            detail="Este colaborador já está vinculado a outro funcionário do IXC. Revise manualmente antes de convidar.",
        )

    if not collaborator.cpf:
        collaborator.cpf = match.normalized_cpf
    elif normalize_document(collaborator.cpf) != match.normalized_cpf:
        raise HTTPException(
            status_code=409,
            detail="O CPF encontrado no IXC não confere com o CPF já cadastrado para este colaborador.",
        )

    if not collaborator.email and match.email:
        collaborator.email = match.email
    if not collaborator.phone and match.phone:
        collaborator.phone = match.phone


def create_invite_from_ixc(
    db: Session,
    admin_user: User,
    client: IxcClient,
    *,
    cpf: str,
    collaborator_id: int,
    email: str,
    role: str,
) -> tuple[dict[str, Any], str]:
    """Confirma o colaborador e gera o convite (Fase 2C). Revalida o CPF contra o IXC de novo
    aqui, dentro da MESMA chamada que cria o convite - nunca confia em dado de uma consulta
    anterior vindo do cliente (o cliente só ecoa o que já viu; a decisão de segurança é sempre
    recalculada no servidor). Enriquecimento e criação do convite dividem a mesma transação: se a
    criação do convite falhar (ex.: convite duplicado pendente), o enriquecimento também não é
    persistido - `create_invite` é quem chama `db.commit()` no fim."""
    match = lookup_collaborator_by_cpf(db, admin_user, client, cpf)

    collaborator = db.get(Collaborator, collaborator_id)
    if not collaborator:
        raise HTTPException(status_code=404, detail="Colaborador não encontrado.")

    before = {
        "ixc_employee_id": collaborator.ixc_employee_id,
        "cpf_filled": bool(collaborator.cpf),
        "email_filled": bool(collaborator.email),
        "phone_filled": bool(collaborator.phone),
    }
    enrich_collaborator_from_ixc(collaborator, match)
    changed = (
        before["ixc_employee_id"] != collaborator.ixc_employee_id
        or (not before["cpf_filled"] and bool(collaborator.cpf))
        or (not before["email_filled"] and bool(collaborator.email))
        or (not before["phone_filled"] and bool(collaborator.phone))
    )
    if changed:
        db.flush()
        # Nunca CPF/e-mail/telefone em claro - só o fato de que o cadastro foi enriquecido e a
        # partir de qual funcionário do IXC (seção 9 do documento de planejamento).
        record_audit_log(
            db,
            admin_user,
            "collaborator.enriched_from_ixc",
            "collaborators",
            collaborator.id,
            before,
            {
                "ixc_employee_id": collaborator.ixc_employee_id,
                "cpf_filled": bool(collaborator.cpf),
                "email_filled": bool(collaborator.email),
                "phone_filled": bool(collaborator.phone),
            },
        )

    return create_invite(db, admin_user, email=email, collaborator_id=collaborator_id, role=role)
