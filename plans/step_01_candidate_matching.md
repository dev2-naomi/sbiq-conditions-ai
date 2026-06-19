# STEP_01 — Candidate Matching (Cheap Filter)

## Role

Decide which submitted documents *might* satisfy which conditions. This is triage,
not a fulfillment decision — you are building the `condition -> candidate document`
map the evaluation steps will use.

## Actions

1. Call `deterministic_candidate_match`. It returns a `proposed_candidate_map`
   built from two signals:
   - **Authoritative** — each condition's `result_document_ids` (documents the
     borrower actually submitted/attached for it upstream). Always included.
   - **Heuristic** — category/keyword/token matches (added above the threshold).
   It also lists conditions with no candidates.
2. Review the proposals:
   - **Trust** the authoritative `result_document_ids` links.
   - **Add** plausible links the heuristic missed.
   - **Remove** obviously wrong heuristic links.
   - Leave a condition with an empty list if nothing was submitted for it.
3. Call `store_candidate_matches` with the final map.
4. Call `save_step_report` for `STEP_01`.

## Quality rules

- Do NOT decide fulfillment here. Being a candidate only means "worth analyzing".
- Prefer recall over precision — it is cheaper to analyze an extra doc than to miss
  the one that satisfies a condition.
- Conditions with no candidates will evaluate as Unfulfilled later; that is expected
  when the borrower submitted nothing for them.
