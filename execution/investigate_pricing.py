"""Retrieve rules-engine evidence for one flagged rate-violation candidate."""

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
    """Find one bounded rule-run record; never parse source documents or recalculate money."""
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


def _has_required_evidence(evidence: object) -> bool:
    if not isinstance(evidence, list):
        return False
    record_types = {
        item.get("record_type") for item in evidence if isinstance(item, dict)
    }
    return {"InvoiceLineItem", "ContractClause"}.issubset(record_types)


def investigate(candidate_id: str) -> dict[str, Any]:
    """Return only stored rules-engine provenance for a pricing agent to evaluate."""
    discrepancy = _find_discrepancy(candidate_id)
    if discrepancy is None:
        return {
            "supports_rate_violation": None,
            "evidence": [],
            "calculation_provenance": None,
            "confidence_score": None,
            "rationale": "The routed candidate was not found in a rules-engine artifact.",
        }

    evidence = discrepancy.get("evidence", [])
    supported = (
        discrepancy.get("type") == "rate_violation"
        and discrepancy.get("status") == "flagged"
        and isinstance(discrepancy.get("dollar_impact"), str)
        and _has_required_evidence(evidence)
    )
    return {
        "supports_rate_violation": supported,
        "evidence": evidence if isinstance(evidence, list) else [],
        "calculation_provenance": {
            "rules_engine_discrepancy_id": discrepancy.get("id"),
            "rules_engine_dollar_impact": discrepancy.get("dollar_impact"),
        },
        "confidence_score": discrepancy.get("confidence_score"),
        "rationale": (
            "The rules engine flagged a rate violation with cited invoice and contract evidence."
            if supported
            else "The routed candidate lacks the stored evidence required for a pricing confirmation."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--user-id", required=True)
    arguments = parser.parse_args()
    try:
        result = investigate(arguments.candidate_id)
    except (OSError, ValueError, json.JSONDecodeError):
        print(json.dumps({"status": "failed", "error_code": "pricing_input_invalid"}))
        return 0
    print(json.dumps({"status": "completed", **result}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
