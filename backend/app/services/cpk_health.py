from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AppSetting, CpkRegionalSnapshot
from app.services.cpk_client import get_cpk_client
from app.services.regional import ROLIM_REGIONAL, SAO_FRANCISCO_REGIONAL, normalize_key
from app.services.scoring_detail import _safe_float, get_setting

CPK_BONUS_POINTS_SETTING = "cpk_bonus_points"
CPK_SYNC_ENABLED_SETTING = "cpk_sync_enabled"
CPK_PENALTY_DISABLED_PERIODS_SETTING = "cpk_penalty_disabled_periods"  # legado (v1): equivale a bonus_only
CPK_RULE_BY_PERIOD_SETTING = "cpk_rule_by_period"

CPK_RULE_BOTH = "both"
CPK_RULE_PENALTY_ONLY = "penalty_only"
CPK_RULE_BONUS_ONLY = "bonus_only"
CPK_RULE_NONE = "none"
CPK_RULES = (CPK_RULE_BOTH, CPK_RULE_PENALTY_ONLY, CPK_RULE_BONUS_ONLY, CPK_RULE_NONE)

# Nome da regional como a API de CPK devolve (normalizado via normalize_key: sem acento, maiusculo,
# espacos colapsados - mas mantendo apostrofos/hifens) -> nome interno da gamificacao (mesmo usado
# por normalize_regional_grouped/REGIONAL_CODE_MAP). "Matriz" fica de fora de proposito - nao tem
# regional de gamificacao correspondente (decisao confirmada com o usuario).
CPK_REGIONAL_NAME_MAP: dict[str, str] = {
    "JI-PARANA": "UNI - JI PARANA",
    "MACHADINHO D'OESTE": "UNI - MACHADINHO DOESTE",
    "ROLIM DE MOURA": ROLIM_REGIONAL,
    "JARU": "UNI - JARU",
    "OURO PRETO D'OESTE": "UNI - OURO PRETO DOESTE",
    "NOVA BRASILANDIA D'OESTE": "UNI - NOVA BRASILANDIA DOESTE",
    "PRESIDENTE MEDICI": "UNI - PRESIDENTE MEDICI",
    "ALVORADA D'OESTE": "UNI - ALVORADA DOESTE",
    "ALTA FLORESTA D'OESTE": "UNI - ALTA FLORESTA DOESTE",
    "SAO FRANCISCO": SAO_FRANCISCO_REGIONAL,
}


def _regional_status_from_agregado(agregado: dict[str, Any]) -> str:
    """"na_meta" / "fora_meta" / "sem_base", a partir do status bruto da API de CPK (bateu/
    nao_bateu/outro). Decisao do usuario: o bonus/penalidade de CPK reflete o momento atual da
    apuracao (inclusive com o mes ainda em andamento, numeros parciais), em vez de esperar o mes
    fechar oficialmente - `mes_fechado` continua sendo gravado no snapshot so como metadado de
    exibicao (ver `row.mes_fechado` em `sync_cpk_snapshot`), nao controla mais se o ajuste e
    aplicado."""
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
        status = _regional_status_from_agregado(agregado)

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


def _period_key(ano: int, mes: int) -> str:
    return f"{ano:04d}-{mes:02d}"


def _legacy_bonus_only_periods(db: Session) -> set[str]:
    """Meses gravados pela primeira versao (lista de competencias SEM desconto) - equivalem a
    'bonus_only'. Continuam valendo para nao reverter setembro/2026 ja configurado."""
    raw = get_setting(db, CPK_PENALTY_DISABLED_PERIODS_SETTING, "")
    return {item.strip() for item in raw.split(",") if item.strip()}


def _rules_by_period(db: Session) -> dict[str, str]:
    rules = {period: CPK_RULE_BONUS_ONLY for period in _legacy_bonus_only_periods(db)}
    raw = get_setting(db, CPK_RULE_BY_PERIOD_SETTING, "")
    for item in raw.split(","):
        period, _, rule = item.strip().partition(":")
        if period and rule in CPK_RULES:
            rules[period] = rule
    return rules


def get_cpk_rule(db: Session, ano: int, mes: int) -> str:
    """Regra de CPK da competencia: both (soma e desconta - padrao), penalty_only (so desconta
    fora da meta), bonus_only (so soma quem esta na meta) ou none (CPK nao interfere)."""
    return _rules_by_period(db).get(_period_key(ano, mes), CPK_RULE_BOTH)


def set_cpk_rule(db: Session, ano: int, mes: int, rule: str) -> None:
    if rule not in CPK_RULES:
        raise ValueError(f"Regra de CPK invalida: {rule}")
    rules = _rules_by_period(db)
    key = _period_key(ano, mes)
    if rule == CPK_RULE_BOTH:
        rules.pop(key, None)
    else:
        rules[key] = rule
    _save_setting(db, CPK_RULE_BY_PERIOD_SETTING, ",".join(f"{p}:{r}" for p, r in sorted(rules.items())),
                  "Regra de CPK por competencia (AAAA-MM:regra); competencia ausente = both")
    # A lista antiga deixa de valer: tudo passa a viver em CPK_RULE_BY_PERIOD_SETTING.
    _save_setting(db, CPK_PENALTY_DISABLED_PERIODS_SETTING, "", None)


def _save_setting(db: Session, key: str, value: str, description: str | None) -> None:
    setting = db.scalar(select(AppSetting).where(AppSetting.key == key))
    if setting:
        setting.value = value
    else:
        db.add(AppSetting(key=key, value=value, description=description))
    db.flush()


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
    rule = get_cpk_rule(db, ano, mes)
    applies_bonus = rule in (CPK_RULE_BOTH, CPK_RULE_BONUS_ONLY)
    applies_penalty = rule in (CPK_RULE_BOTH, CPK_RULE_PENALTY_ONLY)
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
            adjustments[row.regional] = bonus if applies_bonus else 0.0
        elif row.status == "fora_meta":
            adjustments[row.regional] = -bonus if applies_penalty else 0.0
        else:
            adjustments[row.regional] = 0.0
    return adjustments
