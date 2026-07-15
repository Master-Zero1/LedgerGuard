"""Run deterministic LedgerGuard rate, duplicate, and arithmetic checks."""

from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
NORMALIZED_RECORDS_DIR = PROJECT_ROOT / ".tmp" / "normalized-records"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / ".tmp" / "rule-runs"
ID_NAMESPACE = uuid.UUID("6cd52dce-55b3-40be-8315-7640c6fd5f23")


def _stable_id(record_type: str, *parts: str) -> str:
    return f"{record_type.lower()}_{uuid.uuid5(ID_NAMESPACE, '|'.join((record_type, *parts))).hex}"


def _decimal(value: object) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01")))


def _normalize_description(value: str) -> str:
    return " ".join("".join(character if character.isalnum() else " " for character in value.lower()).split())


def _read_normalized_records(path: Path) -> dict[str, Any]:
    resolved = path.resolve(strict=True)
    try:
        resolved.relative_to(NORMALIZED_RECORDS_DIR.resolve())
    except ValueError as error:
        raise ValueError("records_outside_normalized_directory") from error
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("invalid_normalized_records")
    return payload


def _read_config(path: Path | None) -> dict[str, Decimal]:
    config = {"rate_tolerance": Decimal("0.00"), "duplicate_tolerance": Decimal("0.00")}
    if path is None:
        return config
    payload = json.loads(path.resolve(strict=True).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("invalid_rule_config")
    for key in config:
        if key in payload:
            parsed = _decimal(payload[key])
            if parsed is None or parsed < 0:
                raise ValueError("invalid_rule_tolerance")
            config[key] = parsed
    return config


def _item_index(records: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    invoices = {record["id"]: record for record in records.get("invoices", []) if isinstance(record, dict) and "id" in record}
    items = {record["id"]: record for record in records.get("invoice_line_items", []) if isinstance(record, dict) and "id" in record}
    return invoices, items


def _rate_discrepancies(records: dict[str, Any], tolerance: Decimal, warnings: list[dict[str, str]]) -> list[dict[str, Any]]:
    invoices, items = _item_index(records)
    clauses = {record["id"]: record for record in records.get("contract_clauses", []) if isinstance(record, dict) and "id" in record}
    contracts = {record["id"]: record for record in records.get("contracts", []) if isinstance(record, dict) and "id" in record}
    source_types = records.get("source_document_types", {})
    discrepancies: list[dict[str, Any]] = []
    for candidate in records.get("clause_match_candidates", []):
        if not isinstance(candidate, dict):
            continue

        if candidate.get("ambiguous"):
            warnings.append(
                {
                    "code": "ambiguous_clause_match",
                    "line_item_id": str(candidate.get("line_item_id", "")),
                }
            )
            continue
        item = items.get(candidate.get("line_item_id"))
        clause = clauses.get(candidate.get("clause_id"))
        if not item or not clause:
            continue
        invoice = invoices.get(item.get("invoice_id"))
        if not invoice or source_types.get(invoice.get("source_file_id")) != "invoice":
            continue
        contract = contracts.get(clause.get("contract_id"))
        invoice_date = invoice.get("date")
        if not contract or not invoice_date or not contract.get("effective_date") or not contract.get("expiry_date"):
            warnings.append({"code": "unresolved_rate_term", "line_item_id": item["id"]})
            continue
        if not (contract["effective_date"] <= invoice_date <= contract["expiry_date"]):
            warnings.append({"code": "contract_not_effective", "line_item_id": item["id"]})
            continue
        unit_price = _decimal(item.get("unit_price"))
        agreed_price = _decimal(clause.get("agreed_unit_price"))
        quantity = _decimal(item.get("quantity"))
        if unit_price is None or agreed_price is None or quantity is None:
            warnings.append({"code": "incomplete_rate_inputs", "line_item_id": item["id"]})
            continue
        impact = (unit_price - agreed_price) * quantity
        if impact <= tolerance:
            continue
        discrepancy_id = _stable_id("Discrepancy", "rate_violation", item["id"], clause["id"])
        discrepancies.append(
            {
                "id": discrepancy_id,
                "type": "rate_violation",
                "line_item_id": item["id"],
                "clause_id": clause["id"],
                "dollar_impact": _money(impact),
                "confidence_score": 1.0,
                "evidence": [
                    {
                        "record_type": "InvoiceLineItem",
                        "record_id": item["id"],
                        "page_ref": item["page_ref"],
                        "excerpt": f"Billed unit price: {_money(unit_price)}; quantity: {item['quantity']}.",
                    },
                    {
                        "record_type": "ContractClause",
                        "record_id": clause["id"],
                        "page_ref": clause["page_ref"],
                        "excerpt": f"Agreed unit price: {_money(agreed_price)} per {clause['unit']}.",
                    },
                ],
                "status": "flagged",
            }
        )
    return discrepancies


def _price_hike_discrepancies(
    records: dict[str, Any], warnings: list[dict[str, str]]
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Flag deterministic, chronological price increases without deciding whether they were authorized."""
    invoices, items = _item_index(records)
    contracts = {
        record["id"]
        : record
        for record in records.get("contracts", [])
        if isinstance(record, dict) and record.get("id")
    }
    source_types = records.get("source_document_types", {})
    source_artifacts = records.get("source_artifacts", {})
    versions_by_term: dict[
        tuple[str, str, str], list[tuple[dict[str, Any], dict[str, Any]]]
    ] = defaultdict(list)
    for clause in records.get("contract_clauses", []):
        if not isinstance(clause, dict):
            continue
        contract = contracts.get(clause.get("contract_id"))
        if not contract or not contract.get("effective_date"):
            continue
        key = (
            str(contract.get("vendor_id", "")),
            str(contract.get("agreement_reference", contract["id"])),
            _normalize_description(str(clause.get("item_description", ""))),
            str(clause.get("unit", "")),
        )
        if key[1]:
            versions_by_term[key].append((contract, clause))

    discrepancies: list[dict[str, Any]] = []
    contexts: dict[str, dict[str, Any]] = {}
    emitted: set[tuple[str, str]] = set()
    for (vendor_id, agreement_reference, description, unit), versions in versions_by_term.items():
        versions.sort(key=lambda version: str(version[0]["effective_date"]))
        for old_contract, old_clause in versions:
            old_unit_price = _decimal(old_clause.get("agreed_unit_price"))
            if old_unit_price is None:
                continue
            for new_contract, new_clause in versions:
                if old_contract["id"] == new_contract["id"]:
                    continue
                if str(old_contract["effective_date"]) >= str(new_contract["effective_date"]):
                    continue
                new_unit_price = _decimal(new_clause.get("agreed_unit_price"))
                if new_unit_price is None or new_unit_price <= old_unit_price:
                    continue
                for item in items.values():
                    if _normalize_description(str(item.get("description", ""))) != description:
                        continue
                    invoice = invoices.get(item.get("invoice_id"))
                    if not invoice or invoice.get("vendor_id") != vendor_id:
                        continue
                    if invoice.get("agreement_reference") != agreement_reference:
                        continue
                    if source_types.get(invoice.get("source_file_id")) != "invoice":
                        continue
                    invoice_date = invoice.get("date")
                    if not isinstance(invoice_date, str) or invoice_date < str(new_contract["effective_date"]):
                        continue
                    if new_contract.get("expiry_date") and invoice_date > str(new_contract["expiry_date"]):
                        continue
                    billed_unit_price = _decimal(item.get("unit_price"))
                    quantity = _decimal(item.get("quantity"))
                    if billed_unit_price is None or quantity is None:
                        warnings.append({"code": "incomplete_price_hike_inputs", "line_item_id": item["id"]})
                        continue
                    if billed_unit_price != new_unit_price:
                        warnings.append({"code": "billed_rate_differs_from_new_term", "line_item_id": item["id"]})
                        continue
                    impact = (new_unit_price - old_unit_price) * quantity
                    if impact <= 0:
                        continue
                    dedupe_key = (item["id"], new_clause["id"])
                    if dedupe_key in emitted:
                        continue
                    emitted.add(dedupe_key)
                    discrepancy_id = _stable_id(
                        "Discrepancy", "price_hike", item["id"], old_clause["id"], new_clause["id"]
                    )
                    discrepancy = {
                        "id": discrepancy_id,
                        "type": "price_hike",
                        "line_item_id": item["id"],
                        "clause_id": new_clause["id"],
                        "dollar_impact": _money(impact),
                        "confidence_score": 0.8,
                        "evidence": [
                            {
                                "record_type": "InvoiceLineItem",
                                "record_id": item["id"],
                                "page_ref": item["page_ref"],
                                "excerpt": f"Billed unit price: {_money(billed_unit_price)}; quantity: {item['quantity']}.",
                            },
                            {
                                "record_type": "ContractClause",
                                "record_id": old_clause["id"],
                                "page_ref": old_clause["page_ref"],
                                "excerpt": f"Earlier agreed unit price: {_money(old_unit_price)} per {unit}.",
                            },
                            {
                                "record_type": "ContractClause",
                                "record_id": new_clause["id"],
                                "page_ref": new_clause["page_ref"],
                                "excerpt": f"Later recorded unit price: {_money(new_unit_price)} per {unit}.",
                            },
                        ],
                        "status": "flagged",
                    }
                    discrepancies.append(discrepancy)
                    contexts[discrepancy_id] = {
                        "candidate_id": discrepancy_id,
                        "type": "price_hike",
                        "line_item_id": item["id"],
                        "dollar_impact": discrepancy["dollar_impact"],
                        "old_clause": old_clause,
                        "new_clause": new_clause,
                        "old_contract": old_contract,
                        "new_contract": new_contract,
                        "invoice": invoice,
                        "old_source_artifact": source_artifacts.get(old_contract.get("source_file_id")),
                        "new_source_artifact": source_artifacts.get(new_contract.get("source_file_id")),
                    }
    return discrepancies, contexts


def _duplicate_discrepancies(records: dict[str, Any], tolerance: Decimal, warnings: list[dict[str, str]]) -> list[dict[str, Any]]:
    invoices, items = _item_index(records)
    groups: dict[tuple[str, str, str, str, Decimal], list[dict[str, Any]]] = defaultdict(list)
    for item in items.values():
        invoice = invoices.get(item.get("invoice_id"))
        total = _decimal(item.get("total"))
        if not invoice or total is None or total <= tolerance or not invoice.get("date"):
            continue
        key = (
            invoice.get("vendor_id", ""),
            str(invoice.get("agreement_reference", "")),
            invoice["date"],
            _normalize_description(item.get("description", "")),
            total,
        )
        if key[3]:
            groups[key].append(item)
    discrepancies: list[dict[str, Any]] = []
    for (_, _, transaction_date, description, total), grouped_items in groups.items():
        grouped_items.sort(key=lambda item: item["id"])
        for earlier, later in zip(grouped_items, grouped_items[1:]):
            earlier_invoice = invoices[earlier["invoice_id"]]
            later_invoice = invoices[later["invoice_id"]]
            if earlier_invoice["source_file_id"] == later_invoice["source_file_id"]:
                continue
            discrepancy_id = _stable_id("Discrepancy", "duplicate", earlier["id"], later["id"])
            discrepancies.append(
                {
                    "id": discrepancy_id,
                    "type": "duplicate",
                    "line_item_id": later["id"],
                    "clause_id": None,
                    "dollar_impact": _money(total),
                    "confidence_score": 1.0,
                    "evidence": [
                        {
                            "record_type": "InvoiceLineItem",
                            "record_id": earlier["id"],
                            "page_ref": earlier["page_ref"],
                            "excerpt": f"{earlier['description']}; date: {transaction_date}; total: {_money(total)}.",
                        },
                        {
                            "record_type": "InvoiceLineItem",
                            "record_id": later["id"],
                            "page_ref": later["page_ref"],
                            "excerpt": f"{later['description']}; date: {transaction_date}; total: {_money(total)}.",
                        },
                    ],
                    "status": "flagged",
                }
            )
    return discrepancies


def _arithmetic_discrepancies(records: dict[str, Any], warnings: list[dict[str, str]]) -> list[dict[str, Any]]:
    discrepancies: list[dict[str, Any]] = []
    for item in records.get("invoice_line_items", []):
        if not isinstance(item, dict):
            continue
        quantity = _decimal(item.get("quantity"))
        unit_price = _decimal(item.get("unit_price"))
        total = _decimal(item.get("total"))
        if quantity is None or unit_price is None or total is None:
            warnings.append({"code": "incomplete_arithmetic_inputs", "line_item_id": str(item.get("id", ""))})
            continue
        expected = quantity * unit_price
        impact = abs(total - expected)
        if impact == 0:
            continue
        discrepancies.append(
            {
                "id": _stable_id("Discrepancy", "arithmetic_error", item["id"]),
                "type": "other",
                "line_item_id": item["id"],
                "clause_id": None,
                "dollar_impact": _money(impact),
                "confidence_score": 1.0,
                "evidence": [
                    {
                        "record_type": "InvoiceLineItem",
                        "record_id": item["id"],
                        "page_ref": item["page_ref"],
                        "excerpt": f"Quantity × unit price: {_money(expected)}; billed total: {_money(total)}.",
                    }
                ],
                "status": "flagged",
            }
        )
    return discrepancies


def run_rules(records: dict[str, Any], config: dict[str, Decimal]) -> dict[str, Any]:
    """Produce reproducible flagged discrepancies; do not make model calls or judgments."""
    warnings: list[dict[str, str]] = []
    price_hikes, contract_drift_contexts = _price_hike_discrepancies(records, warnings)
    discrepancies = [
        *_rate_discrepancies(records, config["rate_tolerance"], warnings),
        *price_hikes,
        *_duplicate_discrepancies(records, config["duplicate_tolerance"], warnings),
        *_arithmetic_discrepancies(records, warnings),
    ]
    discrepancies.sort(key=lambda discrepancy: (discrepancy["type"], discrepancy["id"]))
    return {
        "status": "completed",
        "discrepancies": discrepancies,
        "contract_drift_contexts": contract_drift_contexts,
        "summary": {
            "rules_applied": ["rate_violation", "price_hike", "duplicate", "arithmetic_error"],
            "records_evaluated": {
                "invoices": len(records.get("invoices", [])),
                "invoice_line_items": len(records.get("invoice_line_items", [])),
                "contract_clauses": len(records.get("contract_clauses", [])),
            },
            "flagged_discrepancies": len(discrepancies),
            "warnings": warnings,
        },
    }


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--normalized-records", type=Path, required=True)
    parser.add_argument("--rule-config", type=Path)
    return parser.parse_args()


def main() -> int:
    arguments = _parse_arguments()
    try:
        result = run_rules(_read_normalized_records(arguments.normalized_records), _read_config(arguments.rule_config))
    except (OSError, ValueError, json.JSONDecodeError):
        print(json.dumps({"status": "failed", "error_code": "rules_input_invalid"}))
        return 0
    result["provenance"] = {
        "normalized_records": str(arguments.normalized_records.resolve())
    }
    run_id = _stable_id("RuleRun", hashlib.sha256(arguments.normalized_records.read_bytes()).hexdigest())
    output_path = DEFAULT_OUTPUT_DIR / f"{run_id}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"status": result["status"], "rule_run_id": run_id, "rule_run": str(output_path)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
