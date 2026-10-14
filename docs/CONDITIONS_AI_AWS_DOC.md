# Conditions AI Frontend Integration Guide

Evaluates loan **conditions** against rack-and-stack **documents**. One verdict per condition: `Fulfilled` / `Partially Fulfilled` / `Unfulfilled` / `Needs Review`.

The engine is still a **LangGraph** graph (`conditions-evaluator`). It is no longer hosted on LangGraph Cloud — it runs on **AWS Lambda** behind a Platform-compatible HTTP API. A run takes **minutes**.

**Did input/output change in the AWS move?** No. Same `input` object, same `final_output` in thread state. Only the **host** and **auth key** changed.

| | LangSmith / LangGraph Cloud (old) | AWS Lambda (now) |
|--|-----------------------------------|------------------|
| Base URL | `https://sbiq-conditions-ai-….us.langgraph.app` | Function URL below |
| Auth | LangSmith API key as `x-api-key` / SDK `apiKey` | Stage **`API_KEY`** as `x-api-key` / SDK `apiKey` (dev and prod are **different** keys) |
| Assistant | `conditions-evaluator` | same |
| Payload | `input` fields below | same |
| Result | thread state `values.final_output` | same |

Do **not** send the LangSmith key to AWS (401). Use **`API_KEY_DEV`** against the dev URL and **`API_KEY_PROD`** against prod (from whoever owns the Lambda deploy / `.env`). A prod key will 401 on dev and vice versa.

---

## 1. Invoke (AWS)

| Stage | Base URL |
|-------|----------|
| prod | `https://4ptmhkbnvvyfh2gqb6yq47ib7a0vihoo.lambda-url.us-east-2.on.aws/` |
| dev | `https://c5n4xqskyfk2ollrqdvbdscekm0cuapj.lambda-url.us-east-2.on.aws/` |

Every request except `GET /health` needs `x-api-key` matching that stage. LangGraph SDK: `new Client({ apiUrl, apiKey })`.

Use **start + poll**. Do not block the browser on `/runs/wait`.

```
POST /threads                              → { thread_id }
POST /threads/{id}/runs                    → { run_id, status: "pending" }   // returns immediately
GET  /threads/{id}/runs/{run_id}           poll until success | error
GET  /threads/{id}/state                   → values.final_output
```

```http
POST /threads/{thread_id}/runs
Content-Type: application/json
x-api-key: <API_KEY_DEV or API_KEY_PROD>

{
  "assistant_id": "conditions-evaluator",
  "input": { ... }
}
```

On `success`, read:

```json
{ "values": { "final_output": { "scenario_summary": {}, "evaluations": [], "stats": {} } } }
```

One thread per loan evaluation. New loan / retry → new thread.

| Method | Path | Notes |
|--------|------|--------|
| `GET` | `/health` | no auth |
| `POST` | `/threads` | create |
| `GET` | `/threads/{id}` | |
| `POST` | `/threads/search` | |
| `GET` | `/threads/{id}/state` | **`final_output` lives here** |
| `POST` | `/threads/{id}/runs` | preferred |
| `GET` | `/threads/{id}/runs/{run_id}` | poll |
| `POST` | `/threads/{id}/runs/wait` | blocks; returns run **status**, not `final_output` |
| `POST` | `/threads/{id}/runs/stream` | SSE; dashboard can ignore |

This is a **subset** of LangGraph Platform. Extra Cloud-only routes (cron, store, extra assistants APIs) 404.

---

## 2. Input

JSON objects/arrays **or** JSON strings — both work.

| Field | Required | Description |
|-------|----------|-------------|
| `conditions_json` | yes | Encompass conditions array |
| `documents_json` | yes | R&S manifest: `{ "documents": [...] }` or a bare array |
| `eligibility_json` | no | Eligibility output (`eligible_programs`). Loan numbers come from `loan_file_xml`; eligibility only fills a field when the loan file omits it |
| `loan_file_xml` | yes | Loan scenario object (or a JSON string of it). See fields below |
| `borrower` / `coborrower` | no | `{ "first_name", "last_name" }` or a name string |
| `env` | no | Free-form, e.g. `"Test"` / `"Prod"` |

**Loan scenario** (`loan_file_xml`)

