"""Retrieve minimal, confirmed report evidence for a draft-only dispute context."""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = PROJECT_ROOT / ".tmp" / "reports"
DRAFT_NAMESPACE = uuid.UUID("b3c2f7be-c449-4d55-9d9f-0e3ef974ce6e")
DISCREPANCY_ID_PATTERN = re.compile(r"discrepancy_[0-9a-f]{32}")


def _read_report(path: Path, user_id: str) -> dict[str, Any]:
    resolved = path.resolve(strict=True)
    try:
        resolved.relative_to(REPORTS_DIR.resolve())
    except ValueError as error:
        raise ValueError("report_outside_reports_directory") from error
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("user_id") != user_id:
        raise ValueError("report_user_mismatch")
    report = payload.get("report_payload")
    if not isinstance(report, dict):
        raise ValueError("invalid_report_payload")
    return report


def _confirmed_item(report: dict[str, Any], discrepancy_id: str) -> dict[str, Any] | None:
    confirmed = report.get("confirmed_discrepancies", [])
    if not isinstance(confirmed, list):
        return None
    for item in confirmed:
        if isinstance(item, dict) and item.get("candidate_id") == discrepancy_id:
            return item
    return None


def _report_for_discrepancy(
    discrepancy_id: str, user_id: str, report_artifact: str | None
) -> dict[str, Any]:
    if report_artifact:
        report = _read_report(Path(report_artifact), user_id)
        if _confirmed_item(report, discrepancy_id) is None:
            raise ValueError("discrepancy_not_confirmed")
        return report
    for path in sorted(REPORTS_DIR.glob("report_*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            report = _read_report(path, user_id)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if _confirmed_item(report, discrepancy_id) is not None:
            return report
    raise ValueError("confirmed_discrepancy_not_found")


def prepare(discrepancy_id: str, user_id: str, report_artifact: str | None) -> dict[str, Any]:
    """Return stored evidence only; drafting and sending are deliberately out of scope."""
    if not DISCREPANCY_ID_PATTERN.fullmatch(discrepancy_id):
        raise ValueError("invalid_discrepancy_id")
    report = _report_for_discrepancy(discrepancy_id, user_id, report_artifact)
    item = _confirmed_item(report, discrepancy_id)
    if item is None:
        raise ValueError("discrepancy_not_confirmed")
    evidence = item.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        raise ValueError("confirmed_discrepancy_missing_evidence")
    return {
        "status": "confirmed",
        "draft_id": "disputedraft_" + uuid.uuid5(DRAFT_NAMESPACE, f"{user_id}|{discrepancy_id}").hex,
        "discrepancy_id": discrepancy_id,
        "discrepancy_type": item.get("discrepancy_type"),
        "dollar_impact": item.get("dollar_impact"),
        "confidence_score": item.get("confidence_score"),
        "evidence": evidence,
        "impact_provenance": item.get("impact_provenance"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--discrepancy-id", required=True)
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--report-artifact")
    arguments = parser.parse_args()
    try:
        context = prepare(arguments.discrepancy_id, arguments.user_id, arguments.report_artifact)
    except (OSError, ValueError, json.JSONDecodeError):
        print(json.dumps({"status": "unavailable", "error_code": "confirmed_discrepancy_not_available"}))
        return 0
    print(json.dumps(context))
    return 0


if __name__ == "__main__":
    sys.exit(main())
