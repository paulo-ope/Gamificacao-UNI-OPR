"""Busca de cliente no IXC (por login ou por CPF) para autopreencher o formulário do UNI Localiza.

Campos confirmados por sondagem manual contra a API real em 2026-09-08 (mesmo método já usado em
`ixc_collaborator_lookup.py` para funcionários):
- `radusuarios` (login de acesso): `id`, `login`, `id_cliente` (FK), `latitude`/`longitude`
  (coordenada cadastrada do endereço de instalação).
- `cliente` (assinante/contrato): `id`, `razao` (nome), `cnpj_cpf` (com MÁSCARA nesta instalação,
  mesmo achado de `funcionarios.cpf_cnpj`), `latitude`/`longitude` (mesma coordenada do login, nos
  registros observados).

Um cliente pode ter zero ou mais logins (contrato assinado mas ainda não instalado, ou múltiplos
contratos) - a busca por CPF devolve uma linha por login encontrado; sem nenhum login, devolve uma
linha só com os dados do cliente (login/coordenada do login ausentes), para o atendente ainda
poder escolher o cliente pelo nome.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException

from app.services.documents import format_cpf_with_mask, is_valid_cpf, mask_document, normalize_document
from app.services.ixc_client import IxcApiError, IxcClient

RADUSUARIOS_TABLE = "radusuarios"
CLIENTE_TABLE = "cliente"


@dataclass
class IxcCustomerMatch:
    login_id: int | None
    login: str | None
    cliente_id: int
    name: str
    cpf_masked: str | None
    latitude: float | None
    longitude: float | None


def _safe_int(value: Any) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _cliente_match(record: dict[str, Any], *, login_id: int | None, login: str | None, latitude: float | None, longitude: float | None) -> IxcCustomerMatch | None:
    cliente_id = _safe_int(record.get("id"))
    name = str(record.get("razao") or record.get("fantasia") or "").strip()
    if not cliente_id or not name:
        return None
    return IxcCustomerMatch(
        login_id=login_id,
        login=login,
        cliente_id=cliente_id,
        name=name,
        cpf_masked=mask_document(record.get("cnpj_cpf")),
        latitude=latitude if latitude is not None else _safe_float(record.get("latitude")),
        longitude=longitude if longitude is not None else _safe_float(record.get("longitude")),
    )


def _fetch_cliente(client: IxcClient, cliente_id: int) -> dict[str, Any] | None:
    try:
        page = client.list(CLIENTE_TABLE, grid_param=[{"TB": "cliente.id", "OP": "=", "P": str(cliente_id)}], rp=1)
    except IxcApiError as exc:
        raise HTTPException(status_code=502, detail="Não foi possível consultar o cadastro do cliente no IXC agora.") from exc
    return page.records[0] if page.records else None


def search_customer_by_login(client: IxcClient, raw_query: str) -> list[IxcCustomerMatch]:
    """Busca por número do login (ID numérico) OU pelo login escrito (texto) - exatamente como o
    atendente tiver em mãos."""
    query = raw_query.strip()
    if not query:
        return []
    field = "radusuarios.id" if query.isdigit() else "radusuarios.login"
    try:
        page = client.list(RADUSUARIOS_TABLE, grid_param=[{"TB": field, "OP": "=", "P": query}], rp=5)
    except IxcApiError as exc:
        raise HTTPException(status_code=502, detail="Não foi possível consultar o login no IXC agora.") from exc

    matches: list[IxcCustomerMatch] = []
    for record in page.records:
        cliente_id = _safe_int(record.get("id_cliente"))
        if not cliente_id:
            continue
        cliente_record = _fetch_cliente(client, cliente_id)
        if not cliente_record:
            continue
        match = _cliente_match(
            cliente_record,
            login_id=_safe_int(record.get("id")),
            login=str(record.get("login") or "").strip() or None,
            latitude=_safe_float(record.get("latitude")),
            longitude=_safe_float(record.get("longitude")),
        )
        if match:
            matches.append(match)
    return matches


def search_customers_by_cpf(client: IxcClient, raw_cpf: str) -> list[IxcCustomerMatch]:
    normalized = normalize_document(raw_cpf)
    if not normalized or not is_valid_cpf(normalized):
        raise HTTPException(status_code=422, detail="Informe um CPF válido.")

    # Mesmo achado de `ixc_collaborator_lookup._fetch_funcionarios_by_cpf`: o documento fica
    # gravado COM MÁSCARA nesta instalação - tenta mascarado primeiro, dígitos puros como
    # resguardo, nunca as duas formas na mesma chamada (o webservice rejeita `IN` com pontuação).
    masked_cpf = format_cpf_with_mask(normalized)
    try:
        page = client.list(CLIENTE_TABLE, grid_param=[{"TB": "cliente.cnpj_cpf", "OP": "=", "P": masked_cpf}], rp=10) if masked_cpf else None
        if not page or not page.records:
            page = client.list(CLIENTE_TABLE, grid_param=[{"TB": "cliente.cnpj_cpf", "OP": "=", "P": normalized}], rp=10)
    except IxcApiError as exc:
        raise HTTPException(status_code=502, detail="Não foi possível consultar o CPF no IXC agora.") from exc

    matches: list[IxcCustomerMatch] = []
    for cliente_record in page.records:
        cliente_id = _safe_int(cliente_record.get("id"))
        if not cliente_id:
            continue
        try:
            logins_page = client.list(RADUSUARIOS_TABLE, grid_param=[{"TB": "radusuarios.id_cliente", "OP": "=", "P": str(cliente_id)}], rp=10)
        except IxcApiError as exc:
            raise HTTPException(status_code=502, detail="Não foi possível consultar os logins do cliente no IXC agora.") from exc

        if not logins_page.records:
            match = _cliente_match(cliente_record, login_id=None, login=None, latitude=None, longitude=None)
            if match:
                matches.append(match)
            continue

        for login_record in logins_page.records:
            match = _cliente_match(
                cliente_record,
                login_id=_safe_int(login_record.get("id")),
                login=str(login_record.get("login") or "").strip() or None,
                latitude=_safe_float(login_record.get("latitude")),
                longitude=_safe_float(login_record.get("longitude")),
            )
            if match:
                matches.append(match)
    return matches
