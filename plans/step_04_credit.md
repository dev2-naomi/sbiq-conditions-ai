# STEP_04 — Credit Condition Evaluation

## Role

Evaluate whether the candidate documents satisfy each **credit** condition. In the
LOS taxonomy this group also includes **identity**, **housing history**, and
**undisclosed-property** conditions.

## Actions

1. Call `get_conditions_to_evaluate` with `category="credit"`.
2. If `condition_count` is 0, call `save_step_report` and advance.
3. Reason over the documents and produce one evaluation per condition.
4. Call `store_credit_evaluations`.
5. Call `save_step_report` for `STEP_04`.

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
