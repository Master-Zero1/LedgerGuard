---
name: discrepancy-evidence-format
description: The exact output schema every investigation agent (pricing, duplicate, contract-drift) must return. Synthesis Agent depends on this being consistent.
---

# Discrepancy Evidence Format

Every investigation agent returns exactly this shape:

```json
{
  "discrepancy_type": "duplicate | rate_violation | price_hike | other",
  "line_item_id": "string",
  "clause_id": "string | null",
  "dollar_impact": 0.00,
  "confidence_score": 0.0,
  "evidence": [
    "short factual statement citing the specific line item and clause"
  ],
  "verdict": "confirmed | dismissed | needs_clarification"
}
```

Rules:
- `evidence` entries must cite specific data (line item ID, clause ID, amounts), never vague claims
- `confidence_score` below 0.6 → Synthesis Agent shows it but flags as low-confidence, never hides it
- No agent may skip `evidence` even for a `confirmed` verdict
