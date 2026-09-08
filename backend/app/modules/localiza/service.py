"""Regras de negócio do UNI Localiza - fora do router, conforme AGENTS.md."""

from __future__ import annotations

import hashlib
import math
import secrets
from datetime import date, datetime, time as dtime, timedelta, timezone
from typing import Any, Literal

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import User
from app.modules.localiza.models import LocationRequest
from app.services.audit_log import record_audit_log
from app.services.calculation import get_setting, upsert_setting
from app.services.calculation_closure import PORTO_VELHO_TZ

# Chave em `AppSetting` pra tornar a validade do link configurável pela própria aplicação, sem
# precisar editar `.env`/reiniciar o backend (pedido do usuário) - o valor de `Settings.localiza_link_ttl_hours`
# (config.py) continua servindo só de PADRÃO INICIAL, usado até alguém configurar isso pela tela.
LINK_TTL_SETTING_KEY = "localiza_link_ttl_hours"

# Limiares de classificação de divergência entre coordenada cadastrada e confirmada -
# centralizados aqui (pedido explícito do escopo: "não espalhados pela aplicação"). Mudar a régua
# é mudar só esta tupla.
DISTANCE_COMPATIBLE_MAX_METERS = 50.0
DISTANCE_MINOR_DIVERGENCE_MAX_METERS = 150.0
DISTANCE_RELEVANT_DIVERGENCE_MAX_METERS = 500.0

DistanceClassification = Literal["compatible", "minor_divergence", "relevant_divergence", "high_divergence"]
EffectiveStatus = Literal["pending", "confirmed", "invalidated", "expired"]

_EARTH_RADIUS_METERS = 6_371_000.0


def haversine_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return _EARTH_RADIUS_METERS * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def classify_distance(meters: float) -> DistanceClassification:
    if meters <= DISTANCE_COMPATIBLE_MAX_METERS:
        return "compatible"
    if meters <= DISTANCE_MINOR_DIVERGENCE_MAX_METERS:
        return "minor_divergence"
    if meters <= DISTANCE_RELEVANT_DIVERGENCE_MAX_METERS:
        return "relevant_divergence"
    return "high_divergence"


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _hash_ip(request: Request | None) -> str | None:
    if request is None or request.client is None:
        return None
    return hashlib.sha256(request.client.host.encode("utf-8")).hexdigest()[:32]


