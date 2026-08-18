# SBIQ Conditions Evaluator

An **agentic underwriting condition evaluator**. The loan's **conditions** are typed
in **Encompass** by underwriters (free-text, plus some default / automated
conditions); the borrower's **submitted documents** are racked & stacked (R&S)
upstream into a manifest that carries each document's structured extracted fields
**and its OCR text**. Given the conditions and that manifest, this engine decides for
each condition whether the documents make it `Fulfilled`, `Partially Fulfilled`,
`Unfulfilled`, or `Needs Review`, and flags items that need human review.

It re-implements the purpose of the original `reference-sbiq-conditions-ai`
React/Gemini app (cheap-filter triage + deep fulfillment analysis + human-in-the-
loop) using the agentic LangGraph architecture of `predicted-conditions`: a single
ReAct agent loop walking a scoped, sequential pipeline. Its inputs mirror
`predicted-conditions` (loan scenario + eligibility + document R&S), with the
conditions list as the thing being evaluated.

## How It Works

A single LLM agent runs an **8-step sequential pipeline**. Before each turn, only
the current step's tools are bound and the current step's plan is injected as a
transient system message. Completed steps are compressed into a summary to keep the
context window bounded.

```
STEP_00  Intake & Normalization      ─ Parse conditions + R&S documents (incl. OCR) + loan/eligibility, normalize, build scenario
STEP_01  Candidate Matching          ─ Associate docs⇄conditions: result_document_ids (authoritative) + an OCR relevance check (first pages, escalate to full) over the full document inventory (type + extracted_fields + OCR)
STEP_02  Income Evaluation           ─ Deep fulfillment reasoning for income conditions
STEP_03  Assets & Reserves Evaluation─ ... asset/reserves conditions
STEP_04  Credit Evaluation           ─ ... credit conditions (incl. identity, housing history, undisclosed property)
STEP_05  Property Evaluation         ─ ... property conditions (appraisal, title, insurance, taxes, flood)
STEP_06  Misc & Other Evaluation     ─ ... remaining conditions
STEP_07  Aggregation & HIL Packaging ─ Merge verdicts, derive status, flag review, build final output
```

> There is no document-extraction/classification step: the documents are already
> racked & stacked upstream and arrive pre-classified (with OCR) as part of the input.

### Key Design Decisions

- **Conditions come from Encompass**: most are custom free-text conditions typed by
  underwriters; some are default/automated conditions. They usually arrive
  **without** pre-linked documents.
- **OCR-driven document⇄condition matching**: STEP_01 actively associates documents.
  Any `result_document_ids` present are honored as authoritative; otherwise a cheap
  deterministic shortlist surfaces plausible docs and the agent runs an **OCR
  relevance check** — reading each document's first OCR pages (`ocr_preview`) and
  escalating to the full OCR via `get_document_ocr` only when inconclusive — to
  decide whether the document is within the condition's context.
- **OCR availability**: the R&S manifest references per-document OCR under a
  top-level `artifacts` array (`type: "ocr"`). This engine assumes that OCR is
  **dereferenced/inlined** by the time the manifest arrives, and splits it into
  pages so steps can read the first pages first and pull the full text on demand.
