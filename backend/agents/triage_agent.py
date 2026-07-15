"""Layer 2 triage: route candidates without issuing discrepancy verdicts."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from ._orchestration import call_execution, read_directive, short_evidence

DIRECTIVE = "triage.md"
SCRIPT = "prepare_triage_candidates.py"
Executor = Callable[[str, list[str]], dict[str, Any]]


def _route(candidate: Mapping[str, Any]) -> tuple[str, str]:
    """Make the Layer 2 routing decision; the execution script never chooses a route."""
    kind = candidate.get("type")
    if kind == "rate_violation":
        return "pricing", "Candidate is a flagged rate mismatch."
    if kind == "duplicate":
        return "duplicate", "Candidate is a flagged duplicate-charge match."
    if kind == "price_hike":
        return "contract_drift", "Candidate may reflect a changed applicable term."
    return "needs_clarification", "Candidate type does not support a bounded investigation route."


def triage(rule_run_id: str, user_id: str, *, executor: Executor = call_execution) -> dict[str, Any]:
    """Return the directive-defined triage queue, with no confirmation or dismissal."""
    read_directive(DIRECTIVE)
    prepared = executor(SCRIPT, ["--rule-run-id", rule_run_id, "--user-id", user_id])
    queue: list[dict[str, Any]] = []
    for candidate in prepared.get("candidates", []):
        if not isinstance(candidate, Mapping):
            continue
        route, rationale = _route(candidate)
        item = {
            "candidate_id": candidate.get("candidate_id"),
            "suggested_investigation_type": route,
            "priority_rationale": rationale,
            "confidence_score": candidate.get("confidence_score"),
            "evidence": short_evidence(candidate.get("evidence")),
        }
        if route == "needs_clarification":
            item["clarification_reason"] = rationale
        queue.append(item)
    return {"triage_queue": queue}
