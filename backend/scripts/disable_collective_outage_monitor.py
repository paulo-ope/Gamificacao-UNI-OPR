"""Desliga o monitor `collective_outage` (detecta clusters de login offline e cria alertas
sozinho, sem nenhuma configuracao do usuario) - pedido explicito 2026-08-24: só regras cadastradas
em Administração → Regras de Alertas devem gerar alerta; nenhuma detecção pré-definida.

Usa `update_monitor_settings` (mesma função do endpoint `PUT /admin/monitors/{key}`) - só grava
`intelligence_monitor_collective_outage_enabled=false` em `app_settings`; o scheduler lê essa
chave a cada ciclo (ver scheduler.py::get_monitor_enabled), sem precisar reiniciar o backend.

Não apaga nem resolve alertas já existentes desse monitor - só lista os ATIVOS pra você decidir
separadamente se quer encerrá-los (uma vez desligado, o monitor nunca mais vai contá-los como
"missed" pra auto-resolver, então eles ficariam presos em ACTIVE pra sempre se não forem tratados).

Uso (dentro do container do backend, como módulo):

    docker exec opr-gamification-backend python -m scripts.disable_collective_outage_monitor
"""
from __future__ import annotations

import app.main  # noqa: F401 - registra todos os mappers antes de qualquer query
from app.db.session import SessionLocal
from app.modules.intelligence.alerts import ACTIVE_STATUSES
from app.modules.intelligence.models import IntelligenceAlert
from app.modules.intelligence.registry import get_monitor
from app.modules.intelligence.scheduler import get_monitor_enabled, update_monitor_settings
from sqlalchemy import select

MONITOR_KEY = "collective_outage"


def main() -> None:
    db = SessionLocal()
    try:
        monitor = get_monitor(MONITOR_KEY)
        if monitor is None:
            print(f"Monitor '{MONITOR_KEY}' não existe no registry.")
            return

        before = get_monitor_enabled(db, monitor)
        update_monitor_settings(db, monitor, enabled=False)
        after = get_monitor_enabled(db, monitor)
        print(f"Monitor '{MONITOR_KEY}': enabled {before} -> {after}")

        active = list(
            db.scalars(
                select(IntelligenceAlert)
                .where(IntelligenceAlert.monitor_key == MONITOR_KEY)
                .where(IntelligenceAlert.status.in_(ACTIVE_STATUSES))
            )
        )
        if active:
            print(f"\n{len(active)} alerta(s) ATIVO(s) desse monitor continuam na tela (não foram tocados):")
            for alert in active:
                print(f"  #{alert.id} [{alert.status}] {alert.title!r} (regional={alert.regional!r}, last_seen_at={alert.last_seen_at})")
            print("\nComo o monitor está desligado, esses alertas não vão mais receber ciclos de 'miss' e não se "
                  "auto-resolvem sozinhos. Avise se quiser que eu os encerre manualmente também.")
        else:
            print("\nNenhum alerta ATIVO desse monitor no momento.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