def _aware(value: datetime) -> datetime:
    """SQLite (testes) não preserva `tzinfo` em `DateTime(timezone=True)` - todo horário desta
    tabela é gravado em UTC por convenção (mesmo padrão de `portal_invites._aware`)."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _effective_status(item: LocationRequest, *, now: datetime) -> EffectiveStatus:
    if item.status == "pending" and _aware(item.expires_at) < now:
        return "expired"
    return item.status  # type: ignore[return-value]


def _generate_public_id(db: Session) -> str:
    for _ in range(5):
        candidate = secrets.token_hex(4).upper()
        if not db.scalar(select(LocationRequest.id).where(LocationRequest.public_id == candidate)):
            return candidate
    raise HTTPException(status_code=500, detail="Não foi possível gerar um identificador único. Tente novamente.")


def _validate_coordinate_pair(latitude: float | None, longitude: float | None) -> None:
    if (latitude is None) != (longitude is None):
        raise HTTPException(status_code=422, detail="Informe latitude e longitude cadastradas juntas, ou nenhuma das duas.")
    if latitude is not None and not (-90.0 <= latitude <= 90.0):
        raise HTTPException(status_code=422, detail="Latitude cadastrada inválida.")
    if longitude is not None and not (-180.0 <= longitude <= 180.0):
        raise HTTPException(status_code=422, detail="Longitude cadastrada inválida.")


def get_link_ttl_hours(db: Session) -> int:
    settings = get_settings()
    raw = get_setting(db, LINK_TTL_SETTING_KEY, str(settings.localiza_link_ttl_hours))
    try:
        return int(raw)
    except (TypeError, ValueError):
        return settings.localiza_link_ttl_hours


def set_link_ttl_hours(db: Session, user: User, hours: int) -> int:
    before = get_link_ttl_hours(db)
    upsert_setting(db, LINK_TTL_SETTING_KEY, str(hours), description="UNI Localiza: validade do link público (horas)")
    record_audit_log(db, user, "location_request.settings_updated", "localiza_settings", None, {"link_ttl_hours": before}, {"link_ttl_hours": hours})
    db.commit()
    return hours


def public_link(raw_token: str) -> str:
    settings = get_settings()
    base = settings.frontend_url.rstrip("/")
    return f"{base}/l/{raw_token}"


def serialize_detail(item: LocationRequest, *, now: datetime) -> dict[str, Any]:
    distance = item.distance_from_registered_meters
    return {
        "id": item.id,
        "public_id": item.public_id,
        "order_code": item.order_code,
        "opa_protocol": item.opa_protocol,
        "customer_id": item.customer_id,
        "customer_name": item.customer_name,
        "status": _effective_status(item, now=now),
        "registered_latitude": item.registered_latitude,
        "registered_longitude": item.registered_longitude,
        "gps_latitude": item.gps_latitude,
        "gps_longitude": item.gps_longitude,
        "confirmed_latitude": item.confirmed_latitude,
        "confirmed_longitude": item.confirmed_longitude,
        "accuracy_meters": item.accuracy_meters,
        "adjusted_manually": item.adjusted_manually,
        "distance_from_registered_meters": distance,
        "distance_classification": classify_distance(distance) if distance is not None else None,
        "created_at": item.created_at,
        "created_by_user_id": item.created_by_user_id,
        "requested_by_name": item.created_by_user.name if item.created_by_user else None,
        "expires_at": item.expires_at,
        "opened_at": item.opened_at,
        "confirmed_at": item.confirmed_at,
        "invalidated_at": item.invalidated_at,
    }


def list_location_requests(
    db: Session,
    *,
    search: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    status: str | None = None,
    created_by_user_id: int | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    conditions = []
    # "Meus links" (pedido do usuário: cada atendente vê por padrão só o que ele mesmo gerou,
    # com a opção de trocar pra "Todos") - filtro simples por dono, sem gate de permissão própria
    # (a permissão do módulo já controla quem acessa a tela; isso é só conveniência de UX).
    if created_by_user_id is not None:
        conditions.append(LocationRequest.created_by_user_id == created_by_user_id)
    if search:
        pattern = f"%{search.strip()}%"
        conditions.append(
            (LocationRequest.order_code.ilike(pattern))
            | (LocationRequest.opa_protocol.ilike(pattern))
            | (LocationRequest.customer_id.ilike(pattern))
            | (LocationRequest.customer_name.ilike(pattern))
            | (LocationRequest.public_id.ilike(pattern))
        )
    # Mesmo padrão de `scheduling/metrics.py` - filtro por data é sempre no fuso da operação
    # (America/Porto_Velho), dia inclusivo dos dois lados, nunca UTC cru (norma permanente de
    # qualidade de dados/filtros, ver docs/normas-qualidade-dados-metricas.md).
    if date_from:
        conditions.append(LocationRequest.created_at >= datetime.combine(date_from, dtime.min, tzinfo=PORTO_VELHO_TZ))
    if date_to:
        conditions.append(LocationRequest.created_at <= datetime.combine(date_to, dtime.max, tzinfo=PORTO_VELHO_TZ))
    # "confirmed"/"invalidated" são valores reais da coluna - filtram direto no SQL, com segurança
    # (o efetivo nunca diverge do gravado para esses dois). "pending"/"expired" são a MESMA coluna
    # ("pending") - só divergem pelo cálculo de expiração (`_effective_status`), então não dá pra
    # empurrar pro SQL sem duplicar essa regra; nesse caso filtra a coluna e refina em Python.
    if status in ("confirmed", "invalidated"):
        conditions.append(LocationRequest.status == status)
    elif status in ("pending", "expired"):
        conditions.append(LocationRequest.status == "pending")

    stmt = select(LocationRequest).where(*conditions).order_by(LocationRequest.created_at.desc()).limit(limit)
    items = db.scalars(stmt).all()
    serialized = [serialize_detail(item, now=now) for item in items]
    if status in ("pending", "expired"):
        serialized = [item for item in serialized if item["status"] == status]
    return serialized


def get_location_request_or_404(db: Session, item_id: int) -> LocationRequest:
    item = db.get(LocationRequest, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Solicitação de localização não encontrada.")
    return item


def create_location_request(
    db: Session,
    user: User,
    *,
    order_code: str | None,
    opa_protocol: str | None,
    customer_id: str | None,
    customer_name: str | None,
    registered_latitude: float | None,
    registered_longitude: float | None,
) -> tuple[dict[str, Any], str]:
    # Nenhum campo é obrigatório sozinho - o link costuma ser enviado ANTES de existir O.S. no
    # IXC (o atendente ainda está coletando a posição para abrir o atendimento). Mas SEM nenhum
    # identificador a solicitação fica impossível de achar depois na listagem, então exige-se
    # pelo menos um.
    order_code = (order_code or "").strip() or None
    opa_protocol = (opa_protocol or "").strip() or None
    customer_id = (customer_id or "").strip() or None
    customer_name = (customer_name or "").strip() or None
    if not any((order_code, opa_protocol, customer_id, customer_name)):
        raise HTTPException(
            status_code=422,
            detail="Informe ao menos um identificador da solicitação (código da O.S., protocolo OPA, ou dados do cliente).",
        )
    _validate_coordinate_pair(registered_latitude, registered_longitude)

    now = datetime.now(timezone.utc)
    raw_token = secrets.token_urlsafe(32)
    item = LocationRequest(
        public_id=_generate_public_id(db),
        token_hash=_hash_token(raw_token),
        order_code=order_code,
        opa_protocol=opa_protocol,
        customer_id=customer_id,
        customer_name=customer_name,
        status="pending",
        registered_latitude=registered_latitude,
        registered_longitude=registered_longitude,
        expires_at=now + timedelta(hours=get_link_ttl_hours(db)),
        created_by_user_id=user.id,
    )
    db.add(item)
    db.flush()
    record_audit_log(
        db, user, "location_request.created", "location_request", item.id,
        None, {"order_code": order_code, "opa_protocol": opa_protocol, "customer_id": customer_id, "expires_at": item.expires_at.isoformat()},
    )
    db.commit()
    db.refresh(item)
    return serialize_detail(item, now=now), raw_token


def attach_order_code(db: Session, user: User, item: LocationRequest, order_code: str) -> dict[str, Any]:
    """Preenche o código da O.S. de uma solicitação criada antes de ela existir no IXC. Permitido
    em qualquer status exceto invalidado (mesmo já confirmada - o cliente pode ter enviado a
    localização antes de a O.S. ser aberta)."""
    now = datetime.now(timezone.utc)
    if _effective_status(item, now=now) == "invalidated":
        raise HTTPException(status_code=409, detail="Não é possível anexar O.S. a uma solicitação invalidada.")
    order_code = order_code.strip()
    if not order_code:
        raise HTTPException(status_code=422, detail="Informe o código da O.S.")
    before = item.order_code
    item.order_code = order_code
    record_audit_log(db, user, "location_request.order_attached", "location_request", item.id, {"order_code": before}, {"order_code": order_code})
    db.commit()
    db.refresh(item)
    return serialize_detail(item, now=now)


def invalidate_location_request(db: Session, user: User, item: LocationRequest) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    if _effective_status(item, now=now) != "pending":
        raise HTTPException(status_code=409, detail="Só é possível invalidar uma solicitação pendente.")
    item.status = "invalidated"
    item.invalidated_at = now
    record_audit_log(db, user, "location_request.invalidated", "location_request", item.id, {"status": "pending"}, {"status": "invalidated"})
    db.commit()
    db.refresh(item)
    return serialize_detail(item, now=now)


def regenerate_location_request(db: Session, user: User, item: LocationRequest) -> tuple[dict[str, Any], str]:
    """Invalida a solicitação atual (se ainda estiver pendente) e cria uma nova, com os mesmos
    dados de O.S./cliente/coordenada cadastrada - link novo para reenviar ao cliente."""
    now = datetime.now(timezone.utc)
    if _effective_status(item, now=now) == "pending":
        item.status = "invalidated"
        item.invalidated_at = now
        record_audit_log(db, user, "location_request.invalidated", "location_request", item.id, {"status": "pending"}, {"status": "invalidated", "reason": "regenerated"})
        db.commit()
    return create_location_request(
        db, user,
        order_code=item.order_code,
        opa_protocol=item.opa_protocol,
        customer_id=item.customer_id,
        customer_name=item.customer_name,
        registered_latitude=item.registered_latitude,
        registered_longitude=item.registered_longitude,
    )


# --- Fluxo público (sem autenticação) ---------------------------------------------------------

def _find_by_token(db: Session, raw_token: str) -> LocationRequest | None:
    if not raw_token:
        return None
    return db.scalar(select(LocationRequest).where(LocationRequest.token_hash == _hash_token(raw_token)))


_STATUS_REASON: dict[EffectiveStatus, str] = {
    "expired": "TOKEN_EXPIRED",
    "invalidated": "INVALIDATED",
    "confirmed": "ALREADY_CONFIRMED",
}


def get_public_status(db: Session, raw_token: str) -> dict[str, Any]:
    item = _find_by_token(db, raw_token)
    if not item:
        return {"valid": False, "reason": "TOKEN_INVALID", "order_code": None, "opa_protocol": None, "customer_name": None, "status": None, "expires_at": None}

    now = datetime.now(timezone.utc)
    effective = _effective_status(item, now=now)
    if effective != "pending":
        return {
            "valid": False,
            "reason": _STATUS_REASON.get(effective, "TOKEN_INVALID"),
            "order_code": None,
            "opa_protocol": None,
            "customer_name": None,
            "status": effective,
            "expires_at": None,
        }

    if item.opened_at is None:
        item.opened_at = now
        record_audit_log(db, None, "location_request.link_opened", "location_request", item.id, None, {"order_code": item.order_code, "opa_protocol": item.opa_protocol})
        db.commit()

    return {
        "valid": True,
        "reason": None,
        "order_code": item.order_code,
        "opa_protocol": item.opa_protocol,
        "customer_name": item.customer_name,
        "status": effective,
        "expires_at": item.expires_at,
    }


def confirm_public_location(
    db: Session,
    raw_token: str,
    *,
    latitude: float,
    longitude: float,
    accuracy_meters: float,
    gps_latitude: float,
    gps_longitude: float,
    adjusted_manually: bool,
    request: Request,
) -> dict[str, Any]:
    item = _find_by_token(db, raw_token)
    if not item:
        raise HTTPException(status_code=404, detail="TOKEN_INVALID")

    now = datetime.now(timezone.utc)
    effective = _effective_status(item, now=now)
    if effective != "pending":
        raise HTTPException(status_code=409, detail=_STATUS_REASON.get(effective, "TOKEN_INVALID"))

    distance = None
    if item.registered_latitude is not None and item.registered_longitude is not None:
        distance = haversine_distance_meters(item.registered_latitude, item.registered_longitude, latitude, longitude)

    item.gps_latitude = gps_latitude
    item.gps_longitude = gps_longitude
    item.confirmed_latitude = latitude
    item.confirmed_longitude = longitude
    item.accuracy_meters = accuracy_meters
    item.adjusted_manually = adjusted_manually
    item.distance_from_registered_meters = distance
    item.status = "confirmed"
    item.confirmed_at = now
    item.confirmed_ip_hash = _hash_ip(request)
    item.user_agent = (request.headers.get("user-agent") or "")[:300]

    record_audit_log(
        db, None, "location_request.geolocation_confirmed", "location_request", item.id,
        None, {"order_code": item.order_code, "distance_meters": distance, "adjusted_manually": adjusted_manually},
    )
    db.commit()
    db.refresh(item)
    return {"status": "confirmed", "confirmed_at": item.confirmed_at}
