# STEP_04 — Assets & Reserves Condition Evaluation

## Role

Evaluate whether the candidate evidence satisfies each **assets/reserves**
condition.

## Actions

1. Call `get_conditions_to_evaluate` with `category="assets"`.
2. If `condition_count` is 0, call `save_step_report` and advance.
3. Reason over the evidence and produce one evaluation per condition.
4. Call `store_assets_evaluations`.
5. Call `save_step_report` for `STEP_04`.

## What asset evidence typically proves

- Bank / brokerage / retirement statements → funds to close and reserves; check
  account ownership, balances, and that statements are recent and complete (all
  pages, consecutive months).
- Gift letters + donor ability/transfer evidence → gift funds.
- Large-deposit sourcing / letters of explanation → unsourced deposits.

## Evaluation rules

- Confirm the account holder matches the borrower.
- **Partially Fulfilled** when statements are present but pages/months are missing,
  or a large deposit is unsourced.
- **Needs Review** when balances/ownership are unclear in the extracted text.
- Evaluate the **collection** as a whole; populate `evidence_used`,
  `satisfied_points`, `missing_or_unclear_points`, `confidence`,
  `recommended_next_action`. Use the same output schema as STEP_03.
