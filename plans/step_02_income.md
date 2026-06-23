# STEP_02 — Income Condition Evaluation

## Role

Evaluate whether the candidate documents satisfy each **income** condition.

## Actions

1. Call `get_conditions_to_evaluate` with `category="income"`. You receive each
   income condition and its candidate documents — each candidate's `document_type`,
   its `extracted_fields` (the structured fields rack & stack pulled from the
   document), and an `ocr_preview` (first OCR pages).
2. If `condition_count` is 0, immediately call `save_step_report` and advance.
3. If a candidate's `ocr_preview` isn't enough to decide (the figure/clause you need
   is deeper in the document), call `get_document_ocr(evidence_id)` for more pages or
   `get_document_ocr(evidence_id, full=True)` for the full OCR.
4. If a condition is ambiguous or you need the standard a document must meet
   (e.g. how many months of bank statements, which tax years/schedules, signed
   P&L recency), call `load_guideline_sections` for the relevant section(s) —
   see "Guidelines (reference)" below.
5. For each condition, reason as a senior underwriter over the documents'
   `extracted_fields` and OCR text and produce one evaluation. Record any sections
   you relied on in `guideline_refs`.
6. Call `store_income_evaluations` with the list of evaluations.
7. Call `save_step_report` for `STEP_02`.

## Guidelines (reference)

The NQMF guidelines are a **reference to clarify acceptance criteria** — they are
NOT a source of new requirements. The condition text is always primary; use
guidelines only to resolve ambiguity or define document-validity standards, and
never to add requirements the condition did not ask for.

Relevant income sections: `FULL DOCUMENTATION`, `EMPLOYMENT`,
`ALTERNATIVE DOCUMENTATION (ALT DOC)`, `RATIOS AND QUALIFYING – FULL AND ALT DOC`,
`OTHER INCOME`, `RENTAL INCOME REQUIREMENTS`.

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
  "recommended_next_action": "...",
  "guideline_refs": ["EMPLOYMENT"]
}
```

`guideline_refs` is optional — include the guideline section name(s) you consulted,
or leave it empty if the verdict came from the condition text and documents alone.
