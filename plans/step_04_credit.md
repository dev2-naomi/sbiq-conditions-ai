# STEP_04 — Credit Condition Evaluation

## Role

Evaluate whether the candidate documents satisfy each **credit** condition. In the
LOS taxonomy this group also includes **identity**, **housing history**, and
**undisclosed-property** conditions.

## Actions

1. Call `get_conditions_to_evaluate` with `category="credit"`. Each candidate
   document carries its `document_type`, `extracted_fields`, and an `ocr_preview`;
   call `get_document_ocr(evidence_id, full=True)` when you need the full OCR.
2. If `condition_count` is 0, call `save_step_report` and advance.
3. If a condition is ambiguous or you need the standard a document must meet
   (e.g. months of housing history, acceptable VOR/cancelled-check substitutes),
   call `load_guideline_sections` (e.g. `CREDIT`, `HOUSING HISTORY`, `LIABILITIES`).
4. Reason over the documents and produce one evaluation per condition; record any
   sections you relied on in `guideline_refs`.
5. Call `store_credit_evaluations`.
6. Call `save_step_report` for `STEP_04`.

## Guidelines (reference)

Guidelines are a reference to clarify acceptance criteria, never a source of new
requirements — the condition text is primary. Relevant sections: `CREDIT`,
`HOUSING HISTORY`, `HOUSING EVENTS AND PRIOR BANKRUPTCY`, `LIABILITIES`.

## What credit evidence typically proves

- Credit report → scores, tradelines, inquiries, derogatory items.
- Letters of explanation (LOE) → inquiries, disputes, address variances.
- VOR + cancelled checks → 12-month housing payment history.
- Government ID (driver's license, passport) → primary identification. Watch quality
  notes ("cut off… need better picture / copy of license").
- Closing Disclosure from a prior sale → proof a prior property was sold / a lien was
  satisfied (undisclosed-property and "property is sold" conditions).

## Evaluation rules

- Match the document to the *specific* item the condition calls out (the named
  inquiry, the named prior property/address, the specific lien/mortgage).
- **Partially Fulfilled** when an LOE/ID is generic, illegible, or covers only some
  required items.
- **Unfulfilled** when nothing relevant was submitted.
- **Needs Review** when the report/letter/ID text is unclear or the referenced item
  is not found.
- Use the same output schema as STEP_02.
