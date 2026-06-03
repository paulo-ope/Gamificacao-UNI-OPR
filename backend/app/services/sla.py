from __future__ import annotations

import re
import unicodedata
from typing import Any


SLA_NO_PRAZO = "NO_PRAZO"
SLA_FORA_DO_PRAZO = "FORA_DO_PRAZO"


def normalize_sla_text(value: Any) -> str:
    if value is None:
        return ""
    cleaned = unicodedata.normalize("NFKD", str(value))
    cleaned = "".join(ch for ch in cleaned if not unicodedata.combining(ch))
    cleaned = cleaned.lower().strip()
    cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def normalize_sla_status(value: Any) -> str | None:
    text = normalize_sla_text(value)
    if not text:
        return None

    compact = text.replace(" ", "")
    out_of_time_terms = {
        "encerradaatrasada",
        "encerradoatrasado",
        "atrasada",
        "atrasado",
        "foradoprazo",
        "foraprazo",
        "slaestourado",
        "estourado",
        "vencido",
        "expirado",
    }
    in_time_terms = {
        "encerradanoprazo",
        "encerradonoprazo",
        "noprazo",
        "dentrodoprazo",
        "dentrodeprazo",
        "emprazo",
    }

    if compact in out_of_time_terms or "atrasad" in text or "fora do prazo" in text or "fora prazo" in text:
        return SLA_FORA_DO_PRAZO
    if compact in in_time_terms or "encerrada no prazo" in text or "encerrado no prazo" in text or "dentro do prazo" in text:
        return SLA_NO_PRAZO
    return None


def sla_status_label(value: Any) -> str:
    normalized = normalize_sla_status(value)
    if normalized == SLA_FORA_DO_PRAZO:
        return "FORA_DO_PRAZO"
    if normalized == SLA_NO_PRAZO:
        return "NO_PRAZO"
    return "NAO_IDENTIFICADO"
