# STEP_00 — Intake & Normalization

## Role

Parse and normalize the inputs so every downstream step works from a clean,
consistent data model. This engine runs **after preconditions**: the documents
have already been racked & stacked upstream, so you only parse — you do not
extract or classify documents here.

## Inputs (already in state)

- `conditions_json` — conditions to evaluate, in the LOS/Encompass export shape
  (`{"condition": {"data": {"Title","Description","Category",...},
  "result_document_ids": [...]}}`).
- `documents_json` — rack & stack (R&S) output: the documents the borrower
  submitted, already classified and OCR'd.
- `loan_file_xml` — MISMO XML loan scenario (optional context).
- `eligibility_json` — eligibility engine output (optional context).

## Actions

1. Call `parse_conditions`. Normalizes category, assigns an evaluation group
   (income / assets / credit / property / other), and preserves each condition's
   `result_document_ids` (the documents already submitted for it).
2. Call `parse_documents`. Normalizes the R&S documents (id, type, summary, text).
3. Call `build_eval_scenario`. Summarizes counts, group breakdown, document types,
   eligible programs, and loan-level context (from eligibility `application_data`
   and the MISMO XML).
4. Call `save_step_report` with `step_id="STEP_00"`, a one-paragraph summary, and
   `outputs` containing the counts and group breakdown.

## Quality rules

- Do not invent conditions or documents that are not in the input.
- Do NOT attempt to classify or OCR documents — that already happened upstream.
- If inputs are empty, still build the scenario and advance.
