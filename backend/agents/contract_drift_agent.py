"""Layer 2 investigation of unauthorized contract-term changes only."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ._orchestration import call_execution, read_directive, short_evidence

DIRECTIVE = "investigate_contract_drift.md"
SCRIPT = "investigate_contract_drift.py"
Executor = Callable[[str, list[str]], dict[str, Any]]


def investigate(candidate_id: str, user_id: str, *, executor: Executor = call_execution) -> dict[str, Any]:
    """Return a drift-only verdict from deterministic evidence; never compute impact."""
    read_directive(DIRECTIVE)
    result = executor(SCRIPT, ["--candidate-id", candidate_id, "--user-id", user_id])
    old_new_terms = short_evidence(result.get("old_new_terms"))
    support = result.get("supports_unauthorized_drift")
    verdict = "confirmed" if support is True and old_new_terms else "dismissed" if support is False and old_new_terms else "needs_clarification"
    return {
        "verdict": verdict,
        "evidence": {
            "old_new_terms": old_new_terms,
            "effective_date_applicability": result.get("effective_date_applicability"),
            "field_level_changes": result.get("field_level_changes"),
        },
        "impact_provenance": result.get("impact_provenance"),
        "confidence_score": result.get("confidence_score"),
    }
