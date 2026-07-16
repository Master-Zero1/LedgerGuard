"""Render a saved LedgerGuard report payload as a read-only PDF export."""

from __future__ import annotations

import io
import re
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import CondPageBreak, ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _money(value: object) -> str:
    try:
        return f"${float(str(value)):,.2f}"
    except (TypeError, ValueError):
        return str(value or "Not available")


def _text(value: object) -> str:
    return str(value or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _title(value: object) -> str:
    return str(value or "discrepancy").replace("_", " ").title()


def _cited_amount(item: dict[str, Any], label: str) -> str | None:
    for citation in item.get("evidence", []):
        if not isinstance(citation, dict):
            continue
        excerpt = str(citation.get("excerpt", ""))
        if label.lower() not in excerpt.lower():
            continue
        match = re.search(
            rf"{re.escape(label)}\s*:\s*(-?\d+(?:\.\d{{1,2}})?)",
            excerpt,
            flags=re.IGNORECASE,
        )
        if match:
            return match.group(1)
    return None


def _explanation(item: dict[str, Any], outcome: str) -> str:
    confirmed = outcome == "confirmed"
    discrepancy_type = item.get("discrepancy_type")
    if discrepancy_type == "rate_violation":
        billed = _cited_amount(item, "Billed unit price")
        contracted = _cited_amount(item, "Agreed unit price")
        if billed and contracted:
            if confirmed:
                return (
                    f"This was flagged because the invoice billed {_money(billed)} per unit against the "
                    f"contracted {_money(contracted)} rate, creating a stored {_money(item.get('dollar_impact'))} difference."
                )
            return f"This was cleared after reviewing the billed {_money(billed)} rate against the contracted {_money(contracted)} rate."
    if discrepancy_type == "duplicate":
        evidence = [citation for citation in item.get("evidence", []) if isinstance(citation, dict)]
        first_excerpt = str(evidence[0].get("excerpt", "the cited charge")) if evidence else "the cited charge"
        description = first_excerpt.split(";", 1)[0]
        amount = _cited_amount(item, "total")
        charge = f"{_money(amount)} {description} charge" if amount else description
        if confirmed:
            return (
                f"This was flagged because the same {charge} appears {len(evidence)} times in the cited records, "
                f"with {_money(item.get('dollar_impact'))} stored as the duplicate impact."
            )
        return f"This was cleared after reviewing {len(evidence)} cited records for a possible {charge}."
    if discrepancy_type == "price_hike":
        old_price = _cited_amount(item, "Earlier recorded unit price")
        new_price = _cited_amount(item, "Later recorded unit price")
        if old_price and new_price:
            if confirmed:
                return f"This was flagged because the rate changed from {_money(old_price)} to {_money(new_price)} and the investigation confirmed the change was unauthorized."
            return f"This was cleared because the rate changed from {_money(old_price)} to {_money(new_price)}, and the investigation confirmed that change was authorized."
    return "This was flagged because the reviewed records support a confirmed discrepancy." if confirmed else "This was cleared because the investigation did not confirm a discrepancy."


def _evidence_items(item: dict[str, Any], style: ParagraphStyle) -> ListFlowable:
    citations = []
    for citation in item.get("evidence", []):
        if not isinstance(citation, dict):
            continue
        record_type = _text(citation.get("record_type", "Record"))
        record_id = _text(citation.get("record_id", ""))
        page = _text(citation.get("page_ref", "not available")) or "not available"
        excerpt = _text(citation.get("excerpt", ""))
        citations.append(ListItem(Paragraph(f"{excerpt}<br/><font color='#64748B'>{record_type} {record_id} - Page {page}</font>", style)))
    return ListFlowable(citations, bulletType="bullet", leftIndent=16, bulletFontSize=7)


def _finding_card(
    item: dict[str, Any],
    outcome: str,
    *,
    width: float,
    title_style: ParagraphStyle,
    body_style: ParagraphStyle,
    meta_style: ParagraphStyle,
    evidence_style: ParagraphStyle,
) -> Table:
    """Create a visual counterpart to the web report's discrepancy card."""
    confirmed = outcome == "confirmed"
    accent = "#3730A3" if confirmed else "#475569"
    background = "#F8FAFC" if confirmed else "#F1F5F9"
    heading = Paragraph(
        f"{_title(item.get('discrepancy_type'))} <font color='{accent}'>{_money(item.get('dollar_impact'))}</font>",
        title_style,
    )
    confidence = item.get("confidence_score")
    confidence_label = (
        f"Confidence: {round(float(confidence) * 100)}%"
        if confidence is not None
        else "Confidence: Not available"
    )
    provenance = item.get("impact_provenance")
    impact = provenance.get("rules_engine_dollar_impact") if isinstance(provenance, dict) else None
    calculation_id = provenance.get("rules_engine_discrepancy_id") if isinstance(provenance, dict) else None
    content: list[Any] = [
        heading,
        Paragraph(_text(_explanation(item, outcome)), body_style),
        Paragraph(confidence_label, meta_style),
        Paragraph("Evidence", evidence_style),
        _evidence_items(item, meta_style),
    ]
    content.append(
        Paragraph(
            f"Impact source: {_money(impact)} from the rules engine" if impact else "Impact source: No stored rules-engine impact",
            meta_style,
        )
    )
    if calculation_id:
        content.append(
            Paragraph(
                f"Stored calculation reference: {_text(calculation_id)}. The displayed impact is not recalculated in this view.",
                meta_style,
            )
        )
    if not confirmed:
        content.append(
            Paragraph("Cleared items remain visible for review but do not contribute to total confirmed impact.", meta_style)
        )
    card = Table([[content]], colWidths=[width])
    card.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(background)),
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#CBD5E1")),
                ("LINEBEFORE", (0, 0), (0, -1), 3, colors.HexColor(accent)),
                ("LEFTPADDING", (0, 0), (-1, -1), 15),
                ("RIGHTPADDING", (0, 0), (-1, -1), 15),
                ("TOPPADDING", (0, 0), (-1, -1), 13),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
            ]
        )
    )
    return card


