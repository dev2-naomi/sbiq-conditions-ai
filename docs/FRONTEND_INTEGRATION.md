# Frontend Integration Guide

This engine is a LangGraph agent. It takes a loan's **conditions** plus the
borrower's **submitted documents** (rack & stack output) and returns, for every
condition, a verdict (`Fulfilled` / `Partially Fulfilled` / `Unfulfilled` /
`Needs Review`) with reasoning and a human-review flag.

> The graph is named **`conditions-evaluator`** (see `langgraph.json`). A full run
> calls the LLM many times and can take **minutes**.

---

## 1. Mental model

```
preconditions  ──▶  borrower uploads docs  ──▶  rack & stack (R&S)  ──▶  THIS ENGINE  ──▶  underwriter UI
(recommends docs)                              (classifies/OCRs)        (evaluates)        (review queue)
```

---

## 2. The contract

### 2.1 Input

You send a single `input` object. Each field below is documented as JSON; you may
send it **either as a JSON string or as an already-parsed object/array** — the
agent accepts both (it only calls `JSON.parse` when it receives a string).

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `conditions_json` | ✅ | JSON array (or string) | Conditions to evaluate, in the LOS/Encompass export shape |
| `documents_json` | ✅ | JSON (or string) | Rack & stack output — the documents the borrower submitted |
| `eligibility_json` | optional | JSON object (or string) | Eligibility engine output (`application_data`, `eligible_programs`) — best source for loan-level numbers |
| `loan_file_xml` | optional | string (MISMO XML) | Loan scenario for extra context; pass `""` if unused |
| `env` | optional | string | `"Test"` or `"Prod"` (free-form tag) |

**Condition shape** (`conditions_json` is an array of these):

```json
{
  "condition": {
    "id": 5660,
    "data": {
      "Title": "CORR:  Property: Insurance - Hazard",
      "Description": "Provide evidence of hazard insurance ...",
      "Category": "Property",
      "Status": "Added",
      "ForRole": "Sr Loan Coordinator"
    },
    "loan_id": 1042,
    "related_category_ids": [1479],
    "result_document_ids": [26030]
  }
}
```

- `data.Category` routes the condition to an evaluation group:
  `Income` → income, `Assets` → assets, `Credit` → credit, `Property` → property,
  everything else → `other`.
- **`result_document_ids`** (optional): document IDs already linked to this
  condition upstream. When present, the engine treats them as **authoritative
  links** (make sure they reference IDs in `documents_json`). **Leaving it empty is
  fine — and is the common case.** The engine still associates documents to each
  condition itself in STEP_01 (matching on document type + extracted fields), so no
  manual linking is required.

**Document shape** (`documents_json` is `{ "documents": [...] }` or a bare array).
This mirrors the **rack & stack (R&S) manifest**: each document is *classified*
(a `category`) and *indexed* into **structured extracted fields** under `metadata`.
R&S does **not** provide raw OCR text — the substance is the structured fields:

```json
{
  "id": 26030,
  "category": { "category_id": 1479, "category_name": "Homeowners Insurance Declaration" },
  "metadata": {
    "insured": "John Q Borrower",
    "property_address": "742 Evergreen Terrace",
    "dwelling_coverage": "$410,000",
    "wind_hail": "Included",
    "effective_date": "10/30/2025",
    "mortgagee_clause": null,
    "total_pages": 1,
    "confidence": 0.9
  }
}
```

How the engine reads it:
- **Document type** ← `category.category_name` (legacy aliases `document_type` /
  `detected_document_type` / `type` still accepted). This may be empty/omitted —
  then the document is matched and evaluated purely on its `extracted_fields`.
- **Extracted fields** ← everything under `metadata` *except* housekeeping keys
  (`confidence`, `exceptions`, `total_pages`, `group_name`, `object_name`,
  `vision_check`, `source`, `blob_id`, …). You may also pass a pre-built field bag
  as `extracted_fields` (or `fields` / `data`).
- **`id`** must match the `result_document_ids` used in the conditions — that's the
  authoritative link.

> A complete, ready-to-send request body lives at
> [`data/samples/sample_run_request.json`](../data/samples/sample_run_request.json).

### 2.2 Output

When the run completes, read **`final_output`** from the run/thread state. Shape:

