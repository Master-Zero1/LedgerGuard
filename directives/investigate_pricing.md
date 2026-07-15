# Investigate Pricing

## Goal

Independently confirm or dismiss suspected contract-rate violations by comparing an invoice line item to the applicable contract clause and terms. This agent handles pricing only.

## Inputs

- Pricing-routed triage candidates.
- Cited normalized invoice line item, candidate contract clause(s), and rule-engine calculation data.

## Execution

Call `execution/investigate_pricing.py` to retrieve the applicable terms and the rules engine's stored comparison provenance. The orchestration agent evaluates the returned evidence and records a `confirmed` or `dismissed` pricing verdict only when supported.

Do not investigate duplicates or contract drift, alter underlying data, or calculate amounts. Only `execution/rules_engine.py` calculates dollar impact.

## Outputs

- A per-candidate verdict: `confirmed`, `dismissed`, or `needs_clarification`.
- Exact evidence references, short clause fragments, calculation provenance, confidence score, and rationale.

## Edge cases

- Expired, future, overlapping, amended, tiered, minimum-commitment, or volume-based clauses: use only demonstrably applicable terms; otherwise require clarification.
- Unit, quantity, tax, discount, currency, rounding, or service-period mismatch: normalize through the execution result or leave unresolved.
- Missing clause/page evidence or ambiguous clause match: never confirm.
