"""Retrieve deterministic authorization evidence for one contract-drift candidate."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_EXTRACTION_DIR = PROJECT_ROOT / ".tmp" / "raw-extractions"
DRIFT_CANDIDATES_DIR = PROJECT_ROOT / ".tmp" / "contract-drift-candidates"
CANDIDATE_ID_PATTERN = re.compile(r"discrepancy_[0-9a-f]{32}")


def _read_candidate(candidate_id: str) -> dict[str, Any]:
    """Load only a bounded deterministic candidate artifact."""
    if not CANDIDATE_ID_PATTERN.fullmatch(candidate_id):
        raise ValueError("invalid_candidate_id")
    path = DRIFT_CANDIDATES_DIR / f"{candidate_id}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("invalid_candidate")
    return payload


def _raw_text(path_value: object) -> str:
    if not isinstance(path_value, str):
        return ""
    path = Path(path_value).resolve(strict=True)
    try:
        path.relative_to(RAW_EXTRACTION_DIR.resolve())
    except ValueError as error:
        raise ValueError("artifact_outside_raw_extractions") from error
    payload = json.loads(path.read_text(encoding="utf-8"))
    text = payload.get("raw_text") if isinstance(payload, dict) else ""
    return text if isinstance(text, str) else ""


def _field(text: str, label: str) -> str | None:
    match = re.search(rf"^{re.escape(label)}\s+(.+)$", text, flags=re.MULTILINE)
    return match.group(1).strip() if match else None


def _date(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%B %d, %Y").date().isoformat()
    except ValueError:
        return None


def _evidence(record_type: str, record: dict[str, Any], excerpt: str) -> dict[str, Any]:
    return {
        "record_type": record_type,
        "record_id": record.get("id"),
        "page_ref": record.get("page_ref", ""),
        "excerpt": excerpt,
    }


def investigate(candidate_id: str) -> dict[str, Any]:
    """Assess authorization markers and dates without recalculating contract or dollar values."""
    candidate = _read_candidate(candidate_id)
    old_clause = candidate.get("old_clause")
    new_clause = candidate.get("new_clause")
    old_contract = candidate.get("old_contract")
    new_contract = candidate.get("new_contract")
    invoice = candidate.get("invoice")
    if not all(isinstance(record, dict) for record in (old_clause, new_clause, old_contract, new_contract, invoice)):
        return {
            "supports_unauthorized_drift": None,
            "old_new_terms": [],
            "effective_date_applicability": None,
            "field_level_changes": [],
            "impact_provenance": None,
            "confidence_score": None,
        }

    old_text = _raw_text(candidate.get("old_source_artifact"))
    new_text = _raw_text(candidate.get("new_source_artifact"))
    original_agreement_id = _field(old_text, "Agreement ID")
    amendment_date = _date(_field(new_text, "Amendment date"))
    invoice_date = invoice.get("date")
    normalized_new_text = new_text.lower()
    authorization_present = all(
        (
            "amendment no." in normalized_new_text,
            "fully executed" in normalized_new_text,
            normalized_new_text.count("signed and approved") >= 2,
            original_agreement_id is not None and original_agreement_id.lower() in normalized_new_text,
            amendment_date is not None and isinstance(invoice_date, str) and amendment_date <= invoice_date,
            str(new_clause.get("agreed_unit_price", "")) in new_text,
        )
    )
    new_effective_date = new_contract.get("effective_date")
    applies = (
        isinstance(invoice_date, str)
        and isinstance(new_effective_date, str)
        and invoice_date >= new_effective_date
        and (not new_contract.get("expiry_date") or invoice_date <= new_contract["expiry_date"])
    )
    support = (not authorization_present) if applies else None
    return {
        "supports_unauthorized_drift": support,
        "old_new_terms": [
            _evidence(
                "ContractClause",
                old_clause,
                f"Earlier recorded unit price: {old_clause.get('agreed_unit_price')} per {old_clause.get('unit')}.",
            ),
            _evidence(
                "ContractClause",
                new_clause,
                f"Later recorded unit price: {new_clause.get('agreed_unit_price')} per {new_clause.get('unit')}.",
            ),
            _evidence(
                "Invoice",
                invoice,
                f"Invoice date: {invoice_date}; billed source file: {invoice.get('source_file_id')}.",
            ),
        ],
        "effective_date_applicability": {
            "invoice_date": invoice_date,
            "new_term_effective_date": new_effective_date,
            "applicable": applies,
            "amendment_date": amendment_date,
        },
        "field_level_changes": [
            {
                "field": "agreed_unit_price",
                "before": old_clause.get("agreed_unit_price"),
                "after": new_clause.get("agreed_unit_price"),
            }
        ],
        "impact_provenance": {
            "rules_engine_discrepancy_id": candidate.get("candidate_id"),
            "rules_engine_dollar_impact": candidate.get("dollar_impact"),
        },
        "confidence_score": 1.0 if support is not None else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--user-id", required=True)
    arguments = parser.parse_args()
    try:
        result = investigate(arguments.candidate_id)
    except (OSError, ValueError, json.JSONDecodeError):
        print(json.dumps({"status": "failed", "error_code": "contract_drift_input_invalid"}))
        return 0
    print(json.dumps({"status": "completed", **result}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
