"""Layer 2 synthesis: merge verdicts only; never re-investigate."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ._orchestration import call_execution, read_directive

DIRECTIVE = "synthesize_report.md"
SCRIPT = "synthesize_report.py"
DISCLAIMER = "LedgerGuard provides informational analysis, not legal or financial advice."
Executor = Callable[[str, list[str]], dict[str, Any]]


def synthesize(verdicts_path: str, user_id: str, *, executor: Executor = call_execution) -> dict[str, Any]:
    """Return the validated, ranked report payload without recalculating or re-investigating."""
    read_directive(DIRECTIVE)
    result = executor(SCRIPT, ["--verdicts", verdicts_path, "--user-id", user_id])
    return {
        "report": result.get("report"),
        "disclaimer": DISCLAIMER,
        "report_payload": result.get("report_payload"),
        "report_artifact": result.get("report_artifact"),
    }
