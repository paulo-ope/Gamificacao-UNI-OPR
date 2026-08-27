"""Geracao do extrato de pagamento individual (PDF) para conferencia/contestacao de um colaborador."""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CalculationRun, Collaborator, CollaboratorScore, PointBalanceEntry
from app.services.calculation_closure import now_porto_velho
from app.services.point_balance import pending_entries_for_collaborator
from app.services.regional import normalize_regional_grouped as normalize_regional
from app.services.scoring_detail import get_collaborator_service_orders_detail

MONTH_NAMES = [
    "", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]

RUN_STATUS_LABEL = {
    "draft": "Rascunho (pré-visualização)",
    "review": "Em conferência",
    "approved": "Aprovado",
    "paid": "Pago (valores definitivos)",
    "cancelled": "Cancelado",
}


def _format_money(value: float | None) -> str:
    if value is None:
        return "-"
    text = f"{abs(value):,.2f}"
    text = text.replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{'-' if value < 0 else ''}R$ {text}"


def _format_points(value: float | None, *, signed: bool = False) -> str:
    if value is None:
        value = 0.0
    text = f"{abs(value):,.1f}".replace(",", "_").replace(".", ",").replace("_", ".")
    if signed and value != 0:
        return f"{'-' if value < 0 else '+'}{text} pts"
    return f"{text} pts"


def _format_datetime(value: datetime | None) -> str:
    if not value:
        return "-"
    return value.strftime("%d/%m/%Y %H:%M")


def _p(value: Any, style: ParagraphStyle) -> Paragraph:
    """Paragraph com o texto escapado - o conteudo vem de dados importados/digitados (nome de
    cliente, diagnostico, motivo do lancamento) e o Paragraph interpreta o texto como mini-XML,
    entao um '&' ou '<' cru quebraria a geracao do PDF."""
    text = "-" if value is None else str(value)
    return Paragraph(escape(text), style)


