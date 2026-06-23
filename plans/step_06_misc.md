# STEP_06 — Misc & Other Condition Evaluation

## Role

Evaluate every remaining condition: **Misc** and any **other** category that did not
fall into income, assets, credit, or property.

## Actions

1. Call `get_conditions_to_evaluate` with `category="other"`. Each candidate
   document carries its `document_type`, `extracted_fields`, and an `ocr_preview`;
   call `get_document_ocr(evidence_id, full=True)` when you need the full OCR.
2. If `condition_count` is 0, call `save_step_report` and advance.
3. If a condition is ambiguous, you may call `load_guideline_sections` (e.g.
   `COMPLIANCE`, `BORROWER ELIGIBILITY`, `GENERAL UNDERWRITING REQUIREMENTS`).
4. Reason over the documents and produce one evaluation per condition; record any
   sections you relied on in `guideline_refs`.
5. Call `store_other_evaluations`.
6. Call `save_step_report` for `STEP_06`. This is the last evaluation step.

## Guidelines (reference)

Guidelines are a reference to clarify acceptance criteria, never a source of new
requirements — the condition text is primary. Relevant sections: `COMPLIANCE`,
`BORROWER ELIGIBILITY`, `GENERAL UNDERWRITING REQUIREMENTS`.

## What this evidence typically proves

- 1008 / 1003 (loan transmittal / application) → loan structure change requests
  ("upload 1008/1003 showing the requesting terms").
- Disclosures, authorizations, and other compliance/administrative items.

## Evaluation rules

- Match the document to the exact item requested.
- **Partially Fulfilled** when a document is present but incomplete.
- **Unfulfilled** when nothing relevant was submitted.
- **Needs Review** when the extracted text is unclear or is the wrong document type.
- Note: some Misc items may already be marked Reviewed upstream — still evaluate
  whether the submitted document satisfies the ask.
- Use the same output schema as STEP_02.
