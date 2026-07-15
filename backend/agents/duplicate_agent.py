"""Layer 2 investigation of suspected duplicate charges only."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ._orchestration import call_execution, read_directive, short_evidence

DIRECTIVE = "investigate_duplicates.md"
SCRIPT = "investigate_duplicates.py"
Executor = Callable[[str, list[str]], dict[str, Any]]


def investigate(candidate_id: str, user_id: str, *, executor: Executor = call_execution) -> dict[str, Any]:
    """Return a duplicate-only verdict from deterministic evidence; never compute impact."""
    read_directive(DIRECTIVE)
    result = executor(SCRIPT, ["--candidate-id", candidate_id, "--user-id", user_id])
    line_items = short_evidence(result.get("line_items"))
    support = result.get("supports_duplicate")
    verdict = "confirmed" if support is True and line_items else "dismissed" if support is False and line_items else "needs_clarification"
    return {
        "verdict": verdict,
        "evidence": {
            "line_items": line_items,
            "match_criteria": result.get("match_criteria"),
            "duplicate_group": result.get("duplicate_group"),
        },
        "calculation_provenance": result.get("calculation_provenance"),
        "confidence_score": result.get("confidence_score"),
    }
