"""Normalize ingestion artifacts into LedgerGuard schema records and clause candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import uuid
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_EXTRACTION_DIR = PROJECT_ROOT / ".tmp" / "raw-extractions"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / ".tmp" / "normalized-records"
ID_NAMESPACE = uuid.UUID("dba49d3e-6d38-4b33-a3dc-c0e1fbe14790")
SIMILARITY_CANDIDATE_THRESHOLD = 0.6
SIMILARITY_REVIEW_THRESHOLD = 0.85


def _stable_id(record_type: str, *parts: str) -> str:
    """Create a deterministic, user-scoped identifier without leaking source text."""
    key = "|".join((record_type, *parts))
    return f"{record_type.lower()}_{uuid.uuid5(ID_NAMESPACE, key).hex}"


def _safe_error(code: str) -> dict[str, str]:
    return {"status": "failed", "error_code": code}


def _normalize_description(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.lower()).split())


def _parse_money(value: str) -> str | None:
    cleaned = value.replace("$", "").replace(",", "").strip()
    if not re.fullmatch(r"-?\d+(?:\.\d{1,2})?", cleaned):
        return None
    whole, _, decimal = cleaned.partition(".")
    return f"{whole}.{(decimal + '00')[:2]}"


def _parse_quantity(value: str) -> str | None:
    cleaned = value.replace(",", "").strip()
    if not re.fullmatch(r"-?\d+(?:\.\d+)?", cleaned):
        return None
    return cleaned


def _parse_date(value: str) -> str | None:
    for date_format in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(value.strip(), date_format).date().isoformat()
        except ValueError:
            continue
    return None


def _match_text(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
    return match.group(1).strip() if match else None


def _table_columns(rows: list[list[Any]]) -> tuple[dict[str, int], list[list[Any]]]:
    if not rows or not isinstance(rows[0], list):
        return {}, []
    headers = {
        _normalize_description(str(value)): index
        for index, value in enumerate(rows[0])
        if isinstance(value, str)
    }
    return headers, rows[1:]


def _artifact_tables(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    tables = artifact.get("tables")
    return tables if isinstance(tables, list) else []


def _text(artifact: dict[str, Any]) -> str:
    raw_text = artifact.get("raw_text")
    return raw_text if isinstance(raw_text, str) else ""


def _cell(row: list[Any], index: int | None) -> str:
    if index is None or index >= len(row) or row[index] is None:
        return ""
    return str(row[index]).strip()


def _append_warning(warnings: list[dict[str, str]], code: str, record: str) -> None:
    warnings.append({"code": code, "record": record})


def _normalize_contract(
    artifact: dict[str, Any], user_id: str, vendors: dict[str, dict[str, Any]], warnings: list[dict[str, str]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    source = artifact.get("source", {})
    text = _text(artifact)
    document_id = str(source.get("document_id", ""))
    vendor_name = _match_text(r"^Provider\s+(.+)$", text)
    agreement_id = _match_text(r"^Agreement ID\s+(.+)$", text)
    effective_range = _match_text(r"^Effective dates\s+(.+)$", text)
    if not vendor_name:
        _append_warning(warnings, "missing_vendor", document_id)
        return [], []
    vendor_key = _normalize_description(vendor_name)
    vendor = vendors.setdefault(
        vendor_key,
        {
            "id": _stable_id("Vendor", user_id, vendor_key),
            "name": vendor_name,
            "aliases": [],
        },
    )
    effective_date = expiry_date = None
    if effective_range:
        dates = re.match(r"(.+?)\s+through\s+(.+)$", effective_range)
        if dates:
            effective_date = _parse_date(dates.group(1))
            expiry_date = _parse_date(dates.group(2))
    if not agreement_id:
        _append_warning(warnings, "missing_contract_id", document_id)
        agreement_id = document_id
    contract = {
        "id": _stable_id("Contract", user_id, document_id, agreement_id),
        "vendor_id": vendor["id"],
        "agreement_reference": agreement_id,
        "effective_date": effective_date,
        "expiry_date": expiry_date,
        "source_file_id": document_id,
    }
    if not effective_date or not expiry_date:
        _append_warning(warnings, "missing_contract_effective_date", contract["id"])

    clauses: list[dict[str, Any]] = []
    for table in _artifact_tables(artifact):
        rows = table.get("rows")
        if not isinstance(rows, list):
            continue
        columns, data_rows = _table_columns(rows)
        required = {"clause", "service", "agreed rate", "unit"}
        if not required.issubset(columns):
            continue
        for row_number, row in enumerate(data_rows, start=1):
            if not isinstance(row, list):
                continue
            clause_ref = _cell(row, columns["clause"])
            description = _cell(row, columns["service"])
            price = _parse_money(_cell(row, columns["agreed rate"]))
            unit_value = _cell(row, columns["unit"])
            period = _cell(row, columns.get("effective period"))
            if not description or not price or not unit_value:
                _append_warning(warnings, "incomplete_contract_clause", f"{contract['id']}:{row_number}")
                continue
            normalized_unit = re.sub(r"^per\s+", "", unit_value, flags=re.IGNORECASE)
            clauses.append(
                {
                    "id": _stable_id("ContractClause", contract["id"], clause_ref or str(row_number)),
                    "contract_id": contract["id"],
                    "item_description": description,
                    "agreed_unit_price": price,
                    "unit": normalized_unit,
                    "terms_text": f"{description}: {price} {unit_value}. {period}".strip(),
                    "page_ref": str(table.get("page_ref", "")),
                }
            )
    if not clauses:
        _append_warning(warnings, "no_contract_clauses_extracted", contract["id"])
    return [contract], clauses


def _normalize_invoice(
    artifact: dict[str, Any], user_id: str, vendors: dict[str, dict[str, Any]], warnings: list[dict[str, str]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    source = artifact.get("source", {})
    text = _text(artifact)
    document_id = str(source.get("document_id", ""))
    vendor_name = _match_text(r"^Vendor\s+(.+)$", text)
    invoice_number = _match_text(r"^Invoice number\s+(.+)$", text)
    invoice_date = _parse_date(_match_text(r"^Issue date\s+(.+)$", text) or "")
    agreement_reference = _match_text(r"^Agreement ID\s+(.+)$", text)
    if not vendor_name:
        _append_warning(warnings, "missing_vendor", document_id)
        return [], []
    vendor_key = _normalize_description(vendor_name)
    vendor = vendors.setdefault(
        vendor_key,
        {
            "id": _stable_id("Vendor", user_id, vendor_key),
            "name": vendor_name,
            "aliases": [],
        },
    )
    if not invoice_number:
        _append_warning(warnings, "missing_invoice_number", document_id)
        invoice_number = document_id
    invoice = {
        "id": _stable_id("Invoice", user_id, document_id, invoice_number),
        "vendor_id": vendor["id"],
        "invoice_number": invoice_number,
        "date": invoice_date,
        "agreement_reference": agreement_reference,
        "source_file_id": document_id,
    }
    if not invoice_date:
        _append_warning(warnings, "missing_invoice_date", invoice["id"])

    line_items: list[dict[str, Any]] = []
    for table in _artifact_tables(artifact):
        rows = table.get("rows")
        if not isinstance(rows, list):
            continue
        columns, data_rows = _table_columns(rows)
        required = {"description", "quantity", "unit price", "line total"}
        if not required.issubset(columns):
            continue
        for row_number, row in enumerate(data_rows, start=1):
            if not isinstance(row, list):
                continue
            description = _cell(row, columns["description"])
            quantity = _parse_quantity(_cell(row, columns["quantity"]))
            unit_price = _parse_money(_cell(row, columns["unit price"]))
            total = _parse_money(_cell(row, columns["line total"]))
            if not description:
                continue  # Invoice-total rows are not line items.
            if not quantity or not unit_price or not total:
                _append_warning(warnings, "incomplete_invoice_line_item", f"{invoice['id']}:{row_number}")
                continue
            line_items.append(
                {
                    "id": _stable_id("InvoiceLineItem", invoice["id"], str(row_number), description),
                    "invoice_id": invoice["id"],
                    "description": description,
                    "quantity": quantity,
                    "unit_price": unit_price,
                    "total": total,
                    "page_ref": str(table.get("page_ref", "")),
                }
            )
    if not line_items:
        _append_warning(warnings, "no_invoice_line_items_extracted", invoice["id"])
    return [invoice], line_items


def _normalize_statement(
    artifact: dict[str, Any], user_id: str, vendors: dict[str, dict[str, Any]], warnings: list[dict[str, str]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Represent debit transactions using existing invoice and line-item schema records."""
    source = artifact.get("source", {})
    text = _text(artifact)
    document_id = str(source.get("document_id", ""))
    vendor_name = _match_text(r"^Vendor\s+(.+)$", text)
    statement_number = _match_text(r"^Statement number\s+(.+)$", text) or document_id
    agreement_reference = _match_text(r"^Agreement ID\s+(.+)$", text)
    if not vendor_name:
        _append_warning(warnings, "missing_vendor", document_id)
        return [], []
    vendor_key = _normalize_description(vendor_name)
    vendor = vendors.setdefault(
        vendor_key,
        {
            "id": _stable_id("Vendor", user_id, vendor_key),
            "name": vendor_name,
            "aliases": [],
        },
    )
    invoices: list[dict[str, Any]] = []
    line_items: list[dict[str, Any]] = []
    for table in _artifact_tables(artifact):
        rows = table.get("rows")
        if not isinstance(rows, list):
            continue
        columns, data_rows = _table_columns(rows)
        required = {"date", "reference", "description", "debit"}
        if not required.issubset(columns):
            continue
        for row_number, row in enumerate(data_rows, start=1):
            if not isinstance(row, list):
                continue
            transaction_date = _parse_date(_cell(row, columns["date"]))
            reference = _cell(row, columns["reference"])
            description = _cell(row, columns["description"])
            debit = _parse_money(_cell(row, columns["debit"]))
            if not debit or debit == "0.00":
                continue
            if not transaction_date or not description:
                _append_warning(warnings, "incomplete_statement_debit", f"{document_id}:{row_number}")
                continue
            invoice_number = f"{statement_number}:{reference or row_number}"
            invoice = {
                "id": _stable_id("Invoice", user_id, document_id, invoice_number),
                "vendor_id": vendor["id"],
                "invoice_number": invoice_number,
                "date": transaction_date,
                "agreement_reference": agreement_reference,
                "source_file_id": document_id,
            }
            invoices.append(invoice)
            line_items.append(
                {
                    "id": _stable_id("InvoiceLineItem", invoice["id"], "1", description),
                    "invoice_id": invoice["id"],
                    "description": description,
                    "quantity": "1",
                    "unit_price": debit,
                    "total": debit,
                    "page_ref": str(table.get("page_ref", "")),
                }
            )
    if not line_items:
        _append_warning(warnings, "no_statement_debits_extracted", document_id)
    return invoices, line_items