All of these are required and always populated. `ReservesMonths` may be omitted (`0` is a real value when it is sent). `IncomeDocType` and `BorrowerType` are not loan-level fields; income is the `Incomes` array.

```json
{
  "FicoScore": 782,
  "LTV": 50,
  "CLTV": 50,
  "DTI": 34,
  "LoanAmount": 1700000,
  "PropertyValue": 3400000,
  "PropertyType": "SFR",
  "Occupancy": "Second Home",
  "LoanPurpose": "Purchase",
  "Incomes": [
    {
      "income_tier": "Primary",
      "is_primary_borrower": true,
      "borrower_type": "Retired / Fixed Income",
      "income_doc": "Asset Utilization",
      "bank_statements_kind": null
    },
    {
      "income_tier": "Secondary",
      "is_primary_borrower": true,
      "borrower_type": "Wage Earner",
      "income_doc": "Written VOE",
      "bank_statements_kind": null
    },
    {
      "income_tier": "Primary",
      "is_primary_borrower": false,
      "borrower_type": "Self-Employed",
      "income_doc": "Bank Statements: 12 Mo.",
      "bank_statements_kind": "Personal"
    }
  ],
  "Channel": "wholesale",
  "Citizenship": "US Citizen",
  "State": "NJ",
  "County": "Ocean",
  "LoanType": "Conventional",
  "ReservesMonths": 0
}
```

`Incomes` has 1–3 rows. The one required row is the primary borrower's primary income: `income_tier` `"Primary"` and `is_primary_borrower` `true`. Further rows are that borrower's secondary income and/or the co-borrower's income. `bank_statements_kind` is `null` unless the income doc is a bank-statement type.

A legacy MISMO XML string is still accepted, but it only yields borrower name and property city/state.

