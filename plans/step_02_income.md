# STEP_02 — Income Condition Evaluation

## Role

Evaluate whether the candidate documents satisfy each **income** condition.

## Actions

1. Call `get_conditions_to_evaluate` with `category="income"`. You receive each
   income condition and the full text of its candidate documents.
2. If `condition_count` is 0, immediately call `save_step_report` and advance.
3. For each condition, reason as a senior underwriter over the document text and
   produce one evaluation.
4. Call `store_income_evaluations` with the list of evaluations.
5. Call `save_step_report` for `STEP_02`.

## What income evidence typically proves

- Paystubs / W-2 / VOE → wage income, employer, YTD earnings, continuity.
- Tax returns (1040, Schedule C/E/K-1), business returns, P&L → self-employed income.
- Bank statements + analysis → bank-statement-program income.
- CPA letter / operating agreement / business license → business existence and
  ownership percentage (e.g., "verify minimum 25% ownership", "verify business is
  active within 30 days of note date").
- Partner acknowledgment letters → use of business assets to qualify.
- 1099s, award/distribution statements → contractor, retirement, SS income.

## Evaluation rules

- Evaluate the **collection** of candidate documents as a whole.
- Match the document to the *specific* ask in the condition (e.g., a letter that
  actually states the business is currently active, or names the business account).
- **Partially Fulfilled** when some but not all required items are present.
- **Unfulfilled** when no relevant document was submitted (no candidates).
- **Needs Review** when extraction is unclear or amounts/dates don't reconcile.
- Set `evidence_used` to the document ids you relied on; `confidence` is 0–100.

## Output per condition

```json
{
  "condition_id": "...",
  "result": "Fulfilled | Partially Fulfilled | Unfulfilled | Needs Review",
  "confidence": 0,
  "short_reason": "one sentence",
  "satisfied_points": ["..."],
  "missing_or_unclear_points": ["..."],
  "evidence_used": ["25988"],
  "recommended_next_action": "..."
}
```
