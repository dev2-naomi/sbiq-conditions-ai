# Frontend Integration Guide

How to drive the **SBIQ Conditions Evaluator** from a frontend (or any client).

This engine is a LangGraph agent. It takes a loan's **conditions** plus the
borrower's **submitted documents** (rack & stack output) and returns, for every
condition, a verdict (`Fulfilled` / `Partially Fulfilled` / `Unfulfilled` /
`Needs Review`) with reasoning and a human-review flag.

> The graph is named **`conditions-evaluator`** (see `langgraph.json`). A full run
> calls the LLM many times and can take **minutes**, so treat it as an async job —
> never block a UI thread waiting for it synchronously.

---

## 1. Mental model

```
preconditions  ──▶  borrower uploads docs  ──▶  rack & stack (R&S)  ──▶  THIS ENGINE  ──▶  underwriter UI
(recommends docs)                              (classifies/OCRs)        (evaluates)        (review queue)
```

Your frontend is the last box: you collect/forward the inputs, kick off a run,
poll/stream until it finishes, then render `final_output`.

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
- **`result_document_ids`** is important: these are the document IDs the borrower
  already submitted for this condition. The engine treats them as **authoritative
  links** — make sure they reference IDs present in `documents_json`.

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
  `detected_document_type` / `type` still accepted).
- **Extracted fields** ← everything under `metadata` *except* housekeeping keys
  (`confidence`, `exceptions`, `total_pages`, `group_name`, `object_name`,
  `vision_check`, `source`, `blob_id`, …). You may also pass a pre-built field bag
  as `extracted_fields` (or `fields` / `data`).
- **`id`** must match the `result_document_ids` used in the conditions — that's the
  authoritative link.
- **Raw OCR text is optional.** If your R&S variant happens to include it, put it in
  `document_text` / `extracted_text` / `ocr_text`; the agent will use it as an extra
  signal, but it is never required.

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

export interface ConditionEvaluation {
  condition_id: string;
  label: string | null;
  body: string;
  category: EvalGroup;
  eval_group: EvalGroup;
  priority: string;
  result: Verdict;
  confidence: number; // 0-100
  short_reason: string;
  satisfied_points: string[];
  missing_or_unclear_points: string[];
  evidence_used: string[]; // document ids
  recommended_next_action: string;
  guideline_refs: string[]; // NQMF guideline sections consulted
  overall_status: OverallStatus;
  needs_human_review: boolean;
}

export interface EvaluatorResult {
  scenario_summary: {
    loan: Record<string, unknown>;
    eligible_programs: string[];
    counts: { conditions: number; submitted_documents: number };
    conditions_by_group: Record<EvalGroup, number>;
    document_types: Record<string, number>;
  };
  evaluations: ConditionEvaluation[];
  stats: {
    total_conditions: number;
    needs_human_review: number;
    by_result: Record<string, number>;
    by_overall_status: Record<string, number>;
    by_category: Record<string, number>;
  };
}

// Rack & stack document (input): classified + structured fields, no raw OCR.
export interface SubmittedDocument {
  id: number | string; // must match conditions[].result_document_ids
  category?: { category_id?: number; category_name?: string };
  metadata?: Record<string, unknown>; // structured extracted fields + housekeeping
  extracted_fields?: Record<string, unknown>; // optional pre-built field bag
  document_text?: string; // optional raw OCR, usually absent
}

export interface EvaluatorInput {
  conditions_json: unknown[] | string;
  documents_json: { documents: SubmittedDocument[] } | SubmittedDocument[] | string;
  eligibility_json?: Record<string, unknown> | string;
  loan_file_xml?: string;
  env?: "Test" | "Prod";
}
```

---

## 3. How to call it

The engine runs on **LangGraph Server** (the deployment target described by
`langgraph.json`). It exposes the standard LangGraph "Assistants" HTTP API. There
are three practical integration paths.

> **Never call Anthropic or run the graph directly from the browser.** The graph
> needs `ANTHROPIC_API_KEY` and is long-running. Always go through a server (the
> LangGraph Server, or your own backend that proxies to it).

### Option A — LangGraph JS SDK (recommended for JS/TS apps)

```bash
npm install @langchain/langgraph-sdk
```

```ts
import { Client } from "@langchain/langgraph-sdk";

const client = new Client({ apiUrl: process.env.LANGGRAPH_URL! });

