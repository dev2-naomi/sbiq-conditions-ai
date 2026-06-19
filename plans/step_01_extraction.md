# STEP_01 — Document Extraction & Classification

## Role

Ensure every evidence document has a `detected_document_type` and a short
`document_summary` so candidate matching and evaluation can reason over it. This
is the "rack & stack" step.

## Actions

1. Call `get_evidence_for_extraction`. It returns each document with a
   `needs_extraction` flag and a `text_preview`.
2. For every document where `needs_extraction` is true, read its `text_preview`
   and determine:
   - `detected_document_type` — the mortgage document type (e.g., Paystub, W-2,
     Bank Statement, Appraisal Report, Title Commitment, Closing Disclosure,
     Homeowners Insurance Declaration, Driver License, Letter of Explanation).
   - `document_summary` — a 1–2 sentence summary of what the document shows.
3. Call `store_evidence_classifications` with a list of
   `{evidence_id, detected_document_type, document_summary}` — include only the
   documents you classified.
4. Call `save_step_report` for `STEP_01`.

## Quality rules

- If all documents are already classified, you may call
  `store_evidence_classifications` with an empty list (or skip straight to
  `save_step_report`).
- Be specific with document types — downstream matching keys off them.
