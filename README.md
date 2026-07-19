# LedgerGuard

LedgerGuard — reconciles invoices, contracts, and statements to find billing discrepancies, with evidence-backed verdicts and zero autonomous send capability.

## The problem

Invoices can disagree with contract terms, repeat charges, or reflect rate changes whose authorization is unclear. LedgerGuard extracts and normalizes document records, applies deterministic rules, and keeps the evidence used for each reported finding.

## Architecture

LedgerGuard separates instructions, orchestration, and deterministic execution:

```text
Directive (SOPs in directives/)
        -> Orchestration (Layer 2 agents in backend/agents/)
        -> Execution (deterministic scripts in execution/)
```

```text
Ingest -> Normalize -> Rules Engine -> Triage -> Investigation (parallel) -> Synthesis -> Dispute Draft
```

### Layer 2 agents

- `triage_agent.py` — routes flagged rule-engine discrepancies to the matching investigation type; it does not issue verdicts.
- `pricing_agent.py` — confirms or dismisses rate-violation candidates using cited contract and invoice evidence.
- `duplicate_agent.py` — confirms or dismisses duplicate-charge candidates using cited records.
- `contract_drift_agent.py` — determines whether a flagged price change is authorized by supporting amendment evidence.
- `synthesis_agent.py` — merges investigation verdicts into the report; it does not re-investigate.
- `dispute_agent.py` — drafts a dispute email for confirmed, evidenced discrepancies; it does not send email.

No agent computes dollar amounts. Discrepancy financial-impact calculations are deterministic `Decimal` arithmetic in `execution/rules_engine.py`; investigation agents use the stored rules-engine impact as provenance.

## How this was built with Codex

- The pipeline was implemented stage by stage and verified before advancing: generated PDFs were first ingested into raw-extraction artifacts, then normalized into schema records and clause-match candidates, then evaluated by the rules engine, agents, synthesis, dispute drafting, API, frontend, and PDF export.
- An edge-case test with three matching $100.00 charges exposed overlapping duplicate-pair handling that would have produced $300.00 of impact. The rules engine was changed to group one representative charge per source document, producing one $200.00 impact for the two excess charges.
- Negative contract-drift tests exposed missing amendment handling in `normalize_data.py`: an authorized $100.00 to $130.00 rate change needed the original agreement and dated, signed amendment as normalized supporting records. The authorized fixture now dismisses that $30.00 price-hike candidate; the otherwise identical fixture without supporting amendment evidence confirms it.

## What's actually verified

The following results were produced from the project fixtures and live API runs.

| Case | Verified result |
| --- | --- |
| Rate violation | An invoice billed **$125.00** against a **$100.00** contracted rate. The pipeline returned one confirmed `rate_violation` with **$25.00** impact. |
| Duplicate group | Three matching **$100.00** charges were grouped into one duplicate finding with **$200.00** impact: two excess charges, without creating overlapping duplicate findings. |
| Unauthorized contract drift | A monthly rate changed from **$100.00** to **$130.00** without a supporting amendment. The result was a confirmed `price_hike` with **$30.00** impact. |
| Authorized contract drift | The same **$100.00** to **$130.00** change, with a signed amendment dated before the invoice and referencing the original agreement, was dismissed. This verifies resistance to that false positive. |
| OCR, readable scan | The scanned clean invoice was extracted at **0.96** OCR confidence. |
| OCR, degraded scan | A deliberately degraded scan produced **0.39** OCR confidence and the `low_ocr_confidence_manual_review` warning rather than a guessed result. |
| Invalid PDFs | Corrupted and password-protected PDFs returned `422` with `invalid_pdf`; neither reached the pipeline or exposed an internal path. |
| Tax and partial payment lines | The tested invoice normalized four line items, including a **$20.00** sales-tax line and a **-$100.00** partial-payment line. The rules run returned zero flagged discrepancies and no warnings. |

### Live processing verification

`POST /analyze` was submitted with the rate-violation invoice and contract, then `GET /status/{job_id}` was polled once per second. The actual run reached `complete` at second **9**:

| Poll time | Observed stage or completed-stage state |
| --- | --- |
| 0-3 seconds | `ingesting` |
| 4 seconds | `normalizing`; ingestion completed |
| 5 seconds | `rules_engine`; normalization completed |
| 6-7 seconds | `investigating`; rules engine and triage completed |
| 8 seconds | `synthesizing`; investigation completed |
| 9 seconds | `complete`; ingesting, normalizing, rules engine, triage, investigating, and synthesizing completed |

The completed asynchronous report had the same public report shape and the same semantic report content as a separate synchronous `POST /upload` run of the same documents. Upload-specific record IDs and `report_id` values differ by design between separate uploads.

## Tech stack

### Backend and document processing

