"""Rotas internas (autenticadas) do UNI Localiza."""

from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.security import require_permission
from app.db.session import get_db
from app.models import User
from app.modules.localiza import ixc_lookup, service
from app.modules.localiza.schemas import (
    IxcCustomerSearchOut,
    LocalizaSettingsOut,
    LocalizaSettingsUpdate,
    LocationRequestAttachOrder,
    LocationRequestCreate,
    LocationRequestCreateOut,
    LocationRequestOut,
    LocationRequestStatus,
)
from app.services.ixc_client import get_ixc_client

router = APIRouter(prefix="/localiza", tags=["localiza"])


@router.get("", response_model=list[LocationRequestOut])
def list_location_requests_route(
    search: str | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    status: LocationRequestStatus | None = Query(default=None),
    mine_only: bool = Query(default=False, description="Só as solicitações geradas pelo usuário autenticado"),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("localiza:read")),
):
    if date_from and date_to and date_to < date_from:
        raise HTTPException(status_code=400, detail="A data final não pode ser anterior à inicial.")
    return service.list_location_requests(
        db, search=search, date_from=date_from, date_to=date_to, status=status,
        created_by_user_id=user.id if mine_only else None, limit=limit,
    )


@router.get("/settings", response_model=LocalizaSettingsOut)
def get_localiza_settings_route(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("localiza:manage")),
):
    return {"link_ttl_hours": service.get_link_ttl_hours(db)}


@router.put("/settings", response_model=LocalizaSettingsOut)
def update_localiza_settings_route(
    payload: LocalizaSettingsUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("localiza:manage")),
):
    return {"link_ttl_hours": service.set_link_ttl_hours(db, user, payload.link_ttl_hours)}


@router.post("", response_model=LocationRequestCreateOut, status_code=201)
def create_location_request_route(
    payload: LocationRequestCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("localiza:manage")),
):
    item, raw_token = service.create_location_request(
        db, user,
        order_code=payload.order_code,
        opa_protocol=payload.opa_protocol,
        customer_id=payload.customer_id,
        customer_name=payload.customer_name,
        registered_latitude=payload.registered_latitude,
        registered_longitude=payload.registered_longitude,
        ixc_cliente_id=payload.ixc_cliente_id,
        ixc_login_id=payload.ixc_login_id,
        ixc_login=payload.ixc_login,
    )
    return {**item, "token": raw_token, "public_link": service.public_link(raw_token)}


@router.get("/ixc/search", response_model=IxcCustomerSearchOut)
def search_ixc_customer_route(
    login: str | None = Query(default=None, description="Número do login ou o login escrito"),
    cpf: str | None = Query(default=None, description="CPF do cliente"),
    user: User = Depends(require_permission("localiza:manage")),
):
    """Busca ao vivo no IXC - por login (número ou texto) OU por CPF, nunca os dois juntos. Usada
    pelo formulário de criação para autopreencher nome/identificador/coordenada cadastrada a
    partir de um cadastro já existente, em vez de o atendente digitar tudo à mão."""
    if bool(login) == bool(cpf):
        raise HTTPException(status_code=422, detail="Informe o login OU o CPF do cliente, nunca os dois.")
    client = get_ixc_client()
    matches = ixc_lookup.search_customer_by_login(client, login) if login else ixc_lookup.search_customers_by_cpf(client, cpf)
    return {"matches": matches}


@router.get("/{item_id}", response_model=LocationRequestOut)
def get_location_request_route(
    item_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("localiza:read")),
):
    item = service.get_location_request_or_404(db, item_id)
    return service.serialize_detail(item, now=datetime.now(timezone.utc))


@router.post("/{item_id}/invalidate", response_model=LocationRequestOut)
def invalidate_location_request_route(
    item_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("localiza:manage")),
):
    item = service.get_location_request_or_404(db, item_id)
    return service.invalidate_location_request(db, user, item)


@router.post("/{item_id}/attach-order", response_model=LocationRequestOut)
def attach_order_code_route(
    item_id: int,
    payload: LocationRequestAttachOrder,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("localiza:manage")),
):
    item = service.get_location_request_or_404(db, item_id)
    return service.attach_order_code(db, user, item, payload.order_code)


@router.post("/{item_id}/regenerate", response_model=LocationRequestCreateOut, status_code=201)
def regenerate_location_request_route(
    item_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("localiza:manage")),
):
    item = service.get_location_request_or_404(db, item_id)
    new_item, raw_token = service.regenerate_location_request(db, user, item)
    return {**new_item, "token": raw_token, "public_link": service.public_link(raw_token)}