**Condition**

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
    "result_document_ids": []
  }
}
```

- `data.Category` → group: Income / Assets / Credit / Property / other.
- `result_document_ids` optional. Empty is the usual case; the engine matches docs in STEP_01. If you pass IDs, they must exist in `documents_json`.

**Document** (structured R&S fields — not raw PDFs)

```json
{
  "id": 26030,
  "category": { "category_id": 1479, "category_name": "Homeowners Insurance Declaration" },
  "metadata": {
    "insured": "John Q Borrower",
    "dwelling_coverage": "$410,000",
    "wind_hail": "Included",
    "confidence": 0.9
  }
}
```

- Type ← `category.category_name` (aliases `document_type` / `type` still work).
- Fields ← `metadata` minus housekeeping (`confidence`, `total_pages`, `blob_id`, …). Or pass `extracted_fields`.
- Verdicts cite document `id` in `evidence_used`.

Full example: [`data/samples/sample_run_request.json`](../data/samples/sample_run_request.json).

---

## 3. Output (`final_output`)

```json
{
  "scenario_summary": {
    "loan": {
      "loan_id": 1042,
      "borrower_name": "...",
      "fico": 782,
      "ltv": 50,
      "cltv": 50,
      "dti": 34,
      "loan_amount": 1700000,
      "property_value": 3400000,
      "property_type": "SFR",
      "occupancy": "Second Home",
      "loan_purpose": "Purchase",
      "incomes": [
        {
          "income_tier": "Primary",
          "is_primary_borrower": true,
          "borrower_type": "Retired / Fixed Income",
          "income_doc": "Asset Utilization",
          "bank_statements_kind": null
        }
      ],
      "channel": "wholesale",
      "citizenship": "US Citizen",
      "property_state": "NJ",
      "county": "Ocean",
      "loan_type": "Conventional",
      "reserves_months": 0
    },
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
      "confidence": 70,
      "short_reason": "Coverage OK; mortgagee clause not shown.",
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

| Field | Meaning |
|-------|---------|
| `result` | `Fulfilled` \| `Partially Fulfilled` \| `Unfulfilled` \| `Needs Review` |
| `evaluations` | Pre-sorted for a review queue (needs-review / worse first). One row per condition |
| `needs_human_review` | Badge this. True unless clean high-confidence `Fulfilled` |
| `confidence` | 0–100 |
| `evidence_used` | Document `id`s |
| `guideline_refs` | NQMF sections consulted; may be `[]` |

Unmatched conditions are back-filled as `Unfulfilled` / `needs_human_review: true`.

Sample: [`data/samples/sample_final_output.json`](../data/samples/sample_final_output.json).

---

## 4. TypeScript

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

export interface SubmittedDocument {
  id: number | string;
  category?: { category_id?: number | string; category_name?: string };
  metadata?: Record<string, unknown>;
  extracted_fields?: Record<string, unknown>;
}

export interface ConditionInput {
  condition: {
    id: number | string;
    data: {
      Title?: string;
      Description?: string;
      Category?: string;
      Status?: string;
      ForRole?: string;
    };
    loan_id?: number | string;
    related_category_ids?: Array<number | string>;
    result_document_ids?: Array<number | string>;
  };
}

export interface IncomeRow {
  income_tier: "Primary" | "Secondary";
  is_primary_borrower: boolean;
  borrower_type: string;
  income_doc: string;
  bank_statements_kind: string | null;
}

export interface LoanFile {
  FicoScore: number;
  LTV: number;
  CLTV: number;
  DTI: number;
  LoanAmount: number;
  PropertyValue: number;
  PropertyType: string;
  Occupancy: string;
  LoanPurpose: string;
  Incomes: IncomeRow[];
  Channel: string;
  Citizenship: string;
  State: string;
  County: string;
  LoanType: string;
  ReservesMonths?: number;
}

export interface EvaluatorInput {
  conditions_json: ConditionInput[] | string;
  documents_json: { documents: SubmittedDocument[] } | SubmittedDocument[] | string;
  loan_file_xml: LoanFile | string;
  eligibility_json?: Record<string, unknown> | string;
  borrower?: { first_name?: string; last_name?: string } | string;
  coborrower?: { first_name?: string; last_name?: string } | string;
  env?: string;
}

export interface Evaluation {
  condition_id: string;
  label: string | null;
  body: string;
  category: EvalGroup;
  eval_group: EvalGroup;
  priority: string;
  result: Verdict;
  confidence: number;
  short_reason: string;
  satisfied_points: string[];
  missing_or_unclear_points: string[];
  evidence_used: string[];
  recommended_next_action: string;
  guideline_refs: string[];
  overall_status: OverallStatus;
  needs_human_review: boolean;
}

export interface FinalOutput {
  scenario_summary: {
    loan: {
      loan_id: number | string | null;
      borrower_name?: string | null;
      fico?: number | null;
      ltv?: number | null;
      cltv?: number | null;
      dti?: number | null;
      loan_amount?: number | null;
      property_value?: number | null;
      property_type?: string | null;
      occupancy?: string | null;
      loan_purpose?: string | null;
      incomes?: IncomeRow[];
      channel?: string | null;
      citizenship?: string | null;
      property_state?: string | null;
      county?: string | null;
      loan_type?: string | null;
      property_city?: string | null;
      reserves_months?: number | null;
    };
    eligible_programs: string[];
    counts: { conditions: number; submitted_documents: number };
    conditions_by_group: Partial<Record<EvalGroup, number>>;
    document_types: Record<string, number>;
  };
  evaluations: Evaluation[];
  stats: {
    total_conditions: number;
    needs_human_review: number;
    by_result: Partial<Record<Verdict, number>>;
    by_overall_status: Partial<Record<OverallStatus, number>>;
    by_category: Partial<Record<EvalGroup, number>>;
  };
}
```

---

## 5. Catches

- **`/runs/wait` does not return `final_output`.** Always `GET …/state` after `success`.
- **Prefer `/runs` + poll.** Gateways time out; Lambda can run up to 15 min. Sample run ~3 min.
- **No `final_output` after `success`:** fail and retry on a new thread.
- **`status: error`:** show run `error`; retry on a new thread.
- **Empty `conditions_json`:** `evaluations: []`.
- **Stale document IDs in `result_document_ids`:** ignored; STEP_01 matching is used.
- **CORS:** Function URL allows `x-api-key` and `content-type`. Current deploys: wildcard origin, credentials off.
- **Do not depend on SSE** for this product.
- **Floats in document metadata** (e.g. `confidence: 0.9`) are fine in `input`; the API stores them safely.
