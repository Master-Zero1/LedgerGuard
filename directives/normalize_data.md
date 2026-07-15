# Normalize Data

## Goal

Convert raw extraction artifacts into the fixed LedgerGuard schema and produce deterministic candidate links between invoice line items and contract clauses. No agent may invent fields or alter the schema.

## Inputs

- Completed or partial raw-extraction artifacts from ingestion.
- Existing user-scoped vendor aliases and normalized records, if available.

## Execution

Call `execution/normalize_data.py`. It must validate types and required fields, create schema-shaped records, retain source/page provenance, and produce clause-match candidates with matching metadata. Embeddings may assist candidate retrieval, but final stored values and identifiers must remain structured and traceable.

Do not calculate discrepancy impact or issue discrepancy verdicts in this stage.

## Outputs

- Validated `Vendor`, `Contract`, `ContractClause`, `Invoice`, and `InvoiceLineItem` records.
- Candidate line-item-to-clause links, each with match method, score, and evidence references.
- Validation warnings and records rejected for missing or ambiguous required data.

## Edge cases

- Missing vendor, invoice number, date, quantity, price, unit, or page reference: preserve the record where possible and emit a field-level warning; do not fabricate data.
- Multiple vendor aliases or multiple plausible clauses: retain all candidates and mark the link ambiguous.
- Currency, tax, unit, date, negative-credit, and rounding variations: normalize only under documented deterministic rules and retain original values.
- Partial extraction: normalize usable fields while carrying ingestion warnings forward.