- Python
- FastAPI `0.139.0` and Uvicorn `0.51.0`
- `python-multipart` `0.0.32` for multipart uploads
- `pdfplumber` `0.11.10`, `pypdf` `6.14.2`, and `pypdfium2` `5.12.0` for PDF extraction, validation, and rendering
- Tesseract, invoked by `execution/ingest_documents.py` for image-only PDF OCR
- Pillow `12.3.0` for image handling
- ReportLab `5.0.0` for report-PDF export
- Python `Decimal` for deterministic discrepancy arithmetic

### Frontend

- Next.js `15.1.0`, React `19.0.0`, and TypeScript `5.7.2`
- Tailwind CSS `3.4.17`
- Local shadcn/ui-style `Card`, `Accordion`, and `Button` components in `frontend/components/ui/`, backed by Radix Accordion and Slot
- Lucide React icons

## Safety and non-negotiables

- No agent sends email. `dispute_agent.py` creates drafts only; the frontend exposes manual copy/send outside the application. A code search across the dispute path found no SMTP, `sendmail`, or `mailto` implementation.
- No agent computes financial impact. Investigation verdicts carry the deterministic rules-engine amount as `impact_provenance`; `rules_engine.py` performs the discrepancy amount calculations with `Decimal`.
- Uploaded document text is treated as untrusted data, never as instructions. The project instructions require extracted invoice, contract, and statement content to remain data and not alter tool use or output behavior.
- The report and exported PDF include: “LedgerGuard provides informational analysis, not legal or financial advice.”

## Setup and run locally

Run the API from the project root, not from inside `backend/`:

```bash
pip install -r requirements.txt
python -m uvicorn backend.api:app --reload
```

Run the frontend in a second terminal:

```bash
cd frontend
npm install
npm run dev
```

The frontend calls the API at `http://localhost:8000`.

## Project structure

```text
ledgerguard/
├── directives/          SOPs for ingest, normalization, rules, triage, investigations, synthesis, and dispute drafting
├── execution/           Deterministic Python scripts for extraction, normalization, matching, rules, and report preparation
├── backend/
│   ├── agents/          Layer 2 triage, investigation, synthesis, and dispute-draft orchestration
│   ├── api.py           FastAPI endpoints: synchronous upload, background analysis/status, drafting, and PDF export
│   ├── pipeline_runner.py  Ordered pipeline runner with injectable stage-status updates
│   ├── report_export.py    ReportLab PDF rendering from stored report payloads
│   ├── ingestion/       Backend ingestion package
│   ├── models/          Backend model package
│   └── rules_engine/    Backend rules-engine package
├── frontend/            Next.js upload, progress, report, and dispute-draft UI
├── test_fixtures/       Generated PDFs and synthetic input used for deterministic tests
├── scripts/             Fixture generation and synthetic-pipeline scripts
├── output/              Generated report artifacts from local verification
├── requirements.txt     Pinned Python dependencies
└── AGENTS.md            Layer boundaries and operating instructions
```

## Test fixtures

- `sample_contract_northstar_2026.pdf` — contract for the clean and rate-violation invoice cases.
- `clean_invoice_march_2026.pdf` — matches the sample contract; verified to produce zero confirmed and zero dismissed items.
- `rate_violation_invoice_march_2026.pdf` — bills managed storage at $125.00 rather than the $100.00 contract rate.
- `duplicate_charge_invoice_march_2026.pdf` and `duplicate_charge_statement_march_2026.pdf` — exact duplicate charge pair with matching date, amount, and description, without a narrated duplicate conclusion.
- `duplicate_group_statement_a_march_2026.pdf` and `duplicate_group_statement_b_march_2026.pdf` — extend the duplicate case to three matching $100.00 charges for grouped-impact testing.
- `contract_drift_original_agreement_2026.pdf`, `contract_drift_rate_schedule_revision_2_2026.pdf`, and `contract_drift_invoice_march_2026.pdf` — unauthorized $100.00 to $130.00 rate-change case.
- `contract_drift_authorized_original_agreement_2026.pdf`, `contract_drift_authorized_amendment_no_1_2026.pdf`, and `contract_drift_authorized_invoice_march_2026.pdf` — authorized variant proving a supported amendment is dismissed rather than falsely flagged.
- `scanned_clean_invoice.pdf` — image-only PDF used to test OCR extraction.
- `wording_variation_invoice_march_2026.pdf` — non-exact line-item wording used to test ambiguous clause-match handling.
- `tax_and_partial_payment_invoice_march_2026.pdf` — tax and negative partial-payment line-item parsing.
- `corrupted_pdf_fixture.pdf` — malformed-PDF rejection path.
- `password_protected_pdf_fixture.pdf` — encrypted-PDF rejection path.
- `synthetic_document_set.json` — structured input for the fixture-backed synthetic pipeline script.

---

<div align="center">

**Built by [master-zero1](https://github.com/master-zero1)**  
**YT-URL - (https://youtu.be/XlCnSVBCQj4)**  
**Built for OpenAI Build Week with Codex and GPT-5.6**
</div>
