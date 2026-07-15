# Rules Engine

## Goal

Run exact, deterministic checks for duplicate charges, contract-rate mismatches, and arithmetic errors against normalized, user-scoped records. Dollar amounts must be computed only here, never by an agent.

## Inputs

- Normalized invoices, line items, contracts, clauses, and candidate clause links.
- Deterministic rule configuration, including approved tolerances and currency handling.

## Execution

Call `execution/rules_engine.py`. It must use decimal-safe arithmetic, preserve evidence citations, and produce only reproducible flagged discrepancies. It must not call an LLM.

## Outputs

- `Discrepancy` records with `status: flagged`, exact `dollar_impact`, confidence score, type, and cited line item/clause evidence.
- A run summary listing rules applied, records evaluated, and safe failure/warning codes.

## Edge cases

- Missing, ambiguous, expired, or overlapping contract terms: do not assert a rate violation; emit an unresolved candidate/warning.
- Partial payments, credits, taxes, discounts, quantity units, currency conversion, and approved tolerance boundaries: apply only configured rules and retain calculation inputs.
- Same invoice re-ingested or duplicate source rows: ensure idempotent processing.
- Arithmetic inconsistency with incomplete fields: flag only the check that can be proven from the available values.
