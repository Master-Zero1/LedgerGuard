"""Generate realistic synthetic contract, invoice, and statement PDFs for parser tests."""

from __future__ import annotations

import argparse
from decimal import Decimal
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / ".tmp" / "test_documents"
VENDOR_NAME = "Northstar Cloud Services"
CUSTOMER_NAME = "Harborview Analytics LLC"


def money(value: Decimal) -> str:
    return f"${value:,.2f}"


def build_document(path: Path, title: str, elements: list[object]) -> None:
    """Create a single polished PDF with stable header and footer styling."""
    styles = getSampleStyleSheet()
    document = SimpleDocTemplate(
        str(path),
        pagesize=letter,
        rightMargin=0.65 * inch,
        leftMargin=0.65 * inch,
        topMargin=0.65 * inch,
        bottomMargin=0.65 * inch,
        title=title,
        author="LedgerGuard synthetic test data",
    )
    title_style = ParagraphStyle(
        "DocumentTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=21,
        leading=25,
        textColor=colors.HexColor("#17324D"),
        spaceAfter=6,
    )
    subtitle_style = ParagraphStyle(
        "Subtitle",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#52616B"),
    )
    document.build(
        [
            Paragraph(title, title_style),
            Paragraph("Synthetic test document - no real financial data", subtitle_style),
            Spacer(1, 16),
            *elements,
        ],
        onFirstPage=_page_footer,
        onLaterPages=_page_footer,
    )


def _page_footer(canvas, document) -> None:
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#D8DEE4"))
    canvas.line(document.leftMargin, 0.48 * inch, letter[0] - document.rightMargin, 0.48 * inch)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#52616B"))
    canvas.drawString(document.leftMargin, 0.32 * inch, "LedgerGuard synthetic test data")
    canvas.drawRightString(letter[0] - document.rightMargin, 0.32 * inch, f"Page {document.page}")
    canvas.restoreState()


def metadata_table(rows: list[tuple[str, str]]) -> Table:
    table = Table(rows, colWidths=[1.4 * inch, 5.2 * inch])
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#17324D")),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def styled_table(rows: list[list[str]], widths: list[float]) -> Table:
    table = Table(rows, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17324D")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#C9D3DC")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F8FA")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
            ]
        )
    )
    return table


def generate_contract(output_dir: Path) -> None:
    styles = getSampleStyleSheet()
    body = ParagraphStyle("ContractBody", parent=styles["BodyText"], leading=14, spaceAfter=9)
    clauses = [
        ["Clause", "Service", "Agreed rate", "Unit", "Effective period"],
        ["3.1", "Managed storage subscription", "$100.00", "per month", "Jan 1-Dec 31, 2026"],
        ["3.2", "Priority support", "$50.00", "per hour", "Jan 1-Dec 31, 2026"],
        ["3.3", "API transactions", "$0.10", "per transaction", "Jan 1-Dec 31, 2026"],
    ]
    elements = [
        metadata_table(
            [
                ("Agreement ID", "NCS-HVA-2026"),
                ("Provider", VENDOR_NAME),
                ("Customer", CUSTOMER_NAME),
                ("Effective dates", "January 1, 2026 through December 31, 2026"),
            ]
        ),
        Spacer(1, 14),
        Paragraph("Commercial terms", styles["Heading2"]),
        Paragraph(
            "The following rates apply to all invoices for the stated effective period. "
            "No other recurring service rates are authorized under this agreement.",
            body,
        ),
        styled_table(clauses, [0.55 * inch, 2.55 * inch, 0.95 * inch, 1.1 * inch, 1.3 * inch]),
    ]
    build_document(output_dir / "sample_contract_northstar_2026.pdf", "Service Agreement", elements)


