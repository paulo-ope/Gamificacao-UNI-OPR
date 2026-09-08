"""Rotas públicas (sem autenticação) do UNI Localiza - página que o cliente abre pelo WhatsApp.

Rate limiting em memória por IP, mesmo padrão de `app/api/routes/invites.py` (defesa em
profundidade - o token já tem 256 bits de entropia própria, força bruta online é inviável).
Aplicado tanto na consulta de status quanto na confirmação, porque a consulta de status também
serve para "adivinhar" se um token existe.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.localiza import service
from app.modules.localiza.schemas import PublicLocationConfirmOut, PublicLocationConfirmRequest, PublicLocationStatusOut

router = APIRouter(prefix="/public/location", tags=["localiza-public"])

RATE_WINDOW_MINUTES = 15
RATE_MAX_ATTEMPTS = 20
_attempts: dict[str, list[datetime]] = {}


def _guard_rate_limit(request: Request) -> None:
    client_host = request.client.host if request.client else "unknown"
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=RATE_WINDOW_MINUTES)
    attempts = [attempt for attempt in _attempts.get(client_host, []) if attempt >= window_start]
    if len(attempts) >= RATE_MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Muitas tentativas. Aguarde alguns minutos e tente novamente.")
    attempts.append(now)
    _attempts[client_host] = attempts


@router.get("/{token}", response_model=PublicLocationStatusOut, dependencies=[Depends(_guard_rate_limit)])
def get_public_location_status(token: str, db: Session = Depends(get_db)):
    return service.get_public_status(db, token)


@router.post("/{token}/confirm", response_model=PublicLocationConfirmOut, dependencies=[Depends(_guard_rate_limit)])
def confirm_public_location(token: str, payload: PublicLocationConfirmRequest, request: Request, db: Session = Depends(get_db)):
    return service.confirm_public_location(
        db, token,
        latitude=payload.latitude,
        longitude=payload.longitude,
        accuracy_meters=payload.accuracy_meters,
        gps_latitude=payload.gps_latitude,
        gps_longitude=payload.gps_longitude,
        adjusted_manually=payload.adjusted_manually,
        request=request,
    )
