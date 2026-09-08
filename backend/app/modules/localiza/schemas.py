from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

LocationRequestStatus = Literal["pending", "confirmed", "invalidated", "expired"]
DistanceClassification = Literal["compatible", "minor_divergence", "relevant_divergence", "high_divergence"]


class LocationRequestCreate(BaseModel):
    # Nenhum campo é individualmente obrigatório - o link costuma ser enviado ANTES de existir
    # O.S. no IXC. `service.create_location_request` exige que ao menos um identificador (O.S.,
    # protocolo OPA, cliente) tenha sido informado, senão a solicitação fica impossível de achar
    # depois na listagem.
    order_code: str | None = Field(default=None, max_length=60)
    opa_protocol: str | None = Field(default=None, max_length=60)
    customer_id: str | None = Field(default=None, max_length=60)
    customer_name: str | None = Field(default=None, max_length=180)
    registered_latitude: float | None = Field(default=None, ge=-90, le=90)
    registered_longitude: float | None = Field(default=None, ge=-180, le=180)
    # Preenchidos pelo frontend quando o cliente foi escolhido pela busca ao vivo no IXC (nunca
    # digitados à mão) - guardam o vínculo real com o cadastro, além do texto de exibição acima.
    ixc_cliente_id: int | None = Field(default=None)
    ixc_login_id: int | None = Field(default=None)
    ixc_login: str | None = Field(default=None, max_length=120)


class LocationRequestAttachOrder(BaseModel):
    order_code: str = Field(min_length=1, max_length=60)


class LocationRequestOut(BaseModel):
    id: int
    public_id: str
    order_code: str | None
    opa_protocol: str | None
    customer_id: str | None
    customer_name: str | None
    ixc_cliente_id: int | None
    ixc_login_id: int | None
    ixc_login: str | None
    status: LocationRequestStatus
    registered_latitude: float | None
    registered_longitude: float | None
    gps_latitude: float | None
    gps_longitude: float | None
    confirmed_latitude: float | None
    confirmed_longitude: float | None
    accuracy_meters: float | None
    adjusted_manually: bool
    distance_from_registered_meters: float | None
    distance_classification: DistanceClassification | None
    created_at: datetime
    created_by_user_id: int | None
    requested_by_name: str | None
    expires_at: datetime
    opened_at: datetime | None
    confirmed_at: datetime | None
    invalidated_at: datetime | None


class LocationRequestCreateOut(LocationRequestOut):
    token: str
    public_link: str


# --- Público (sem autenticação) --------------------------------------------------------------

class PublicLocationStatusOut(BaseModel):
    valid: bool
    reason: str | None = None
    order_code: str | None = None
    opa_protocol: str | None = None
    customer_name: str | None = None
    status: LocationRequestStatus | None = None
    expires_at: datetime | None = None


class PublicLocationConfirmRequest(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy_meters: float = Field(gt=0, le=50_000)
    gps_latitude: float = Field(ge=-90, le=90)
    gps_longitude: float = Field(ge=-180, le=180)
    adjusted_manually: bool = False


class PublicLocationConfirmOut(BaseModel):
    status: Literal["confirmed"]
    confirmed_at: datetime


# --- Busca de cliente no IXC (por login ou CPF) -----------------------------------------------

class IxcCustomerMatchOut(BaseModel):
    login_id: int | None
    login: str | None
    cliente_id: int
    name: str
    cpf_masked: str | None
    latitude: float | None
    longitude: float | None


class IxcCustomerSearchOut(BaseModel):
    matches: list[IxcCustomerMatchOut]


# --- Configuração do módulo --------------------------------------------------------------------

class LocalizaSettingsOut(BaseModel):
    link_ttl_hours: int


class LocalizaSettingsUpdate(BaseModel):
    # Mesma faixa do bom senso operacional: menos de 1h expiraria antes de o cliente conseguir
    # abrir o WhatsApp; mais de 30 dias não faz sentido pra um link de atendimento pontual.
    link_ttl_hours: int = Field(ge=1, le=720)
