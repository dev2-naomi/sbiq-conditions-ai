# STEP_01 — Candidate Matching (relevance check)

## Role

Decide which submitted documents *could* satisfy which conditions. This is triage,
not a fulfillment decision — you are building the `condition -> candidate document`
map the evaluation steps will use.

Conditions are typed in Encompass by underwriters (free-text, plus some default /
automated conditions), so they usually arrive **WITHOUT pre-linked documents** and
their wording is unstructured. You must actively match them yourself, and confirm
relevance against each document's OCR text.

## Actions

1. Call `deterministic_candidate_match`. It returns the matching workspace:
   - `conditions` — each with `label`, `body`, `category`, `prelinked_document_ids`
     (authoritative `result_document_ids`, usually empty), and `proposed_candidates`
     (a cheap keyword/field shortlist — a **hint**, not the answer).
   - `document_inventory` — **every** submitted document with its `document_type`,
     `extracted_fields`, and an `ocr_preview` (first ~2 OCR pages).
2. For each condition, build its candidate list:
   - **Always include** any `prelinked_document_ids` (authoritative).
   - **Scan the full `document_inventory`** and, for each document that is plausibly
     relevant, run the relevance check below.
   - Use `proposed_candidates` as hints, but **add** docs they missed and **drop**
     irrelevant ones.
3. **Relevance check (OCR-driven).** For a document/condition pair, judge whether the
   document is *within the context of the condition* (`<condition>{label} {body}</condition>`):
   - First read the document's `ocr_preview` (first pages) together with its
     `document_type` and `extracted_fields`.
   - If the first pages are inconclusive, call `get_document_ocr(evidence_id)` for
     more pages, then `get_document_ocr(evidence_id, full=True)` for the full OCR.
   - A document is a candidate when it is **related** to the condition's context
     (e.g. a hazard-insurance condition ↔ an insurance declaration page; a "verify
     25% ownership" condition ↔ an operating agreement listing member ownership).
     Treat clearly **unrelated** documents as non-candidates.
   - If a document has no OCR (`ocr_total_pages` is 0 / `ocr_available` is false),
     fall back to `document_type` + `extracted_fields`.
4. Call `store_candidate_matches` with the final map:
   `{ "<condition_id>": ["<evidence_id>", ...], ... }`.
5. Call `save_step_report` for `STEP_01`.

## Quality rules

- Being a candidate only means "worth analyzing in the evaluation step" — you are
  **not** deciding fulfillment here.
- **Prefer recall over precision** — it is cheaper to analyze an extra document than
  to miss the one that satisfies a condition. When in doubt, keep it.
- Match on **meaning**, not just keywords: the relevance check is about whether the
  document's content is within the condition's context.
- A document may be a candidate for **multiple** conditions; a condition may have
  **multiple** candidate documents.
- Don't read the full OCR by default — start with the preview and escalate only when
  needed, to keep the context bounded.
- Leave a condition's list empty only if **nothing** in the inventory is plausibly
  relevant. Conditions with no plausible documents will evaluate as `Unfulfilled`
  later; that is expected when nothing relevant was submitted.
