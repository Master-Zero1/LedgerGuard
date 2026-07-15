"""Run the fixture-backed LedgerGuard pipeline and print its final report payload."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "test_fixtures" / "synthetic_document_set.json"
sys.path.insert(0, str(ROOT))

from backend.pipeline_runner import run_document_set  # noqa: E402


def load_fixture() -> dict[str, Any]:
    """Load the disposable synthetic document set."""
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def fixture_executor(fixture: dict[str, Any]):
    """Return deterministic fixture responses for the pipeline's execution boundary."""
    discrepancies = {
        item["candidate_id"]: item for item in fixture["expected_discrepancies"]
    }

    def execute(script: str, arguments: list[str]) -> dict[str, Any]:
        if script == "ingest_documents.py":
            return {"extraction_artifact": str(FIXTURE_PATH)}
        if script == "normalize_data.py":
            return {"normalized_records": str(FIXTURE_PATH)}
        if script == "rules_engine.py":
            return {"rule_run_id": "synthetic-rule-run"}
        if script == "prepare_triage_candidates.py":
            return {"candidates": list(discrepancies.values())}
        if script == "investigate_pricing.py":
            item = discrepancies["rate-violation-storage"]
            return {
                "supports_rate_violation": True,
                "evidence": item["evidence"],
                "calculation_provenance": {
                    "rules_engine_dollar_impact": item["dollar_impact"]
                },
                "confidence_score": item["confidence_score"],
                "rationale": "The cited storage clause applies to the invoice date."
            }
        if script == "investigate_duplicates.py":
            item = discrepancies["duplicate-support"]
            return {
                "supports_duplicate": True,
                "line_items": item["evidence"],
                "match_criteria": "same description, quantity, unit price, and total",
                "duplicate_group": ["line-support-1", "line-support-duplicate"],
                "calculation_provenance": {
                    "rules_engine_dollar_impact": item["dollar_impact"]
                },
                "confidence_score": item["confidence_score"]
            }
        if script == "investigate_contract_drift.py":
            raise AssertionError("The fixture contains no contract-drift candidate.")
        if script == "synthesize_report.py":
            investigations = json.loads(
                Path(arguments[1]).read_text(encoding="utf-8")
            )
            confirmed = [
                item for item in investigations if item["verdict"]["verdict"] == "confirmed"
            ]
            report_payload = {
                "confirmed_discrepancies": [
                    {
                        "candidate_id": item["candidate_id"],
                        "investigation_type": item["investigation_type"],
                        "verdict": item["verdict"]["verdict"],
                    }
                    for item in confirmed
                ],
                "fixture_expected_impacts": {
                    item["candidate_id"]: item["dollar_impact"]
                    for item in discrepancies.values()
                },
            }
            return {"report": report_payload, "report_payload": report_payload}
        raise AssertionError(f"Unexpected execution script: {script}")

    return execute


def main() -> None:
    fixture = load_fixture()
    result = run_document_set(
        document_id=fixture["invoice"]["id"],
        source_path=fixture["invoice"]["source_file_id"],
        document_type="invoice",
        user_id=fixture["user_id"],
        rule_config="synthetic-fixture",
        executor=fixture_executor(fixture),
    )
    print(json.dumps(result["synthesis"]["report_payload"], indent=2))


if __name__ == "__main__":
    main()