```json
{
  "scenario_summary": {
    "loan": { "loan_id": 1042, "borrower_name": "...", "loan_amount": 420000, "ltv": 80.0, "fico": 728 },
    "eligible_programs": ["Flex Select"],
    "counts": { "conditions": 5, "submitted_documents": 5 },
    "conditions_by_group": { "assets": 2, "property": 1, "credit": 1, "income": 1 },
    "document_types": { "Driver License": 1 }
  },
  "evaluations": [
    {
      "condition_id": "5660",
      "label": "CORR:  Property: Insurance - Hazard",
      "body": "Provide evidence of hazard insurance ...",
      "category": "property",
      "eval_group": "property",
      "priority": "normal",
      "result": "Partially Fulfilled",
      "confidence": 70.0,
      "short_reason": "Coverage and wind/hail OK, but mortgagee clause not shown.",
      "satisfied_points": ["Dwelling coverage $410,000 supports the loan amount"],
      "missing_or_unclear_points": ["Mortgagee clause not on the page provided"],
      "evidence_used": ["26030"],
      "recommended_next_action": "Request an updated dec page with the mortgagee clause.",
      "guideline_refs": ["PROPERTY INSURANCE"],
      "overall_status": "partially_fulfilled",
      "needs_human_review": true
    }
  ],
  "stats": {
    "total_conditions": 5,
    "needs_human_review": 2,
    "by_result": { "Fulfilled": 3, "Partially Fulfilled": 1, "Unfulfilled": 1 },
    "by_overall_status": { "fulfilled": 3, "partially_fulfilled": 1, "unfulfilled": 1 },
    "by_category": { "assets": 2, "property": 1, "credit": 1, "income": 1 }
  }
}
```

- `evaluations` is **pre-sorted**: items needing human review come first, then by
  severity (`Unfulfilled` → `Needs Review` → `Partially Fulfilled` → `Fulfilled`).
  This is the natural order for an underwriter review queue.
- Every condition appears exactly once. A condition with no matched evidence is
  back-filled as `Unfulfilled` / `needs_human_review: true`.
- `confidence` is `0–100`.

> A representative response lives at
> [`data/samples/sample_final_output.json`](../data/samples/sample_final_output.json).

### 2.3 TypeScript types

```ts
export type Verdict =
  | "Fulfilled"
  | "Partially Fulfilled"
  | "Unfulfilled"
  | "Needs Review";

export type OverallStatus =
  | "fulfilled"
  | "partially_fulfilled"
  | "unfulfilled"
  | "needs_human_review";

export type EvalGroup = "income" | "assets" | "credit" | "property" | "other";

```

---

## 3. How to call it

The engine is deployed on **LangGraph Platform** and exposes the standard LangGraph
"Assistants" HTTP API — usable via the `@langchain/langgraph-sdk` client or plain
REST. Wire up the calls however the frontend/backend prefers; you only need:

| What | Value |
|------|-------|
| **Base URL** | `https://sbiq-conditions-ai-c8388c5972925cd8a55f0f86b1fab478.us.langgraph.app` |
| **Auth** | a **LangSmith API key**, sent as the `X-Api-Key` header (REST) or `apiKey` in the SDK `Client` |
| **Assistant / graph id** | `conditions-evaluator` |
| **Input** | the `EvaluatorInput` object (§2.1) |
| **Result** | read `final_output` from the thread/run state (§2.2) |

---

## 4. Rendering guidance

- **Review queue:** `evaluations` is already ordered for review — render it top to
  bottom. Show a "Needs review" badge when `needs_human_review` is true.
- **Verdict colors** (suggested):

  | `result` | Color |
  |----------|-------|
  | `Fulfilled` | green |
  | `Partially Fulfilled` | amber |
  | `Unfulfilled` | red |
  | `Needs Review` | gray/blue |

- **Header stats:** drive summary chips from `stats` (`total_conditions`,
  `needs_human_review`, `by_result`).
- **Grouping/filters:** group by `category`/`eval_group`; filter by `result` or
  `needs_human_review`.
- **Per-condition detail:** show `body` (the underwriter ask), `short_reason`,
  `satisfied_points` ✅, `missing_or_unclear_points` ⚠️, and
  `recommended_next_action`. Link `evidence_used` IDs back to the documents.
- **Audit:** display `guideline_refs` as "Guideline reference: …" — these are the
  NQMF sections the agent consulted; the condition text is always primary.
- **Confidence:** render `confidence` (0–100) as a meter; values below ~50 are
  already flagged for human review.

---

## 5. Errors & edge cases

- **No `final_output`:** the run ended early. Surface a retry; inspect run status /
  last messages for the cause.
- **Empty `conditions_json`:** you'll get `evaluations: []` and zeroed stats.
- **`result_document_ids` referencing missing documents:** the link is ignored and
  the condition falls back to STEP_01 matching; it may come back `Unfulfilled` or
  `Needs Review`. Keep document IDs consistent across the two inputs.
- **Timeouts:** runs take minutes, so don't rely on a single blocking request.
  Prefer the **non-blocking "start + poll" pattern**: create a run (returns
  immediately with a `run_id` / `pending` status), then poll the run status or the
  thread state every few seconds until it's `success`/`error`, and read
  `final_output` then. This way a gateway/proxy timeout never kills the run.
- **Idempotency:** reuse one thread per loan evaluation; create a new thread for a
  fresh run.

---

## 6. Sample files

| File | Purpose |
|------|---------|
| [`data/samples/sample_run_request.json`](../data/samples/sample_run_request.json) | Complete run request body (`assistant_id` + `input`) for the Assistants API |
| [`data/samples/sample_final_output.json`](../data/samples/sample_final_output.json) | Representative `final_output` to build/test the UI against |
| [`data/input/`](../data/input/) | The raw inputs split into individual files (conditions, documents, eligibility) used by `test_pipeline.py` |