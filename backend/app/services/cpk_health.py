from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CpkRegionalSnapshot
from app.services.cpk_client import get_cpk_client
from app.services.regional import SAO_FRANCISCO_REGIONAL, normalize_key
from app.services.scoring_detail import _safe_float, get_setting

CPK_BONUS_POINTS_SETTING = "cpk_bonus_points"
CPK_SYNC_ENABLED_SETTING = "cpk_sync_enabled"

# Nome da regional como a API de CPK devolve (normalizado via normalize_key: sem acento, maiusculo,
# espacos colapsados - mas mantendo apostrofos/hifens) -> nome interno da gamificacao (mesmo usado
# por normalize_regional_grouped/REGIONAL_CODE_MAP). "Matriz" fica de fora de proposito - nao tem
# regional de gamificacao correspondente (decisao confirmada com o usuario).
CPK_REGIONAL_NAME_MAP: dict[str, str] = {
    "JI-PARANA": "UNI - JI PARANA",
    "MACHADINHO D'OESTE": "UNI - MACHADINHO DOESTE",
    "ROLIM DE MOURA": "UNI - ROLIM DE MOURA",
    "JARU": "UNI - JARU",
    "OURO PRETO D'OESTE": "UNI - OURO PRETO DOESTE",
    "NOVA BRASILANDIA D'OESTE": "UNI - NOVA BRASILANDIA DOESTE",
    "PRESIDENTE MEDICI": "UNI - PRESIDENTE MEDICI",
    "ALVORADA D'OESTE": "UNI - ALVORADA DOESTE",
    "ALTA FLORESTA D'OESTE": "UNI - ALTA FLORESTA DOESTE",
    "SAO FRANCISCO": SAO_FRANCISCO_REGIONAL,
}


def _regional_status_from_agregado(agregado: dict[str, Any], mes_fechado: bool) -> str:
    """"na_meta" / "fora_meta" / "sem_base". Um mes ainda em andamento (mes_fechado=false) ou uma
    regional sem base suficiente (status="sem_base"/atingiu_meta=null) nunca gera ajuste - so o
    "bateu"/"nao_bateu" de um mes JA FECHADO vira +/-cpk_bonus_points (ver guia de integracao:
    "mes em andamento: numeros parciais, nao usar para pagamento")."""
    if not mes_fechado:
        return "sem_base"
    status = agregado.get("status")
    if status == "bateu":
        return "na_meta"
    if status == "nao_bateu":
        return "fora_meta"
    return "sem_base"


def sync_cpk_snapshot(db: Session, ano: int, mes: int) -> dict[str, int]:
    """Busca o relatorio estruturado da API de CPK e grava/atualiza o snapshot local por
    regional. Chamado manualmente (tela de configuracao) ou por uma sincronizacao periodica -
    nunca ao vivo durante o calculo de folha (ver get_cpk_adjustment_by_regional)."""
    client = get_cpk_client()
    payload = client.get_relatorio_estruturado(ano, mes)
    mes_fechado = bool(payload.get("mes_fechado"))
    now = datetime.now(timezone.utc)

    synced = 0
    skipped_unmapped: list[str] = []
    for regional_entry in payload.get("regionais") or []:
        raw_name = str(regional_entry.get("regional") or "")
        mapped_regional = CPK_REGIONAL_NAME_MAP.get(normalize_key(raw_name))
        if not mapped_regional:
            skipped_unmapped.append(raw_name)
            continue

        agregado = regional_entry.get("agregado") or {}
        status = _regional_status_from_agregado(agregado, mes_fechado)

        row = db.scalar(
            select(CpkRegionalSnapshot).where(
                CpkRegionalSnapshot.reference_year == ano,
                CpkRegionalSnapshot.reference_month == mes,
                CpkRegionalSnapshot.regional == mapped_regional,
            )
        )
        if not row:
            row = CpkRegionalSnapshot(reference_year=ano, reference_month=mes, regional=mapped_regional)
            db.add(row)
        row.status = status
        row.cpk_realizado = agregado.get("cpk_realizado")
        row.cpk_meta = agregado.get("cpk_meta")
        row.mes_fechado = mes_fechado
        row.synced_at = now
        synced += 1

    db.flush()
    return {"synced": synced, "skipped_unmapped": len(skipped_unmapped)}


def get_cpk_status_by_regional(db: Session, ano: int, mes: int) -> dict[str, str]:
    """Le o status bruto ja sincronizado ("na_meta"/"fora_meta"/"sem_base") sem aplicar
    cpk_bonus_points - usado so pra exibicao (extrato do colaborador, dashboard), separado do
    ajuste numerico que get_cpk_adjustment_by_regional calcula pro multiplicador."""
    rows = list(
        db.scalars(
            select(CpkRegionalSnapshot).where(
                CpkRegionalSnapshot.reference_year == ano,
                CpkRegionalSnapshot.reference_month == mes,
            )
        )
    )
    return {row.regional: row.status for row in rows}


def get_cpk_adjustment_by_regional(db: Session, ano: int, mes: int) -> dict[str, float]:
    """Le o snapshot JA SINCRONIZADO (nao chama a API ao vivo) e devolve o ajuste de multiplicador
    por regional: +cpk_bonus_points (na meta), -cpk_bonus_points (fora da meta), ou 0.0 (sem
    snapshot pra esse periodo, ou regional sem base suficiente/mes ainda em andamento)."""
    bonus = _safe_float(get_setting(db, CPK_BONUS_POINTS_SETTING, "0.2"), 0.2)
    rows = list(
        db.scalars(
            select(CpkRegionalSnapshot).where(
                CpkRegionalSnapshot.reference_year == ano,
                CpkRegionalSnapshot.reference_month == mes,
            )
        )
    )
    adjustments: dict[str, float] = {}
    for row in rows:
        if row.status == "na_meta":
            adjustments[row.regional] = bonus
        elif row.status == "fora_meta":
            adjustments[row.regional] = -bonus
        else:
            adjustments[row.regional] = 0.0
    return adjustments