- **Borrower / co-borrower resolution**: when a loan has a co-borrower, conditions
  and documents are attributed to the correct party so a condition is satisfied only
  by *that party's* evidence. STEP_00 resolves the parties and tags every document
  (`party_tags`) and condition (`target_parties`); STEP_01 scopes candidates
  accordingly. Single-borrower loans are unaffected. See
  [Borrower / co-borrower resolution](#borrower--co-borrower-resolution).
- **Agentic, not rule-coded**: Steps 02–06 use the LLM to reason over each document's
  **structured extracted fields** plus its **OCR text** rather than hard-coded checks,
  mirroring `predicted-conditions`.
- **Guidelines as a scoped reference**: during evaluation the agent can call
  `load_guideline_sections` to consult `data/guidelines.md` (NQMF) — strictly to
  clarify a condition's acceptance criteria or document-validity standards. The
  **condition text is always primary**; guidelines never add new requirements. Any
  section consulted is recorded in the evaluation's `guideline_refs`.
- **Dynamic tool scoping & plan injection**: Each step only sees its own tools and
  plan (`plans/step_XX_*.md`), reducing context cost and out-of-scope tool calls.
- **Message summarization**: Completed-step messages are compressed before each LLM
  call (see `agent.py:_summarize_completed_steps`).
- **Normalization layer**: The LOS/Encompass condition shape, R&S document shape,
  categories, verdicts, and evaluation fields are all coerced to a canonical schema
  in `tools/shared/normalize.py`.
- **Human-in-the-loop gating**: STEP_07 flags low-confidence, partial, unfulfilled,
  and ambiguous verdicts as `needs_human_review`.

## Inputs

Passed as raw strings (the agent parses them itself):

| Input | Format | Description |
|-------|--------|-------------|
| `conditions_json` | JSON | Conditions to evaluate, in the Encompass export shape (`{"condition": {"data": {"Title","Description","Category",...}, "result_document_ids": [...]}}`). A leading log/prefix line is tolerated. |
| `documents_json` | JSON | Rack & stack (R&S) manifest — submitted documents: each has `id`, a `category` (type) and `metadata` of **structured extracted fields**, plus per-document **OCR** referenced under a top-level `artifacts` array (`type: "ocr"`), assumed dereferenced/inlined |
| `eligibility_json` | JSON (optional) | Eligibility engine output (`application_data`, `eligible_programs`) |
| `loan_file_xml` | MISMO XML (optional) | Loan scenario for additional context |
| `borrower` | JSON/dict or string (optional) | Primary borrower identity — `{"first_name","last_name"}` or a name string. Falls back to eligibility / XML when omitted. |
| `coborrower` | JSON/dict or string (optional) | Co-borrower identity. Empty/absent ⇒ single-party loan. |

Conditions are routed to one of five evaluation groups by `Category`:
`Income`, `Assets`, `Credit` (incl. identity / housing history / undisclosed
property), `Property` (appraisal / title / insurance / taxes / flood), and
`Misc → other`.

### Cloud / LangGraph invocation

Deployed on **AWS Lambda** (preferred) at:

```
https://c5n4xqskyfk2ollrqdvbdscekm0cuapj.lambda-url.us-east-2.on.aws/
```

(Requests require the deploy `API_KEY` via the `X-Api-Key` header.)

Still available on LangGraph Platform at:

```
https://sbiq-conditions-ai-c8388c5972925cd8a55f0f86b1fab478.us.langgraph.app
```

(Requests require a LangSmith API key via the `X-Api-Key` header.)

> **AWS Lambda hosting:** see [`docs/AWS_DEPLOYMENT.md`](docs/AWS_DEPLOYMENT.md).
> Deploy with `./infra/deploy.sh dev`, then point clients at the Function URL
> with `x-api-key` from `.env` (`API_KEY`). Assistant id stays `conditions-evaluator`.

```json
POST /threads/{thread_id}/runs

{
  "assistant_id": "conditions-evaluator",
  "input": {
    "conditions_json": "<raw conditions JSON string>",
    "documents_json": "<raw R&S documents JSON string>",
    "eligibility_json": "<optional eligibility JSON string>",
    "loan_file_xml": "<optional MISMO XML string>",
    "borrower": {"first_name": "Israel", "last_name": "Ortiz"},
    "coborrower": {"first_name": "Natalya", "last_name": "Ortiz"}
  }
}
```

The agent auto-generates its own instruction prompt and defaults to `STEP_00`, so
callers only need to send data. The final result is in thread state under
`final_output`.

> **Building a UI / calling this from a client?** See
> [`docs/FRONTEND_INTEGRATION.md`](docs/FRONTEND_INTEGRATION.md) for the full
> request/response contract, TypeScript types, invocation options (LangGraph SDK /
> REST / backend wrapper), and rendering guidance. Ready-to-use samples live in
> [`data/samples/`](data/samples/).

## Output

```json
{
  "scenario_summary": { "loan": {}, "borrowers": [], "eligible_programs": [], "counts": {}, "conditions_by_group": {} },
  "evaluations": [
    {
      "condition_id": "5660",
      "label": "CORR:  Property: Insurance - Hazard",
      "category": "property",
      "result": "Partially Fulfilled",
      "confidence": 70,
      "short_reason": "Hazard dec page shows sufficient coverage and wind/hail, but the mortgagee clause is not listed.",
      "satisfied_points": ["Coverage $410,000 ≥ loan amount", "Wind/Hail included"],
      "missing_or_unclear_points": ["Loss payee / mortgagee clause (ISAOA + loan number) not shown"],
      "evidence_used": ["26030"],
      "recommended_next_action": "Request updated dec page with the lender's mortgagee clause.",
      "guideline_refs": ["PROPERTY INSURANCE"],
      "overall_status": "partially_fulfilled",
      "needs_human_review": true
    }
  ],
  "stats": {
    "total_conditions": 10,
    "needs_human_review": 4,
    "by_result": {},
    "by_overall_status": {},
    "by_category": {}
  }
}
```

> On multi-party loans, `scenario_summary.borrowers` lists the resolved parties,
> each evaluation carries `party_tags` + `applicable_parties`, and `stats.by_party`
> counts conditions per party. See
> [Borrower / co-borrower resolution](#borrower--co-borrower-resolution).

### Verdict values

| Value | Meaning |
|-------|---------|
| `Fulfilled` | Submitted documents fully satisfy the condition |
| `Partially Fulfilled` | Some required documents/data present, set incomplete |
| `Unfulfilled` | Not satisfied, or no relevant document submitted |
| `Needs Review` | Ambiguous/unclear extraction; human judgment required |

## Borrower / co-borrower resolution

A loan can have a primary **borrower** and (optionally) a **co-borrower**. Conditions
and documents are often party-specific — a *"verify employment for the Co-Borrower"*
condition must be cleared by the **co-borrower's** VOE, not the borrower's — yet the
raw inputs carry no structural party flag (the only signal is the wording of the
condition and the names on the documents). This engine makes party attribution
explicit and deterministic. All logic lives in
[`tools/shared/parties.py`](tools/shared/parties.py) and runs inside STEP_00 /
STEP_01, so it needs no extra pipeline step.

```
  borrower / coborrower ─┐
  eligibility_json      ─┼─▶ 1. resolve_parties()   → [borrower, coborrower?]
  loan_file_xml         ─┘
                                     │
  manifest documents ────────────────▼───────────────────────────
  (names in extracted   ┌──────────────────────────────────────┐
   fields)              │ 2. assign_doc_parties()   → party_tags │
                        └──────────────────────────────────────┘
  conditions ──────────┌──────────────────────────────────────┐
  (title / body text)  │ 3. condition_target_parties() → target │
                        └──────────────────────────────────────┘
                                     │
  STEP_01 candidates ─────────────────▼───────────────────────────
                        4. keep a link only when party_tags ∩ target_parties
```

### 1. Resolve parties

`resolve_parties()` returns at most one primary + one co-borrower, each
`{name, first_name, last_name, role, tag}` (`tag` = `"borrower"` / `"coborrower"`).
Identity resolution order:

| Party | Resolution order |
|-------|------------------|
| Primary | `borrower` input → eligibility `BorrowerFirstName`/`BorrowerLastName` (or `borrower_first_name`… / `BorrowerName`) → MISMO XML borrower name |
| Co-borrower | `coborrower` input → eligibility `CoBorrowerFirstName`/`CoBorrowerLastName` (or `co_borrower_first_name`…) |

A co-borrower is only added when its normalized name **differs** from the primary's
(the same person listed twice never creates a phantom party). If no primary can be
resolved, the party list is empty and all party logic is a no-op.

### 2. Assign documents to parties

`assign_doc_parties()` reads the person name(s) off each document's extracted fields
(`employee`, `employments[].employee`, `borrowers[]`, `customer`, `insured`, `name`,
`members[]`, …) and fuzzy-matches them to a party:

| Document metadata | Assigned to |
|-------------------|-------------|
| Names a specific party | that party (or **both**, if it names both) |
| **No** person name (loan-level: appraisal, title, flood…) | **all** parties |
| Names someone but matches **no** known party | **all** parties (never dropped) |

The *"unnamed → all"* rule lets one shared loan-level document satisfy each party's
loan-level conditions.

### 3. Attribute conditions to parties

`condition_target_parties()` reads a condition's title/body for a party signal:

1. An explicit party **name** (requires both first **and** last name, so a shared
   surname like *"Ortiz"* alone can't misroute) → that party.
2. Otherwise a distinguishing **role phrase**: *"Co-Borrower"* → co-borrower; a
   primary targeting marker (*"for Borrower"*, *"Borrower's"*, *"(Borrower)"*, …) →
   borrower; both present → both.
3. No party signal (generic condition) → **all** parties.

Note a *bare* generic mention of "borrower" (e.g. *"the borrower must provide…"*) is
**not** treated as targeting the primary — it applies to all parties, so a generic
condition is never accidentally withheld from the co-borrower.

### Fuzzy name matching

Document/eligibility names rarely match character-for-character (`"Isral,Ortiz"` vs
`"Israel Ortiz"`). `_name_matches()` normalizes (lowercase, strip punctuation,
collapse spaces) then matches on **any** of: exact equality; **≥2 shared whole
tokens** (first **and** last — a single shared surname is not enough); a high
whole-string similarity ratio (≥ 0.82, typo-tolerant); or first-and-last tokens that
are each individually close.

### 4. Candidate scoping

In STEP_01, `doc_matches_condition_party()` keeps a document⇄condition link only when
the document's `party_tags` intersect the condition's `target_parties`. Because both
default to *all* parties when unresolved, only clearly cross-party pairs are dropped
(e.g. the borrower's VOE for a co-borrower condition) — this is enforced
deterministically in `store_candidate_matches`, so a wrong LLM link can't leak
through. The evaluation steps (02–06) also surface each candidate's `party_tags` and
each condition's `target_parties` so the model reasons per party.

### Single-party loans & failure handling

With fewer than two resolved parties every predicate is a no-op and behavior is
identical to before this feature. Resolution is defensive: unresolved parties simply
mean no scoping. The final output carries `scenario_summary.borrowers`
(`[{name, role, tag}]`), a `party_tags` / `applicable_parties` tag on each multi-party
evaluation, and a `stats.by_party` breakdown.

## Project Structure

```
sbiq-conditions-ai/
├── agent.py                  # LangGraph StateGraph, orchestrator node, summarization
├── registry.py               # AUTO-GENERATED step→tool/plan mappings
├── step_loader.py            # Dynamic tool/plan resolution per step
├── test_pipeline.py          # Local runner (full + --offline modes)
├── langgraph.json            # LangGraph deployment descriptor
├── requirements.txt
├── env.example
│
├── config/
│   ├── workflow_config.json  # Step definitions + tool assignments (source of truth)
│   └── generate.py           # Regenerates registry.py from workflow_config.json
│
├── plans/                    # Per-step plans injected as system messages
│   ├── system_prompt.md
│   ├── step_00_intake.md ... step_07_aggregation.md
│
├── tools/
│   ├── __init__.py           # Exports ALL_TOOLS
│   ├── general.py            # write_todo, save_step_report, get_workflow_status
│   ├── intake_tools.py       # STEP_00 (parse_conditions, parse_documents, build_eval_scenario)
│   ├── matching_tools.py     # STEP_01 (candidate matching + get_document_ocr relevance check)
│   ├── evaluation_tools.py   # STEP_02–06 (shared getter, load_guideline_sections, per-category storers)
│   ├── aggregation_tools.py  # STEP_07
│   └── shared/
│       ├── normalize.py      # Encompass condition + R&S document (incl. OCR) + verdict normalization, HIL gating
│       ├── ocr.py            # OCR page-splitting, first-pages/full previews, artifact merge
│       ├── parties.py        # Borrower/co-borrower resolution, per-party doc + condition attribution
│       ├── matching.py       # result_document_ids + deterministic cheap-filter matcher
│       ├── evaluation.py     # Category context builder + evaluation storage
│       └── guidelines.py     # NQMF guidelines parser (section lookup)
│
├── docs/
│   └── FRONTEND_INTEGRATION.md # Request/response contract, TS types, invocation + UI guidance
│
├── data/
│   ├── guidelines.md         # NQMF underwriting guidelines (evaluation reference)
│   ├── input/                # Sample conditions (Encompass shape), R&S documents, eligibility
│   └── samples/              # Packaged API request body + representative final_output
```

## Run Locally

**Prerequisites:** Python 3.10+, an Anthropic API key.

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp env.example .env   # then set ANTHROPIC_API_KEY

# Offline structural check (no key/network):
python test_pipeline.py --offline

# Full agentic run:
python test_pipeline.py
```

To change the pipeline, edit `config/workflow_config.json` and run
`python config/generate.py` to regenerate `registry.py`.
