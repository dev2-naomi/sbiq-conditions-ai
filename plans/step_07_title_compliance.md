# STEP_07 — Title, Insurance, Compliance & Identity Evaluation

## Role

Evaluate every remaining condition: **title, insurance, identity, compliance, and
other** categories.

## Actions

1. Call `get_conditions_to_evaluate` with `category="title_compliance"`.
2. If `condition_count` is 0, call `save_step_report` and advance.
3. Reason over the evidence and produce one evaluation per condition.
4. Call `store_title_compliance_evaluations`.
5. Call `save_step_report` for `STEP_07`. This is the last evaluation step.

## What this evidence typically proves

- Title commitment / preliminary title → vesting, liens, exceptions.
- Closing Disclosure / settlement statement → fees, payoff, cash to close.
- Homeowners / flood insurance declaration → coverage amount, dates, mortgagee
  clause.
- Government ID / SSN card → identity verification (Patriot Act).
- Trust/entity docs, occupancy certifications, authorizations → compliance items.

## Evaluation rules

- Match the document to the exact item requested (e.g., insurance coverage ≥ loan
  amount, correct mortgagee clause, valid policy dates).
- **Partially Fulfilled** when a document is present but a required field (dates,
  mortgagee clause, signatures) is missing or expired.
- **Needs Review** when the extracted text is unclear or the document is the wrong
  type for the condition.
- Use the same output schema as STEP_03.
