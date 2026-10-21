# STEP_00 — Intake & Normalization

## Role

Parse and normalize the inputs so every downstream step works from a clean,
consistent data model. The documents have already been racked & stacked (and OCR'd)
upstream, so you only parse — you do not extract or classify documents here.

## Inputs (already in state)

- `conditions_json` — conditions to evaluate, in the Encompass export shape
  (`{"condition": {"data": {"Title","Description","Category",...},
  "result_document_ids": [...]}}`). Conditions are typed by underwriters (mostly
  free-text) plus some default/automated conditions.
- `documents_json` — rack & stack (R&S) manifest: the documents the borrower
  submitted, each classified into a `category` (type) and indexed into structured
  extracted fields under `metadata`, plus per-document OCR (referenced under the
  manifest's `artifacts`, assumed dereferenced/inlined and split into pages here).
- `loan_file_xml` — loan scenario. JSON object (or a JSON string of that object).
  These keys are required and always populated: `FicoScore`, `LTV`, `CLTV`, `DTI`,
  `LoanAmount`, `PropertyAddress`, `LoanNumber`, `PropertyValue`, `PropertyType`,
  `Occupancy`, `LoanPurpose`, `Incomes`, `Channel`, `Citizenship`, `State`,
  `County`, `LoanType`.
  `Incomes` is 1–3 rows. The required row is the primary borrower's primary
  income (`income_tier` `"Primary"` and `is_primary_borrower` true). Extra rows
  are that borrower's secondary income and/or the co-borrower's income.
  `ReservesMonths` may be omitted. A legacy MISMO XML string is still accepted.
- `eligibility_json` — eligibility engine output (optional). Used for
  `eligible_programs` and as a fallback when a loan field is absent.
- `borrower` / `coborrower` — the loan's party identities (optional; dict
  `{first_name, last_name}` or a name string). When `coborrower` is empty/absent the
  loan is single-party.

## Actions

1. Call `parse_conditions`. Normalizes category, assigns an evaluation group
   (income / assets / credit / property / other), and preserves each condition's
   `result_document_ids` (the documents already submitted for it).
2. Call `parse_documents`. Normalizes the R&S documents (id, type from `category`,
   `extracted_fields` from `metadata`, and OCR text — merged from the manifest's
   `artifacts` and split into pages).
3. Call `build_eval_scenario`. Summarizes counts, group breakdown, document types,
   eligible programs, and loan-level context (from `loan_file_xml`; eligibility
   `application_data` only fills gaps when that optional input is sent). It also **resolves the loan's parties** (primary borrower +
   optional co-borrower) from the `borrower`/`coborrower` input (falling back to
   eligibility, then XML), tags each document with the party it belongs to
   (`party_tags`, via the names in its extracted fields) and each condition with the
   party it applies to (`target_parties`, via its title/body text). On a
   single-borrower loan this is a no-op.
4. Call `save_step_report` with `step_id="STEP_00"`, a one-paragraph summary, and
   `outputs` containing the counts and group breakdown.

## Quality rules

- You MUST actually call `parse_conditions`, `parse_documents`, and
  `build_eval_scenario`. Marking todos `completed` with `write_todo` does NOT run
  them — `save_step_report` for STEP_00 is rejected until these tools have populated
  `conditions`, `evidence`, and `eval_scenario` in state.
- Do not invent conditions or documents that are not in the input.
- Do NOT attempt to classify or OCR documents — that already happened upstream.
- If inputs are empty, still call the three tools and build the scenario, then advance.
