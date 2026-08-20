"""Auditoria de qualidade de coordenadas - pedido do usuário em 2026-08-15 (Fase 1 do plano de
confiabilidade de dado, item 2). Propositalmente SÓ AUDITA - nenhuma correção automática, nenhum
UPDATE. Um cluster geográfico sofisticado em cima de coordenada ruim produz resposta errada com
aparência de confiável; antes de investir em motor de cluster maior, precisamos saber o tamanho
real do problema.

Classificação por registro (mutuamente exclusiva, nesta ordem de prioridade):
    MISSING          - latitude ou longitude nula.
    INVALID           - fora do intervalo geograficamente possível (lat ∉ [-90,90] ou lng ∉ [-180,180]).
    ZERO_ZERO          - exatamente (0, 0) - marcador clássico de "nunca preenchido" em várias
                         integrações, distinto de MISSING porque aqui o campo TEM valor.
    OUT_OF_REGION      - dentro do intervalo válido, mas a mais de `outlier_km` do centróide dos
                         próprios registros válidos daquela regional (outlier autorreferente - não
                         depende de nenhuma fonte externa de geometria de regional).
    SUSPICIOUS         - coordenada exata (arredondada a 5 casas, ~1m) compartilhada por mais de
                         `duplicate_threshold` outros registros - indício de valor "chumbado"
                         (ex.: sede da empresa, centro da cidade usado como fallback).
    VALIDATED          - passou por todas as checagens acima.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.ai_governance.response_meta import build_meta

from .models import OperationLoginCurrentStatus, OperationOnuSignalCurrent, OperationOrder

EARTH_RADIUS_KM = 6371.0
DEFAULT_OUTLIER_KM = 300.0
DEFAULT_DUPLICATE_THRESHOLD = 20

CoordinateEntity = str  # "operations_orders" | "operations_login_current_status" | "operations_onu_signal_current"


@dataclass
class _Record:
    regional: str | None
    latitude: float | None
    longitude: float | None


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    lat1_r, lng1_r, lat2_r, lng2_r = (math.radians(v) for v in (lat1, lng1, lat2, lng2))
    cos_angle = math.sin(lat1_r) * math.sin(lat2_r) + math.cos(lat1_r) * math.cos(lat2_r) * math.cos(lng2_r - lng1_r)
    cos_angle = max(-1.0, min(1.0, cos_angle))
    return EARTH_RADIUS_KM * math.acos(cos_angle)


def _load_records(db: Session, entity: CoordinateEntity) -> list[_Record]:
    if entity == "operations_orders":
        rows = db.execute(select(OperationOrder.regional, OperationOrder.latitude, OperationOrder.longitude)).all()
        return [_Record(regional=r[0], latitude=r[1], longitude=r[2]) for r in rows]
    if entity == "operations_login_current_status":
        rows = db.execute(
            select(OperationLoginCurrentStatus.regional, OperationLoginCurrentStatus.latitude, OperationLoginCurrentStatus.longitude)
        ).all()
        return [_Record(regional=r[0], latitude=r[1], longitude=r[2]) for r in rows]
    if entity == "operations_onu_signal_current":
        # Sem coluna própria de regional - join com login_current_status (mesmo padrão já usado em
        # login_search.py/login_aggregate.py) pra poder quebrar por regional também aqui.
        rows = db.execute(
            select(OperationLoginCurrentStatus.regional, OperationOnuSignalCurrent.latitude, OperationOnuSignalCurrent.longitude)
            .select_from(OperationOnuSignalCurrent)
            .join(OperationLoginCurrentStatus, OperationLoginCurrentStatus.login_id == OperationOnuSignalCurrent.login_id)
        ).all()
        return [_Record(regional=r[0], latitude=r[1], longitude=r[2]) for r in rows]
    raise ValueError(
        f"entity inválida: '{entity}'. Aceitas: operations_orders, operations_login_current_status, "
        "operations_onu_signal_current."
    )


def coordinate_quality_audit(
    db: Session,
    *,
    entity: CoordinateEntity,
    outlier_km: float = DEFAULT_OUTLIER_KM,
    duplicate_threshold: int = DEFAULT_DUPLICATE_THRESHOLD,
) -> dict:
    """Audita a qualidade de latitude/longitude de uma entidade, quebrado por regional. Não
    corrige nada - só classifica e conta. `outlier_km`: distância do centróide dos próprios
    registros válidos da regional acima da qual uma coordenada válida (dentro do intervalo
    geográfico possível) é considerada fora de lugar. `duplicate_threshold`: quantos registros
    compartilhando a mesma coordenada exata (~1m) fazem ela ser "suspeita de valor chumbado".

    Retorna {"meta": {...}, "data": [...]} (envelope padrão da Fase 1, item 1 - ver
    `app.modules.ai_governance.response_meta`), um item de `data` por regional."""
    records = _load_records(db, entity)

    by_regional: dict[str, list[_Record]] = defaultdict(list)
    for record in records:
        by_regional[record.regional or "NÃO IDENTIFICADO"].append(record)

    coord_counter: Counter[tuple[float, float]] = Counter()
    for record in records:
        if record.latitude is not None and record.longitude is not None:
            coord_counter[(round(record.latitude, 5), round(record.longitude, 5))] += 1

    results = []
    for regional, group in sorted(by_regional.items()):
        total = len(group)
        missing = 0
        invalid_range = 0
        zero_zero = 0
        valid_points: list[tuple[float, float]] = []

        for record in group:
            lat, lng = record.latitude, record.longitude
            if lat is None or lng is None:
                missing += 1
                continue
            if not (-90 <= lat <= 90 and -180 <= lng <= 180):
                invalid_range += 1
                continue
            if lat == 0 and lng == 0:
                zero_zero += 1
                continue
            valid_points.append((lat, lng))

        outside_region = 0
        suspicious_duplicates = 0
        if valid_points:
            centroid_lat = sum(p[0] for p in valid_points) / len(valid_points)
            centroid_lng = sum(p[1] for p in valid_points) / len(valid_points)
            for lat, lng in valid_points:
                if _haversine_km(lat, lng, centroid_lat, centroid_lng) > outlier_km:
                    outside_region += 1
                if coord_counter[(round(lat, 5), round(lng, 5))] > duplicate_threshold:
                    suspicious_duplicates += 1

        validated = len(valid_points) - outside_region - suspicious_duplicates
        results.append(
            {
                "entity": entity,
                "regional": regional,
                "total": total,
                "validated": validated,
                "missing": missing,
                "invalid_range": invalid_range,
                "zero_zero": zero_zero,
                "outside_region": outside_region,
                "suspicious_duplicates": suspicious_duplicates,
                "valid_coverage_pct": round((validated / total) * 100, 2) if total else 0.0,
            }
        )
    results.sort(key=lambda item: item["total"], reverse=True)
    return {
        "meta": build_meta(
            applied_filters={"entity": entity, "outlier_km": outlier_km, "duplicate_threshold": duplicate_threshold}
        ),
        "data": results,
    }