def distribute_amount_by_weight(total: float, weights: list[float]) -> list[float]:
    """Reparte `total` (em reais) entre as O.S. proporcionalmente a `weights`, garantindo que a
    soma das fatias seja EXATAMENTE `round(total, 2)`.

    Existe por causa do achado A8 da auditoria 2026-08-26: a coluna "Valor" de cada O.S. era
    `net_points * point_value`, ignorando o multiplicador de saúde da regional. Para um
    colaborador com multiplicador 0,30 a coluna somava ~3,3x o "Valor a pagar" impresso no
    resumo do MESMO documento - num papel chamado "Extrato de Pagamento - Conferência
    Individual". O pagamento nunca esteve errado; o documento que o explica é que não fechava.

    Reparte pelo método do maior resto (mesma ideia de `_distribute_cents_exactly` no bônus de
    liderança), em vez de arredondar cada linha isoladamente - N linhas arredondadas
    individualmente não somam o total arredondado uma vez só.
    """
    count = len(weights)
    if count == 0:
        return []
    total_cents = round(float(total) * 100)
    weight_sum = sum(weights)
    if weight_sum <= 0:
        # Sem peso (nenhuma O.S. pontuou): não há como distribuir proporcionalmente.
        return [0.0] * count

    exact = [total_cents * (weight / weight_sum) for weight in weights]
    floors = [int(value // 1) for value in exact]
    remainder = total_cents - sum(floors)
    # Os centavos restantes vão para as linhas de maior resto fracionário, maior peso como
    # desempate - determinístico, para o mesmo extrato sair igual toda vez que for gerado.
    order = sorted(range(count), key=lambda index: (-(exact[index] - floors[index]), -weights[index], index))
    for position in range(remainder):
        floors[order[position % count]] += 1
    return [cents / 100 for cents in floors]


def _entry_trace(entry: PointBalanceEntry) -> str:
    if entry.entry_type != "post_payment_warranty_debit" or not entry.original_os_code:
        return entry.reason or "-"
    return f"O.S {entry.original_os_code} → garantia O.S {entry.related_os_code or '-'}"


def build_collaborator_statement_pdf(
    db: Session,
    collaborator: Collaborator,
    run: CalculationRun,
    score: CollaboratorScore,
) -> bytes:
    detail = get_collaborator_service_orders_detail(
        db,
        collaborator_id=collaborator.id,
        reference_month=run.reference_month,
        reference_year=run.reference_year,
        regional=run.regional,
        point_value=run.point_value,
    )
    orders = detail["orders"]

    # Um fechamento so "aplica" (consome) os lancamentos pendentes quando vira "paid" - ver
    # apply_pending_entries_for_paid_run. Antes disso, o desconto exibido no score e apenas uma
    # previa (preview_pending_adjustment) sobre os lancamentos ainda pendentes do colaborador.
    # Usar sempre applied_calculation_run_id aqui faria o extrato de um rascunho mostrar "0
    # lancamentos" ao lado de um desconto de garantia diferente de zero.
    if run.status == "paid":
        garantia_entries = list(
            db.scalars(
                select(PointBalanceEntry)
                .where(
                    PointBalanceEntry.collaborator_id == collaborator.id,
                    PointBalanceEntry.applied_calculation_run_id == run.id,
                )
                .order_by(PointBalanceEntry.created_at.asc())
            )
        )
    else:
        garantia_entries = [
            entry for entry in pending_entries_for_collaborator(db, collaborator.id) if not entry.requires_review
        ]

    garantia_discount = score.balance_adjustment_points or 0.0
    month_points = score.final_points - garantia_discount
    point_value = run.point_value or 0.0

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        title=f"Extrato de pagamento - {collaborator.name}",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("StatementTitle", parent=styles["Title"], fontSize=16, spaceAfter=2)
    subtitle_style = ParagraphStyle("StatementSubtitle", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#475569"))
    section_style = ParagraphStyle("StatementSection", parent=styles["Heading3"], fontSize=11, spaceBefore=10, spaceAfter=4, textColor=colors.HexColor("#0f172a"))
    note_style = ParagraphStyle("StatementNote", parent=styles["Normal"], fontSize=8, textColor=colors.HexColor("#64748b"))
    cell_style = ParagraphStyle("StatementCell", parent=styles["Normal"], fontSize=7.5, leading=9.5)
    cell_style_bold = ParagraphStyle("StatementCellBold", parent=cell_style, fontName="Helvetica-Bold")
    cell_style_right = ParagraphStyle("StatementCellRight", parent=cell_style, alignment=TA_RIGHT)
    cell_style_right_bold = ParagraphStyle("StatementCellRightBold", parent=cell_style_right, fontName="Helvetica-Bold")
    cell_style_right_red = ParagraphStyle("StatementCellRightRed", parent=cell_style_right, textColor=colors.HexColor("#dc2626"))

    period_label = f"{MONTH_NAMES[run.reference_month]}/{run.reference_year}"
    story: list[Any] = []

    story.append(Paragraph("Extrato de Pagamento - Conferência Individual", title_style))
    story.append(Paragraph("UNI OPR · Gamificação Operacional", subtitle_style))
    story.append(Spacer(1, 8))

    header_table = Table(
        [
            ["Colaborador", collaborator.name, "Período", period_label],
            ["Cargo/função", collaborator.role or "Não informado", "Regional", normalize_regional(collaborator.regional) or "Não informado"],
            ["Situação do fechamento", RUN_STATUS_LABEL.get(run.status, run.status), "Emitido em", _format_datetime(now_porto_velho())],
        ],
        colWidths=[38 * mm, 58 * mm, 32 * mm, 52 * mm],
    )
    header_table.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#64748b")),
                ("TEXTCOLOR", (2, 0), (2, -1), colors.HexColor("#64748b")),
                ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
                ("FONTNAME", (3, 0), (3, -1), "Helvetica-Bold"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("LINEBELOW", (0, -1), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ]
        )
    )
    story.append(header_table)

    story.append(Paragraph("Como chegamos no valor a pagar", section_style))
    summary_rows = [["Descrição", "Valor"]]
    summary_rows.append(["Pontos brutos no período", _format_points(score.gross_points)])
    summary_rows.append(["Pontos anulados (SLA/diagnóstico/reincidência)", f"-{_format_points(abs(score.penalty_points))}"])
    summary_rows.append(["Pontos líquidos", _format_points(score.net_points)])
    summary_rows.append([f"Multiplicador de saúde da regional ({score.health_status})", f"{score.health_multiplier:.2f}x"])
    summary_rows.append(["Pontos do mês (líquidos x multiplicador)", _format_points(month_points)])
    discount_label = (
        f"Desconto de garantia ({len(garantia_entries)} lançamento(s) aplicados neste fechamento)"
        if run.status == "paid"
        else f"Desconto de garantia previsto ({len(garantia_entries)} lançamento(s) pendente(s) - sujeito a mudança até o pagamento)"
    )
    if abs(garantia_discount) > 0.001:
        summary_rows.append([discount_label, _format_points(garantia_discount, signed=True)])
    summary_rows.append(["Pontos a pagar neste fechamento", _format_points(score.final_points)])
    summary_rows.append(["Valor do ponto", _format_money(point_value)])
    summary_rows.append(["Valor a pagar", _format_money(score.estimated_payment)])

    summary_table = Table(summary_rows, colWidths=[130 * mm, 50 * mm], repeatRows=1)
    summary_style = [
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#ecfdf5")),
    ]
    if abs(garantia_discount) > 0.001:
        discount_row_index = summary_rows.index([discount_label, _format_points(garantia_discount, signed=True)])
        summary_style.append(("TEXTCOLOR", (1, discount_row_index), (1, discount_row_index), colors.HexColor("#dc2626")))
    summary_table.setStyle(TableStyle(summary_style))
    story.append(summary_table)

    if garantia_entries:
        garantia_section_title = (
            "Garantias descontadas neste fechamento"
            if run.status == "paid"
            else "Garantias pendentes que serão descontadas ao pagar este fechamento"
        )
        story.append(Paragraph(garantia_section_title, section_style))
        garantia_rows = [["Rastro", "Pontos", "Motivo"]]
        for entry in garantia_entries:
            garantia_rows.append([
                _p(_entry_trace(entry), cell_style),
                Paragraph(_format_points(entry.points, signed=True), cell_style_right_red),
                _p(entry.reason or "-", cell_style),
            ])
        garantia_table = Table(garantia_rows, colWidths=[70 * mm, 25 * mm, 85 * mm], repeatRows=1)
        garantia_table.setStyle(
            TableStyle(
                [
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                    ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        story.append(garantia_table)

    story.append(Paragraph(f"Ordens de serviço do período ({len(orders)})", section_style))
    header_style = ParagraphStyle("StatementOrdersHeader", parent=cell_style, textColor=colors.white, fontName="Helvetica-Bold")
    orders_rows = [
        [Paragraph(label, header_style) for label in ["O.S", "Data", "Cliente", "Assunto", "SLA", "Pontos", "Valor", "Status"]]
    ]
    # Cada O.S. recebe a fatia do valor a pagar proporcional ao que ela representa dos pontos
    # líquidos do colaborador, e as fatias somam exatamente o "Valor a pagar" do resumo acima
    # (ver `distribute_amount_by_weight`). O peso usa o valor do ponto de cada O.S., porque
    # assunto e grupo podem ter valor de ponto próprio (`effective_rule_point_value`).
    order_weights = [
        float(order["net_points"]) * float(order.get("point_value") or point_value) for order in orders
    ]
    order_amounts = distribute_amount_by_weight(float(score.estimated_payment), order_weights)

    for order, amount in zip(orders, order_amounts):
        net_points = order["net_points"]
        closed_at = order.get("closed_at") or order.get("opened_at")
        date_html = f"{closed_at.strftime('%d/%m/%Y')}<br/>{closed_at.strftime('%H:%M')}" if closed_at else "-"
        orders_rows.append(
            [
                _p(order["os_code"], cell_style_bold),
                Paragraph(date_html, cell_style),
                _p(order["customer_name"], cell_style),
                _p(order["os_subject"], cell_style),
                _p(order["sla_status_normalized"], cell_style),
                Paragraph(_format_points(net_points), cell_style_right),
                Paragraph(_format_money(amount), cell_style_right),
                _p(order["scoring_status"], cell_style),
            ]
        )

    # Linha de total: é o que permite conferir o documento sem somar 128 linhas na mão. Fecha
    # exatamente com "Valor a pagar" do resumo, por construção.
    orders_rows.append(
        [
            Paragraph("Total", cell_style_bold),
            Paragraph("", cell_style),
            Paragraph("", cell_style),
            Paragraph("", cell_style),
            Paragraph("", cell_style),
            Paragraph(_format_points(sum(float(order["net_points"]) for order in orders)), cell_style_right_bold),
            Paragraph(_format_money(sum(order_amounts)), cell_style_right_bold),
            Paragraph("", cell_style),
        ]
    )

    orders_table = Table(
        orders_rows,
        colWidths=[18 * mm, 20 * mm, 32 * mm, 34 * mm, 24 * mm, 18 * mm, 20 * mm, 22 * mm],
        repeatRows=1,
    )
    orders_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#f8fafc")]),
                # Linha de total destacada e separada por um traço mais forte.
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#e2e8f0")),
                ("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.HexColor("#0f172a")),
            ]
        )
    )
    story.append(orders_table)

    story.append(Spacer(1, 10))
    story.append(
        Paragraph(
            "Este extrato reflete a régua de pontuação e o multiplicador de saúde congelados no momento do fechamento "
            f"({period_label}). Em caso de divergência, entre em contato com o time responsável pela gamificação "
            "informando o código da O.S contestada.",
            note_style,
        )
    )

    def _footer(canvas, doc_):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor("#94a3b8"))
        canvas.drawString(14 * mm, 10 * mm, f"Extrato gerado em {_format_datetime(now_porto_velho())}")
        canvas.drawRightString(doc_.pagesize[0] - 14 * mm, 10 * mm, f"Página {doc_.page}")
        canvas.restoreState()

    doc.build([KeepTogether(story[:2])] + story[2:], onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()