export async function evaluateConditions(input: EvaluatorInput): Promise<EvaluatorResult> {
  const thread = await client.threads.create();

  // Blocking helper: waits for the run to finish and returns final state values.
  const state = await client.runs.wait(thread.thread_id, "conditions-evaluator", {
    input,
  });

  const result = (state as any).final_output as EvaluatorResult | undefined;
  if (!result) throw new Error("Run finished without final_output");
  return result;
}
```

Stream progress instead of blocking (good for a progress bar — you can surface
each step as the agent advances):

```ts
const stream = client.runs.stream(thread.thread_id, "conditions-evaluator", {
  input,
  streamMode: "updates",
});
for await (const chunk of stream) {
  // chunk.event === "updates"; inspect chunk.data for current_step / step_reports
}
const finalState = await client.threads.getState(thread.thread_id);
const result = finalState.values.final_output;
```

### Option B — Raw REST (any language)

```bash
# 1) Create a thread
curl -s -X POST "$LANGGRAPH_URL/threads" -H "Content-Type: application/json" -d '{}'
# -> { "thread_id": "..." }

# 2) Create a run and wait for the result (returns final state values)
curl -s -X POST "$LANGGRAPH_URL/threads/$THREAD_ID/runs/wait" \
  -H "Content-Type: application/json" \
  -d @data/samples/sample_run_request.json
# -> final state, including "final_output"
```

For long runs prefer the non-blocking variant and poll:

```
POST /threads/{thread_id}/runs           -> { run_id, status: "pending" }
GET  /threads/{thread_id}/runs/{run_id}  -> { status: "running" | "success" | "error" }
GET  /threads/{thread_id}/state          -> { values: { final_output, current_step, ... } }
```

### Option C — Thin backend wrapper

If you don't want the frontend to speak the LangGraph API directly, put a small
endpoint in your own backend that (a) accepts the four inputs, (b) calls Option A
or B, and (c) returns just `final_output`. This is the cleanest contract for a UI:

```
POST /api/conditions/evaluate   { conditions, documents, eligibility?, loanXml? }
  -> 202 { jobId }
GET  /api/conditions/evaluate/{jobId}
  -> 200 { status, result?: EvaluatorResult }
```

Internally your backend can also run the graph in-process (`from agent import agent;
agent.invoke(input)`) if you deploy this repo as a Python service rather than on
LangGraph Server.

---

## 4. Recommended frontend flow

1. **Gather inputs.** Usually you already have `conditions_json`, `documents_json`,
   and `eligibility_json` from upstream systems — forward them as-is.
2. **Start the run** (Option A/B/C) and immediately show a "Evaluating…" state.
   Runs take minutes; do it in the background and let the user navigate away.
3. **Show progress** (optional) by streaming `updates` and reading `current_step`
   (`STEP_00` … `STEP_07`) and `step_reports`.
4. **On completion**, read `final_output` and render.
5. **Persist** `final_output` keyed by `loan_id` / `thread_id` so reviewers can
   reopen it without re-running.

---

## 5. Rendering guidance

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

## 6. Errors & edge cases

- **No `final_output`:** the run ended early. Surface a retry; inspect run status /
  last messages for the cause.
- **Empty `conditions_json`:** you'll get `evaluations: []` and zeroed stats.
- **`result_document_ids` referencing missing documents:** the link is ignored and
  the condition relies on heuristic matching; it may come back `Unfulfilled` or
  `Needs Review`. Keep document IDs consistent across the two inputs.
- **Timeouts:** size client/proxy timeouts in minutes, or use the non-blocking
  poll pattern (Option B) so a gateway timeout never kills the run.
- **Idempotency:** reuse one thread per loan evaluation; create a new thread for a
  fresh run.

---

## 7. Sample files

| File | Purpose |
|------|---------|
| [`data/samples/sample_run_request.json`](../data/samples/sample_run_request.json) | Complete request body (`assistant_id` + `input`) you can POST to `/runs/wait` |
| [`data/samples/sample_final_output.json`](../data/samples/sample_final_output.json) | Representative `final_output` to build/test the UI against |
| [`data/input/`](../data/input/) | The raw inputs split into individual files (conditions, documents, eligibility) used by `test_pipeline.py` |

Quick local smoke test of the contract (no UI, no API key needed for the offline
structural check):

```bash
python test_pipeline.py --offline   # deterministic plumbing only
python test_pipeline.py             # full run; writes test_results/last_run.json
```

`test_results/last_run.json` is exactly the `final_output` your frontend receives.