def generate_contract_drift_documents(output_dir: Path) -> None:
    """Create an original agreement, an unexplained revised schedule, and a matching invoice."""
    styles = getSampleStyleSheet()
    body = ParagraphStyle("ContractDriftBody", parent=styles["BodyText"], leading=14, spaceAfter=9)
    original_clauses = [
        ["Clause", "Service", "Agreed rate", "Unit", "Effective period"],
        ["4.1", "Managed storage subscription", "$100.00", "per month", "Jan 1-Dec 31, 2026"],
        ["4.2", "Priority support", "$50.00", "per hour", "Jan 1-Dec 31, 2026"],
    ]
    original_elements = [
        metadata_table(
            [
                ("Agreement ID", "NCS-HVA-DRIFT-2026"),
                ("Provider", VENDOR_NAME),
                ("Customer", CUSTOMER_NAME),
                ("Effective dates", "January 1, 2026 through December 31, 2026"),
                ("Document version", "Original executed agreement"),
            ]
        ),
        Spacer(1, 14),
        Paragraph("Commercial terms", styles["Heading2"]),
        Paragraph("The following rates apply to the agreement term.", body),
        styled_table(original_clauses, [0.55 * inch, 2.55 * inch, 0.95 * inch, 1.1 * inch, 1.3 * inch]),
    ]
    build_document(
        output_dir / "contract_drift_original_agreement_2026.pdf",
        "Service Agreement - Original",
        original_elements,
    )

    revised_clauses = [
        ["Clause", "Service", "Agreed rate", "Unit", "Effective period"],
        ["4.1", "Managed storage subscription", "$130.00", "per month", "Mar 1-Dec 31, 2026"],
        ["4.2", "Priority support", "$50.00", "per hour", "Jan 1-Dec 31, 2026"],
    ]
    revised_elements = [
        metadata_table(
            [
                ("Agreement ID", "NCS-HVA-DRIFT-2026"),
                ("Provider", VENDOR_NAME),
                ("Customer", CUSTOMER_NAME),
                ("Effective dates", "March 1, 2026 through December 31, 2026"),
                ("Document version", "Rate schedule revision 2"),
            ]
        ),
        Spacer(1, 14),
        Paragraph("Commercial terms", styles["Heading2"]),
        Paragraph("The following schedule reflects the rates recorded for the stated period.", body),
        styled_table(revised_clauses, [0.55 * inch, 2.55 * inch, 0.95 * inch, 1.1 * inch, 1.3 * inch]),
    ]
    build_document(
        output_dir / "contract_drift_rate_schedule_revision_2_2026.pdf",
        "Service Agreement Rate Schedule - Revision 2",
        revised_elements,
    )

    generate_invoice(
        output_dir,
        "contract_drift_invoice_march_2026.pdf",
        "INV-2026-DRIFT-01",
        "March 15, 2026",
        "March 2026",
        [
            ("Managed storage subscription", Decimal("1"), Decimal("130.00")),
            ("Priority support", Decimal("2"), Decimal("50.00")),
        ],
        agreement_reference="NCS-HVA-DRIFT-2026",
    )


