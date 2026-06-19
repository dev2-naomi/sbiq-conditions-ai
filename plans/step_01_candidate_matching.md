# STEP_01 — Candidate Matching (associate documents to conditions)

## Role

Decide which submitted documents *could* satisfy which conditions. This is triage,
not a fulfillment decision — you are building the `condition -> candidate document`
map the evaluation steps will use.

**Most conditions arrive WITHOUT pre-linked documents**, so you must actively match
them yourself from the document inventory. Do not just rubber-stamp the cheap
deterministic proposals.

## Actions

1. Call `deterministic_candidate_match`. It returns the matching workspace:
   - `conditions` — each with `label`, `body`, `category`, `prelinked_document_ids`
     (authoritative `result_document_ids`, usually empty), and `proposed_candidates`
     (a cheap keyword/field shortlist — a **hint**, not the answer).
   - `document_inventory` — **every** submitted document with its `document_type`
     and `extracted_fields`.
2. For each condition, build its candidate list yourself:
   - **Always include** any `prelinked_document_ids` (authoritative).
   - **Scan the full `document_inventory`** and add every document that is plausibly
     relevant to the condition's ask — match on `document_type` **and** on field
     semantics (e.g. a hazard-insurance condition ↔ a "Homeowners Insurance
     Declaration" doc with `dwelling_coverage` / `wind_hail` fields; a "verify 25%
     ownership" condition ↔ an "Operating Agreement" with `members[].ownership_percent`).
   - Use `proposed_candidates` as hints, but **add** docs they missed and **drop**
     irrelevant ones.
   - A document may be a candidate for **multiple** conditions; a condition may have
     **multiple** candidate documents.
   - Leave a condition's list empty only if **nothing** in the inventory is plausibly
     relevant.
3. Call `store_candidate_matches` with the final map:
   `{ "<condition_id>": ["<evidence_id>", ...], ... }`.
4. Call `save_step_report` for `STEP_01`.

## Quality rules

- Being a candidate only means "worth analyzing in the evaluation step" — you are
  not deciding fulfillment here.
- **Prefer recall over precision** — it is cheaper to analyze an extra document than
  to miss the one that satisfies a condition.
- Match on **meaning**, not just keywords: read each document's `document_type` and
  `extracted_fields`, and each condition's `body`.
- Conditions with no plausible documents will evaluate as `Unfulfilled` later; that
  is expected when nothing relevant was submitted.
