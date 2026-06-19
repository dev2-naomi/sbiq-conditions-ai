# STEP_06 — Property & Appraisal Condition Evaluation

## Role

Evaluate whether the candidate evidence satisfies each **property / appraisal /
collateral** condition.

## Actions

1. Call `get_conditions_to_evaluate` with `category="property"`.
2. If `condition_count` is 0, call `save_step_report` and advance.
3. Reason over the evidence and produce one evaluation per condition.
4. Call `store_property_evaluations`.
5. Call `save_step_report` for `STEP_06`.

## What property evidence typically proves

- Appraisal report (1004 / 1073 / 1025) → value, condition, comparables.
- Form 1007 rent schedule → market rent for rental income support.
- Inspections, repair certifications, recertification of value → conditions/repairs.
- Photos, plat/survey → property characteristics.

## Evaluation rules

- Confirm the appraised property address matches the subject property.
- **Partially Fulfilled** when the appraisal is present but a required addendum,
  repair completion, or recert is missing.
- **Needs Review** when value, condition, or addenda are unclear in the text.
- Use the same output schema as STEP_03.
