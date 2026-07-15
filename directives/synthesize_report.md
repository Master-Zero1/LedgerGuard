# Synthesize Report

## Goal

Merge completed investigation verdicts into a plain-English, user-facing report ranked by deterministic dollar impact. Synthesis never re-investigates or upgrades unsupported claims.

## Inputs

- Confirmed, dismissed, and clarification-needed verdicts from the three independent investigations.
- Cited discrepancy records, confidence scores, calculation provenance, and user-scoped report preferences.

## Execution

Call `execution/synthesize_report.py` to validate evidence completeness, deduplicate verdict references, rank confirmed discrepancies by stored dollar impact, and render a structured report payload. The orchestration agent writes neutral explanatory prose from that payload only.

Do not rerun comparisons, infer missing facts, recompute amounts, generate a dispute email, send anything, or include raw document text.

## Outputs

- A report containing confirmed discrepancies, ranked dollar impact, confidence scores, concise evidence citations, dismissed items where useful, and clarification requests.
- The required disclaimer: “LedgerGuard provides informational analysis, not legal or financial advice.”
- A machine-readable report payload suitable for later, explicitly requested dispute drafting.

## Edge cases

- No confirmed discrepancies: state that no supported discrepancies were confirmed; do not imply clean books.
- Conflicting verdicts, duplicate findings, missing evidence, or missing impact: retain status and explain the limitation; do not merge into a stronger claim.
- Sensitive content: cite short clause fragments and page references only; never include full document text or PII beyond what the report requires.
