# STEP_05 — Property Condition Evaluation

## Role

Evaluate whether the candidate documents satisfy each **property** condition. In the
LOS taxonomy this group bundles **appraisal, title, insurance, taxes, flood, and
purchase agreement** conditions.

## Actions

1. Call `get_conditions_to_evaluate` with `category="property"`.
2. If `condition_count` is 0, call `save_step_report` and advance.
3. Reason over the documents and produce one evaluation per condition.
4. Call `store_property_evaluations`.
5. Call `save_step_report` for `STEP_05`.

## What property evidence typically proves

- Appraisal report (1004/1073/1025), 2nd appraisal → value/condition; flipping rules.
- Preliminary title commitment + 24-month chain of title; CPL → title conditions.
- Hazard insurance declaration → coverage ≥ lesser of loan amount or replacement
  cost, wind/hail included, correct loss payee/mortgagee clause, and **effective
  date within the required window of the note date**.
- Flood certification (life-of-loan) → flood cert conditions.
- Property tax documentation with disbursement dates / current tax bill.
- Executed purchase agreement with all addenda → purchase conditions.
- Seller entity authorization docs → corporate/LLC seller conditions.

## Evaluation rules

- Confirm the document address matches the subject property.
- Check the explicit constraints in the condition text (coverage amounts, dates,
  mortgagee clause wording, chain-of-title length, "executed by all parties").
- **Partially Fulfilled** when a document is present but a required field, addendum,
  signature, or date window is missing/expired.
- **Unfulfilled** when nothing relevant was submitted.
- Use the same output schema as STEP_02.
