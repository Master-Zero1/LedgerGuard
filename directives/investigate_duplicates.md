# Investigate Duplicates

## Goal

Independently confirm or dismiss suspected duplicate charges across invoices, statements, and line items. This agent handles duplicates only.

## Inputs

- Duplicate-routed triage candidates.
- Cited normalized source line items and exact matching features from the rules engine.

## Execution

Call `execution/investigate_duplicates.py` to retrieve candidate records, deterministic match evidence, and the rules engine's stored impact provenance. The orchestration agent issues a verdict only from the returned evidence.

Do not determine contract rates, term drift, or payment status beyond what the cited records prove. Only `execution/rules_engine.py` calculates dollar impact.

## Outputs

- A per-candidate verdict: `confirmed`, `dismissed`, or `needs_clarification`.
- Evidence linking each cited line item, match criteria, duplicate grouping, exact impact provenance, and confidence score.

## Edge cases

- Legitimate recurring charges, installments, split shipments, credits/rebills, corrected invoices, tax-only lines, and partial payments: do not confirm without deterministic evidence of duplicate billing.
- Similar descriptions with different dates, quantities, units, currencies, or service periods: leave unresolved or dismiss with cited distinctions.
- More than two possible duplicates: preserve the full group and avoid double-counting impact.
