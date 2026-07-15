# Draft Dispute

## Goal

Draft, but never send, one neutral dispute email for each confirmed discrepancy using only cited evidence and stored deterministic calculations.

## Inputs

- A confirmed discrepancy, its short evidence citations, confidence score, and calculation provenance.
- User-approved sender and recipient context, when available.

## Execution

Call `execution/prepare_dispute_context.py` to validate confirmed status and retrieve the minimal, cited context. The orchestration agent drafts the email from that context only. It must never send an email or modify a payment.

## Outputs

- A `DisputeDraft` with `id`, `discrepancy_id`, `subject`, `body`, and `status: draft`.
- A safe failure or clarification result when the discrepancy is not confirmed or evidence is incomplete.

## Edge cases

- Missing recipient, supporting evidence, or exact discrepancy ID: return clarification-needed; do not draft speculative claims.
- Multiple confirmed discrepancies: create one independent draft per discrepancy.
- Never include full source documents, unsupported conclusions, or legal/financial advice.
