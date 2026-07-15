"""Retrieve flagged rules-engine discrepancies as triage candidates."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RULE_RUNS_DIR = PROJECT_ROOT / ".tmp" / "rule-runs"
DRIFT_CANDIDATES_DIR = PROJECT_ROOT / ".tmp" / "contract-drift-candidates"
RULE_RUN_ID_PATTERN = re.compile(r"rulerun_[0-9a-f]{32}")


def _read_rule_run(rule_run_id: str) -> dict[str, Any]:
    """Load one bounded rule-run artifact without accepting arbitrary filesystem paths."""
    if not RULE_RUN_ID_PATTERN.fullmatch(rule_run_id):
        raise ValueError("invalid_rule_run_id")
    path = RULE_RUNS_DIR / f"{rule_run_id}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("invalid_rule_run")
    return payload


def _write_drift_candidate(candidate: dict[str, Any]) -> None:
    path = DRIFT_CANDIDATES_DIR / f"{candidate['candidate_id']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".partial")
    partial.write_text(json.dumps(candidate), encoding="utf-8")
    partial.replace(path)


def prepare(rule_run_id: str) -> list[dict[str, Any]]:
    """Preserve deterministic evidence and fields; routing remains Layer 2 work."""
    rule_run = _read_rule_run(rule_run_id)
    candidates: list[dict[str, Any]] = []
    drift_contexts = rule_run.get("contract_drift_contexts", {})
    for discrepancy in rule_run.get("discrepancies", []):
        if not isinstance(discrepancy, dict) or discrepancy.get("status") != "flagged":
            continue
        if discrepancy.get("type") == "price_hike" and isinstance(drift_contexts, dict):
            context = drift_contexts.get(discrepancy.get("id"))
            if isinstance(context, dict):
                _write_drift_candidate(context)
        candidates.append(
            {
                "candidate_id": discrepancy.get("id"),
                "type": discrepancy.get("type"),
                "confidence_score": discrepancy.get("confidence_score"),
                "evidence": discrepancy.get("evidence", []),
            }
        )
    return candidates


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rule-run-id", required=True)
    parser.add_argument("--user-id", required=True)
    arguments = parser.parse_args()
    try:
        candidates = prepare(arguments.rule_run_id)
    except (OSError, ValueError, json.JSONDecodeError):
        print(json.dumps({"status": "failed", "error_code": "triage_input_invalid"}))
        return 0
    print(json.dumps({"status": "completed", "candidates": candidates}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
