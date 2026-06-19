# STEP_05 — Credit Condition Evaluation

## Role

Evaluate whether the candidate evidence satisfies each **credit** condition.

## Actions

1. Call `get_conditions_to_evaluate` with `category="credit"`.
2. If `condition_count` is 0, call `save_step_report` and advance.
3. Reason over the evidence and produce one evaluation per condition.
4. Call `store_credit_evaluations`.
5. Call `save_step_report` for `STEP_05`.

## What credit evidence typically proves

- Credit report → scores, tradelines, inquiries, derogatory items.
- Letters of explanation (LOE) → inquiries, disputes, late payments, credit events.
- Verification of rent/mortgage (VOR/VOM) → housing payment history.

## Evaluation rules

- Match the explanation/evidence to the specific item the condition calls out
  (e.g., an LOE that addresses the *named* inquiry or derog).
- **Partially Fulfilled** when an LOE is generic or covers only some required items.
- **Needs Review** when the report/letter text is unclear or the item referenced is
  not found.
- Use the same output schema as STEP_03 (`condition_id`, `result`, `confidence`,
  `short_reason`, `satisfied_points`, `missing_or_unclear_points`, `evidence_used`,
  `recommended_next_action`).
