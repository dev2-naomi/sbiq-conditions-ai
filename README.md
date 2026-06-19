# SBIQ Conditions Evaluator

An **agentic underwriting condition evaluator**. It runs **after preconditions**:
preconditions recommends the documents a borrower must submit; the borrower submits
them; those documents are racked & stacked (R&S) upstream. Given the loan's
**conditions** and the borrower's **submitted documents** (R&S output), this engine
decides for each condition whether the documents make it `Fulfilled`,
`Partially Fulfilled`, `Unfulfilled`, or `Needs Review`, and flags items that need
human review.

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
STEP_00  Intake & Normalization      ─ Parse conditions + R&S documents + loan/eligibility, normalize, build scenario
STEP_01  Candidate Matching          ─ Associate docs⇄conditions: result_document_ids (authoritative) + LLM matching over the full document inventory (type + extracted_fields)
STEP_02  Income Evaluation           ─ Deep fulfillment reasoning for income conditions
STEP_03  Assets & Reserves Evaluation─ ... asset/reserves conditions
STEP_04  Credit Evaluation           ─ ... credit conditions (incl. identity, housing history, undisclosed property)
STEP_05  Property Evaluation         ─ ... property conditions (appraisal, title, insurance, taxes, flood)
STEP_06  Misc & Other Evaluation     ─ ... remaining conditions
STEP_07  Aggregation & HIL Packaging ─ Merge verdicts, derive status, flag review, build final output
```

> There is no document-extraction/classification step: the documents are already
> racked & stacked upstream and arrive pre-classified as part of the input.

### Key Design Decisions

- **Runs after preconditions**: inputs are the loan scenario, eligibility output, and
  the R&S document set — the same upstream artifacts `predicted-conditions` uses.
- **Active document⇄condition matching**: conditions usually arrive **without**
  pre-linked documents, so STEP_01 actively associates them. Any
  `result_document_ids` present are honored as authoritative; otherwise the LLM
  matches each condition against the full document inventory (type +
  `extracted_fields`), with a cheap deterministic shortlist for recall.
- **Agentic, not rule-coded**: Steps 02–06 use the LLM to reason over each document's
  **structured extracted fields** (the R&S output) rather than hard-coded checks,
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
| `conditions_json` | JSON | Conditions to evaluate, in the LOS/Encompass export shape (`{"condition": {"data": {"Title","Description","Category",...}, "result_document_ids": [...]}}`) |
| `documents_json` | JSON | Rack & stack (R&S) output — submitted documents as a manifest: each has `id`, a `category` (type) and `metadata` of **structured extracted fields** (no raw OCR text) |
| `eligibility_json` | JSON (optional) | Eligibility engine output (`application_data`, `eligible_programs`) |
| `loan_file_xml` | MISMO XML (optional) | Loan scenario for additional context |

Conditions are routed to one of five evaluation groups by `Category`:
`Income`, `Assets`, `Credit` (incl. identity / housing history / undisclosed
property), `Property` (appraisal / title / insurance / taxes / flood), and
`Misc → other`.

### Cloud / LangGraph invocation

Deployed on LangGraph Platform at:

```
https://sbiq-conditions-ai-c8388c5972925cd8a55f0f86b1fab478.us.langgraph.app
```

(Requests require a LangSmith API key via the `X-Api-Key` header.)

```json
POST /threads/{thread_id}/runs

{
  "assistant_id": "conditions-evaluator",
  "input": {
    "conditions_json": "<raw conditions JSON string>",
    "documents_json": "<raw R&S documents JSON string>",
    "eligibility_json": "<optional eligibility JSON string>",
    "loan_file_xml": "<optional MISMO XML string>"
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
  "scenario_summary": { "loan": {}, "eligible_programs": [], "counts": {}, "conditions_by_group": {} },
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

### Verdict values

| Value | Meaning |
|-------|---------|
| `Fulfilled` | Submitted documents fully satisfy the condition |
| `Partially Fulfilled` | Some required documents/data present, set incomplete |
| `Unfulfilled` | Not satisfied, or no relevant document submitted |
| `Needs Review` | Ambiguous/unclear extraction; human judgment required |

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
│   ├── matching_tools.py     # STEP_01 (candidate matching)
│   ├── evaluation_tools.py   # STEP_02–06 (shared getter, load_guideline_sections, per-category storers)
│   ├── aggregation_tools.py  # STEP_07
│   └── shared/
│       ├── normalize.py      # LOS condition + R&S document + verdict normalization, HIL gating
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