def generate_authorized_contract_drift_documents(output_dir: Path) -> None:
    """Create an original agreement, executed amendment, and invoice for an authorized increase."""
    styles = getSampleStyleSheet()
    body = ParagraphStyle("AuthorizedDriftBody", parent=styles["BodyText"], leading=14, spaceAfter=9)
    original_clauses = [
        ["Clause", "Service", "Agreed rate", "Unit", "Effective period"],
        ["4.1", "Managed storage subscription", "$100.00", "per month", "Jan 1-Dec 31, 2026"],
        ["4.2", "Priority support", "$50.00", "per hour", "Jan 1-Dec 31, 2026"],
    ]
    original_elements = [
        metadata_table(
            [
                ("Agreement ID", "NCS-HVA-DRIFT-AUTH-2026"),
                ("Provider", VENDOR_NAME),
                ("Customer", CUSTOMER_NAME),
                ("Effective dates", "January 1, 2026 through December 31, 2026"),
                ("Document version", "Original executed agreement"),
            ]
        ),
        Spacer(1, 14),
        Paragraph("Commercial terms", styles["Heading2"]),
        Paragraph("The following rates apply to the agreement term.", body),
        styled_table(original_clauses, [0.55 * inch, 2.55 * inch, 0.95 * inch, 1.1 * inch, 1.3 * inch]),
    ]
    build_document(
        output_dir / "contract_drift_authorized_original_agreement_2026.pdf",
        "Service Agreement - Authorized Variant Original",
        original_elements,
    )

    amendment_terms = [
        ["Clause", "Service", "Prior rate", "New rate", "Unit", "Effective date"],
        ["4.1", "Managed storage subscription", "$100.00", "$130.00", "per month", "March 1, 2026"],
    ]
    approval_rows = [
        ["Party", "Authorized signatory", "Approval status", "Date"],
        [VENDOR_NAME, "Jordan Patel, VP Finance", "Signed and approved", "February 20, 2026"],
        [CUSTOMER_NAME, "Riley Chen, CFO", "Signed and approved", "February 20, 2026"],
    ]
    approvals = styled_table(approval_rows, [1.6 * inch, 2.0 * inch, 1.5 * inch, 1.5 * inch])
    approvals.setStyle(TableStyle([("ALIGN", (0, 1), (-1, -1), "LEFT")]))
    amendment_elements = [
        metadata_table(
            [
                ("Amendment number", "Amendment No. 1"),
                ("Original agreement", "NCS-HVA-DRIFT-AUTH-2026"),
                ("Agreement ID", "NCS-HVA-DRIFT-AUTH-2026"),
                ("Provider", VENDOR_NAME),
                ("Amendment date", "February 20, 2026"),
                ("Rate effective date", "March 1, 2026"),
                ("Effective dates", "March 1, 2026 through December 31, 2026"),
                ("Status", "Fully executed"),
            ]
        ),
        Spacer(1, 14),
        Paragraph("Authorized rate change", styles["Heading2"]),
        Paragraph(
            "This Amendment No. 1 expressly amends clause 4.1 of Service Agreement "
            "NCS-HVA-DRIFT-AUTH-2026. The managed storage subscription rate changes "
            "from $100.00 to $130.00 per month, effective March 1, 2026. All other "
            "agreement terms remain unchanged.",
            body,
        ),
        styled_table(amendment_terms, [0.5 * inch, 2.0 * inch, 0.8 * inch, 0.8 * inch, 0.9 * inch, 1.1 * inch]),
        Spacer(1, 14),
        Paragraph("Amended rate schedule", styles["Heading2"]),
        styled_table(
            [
                ["Clause", "Service", "Agreed rate", "Unit", "Effective period"],
                ["4.1", "Managed storage subscription", "$130.00", "per month", "Mar 1-Dec 31, 2026"],
            ],
            [0.55 * inch, 2.55 * inch, 0.95 * inch, 1.1 * inch, 1.3 * inch],
        ),
        Spacer(1, 14),
        Paragraph("Approvals", styles["Heading2"]),
        approvals,
    ]
    build_document(
        output_dir / "contract_drift_authorized_amendment_no_1_2026.pdf",
        "Amendment No. 1 - Authorized Rate Change",
        amendment_elements,
    )

    generate_invoice(
        output_dir,
        "contract_drift_authorized_invoice_march_2026.pdf",
        "INV-2026-DRIFT-AUTH-01",
        "March 15, 2026",
        "March 2026",
        [
            ("Managed storage subscription", Decimal("1"), Decimal("130.00")),
            ("Priority support", Decimal("2"), Decimal("50.00")),
        ],
        agreement_reference="NCS-HVA-DRIFT-AUTH-2026",
    )


def generate_invoice(
    output_dir: Path,
    filename: str,
    invoice_number: str,
    issue_date: str,
    period: str,
    items: list[tuple[str, Decimal, Decimal]],
    *,
    agreement_reference: str | None = None,
) -> None:
    total = sum((quantity * unit_price for _, quantity, unit_price in items), Decimal("0.00"))
    rows = [["Description", "Service period", "Quantity", "Unit price", "Line total"]]
    for description, quantity, unit_price in items:
        rows.append(
            [
                description,
                period,
                f"{quantity}",
                money(unit_price),
                money(quantity * unit_price),
            ]
        )
    rows.append(["", "", "", "Invoice total", money(total)])
    table = styled_table(rows, [2.0 * inch, 1.4 * inch, 0.7 * inch, 0.85 * inch, 0.85 * inch])
    table.setStyle(TableStyle([("FONTNAME", (3, -1), (-1, -1), "Helvetica-Bold")]))
    metadata_rows = [
        ("Invoice number", invoice_number),
        ("Issue date", issue_date),
        ("Vendor", VENDOR_NAME),
        ("Bill to", CUSTOMER_NAME),
    ]
    if agreement_reference:
        metadata_rows.append(("Agreement ID", agreement_reference))
    elements = [
        metadata_table(
            metadata_rows
        ),
        Spacer(1, 14),
        KeepTogether([Paragraph("Invoice line items", getSampleStyleSheet()["Heading2"]), table]),
        Spacer(1, 12),
        Paragraph("Payment terms: Net 30 days.", getSampleStyleSheet()["BodyText"]),
    ]
    build_document(output_dir / filename, "Invoice", elements)