def render_report_pdf(report: dict[str, Any]) -> bytes:
    """Render report payload fields only; no source document text or new calculations."""
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.65 * inch,
        leftMargin=0.65 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
        title="LedgerGuard Report",
        author="LedgerGuard",
    )
    styles = getSampleStyleSheet()
    wordmark = ParagraphStyle("ExportWordmark", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=18, leading=22, textColor=colors.HexColor("#0F172A"))
    eyebrow = ParagraphStyle("ExportEyebrow", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=colors.HexColor("#6366F1"), spaceAfter=3)
    subtitle = ParagraphStyle("ExportSubtitle", parent=styles["Normal"], fontSize=9, leading=13, textColor=colors.HexColor("#64748B"), spaceAfter=0)
    section = ParagraphStyle("ExportSection", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=14, leading=18, textColor=colors.HexColor("#0F172A"), spaceBefore=18, spaceAfter=9)
    item_title = ParagraphStyle("ExportItemTitle", parent=styles["Heading3"], fontName="Helvetica-Bold", fontSize=12, leading=16, textColor=colors.HexColor("#0F172A"), spaceAfter=5)
    body = ParagraphStyle("ExportBody", parent=styles["BodyText"], fontSize=9.3, leading=14, textColor=colors.HexColor("#334155"), spaceAfter=8)
    small = ParagraphStyle("ExportSmall", parent=styles["BodyText"], fontSize=8.3, leading=12, textColor=colors.HexColor("#64748B"), spaceAfter=4)
    evidence_heading = ParagraphStyle("ExportEvidence", parent=small, fontName="Helvetica-Bold", textColor=colors.HexColor("#475569"), spaceBefore=2)
    report_id_style = ParagraphStyle("ExportReportId", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=7.5, leading=10, textColor=colors.HexColor("#64748B"), spaceBefore=4)
    logo = Table([[Paragraph("LG", ParagraphStyle("ExportLogo", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=10, leading=12, textColor=colors.white, alignment=1))]], colWidths=[0.34 * inch], rowHeights=[0.34 * inch])
    logo.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#4338CA")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (0, 0), (-1, -1), "CENTER")]))
    report_identifier = _text(report.get("report_id", ""))
    brand_details: list[Any] = [Paragraph("LEDGERGUARD", eyebrow), Paragraph("Review report", wordmark), Paragraph("Evidence-backed document analysis", subtitle)]
    if report_identifier:
        brand_details.append(Paragraph(f"REPORT ID: {report_identifier}", report_id_style))
    brand = Table([[logo, brand_details]], colWidths=[0.48 * inch, document.width - 0.48 * inch])
    brand.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    story: list[Any] = [brand, Spacer(1, 18)]
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    impact = ParagraphStyle("ExportImpact", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=33, leading=38, textColor=colors.white, alignment=2)
    impact_label = ParagraphStyle("ExportImpactLabel", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=8, leading=11, textColor=colors.HexColor("#C7D2FE"), alignment=2)
    impact_summary = Table(
        [[
            [Paragraph("ANALYSIS COMPLETE", eyebrow), Paragraph("Confirmed discrepancies", ParagraphStyle("SummaryHeading", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=15, leading=19, textColor=colors.white)), Paragraph(f"{summary.get('confirmed_discrepancy_count', 0)} finding(s) requiring review", ParagraphStyle("SummaryBody", parent=subtitle, textColor=colors.HexColor("#CBD5E1")))],
            [Paragraph("TOTAL CONFIRMED IMPACT", impact_label), Paragraph(_money(summary.get("total_confirmed_dollar_impact")), impact), Paragraph("Stored rule impacts only", impact_label)],
        ]],
        colWidths=[document.width * 0.56, document.width * 0.44],
    )
    impact_summary.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#0F172A")), ("LINEBEFORE", (1, 0), (1, -1), 0.5, colors.HexColor("#334155")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 18), ("RIGHTPADDING", (0, 0), (-1, -1), 18), ("TOPPADDING", (0, 0), (-1, -1), 17), ("BOTTOMPADDING", (0, 0), (-1, -1), 17)]))
    story.extend([impact_summary, Paragraph("Confirmed discrepancies", section)])
    confirmed = report.get("confirmed_discrepancies", [])
    if not isinstance(confirmed, list) or not confirmed:
        story.append(Paragraph("No confirmed discrepancies were found.", body))
    else:
        for item in confirmed:
            if not isinstance(item, dict):
                continue
            story.extend([_finding_card(item, "confirmed", width=document.width, title_style=item_title, body_style=body, meta_style=small, evidence_style=evidence_heading), Spacer(1, 10)])
    dismissed = report.get("dismissed_items", [])
    if isinstance(dismissed, list) and dismissed:
        story.append(CondPageBreak(2.8 * inch))
        story.append(Paragraph("Considered but not counted", section))
        story.append(Paragraph("These items were reviewed and do not contribute to the confirmed total.", body))
        for item in dismissed:
            if not isinstance(item, dict):
                continue
            story.extend([_finding_card(item, "dismissed", width=document.width, title_style=item_title, body_style=body, meta_style=small, evidence_style=evidence_heading), Spacer(1, 10)])
    story.extend([Spacer(1, 12), Paragraph(_text(report.get("disclaimer", "LedgerGuard provides informational analysis, not legal or financial advice.")), small)])
    document.build(story)
    return buffer.getvalue()
