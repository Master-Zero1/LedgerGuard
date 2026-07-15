"""Validate, rank, and render a report payload from completed investigation verdicts."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMP_DIR = PROJECT_ROOT / ".tmp"
REPORTS_DIR = TEMP_DIR / "reports"
DISCLAIMER = "LedgerGuard provides informational analysis, not legal or financial advice."
TYPE_BY_INVESTIGATION = {
    "pricing": "rate_violation",
    "duplicate": "duplicate",
    "contract_drift": "price_hike",
}


def _money(value: object) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _formatted_money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01")))


def _read_verdicts(path_value: str) -> list[dict[str, Any]]:
    path = Path(path_value).resolve(strict=True)
    try:
        path.relative_to(TEMP_DIR.resolve())
    except ValueError as error:
        raise ValueError("verdicts_outside_temp_directory") from error
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("invalid_verdicts")
    return [item for item in payload if isinstance(item, dict)]


def _short_citation(value: object) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    excerpt = value.get("excerpt")
    if not isinstance(excerpt, str) or not excerpt:
        return None
    return {
        "record_type": str(value.get("record_type", "")),
        "record_id": str(value.get("record_id", "")),
        "page_ref": str(value.get("page_ref", "")),
        "excerpt": excerpt[:240],
    }


def _citations(evidence: object) -> list[dict[str, str]]:
    if isinstance(evidence, list):
        return [citation for item in evidence if (citation := _short_citation(item))]
    if not isinstance(evidence, dict):
        return []
    citations: list[dict[str, str]] = []
    for key in ("line_items", "old_new_terms"):
        value = evidence.get(key)
        if isinstance(value, list):
            citations.extend(citation for item in value if (citation := _short_citation(item)))
    return citations


def _impact_provenance(verdict: dict[str, Any]) -> tuple[dict[str, Any] | None, Decimal | None]:
    for key in ("calculation_provenance", "impact_provenance"):
        provenance = verdict.get(key)
        if not isinstance(provenance, dict):
            continue
        impact = _money(provenance.get("rules_engine_dollar_impact"))
        if impact is not None:
            return dict(provenance), impact
    return None, None


def _report_item(investigation: dict[str, Any]) -> tuple[dict[str, Any], Decimal | None] | None:
    candidate_id = investigation.get("candidate_id")
    investigation_type = investigation.get("investigation_type")
    verdict = investigation.get("verdict")
    if not isinstance(candidate_id, str) or not isinstance(investigation_type, str) or not isinstance(verdict, dict):
        return None
    status = verdict.get("verdict")
    if status not in {"confirmed", "dismissed", "needs_clarification"}:
        return None
    provenance, impact = _impact_provenance(verdict)
    item = {
        "candidate_id": candidate_id,
        "discrepancy_type": TYPE_BY_INVESTIGATION.get(investigation_type, "other"),
        "investigation_type": investigation_type,
        "verdict": status,
        "dollar_impact": _formatted_money(impact) if impact is not None else None,
        "confidence_score": verdict.get("confidence_score"),
        "evidence": _citations(verdict.get("evidence")),
        "impact_provenance": provenance,
    }
    return item, impact


def synthesize(verdicts: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge verdicts only; rankings and totals use stored rules-engine amounts."""
    confirmed: list[tuple[dict[str, Any], Decimal]] = []
    dismissed: list[dict[str, Any]] = []
    clarification_requests: list[dict[str, Any]] = []
    for investigation in verdicts:
        resolved = _report_item(investigation)
        if resolved is None:
            continue
        item, impact = resolved
        if item["verdict"] == "confirmed" and impact is not None:
            confirmed.append((item, impact))
        elif item["verdict"] == "dismissed":
            dismissed.append(item)
        else:
            clarification_requests.append(item)

    confirmed.sort(key=lambda pair: (-pair[1], pair[0]["candidate_id"]))
    total_confirmed_impact = sum((impact for _, impact in confirmed), Decimal("0.00"))
    confirmed_items = [item for item, _ in confirmed]
    payload = {
        "disclaimer": DISCLAIMER,
        "summary": {
            "confirmed_discrepancy_count": len(confirmed_items),
            "total_confirmed_dollar_impact": _formatted_money(total_confirmed_impact),
        },
        "confirmed_discrepancies": confirmed_items,
        "dismissed_items": dismissed,
        "clarification_requests": clarification_requests,
    }
    return payload


def _write_report_artifact(user_id: str, payload: dict[str, Any]) -> Path:
    """Persist the machine-readable report payload for later draft-only context retrieval."""
    artifact = {"user_id": user_id, "report_payload": payload}
    fingerprint = hashlib.sha256(
        json.dumps(artifact, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    path = REPORTS_DIR / f"report_{fingerprint}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".partial")
    partial.write_text(json.dumps(artifact), encoding="utf-8")
    partial.replace(path)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verdicts", required=True)
    parser.add_argument("--user-id", required=True)
    arguments = parser.parse_args()
    try:
        payload = synthesize(_read_verdicts(arguments.verdicts))
        report_artifact = _write_report_artifact(arguments.user_id, payload)
    except (OSError, ValueError, json.JSONDecodeError):
        print(json.dumps({"status": "failed", "error_code": "synthesis_input_invalid"}))
        return 0
    print(
        json.dumps(
            {
                "status": "completed",
                "report": payload,
                "report_payload": payload,
                "report_artifact": str(report_artifact),
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
