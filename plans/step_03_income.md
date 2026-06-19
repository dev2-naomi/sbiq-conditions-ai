# STEP_03 — Income Condition Evaluation

## Role

Evaluate whether the candidate evidence satisfies each **income** condition.

## Actions

1. Call `get_conditions_to_evaluate` with `category="income"`. You receive each
   income condition and the full text of its candidate evidence documents.
2. If `condition_count` is 0, immediately call `save_step_report` and advance.
3. For each condition, reason as a senior underwriter over the evidence text and
   produce one evaluation.
4. Call `store_income_evaluations` with the list of evaluations.
5. Call `save_step_report` for `STEP_03`.

## What income evidence typically proves

- Paystubs / W-2 / VOE → wage income, employer, YTD earnings, continuity.
- Tax returns (1040, Schedule C/E/K-1), business returns, P&L → self-employed income.
- Bank statements + analysis → bank-statement-program income; check consecutive
  months and large deposits.
- 1099s → contractor income.
- Award letters / distribution statements → retirement, pension, social security.
- Lease + Form 1007 + Schedule E → rental income.

## Evaluation rules

- Evaluate the **collection** of documents as a whole.
- Use **Partially Fulfilled** when some but not all required items are present
  (e.g., missing one of two tax years, missing months of bank statements).
- Use **Needs Review** when extraction is unclear, a referenced document is absent,
  or amounts/dates don't reconcile.
- Set `evidence_used` to the `evidence_id`s you actually relied on.
- `confidence` is 0–100. Lower it when the text is ambiguous or incomplete.

## Output per condition

```json
{
  "condition_id": "...",
  "result": "Fulfilled | Partially Fulfilled | Unfulfilled | Needs Review",
  "confidence": 0,
  "short_reason": "one sentence",
  "satisfied_points": ["..."],
  "missing_or_unclear_points": ["..."],
  "evidence_used": ["DOC-..."],
  "recommended_next_action": "..."
}
```
