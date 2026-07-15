"""Layer 2 investigation of suspected contract-rate violations only."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ._orchestration import call_execution, read_directive, short_evidence

DIRECTIVE = "investigate_pricing.md"
SCRIPT = "investigate_pricing.py"
Executor = Callable[[str, list[str]], dict[str, Any]]


def investigate(candidate_id: str, user_id: str, *, executor: Executor = call_execution) -> dict[str, Any]:
    """Return a pricing-only verdict from deterministic evidence; never compute impact."""
    read_directive(DIRECTIVE)
    result = executor(SCRIPT, ["--candidate-id", candidate_id, "--user-id", user_id])
    evidence = short_evidence(result.get("evidence"))
    support = result.get("supports_rate_violation")
    verdict = "confirmed" if support is True and evidence else "dismissed" if support is False and evidence else "needs_clarification"
    return {
        "verdict": verdict,
        "evidence": evidence,
        "calculation_provenance": result.get("calculation_provenance"),
        "confidence_score": result.get("confidence_score"),
        "rationale": result.get("rationale"),
    }
