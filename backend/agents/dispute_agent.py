"""Layer 2 drafting of one dispute email per confirmed discrepancy; never sends."""

from __future__ import annotations

from typing import Any

from ._orchestration import call_execution, read_directive, short_evidence

DIRECTIVE = "draft_dispute.md"
SCRIPT = "prepare_dispute_context.py"
def draft(
    discrepancy_id: str, user_id: str, *, report_artifact: str | None = None
) -> dict[str, Any]:
    """Create a draft-only DisputeDraft from validated context; it has no send capability."""
    read_directive(DIRECTIVE)
    arguments = ["--discrepancy-id", discrepancy_id, "--user-id", user_id]
    if report_artifact:
        arguments.extend(("--report-artifact", report_artifact))
    context = call_execution(SCRIPT, arguments)
    evidence = short_evidence(context.get("evidence"))
    if context.get("status") != "confirmed" or not evidence:
        return {"clarification_needed": "Confirmed discrepancy evidence is required before drafting."}
    cited_facts = "\n".join(
        f"- {item.get('excerpt')} (record {item.get('record_id')})" for item in evidence
    )
    discrepancy_type = str(context.get("discrepancy_type", "discrepancy")).replace("_", " ")
    dollar_impact = context.get("dollar_impact")
    closing_lines = {
        "duplicate": "Please review these records and issue a refund or credit for the repeated charge.",
        "price hike": "Please review these records and clarify the authorization for the price change.",
        "rate violation": "Please review these records and provide a corrected invoice for the contracted rate.",
    }
    closing_line = closing_lines.get(
        discrepancy_type,
        "Please review these records and advise on the appropriate correction.",
    )
    return {
        "id": context.get("draft_id"),
        "discrepancy_id": discrepancy_id,
        "subject": f"Request to review confirmed {discrepancy_type}",
        "body": (
            "Hello,\n\n"
            f"Please review the confirmed {discrepancy_type} with a stored impact of ${dollar_impact}. "
            "The cited records show:\n"
            f"{cited_facts}\n\n"
            f"{closing_line}\n\n"
            "Thank you."
        ),
        "status": "draft",
    }
