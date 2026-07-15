---
name: clause-matching
description: Use when matching an invoice line item to the correct contract clause. This is the hardest part of the reconciliation pipeline — do not re-derive an approach from scratch if this file has one.
---

# Clause Matching

## Current deterministic baseline

Normalize line-item and clause descriptions by lowercasing, removing punctuation, and collapsing whitespace. Confirm an exact normalized-description match as a candidate with `match_method: exact_normalized_description` and `match_score: 1.0`.

For non-exact descriptions, use deterministic string similarity only to retrieve candidates at a score of at least `0.6`; label them `normalized_description_similarity`. Mark candidates below `0.85` as ambiguous for review rather than treating them as confident links. Do not treat this retrieval score as a discrepancy verdict or calculate dollar impact.

Retain every plausible candidate. Also mark equal top-scoring candidates as ambiguous and preserve line-item/clause IDs, page references, and short description excerpts for each link. Route missing descriptions, units, or supporting page references to warnings rather than guessing.
