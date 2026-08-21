"""Escala alternada (12x36 etc.) - lógica pura, sem banco, compartilhada entre `management`
(que grava o cadastro do colaborador, `ManagementOperationalMember`) e `operations` (que pinta o
calendário mensal com o mesmo critério de dia de folga). Fica em `app/services` porque nenhum dos
dois módulos pode depender do outro pra isso: `management` já importa de `operations` (models,
regional), então colocar aqui evita que `operations` precisasse importar `management` de volta
só pra saber se um dia é a folga de alguém - achado real de 2026-08-21 (ver o calendário
mostrando "abaixo da meta" no dia de folga de um 12x36, quando o motor de casos automáticos já
sabia pular esse dia)."""

from __future__ import annotations

from datetime import date


def is_scheduled_workday(
    shift_pattern: str | None,
    shift_cycle_days_on: int | None,
    shift_cycle_days_off: int | None,
    shift_anchor_date: date | None,
    day: date,
) -> bool:
    """`False` quando `day` cai na folga da escala alternada. Sem escala configurada (`None`/
    "standard", ou dados incompletos), sempre `True` - trata como dia comercial normal."""
    if shift_pattern != "alternating":
        return True
    if not shift_anchor_date or not shift_cycle_days_on or not shift_cycle_days_off:
        return True
    cycle_length = shift_cycle_days_on + shift_cycle_days_off
    if cycle_length <= 0:
        return True
    # `%` do Python sempre devolve resultado no sinal do divisor (positivo aqui), então funciona
    # tanto pra `day` depois quanto antes de `shift_anchor_date`.
    offset = (day - shift_anchor_date).days % cycle_length
    return offset < shift_cycle_days_on
