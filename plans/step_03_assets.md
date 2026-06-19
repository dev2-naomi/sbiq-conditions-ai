# STEP_03 — Assets & Reserves Condition Evaluation

## Role

Evaluate whether the candidate documents satisfy each **assets/reserves** condition.

## Actions

1. Call `get_conditions_to_evaluate` with `category="assets"`.
2. If `condition_count` is 0, call `save_step_report` and advance.
3. Reason over the documents and produce one evaluation per condition.
4. Call `store_assets_evaluations`.
5. Call `save_step_report` for `STEP_03`.

## What asset evidence typically proves

- Bank / brokerage / retirement statements (or EVOD) → funds to close and reserves;
  check account ownership, balances, recency, and completeness (all pages/months).
- A specific dollar requirement (e.g., "require a total of $132,314.27 which
  includes $13,163.46 in reserves") → confirm the documented balances meet it.
- Earnest money deposit proof (copy of check or title receipt) → EMD conditions.
- Gift letters + transfer evidence; large-deposit sourcing letters.

## Evaluation rules

- Confirm the account holder matches the borrower.
- Watch expiry notes (e.g., "EVOD is acceptable but expires in 3 business days") —
  flag timing risk in `missing_or_unclear_points` and consider **Needs Review**.
- **Partially Fulfilled** when statements are present but pages/months are missing,
  the dollar threshold isn't clearly met, or a large deposit is unsourced.
- **Unfulfilled** when nothing relevant was submitted.
- Use the same output schema as STEP_02.