def generate_statement(output_dir: Path) -> None:
    rows = [
        ["Date", "Reference", "Description", "Debit", "Credit", "Balance"],
        ["Mar 1, 2026", "INV-2026-103", "Monthly invoice posted", "$200.00", "$0.00", "$200.00"],
        ["Mar 12, 2026", "SUP-2026-03", "Priority support", "$100.00", "$0.00", "$300.00"],
        ["Mar 20, 2026", "PAY-1029", "Payment received", "$0.00", "$200.00", "$100.00"],
    ]
    elements = [
        metadata_table(
            [
                ("Statement number", "STMT-2026-03"),
                ("Statement date", "March 31, 2026"),
                ("Vendor", VENDOR_NAME),
                ("Account", "HVA-8891"),
                ("Agreement ID", "NCS-HVA-2026"),
            ]
        ),
        Spacer(1, 14),
        Paragraph("Account activity", getSampleStyleSheet()["Heading2"]),
        styled_table(rows, [0.85 * inch, 1.0 * inch, 2.3 * inch, 0.75 * inch, 0.75 * inch, 0.75 * inch]),
    ]
    build_document(output_dir / "duplicate_charge_statement_march_2026.pdf", "Account Statement", elements)


def generate_documents(output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    generate_contract(output_dir)
    generate_invoice(
        output_dir,
        "clean_invoice_march_2026.pdf",
        "INV-2026-101",
        "March 1, 2026",
        "March 2026",
        [
            ("Managed storage subscription", Decimal("1"), Decimal("100.00")),
            ("Priority support", Decimal("4"), Decimal("50.00")),
            ("API transactions", Decimal("1000"), Decimal("0.10")),
        ],
        agreement_reference="NCS-HVA-2026",
    )
    generate_invoice(
        output_dir,
        "rate_violation_invoice_march_2026.pdf",
        "INV-2026-102",
        "March 5, 2026",
        "March 2026",
        [
            ("Managed storage subscription", Decimal("1"), Decimal("125.00")),
            ("Priority support", Decimal("3"), Decimal("50.00")),
            ("API transactions", Decimal("500"), Decimal("0.10")),
        ],
        agreement_reference="NCS-HVA-2026",
    )
    generate_invoice(
        output_dir,
        "duplicate_charge_invoice_march_2026.pdf",
        "INV-2026-103",
        "March 12, 2026",
        "March 2026",
        [
            ("Managed storage subscription", Decimal("1"), Decimal("100.00")),
            ("Priority support", Decimal("2"), Decimal("50.00")),
        ],
        agreement_reference="NCS-HVA-2026",
    )
    generate_invoice(
        output_dir,
        "wording_variation_invoice_march_2026.pdf",
        "INV-2026-104",
        "March 25, 2026",
        "March 2026",
        [
            ("Managed storage service", Decimal("1"), Decimal("100.00")),
            ("Priority support hours", Decimal("2"), Decimal("50.00")),
            ("API usage transactions", Decimal("250"), Decimal("0.10")),
        ],
        agreement_reference="NCS-HVA-2026",
    )
    generate_statement(output_dir)
    generate_contract_drift_documents(output_dir)
    generate_authorized_contract_drift_documents(output_dir)
    return sorted(output_dir.glob("*.pdf"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    arguments = parser.parse_args()
    for path in generate_documents(arguments.output_dir):
        print(path)


if __name__ == "__main__":
    main()
