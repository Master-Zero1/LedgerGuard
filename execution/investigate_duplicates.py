"""Retrieve rules-engine evidence for one flagged duplicate-charge candidate."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RULE_RUNS_DIR = PROJECT_ROOT / ".tmp" / "rule-runs"
CANDIDATE_ID_PATTERN = re.compile(r"discrepancy_[0-9a-f]{32}")


def _find_discrepancy(candidate_id: str) -> dict[str, Any] | None:
    """Find one bounded rule-run record; no source parsing or arithmetic occurs here."""
    if not CANDIDATE_ID_PATTERN.fullmatch(candidate_id):
        raise ValueError("invalid_candidate_id")
    for path in sorted(RULE_RUNS_DIR.glob("rulerun_*.json"), reverse=True):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            continue
        for discrepancy in payload.get("discrepancies", []):
            if isinstance(discrepancy, dict) and discrepancy.get("id") == candidate_id:
                return discrepancy
    return None


def _line_item_evidence(evidence: object) -> list[dict[str, Any]]:
    if not isinstance(evidence, list):
        return []
    return [
        item
        for item in evidence
        if isinstance(item, dict) and item.get("record_type") == "InvoiceLineItem"
    ]


def investigate(candidate_id: str) -> dict[str, Any]:
    """Return stored duplicate evidence and impact provenance without recomputing either."""
    discrepancy = _find_discrepancy(candidate_id)
    if discrepancy is None:
        return {
            "supports_duplicate": None,
            "line_items": [],
            "match_criteria": None,
            "duplicate_group": [],
            "calculation_provenance": None,
            "confidence_score": None,
        }

    line_items = _line_item_evidence(discrepancy.get("evidence"))
    supported = (
        discrepancy.get("type") == "duplicate"
        and discrepancy.get("status") == "flagged"
        and isinstance(discrepancy.get("dollar_impact"), str)
        and len(line_items) >= 2
    )
    return {
        "supports_duplicate": supported,
        "line_items": line_items,
        "match_criteria": (
            "rules_engine_duplicate_match"
            if supported
            else "insufficient_rules_engine_evidence"
        ),
        "duplicate_group": [item.get("record_id") for item in line_items],
        "calculation_provenance": {
            "rules_engine_discrepancy_id": discrepancy.get("id"),
            "rules_engine_dollar_impact": discrepancy.get("dollar_impact"),
        },
        "confidence_score": discrepancy.get("confidence_score"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--user-id", required=True)
    arguments = parser.parse_args()
    try:
        result = investigate(arguments.candidate_id)
    except (OSError, ValueError, json.JSONDecodeError):
        print(json.dumps({"status": "failed", "error_code": "duplicate_input_invalid"}))
        return 0
    print(json.dumps({"status": "completed", **result}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