def _clause_candidates(
    line_items: list[dict[str, Any]],
    clauses: list[dict[str, Any]],
    invoices: list[dict[str, Any]],
    contracts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    invoices_by_id = {invoice["id"]: invoice for invoice in invoices if "id" in invoice}
    contracts_by_id = {contract["id"]: contract for contract in contracts if "id" in contract}
    candidates: list[dict[str, Any]] = []
    for item in line_items:
        invoice = invoices_by_id.get(item.get("invoice_id"))
        agreement_reference = invoice.get("agreement_reference") if invoice else None
        item_key = _normalize_description(item["description"])
        plausible: list[dict[str, Any]] = []
        for clause in clauses:
            contract = contracts_by_id.get(clause.get("contract_id"))
            if agreement_reference and (
                not contract or contract.get("agreement_reference") != agreement_reference
            ):
                continue
            clause_key = _normalize_description(clause["item_description"])
            score = SequenceMatcher(a=item_key, b=clause_key).ratio()
            if score < SIMILARITY_CANDIDATE_THRESHOLD:
                continue
            method = "exact_normalized_description" if item_key == clause_key else "normalized_description_similarity"
            plausible.append(
                {
                    "line_item_id": item["id"],
                    "clause_id": clause["id"],
                    "match_method": method,
                    "match_score": round(score, 4),
                    "evidence": [
                        {
                            "record_type": "InvoiceLineItem",
                            "record_id": item["id"],
                            "page_ref": item["page_ref"],
                            "excerpt": item["description"],
                        },
                        {
                            "record_type": "ContractClause",
                            "record_id": clause["id"],
                            "page_ref": clause["page_ref"],
                            "excerpt": clause["item_description"],
                        },
                    ],
                }
            )
        plausible.sort(key=lambda candidate: candidate["match_score"], reverse=True)
        for candidate in plausible:
            candidate["ambiguous"] = (
                candidate["match_method"] != "exact_normalized_description"
                and candidate["match_score"] < SIMILARITY_REVIEW_THRESHOLD
            ) or (
                len(plausible) > 1
                and candidate["match_score"] == plausible[0]["match_score"]
            )
            candidates.append(candidate)
    return candidates


def _read_artifact(path: Path) -> dict[str, Any]:
    resolved = path.resolve(strict=True)
    try:
        resolved.relative_to(RAW_EXTRACTION_DIR.resolve())
    except ValueError as error:
        raise ValueError("artifact_outside_raw_extractions") from error
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("invalid_artifact_payload")
    return payload


def normalize(artifact_paths: list[Path], user_id: str) -> dict[str, Any]:
    """Convert completed/partial ingestion artifacts into schema-shaped record collections."""
    warnings: list[dict[str, str]] = []
    rejected_records: list[dict[str, str]] = []
    vendors: dict[str, dict[str, Any]] = {}
    contracts: list[dict[str, Any]] = []
    clauses: list[dict[str, Any]] = []
    invoices: list[dict[str, Any]] = []
    line_items: list[dict[str, Any]] = []
    source_document_types: dict[str, str] = {}
    source_artifacts: dict[str, str] = {}

    for path in artifact_paths:
        artifact = _read_artifact(path)
        source = artifact.get("source", {})
        document_id = str(source.get("document_id", path.name))
        artifact_status = artifact.get("status")
        if artifact_status not in {"completed", "partial"}:
            rejected_records.append({"source_file_id": document_id, "reason": "ingestion_not_usable"})
            continue
        for warning in artifact.get("warnings", []):
            _append_warning(warnings, str(warning), document_id)
        document_type = source.get("document_type")
        source_document_types[document_id] = str(document_type)
        source_artifacts[document_id] = str(path.resolve())
        if document_type == "contract":
            normalized_contracts, normalized_clauses = _normalize_contract(artifact, user_id, vendors, warnings)
            contracts.extend(normalized_contracts)
            clauses.extend(normalized_clauses)
        elif document_type == "invoice":
            normalized_invoices, normalized_items = _normalize_invoice(artifact, user_id, vendors, warnings)
            invoices.extend(normalized_invoices)
            line_items.extend(normalized_items)
        elif document_type == "statement":
            normalized_invoices, normalized_items = _normalize_statement(artifact, user_id, vendors, warnings)
            invoices.extend(normalized_invoices)
            line_items.extend(normalized_items)
        else:
            rejected_records.append({"source_file_id": document_id, "reason": "unsupported_document_type"})

    candidates = _clause_candidates(line_items, clauses, invoices, contracts)
    return {
        "status": "partial" if warnings or rejected_records else "completed",
        "user_id": user_id,
        "vendors": list(vendors.values()),
        "contracts": contracts,
        "contract_clauses": clauses,
        "invoices": invoices,
        "invoice_line_items": line_items,
        "source_document_types": source_document_types,
        "source_artifacts": source_artifacts,
        "clause_match_candidates": candidates,
        "warnings": warnings,
        "rejected_records": rejected_records,
    }


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extraction-artifact", type=Path, action="append", required=True)
    parser.add_argument("--user-id", required=True)
    return parser.parse_args()


def main() -> int:
    arguments = _parse_arguments()
    output_path = DEFAULT_OUTPUT_DIR / f"normalized-{uuid.uuid4().hex}.json"
    try:
        normalized = normalize(arguments.extraction_artifact, arguments.user_id)
    except (OSError, ValueError, json.JSONDecodeError):
        print(json.dumps(_safe_error("normalization_input_invalid")))
        return 0
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(normalized, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"status": normalized["status"], "normalized_records": str(output_path)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
