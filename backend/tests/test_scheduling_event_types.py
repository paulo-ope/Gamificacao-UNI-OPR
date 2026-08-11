from datetime import datetime

from app.modules.scheduling import metrics
from app.modules.scheduling.metrics import EVENT_TYPE_LABELS
from app.modules.scheduling.models import SYNCED_EVENT_TYPES, SchedulingEvent, SchedulingOrder
from app.services.calculation_closure import PORTO_VELHO_TZ

# Os 10 tipos de `su_oss_evento` que o sync agora espelha (ver models.py:SYNCED_EVENT_TYPES) e o
# rótulo esperado de cada um - mesma lista pedida pelo dono do produto para o log completo da O.S.
EXPECTED_EVENT_LABELS = {
    "1": "Abertura",
    "2": "Alteração",
    "3": "Reabertura",
    "4": "Alteração de setor",
    "5": "Agendamento",
    "6": "Fechamento",
    "7": "Em Análise",
    "8": "Assumido",
    "9": "Em Execução",
    "10": "Reagendar",
}


def _dt(day: int, hour: int = 9) -> datetime:
    return datetime(2026, 7, day, hour, 0, tzinfo=PORTO_VELHO_TZ)


def test_synced_event_types_cover_all_ten_su_oss_evento_types():
    assert set(SYNCED_EVENT_TYPES) == set(EXPECTED_EVENT_LABELS)


def test_event_type_labels_cover_every_synced_type():
    assert set(EVENT_TYPE_LABELS) == set(SYNCED_EVENT_TYPES)
    assert EVENT_TYPE_LABELS == EXPECTED_EVENT_LABELS


def test_order_timeline_returns_all_ten_event_types_with_correct_labels(db_session):
    order = SchedulingOrder(
        ixc_os_id=5001,
        opened_at=_dt(1),
        setor_id="7",
        setor_name="Setor Técnico",
        filial_id="1",
        assunto_id="10",
        assunto_name="Instalação",
        status="A",
    )
    db_session.add(order)
    db_session.flush()

    db_session.add_all(
        [
            SchedulingEvent(
                ixc_message_id=index,
                ixc_os_id=order.ixc_os_id,
                event_type=event_type,
                event_at=_dt(1, hour=8 + index),
            )
            for index, event_type in enumerate(sorted(EXPECTED_EVENT_LABELS, key=int), start=1)
        ]
    )
    db_session.commit()

    timeline = metrics.order_timeline(db_session, order.ixc_os_id)

    assert timeline is not None
    assert len(timeline["events"]) == 10
    labels_by_type = {event["event_type"]: event["event_label"] for event in timeline["events"]}
    assert labels_by_type == EXPECTED_EVENT_LABELS
    # Nenhum tipo cai no fallback genérico "Evento N" - todos os 10 têm rótulo próprio.
    assert all(not label.startswith("Evento ") for label in labels_by_type.values())
