"""Expressões SQL dos indicadores de tempo do OPA pela REGRA DO OPA (2026-10-15).

Um só lugar para a Visão Geral, a série diária, os breakdowns e os Indicadores do Suporte calcularem TMA e
TMR do mesmo jeito (norma de qualidade de dados: fonte única de regra):

- TMA = média, entre os atendimentos encerrados, de `tma_active_seconds` (1ª mensagem humana até a conclusão,
  cada silêncio limitado a 1 h);
- TMR (mostrado como "TMR Geral") = SOMA de todos os intervalos de resposta dividida pela QUANTIDADE de
  respostas dos atendimentos encerrados - todas as respostas juntas, não a média das médias por conversa.
  Foi o que aproximou o número do relatório por atendente do OPA (erro médio de 30% para 16%).

Os nomes dos campos da API (`average_tma_effective_seconds`, `average_tmr_effective_seconds`...) foram
mantidos para não quebrar telas, MCP e clientes; só o cálculo por trás mudou.
"""

from __future__ import annotations

from sqlalchemy import Float, and_, case, cast, func

from .models import SupportOpaAttendance


def _closed(expression):
    return case((SupportOpaAttendance.closed_at.isnot(None), expression))


def avg_tma_active():
    return func.avg(_closed(SupportOpaAttendance.tma_active_seconds))


def count_tma_active():
    return func.count(_closed(SupportOpaAttendance.tma_active_seconds))


def avg_tmr_pooled():
    total = func.sum(_closed(SupportOpaAttendance.tmr_gap_sum_seconds))
    responses = func.sum(_closed(SupportOpaAttendance.tmr_gap_count))
    return cast(total, Float) / func.nullif(cast(responses, Float), 0.0)


def count_tmr_pooled():
    """Atendimentos encerrados que entram na média do TMR (têm ao menos uma resposta medida)."""
    return func.count(case((and_(SupportOpaAttendance.closed_at.isnot(None), SupportOpaAttendance.tmr_gap_count > 0), 1)))
