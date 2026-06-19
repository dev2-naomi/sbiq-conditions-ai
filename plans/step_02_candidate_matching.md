# STEP_02 — Candidate Matching (Cheap Filter)

## Role

Decide which evidence documents *might* satisfy which conditions. This is triage,
not a fulfillment decision — you are building the `condition -> candidate evidence`
map that the evaluation steps will use.

## Actions

1. Call `deterministic_candidate_match`. It returns a `proposed_candidate_map`
   (condition_id → candidate docs with confidence/reason) plus a list of
   conditions with no candidates.
2. Review the proposals against the conditions and the evidence types:
   - **Add** plausible links the deterministic matcher missed (e.g., a generically
     named PDF whose summary clearly matches a condition).
   - **Remove** obviously wrong links.
   - It is fine for a document to be a candidate for multiple conditions, and for a
     condition to have multiple candidate documents.
   - Leave a condition with an empty list if nothing plausibly matches.
3. Call `store_candidate_matches` with the final map. Each entry can be a plain
   `evidence_id` or `{evidence_id, confidence, reason}`.
4. Call `save_step_report` for `STEP_02`.

## Quality rules

- Do NOT decide fulfillment here. Being a candidate only means "worth analyzing".
- Prefer recall over precision — it is cheaper to analyze an extra doc than to miss
  the document that actually satisfies a condition.
