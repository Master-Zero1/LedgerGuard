# Investigate Contract Drift

## Goal

Independently confirm or dismiss suspected unauthorized changes between applicable contract terms and billed terms. This agent handles contract drift only.

## Inputs

- Contract-drift-routed triage candidates.
- Cited normalized clauses, amendments/renewals when available, invoice line items, and rule-engine evidence.

## Execution

Call `execution/investigate_contract_drift.py` to retrieve chronological terms, deterministic field-level differences, and any rules engine impact provenance. The orchestration agent evaluates applicability and records a verdict only with cited evidence.

Do not decide duplicate billing or ordinary rate violations outside a demonstrated term change. Only `execution/rules_engine.py` calculates dollar impact.

## Outputs

- A per-candidate verdict: `confirmed`, `dismissed`, or `needs_clarification`.
- Cited old/new terms, effective-date applicability, field-level changes, any exact impact provenance, and confidence score.

## Edge cases

- Authorized amendments, renewals, notice-based escalators, index-linked increases, negotiated exceptions, and retroactive credits: do not call them unauthorized without supporting terms.
- Missing effective dates, amendment pages, or an unambiguous baseline clause: require clarification.
- Clauses that change non-price terms only: retain evidence but do not claim a monetary impact unless deterministically computable.
