# STEP_00 — Intake & Normalization

## Role

Parse and normalize the raw inputs so every downstream step works from a clean,
consistent data model.

## Inputs (already in state)

- `conditions_json` — raw JSON list of conditions to evaluate.
- `evidence_json` — raw JSON list of uploaded evidence documents.
- `loan_json` — optional loan/borrower context.

## Actions

1. Call `parse_conditions`. This normalizes each condition's category and assigns
   an evaluation group (income / assets / credit / property / title_compliance).
2. Call `parse_evidence`. This normalizes each evidence document (id, file name,
   detected type, summary, text).
3. Call `build_eval_scenario` to produce a compact summary (counts, category
   breakdown, evidence types, loan context).
4. Call `save_step_report` with `step_id="STEP_00"`, a one-paragraph summary, and
   `outputs` containing the counts and group breakdown.

## Quality rules

- Do not invent conditions or evidence that are not in the input.
- If the inputs are empty, still build the scenario and advance — later steps will
  produce "Unfulfilled / no evidence" results.
