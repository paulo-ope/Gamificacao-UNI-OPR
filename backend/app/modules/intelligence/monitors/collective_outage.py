"""Monitor de incidente coletivo de rede - adaptador fino sobre `login_incident_analysis`
(operations/login_aggregate.py) e os clusters geograficos que ela ja calcula via
`find_offline_login_clusters` (operations/login_geo_clusters.py). Nao reimplementa nenhuma
deteccao: so decide, a partir do que essas funcoes ja produzem, quais clusters viram um
IntelligenceAlert, com que severidade e confianca.

`login_incident_analysis` nao recebe `user` (nao aplica escopo por gestor regional - analisa
rede, nao O.S. de um colaborador), entao nao precisamos do usuario transiente de scope.py aqui."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.operations.coordinate_quality import coordinate_quality_audit
from app.modules.operations.login_aggregate import login_incident_analysis
from app.modules.operations.models import OperationLoginCurrentStatus, OperationOnuSignalCurrent
from app.modules.operations.scope import transmitter_display_name

from ..types import MonitorDetection, MonitorRunResult

WINDOW_MINUTES = 90
CLUSTER_RADIUS_METERS = 300.0
CLUSTER_MIN_SIZE = 3

# ~3 casas decimais de lat/long equivalem a ~111 metros - suficiente pra manter a dedupe_key
# estavel entre execucoes do MESMO cluster real (que pode oscilar em poucos metros de um ciclo
# pro outro), sem juntar clusters distintos que estejam genuinamente separados.
_COORD_GRID_PRECISION = 3


def _regional_for_login(db: Session, login: str) -> str | None:
    return db.scalar(select(OperationLoginCurrentStatus.regional).where(OperationLoginCurrentStatus.login == login))


def _login_ids_for_logins(db: Session, logins: list[str]) -> list[int]:
    """`login_incident_analysis` devolve `geo_clusters[i]['logins']` como lista de CÓDIGOS de
    login (str), não de login_id - `OperationOnuSignalCurrent` é chaveada por login_id (int), daí
    esse lookup intermediário antes de buscar o transmissor dominante."""
    if not logins:
        return []
    rows = db.execute(select(OperationLoginCurrentStatus.login_id).where(OperationLoginCurrentStatus.login.in_(logins))).all()
    return [row[0] for row in rows]


def _dominant_transmitter(db: Session, login_ids: list[int]) -> tuple[str | None, float]:
    if not login_ids:
        return None, 0.0
    rows = db.execute(
        select(OperationOnuSignalCurrent.transmitter_id).where(OperationOnuSignalCurrent.login_id.in_(login_ids))
    ).all()
    counts: dict[str, int] = {}
    for (transmitter_id,) in rows:
        if not transmitter_id:
            continue
        counts[transmitter_id] = counts.get(transmitter_id, 0) + 1
    if not counts:
        return None, 0.0
    transmitter_id, count = max(counts.items(), key=lambda item: item[1])
    return transmitter_id, round(count / len(login_ids), 2)


def _severity_for_cluster(size: int) -> str:
    if size >= CLUSTER_MIN_SIZE * 3:
        return "CRITICAL"
    if size >= CLUSTER_MIN_SIZE * 2:
        return "HIGH"
    return "MEDIUM"


def _confidence_for_cluster(size: int, transmitter_share: float) -> float:
    """Base conservadora (0.5) + até 0.3 pelo tamanho do cluster acima do mínimo configurado +
    até 0.2 se a maioria dos logins compartilha o mesmo transmissor (evidência de causa comum,
    não coincidência geográfica). Clampado em 0.97 - nunca declara certeza absoluta."""
    size_factor = min((size - CLUSTER_MIN_SIZE) / (CLUSTER_MIN_SIZE * 2), 1.0) if size > CLUSTER_MIN_SIZE else 0.0
    confidence = 0.5 + size_factor * 0.3 + transmitter_share * 0.2
    return round(min(confidence, 0.97), 2)


def _coverage_for_regional(db: Session, regional: str | None) -> dict:
    """Cobertura de coordenadas do login corrente para a regional do cluster - herda a Fase 1 de
    confiabilidade: uma conclusao geografica (o cluster, a ausencia de cluster) so vale o que a
    cobertura de coordenadas daquela regional sustenta."""
    if not regional:
        return {}
    audit = coordinate_quality_audit(db, entity="operations_login_current_status")
    row = next((item for item in audit.get("data", []) if item.get("regional") == regional), None)
    if not row:
        return {}
    return {
        "coordinate_coverage_pct": row.get("valid_coverage_pct"),
        "regional_population": row.get("total"),
    }


def run_collective_outage_monitor(db: Session) -> MonitorRunResult:
    analysis = login_incident_analysis(
        db,
        window_minutes=WINDOW_MINUTES,
        regionals=None,
        cluster_radius_meters=CLUSTER_RADIUS_METERS,
        cluster_min_size=CLUSTER_MIN_SIZE,
    )
    meta = analysis.get("meta") or {}
    source_last_sync = meta.get("source_last_sync")
    warnings = meta.get("warnings", [])

    detections: list[MonitorDetection] = []
    for cluster in analysis.get("geo_clusters", []):
        size = cluster["size"]
        logins = cluster.get("logins", [])  # list[str] - códigos de login, não login_id
        regional = _regional_for_login(db, logins[0]) if logins else None
        login_ids = _login_ids_for_logins(db, logins)
        transmitter_id, transmitter_share = _dominant_transmitter(db, login_ids)

        lat_key = round(cluster["center_latitude"], _COORD_GRID_PRECISION)
        lng_key = round(cluster["center_longitude"], _COORD_GRID_PRECISION)
        dedupe_key = f"collective_outage:{regional or 'sem_regional'}:{lat_key}:{lng_key}"

        sample_logins = logins[:5]
        transmitter_label = transmitter_display_name(transmitter_id)
        summary = (
            f"{size} logins offline concentrados em um raio de {cluster['radius_meters']:.0f}m "
            f"nos ultimos {WINDOW_MINUTES} minutos"
            + (f", predominantemente no transmissor {transmitter_label}" if transmitter_label and transmitter_share >= 0.5 else "")
            + "."
        )

        detections.append(
            MonitorDetection(
                dedupe_key=dedupe_key,
                kind="INCIDENT",
                alert_type="COLLECTIVE_OUTAGE",
                severity=_severity_for_cluster(size),
                title=f"Possível incidente coletivo{f' - {regional}' if regional else ''}",
                summary=summary,
                regional=regional,
                scope={
                    "regional": regional,
                    "center_latitude": cluster["center_latitude"],
                    "center_longitude": cluster["center_longitude"],
                },
                recommended_action="evitar despacho individual até validação da equipe de infraestrutura",
                evidence={
                    "cluster_size": size,
                    "radius_meters": cluster["radius_meters"],
                    "window_minutes": WINDOW_MINUTES,
                    "logins_sample": sample_logins,
                    "dominant_transmitter_id": transmitter_id,
                    "dominant_transmitter_label": transmitter_label,
                    "transmitter_share": transmitter_share,
                    "still_offline_total": analysis.get("still_offline"),
                    "new_drops_total": analysis.get("new_drops"),
                },
                confidence=_confidence_for_cluster(size, transmitter_share),
                coverage=_coverage_for_regional(db, regional),
                warnings=warnings,
                source_last_sync=source_last_sync,
            )
        )

    return MonitorRunResult(
        detections=detections,
        stats={
            "clusters_evaluated": len(analysis.get("geo_clusters", [])),
            "new_drops": analysis.get("new_drops"),
            "still_offline": analysis.get("still_offline"),
            "reconnects": analysis.get("reconnects"),
        },
    )
