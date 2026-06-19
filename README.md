# SBIQ Conditions Evaluator

An **agentic underwriting condition evaluator**. Given a loan's **conditions**
(requirements an underwriter placed on the file) and a set of uploaded **evidence
documents**, it decides for each condition whether the evidence makes it
`Fulfilled`, `Partially Fulfilled`, `Unfulfilled`, or `Needs Review`, and flags
items that require human review.

It re-implements the purpose of the original `reference-sbiq-conditions-ai`
React/Gemini app (cheap-filter triage + deep fulfillment analysis + human-in-the-
loop) using the agentic LangGraph architecture of `predicted-conditions`: a single
ReAct agent loop walking a scoped, sequential pipeline.

## How It Works

A single LLM agent runs a **9-step sequential pipeline**. Before each turn, only
the current step's tools are bound and the current step's plan is injected as a
transient system message. Completed steps are compressed into a summary to keep the
context window bounded.

```
STEP_00  Intake & Normalization        ─ Parse conditions + evidence + loan, normalize, build scenario
STEP_01  Document Extraction            ─ Classify/summarize evidence docs (rack & stack)
STEP_02  Candidate Matching (cheap)     ─ Deterministic + LLM triage -> condition⇄evidence candidate map
STEP_03  Income Evaluation              ─ Deep fulfillment reasoning for income conditions
STEP_04  Assets & Reserves Evaluation   ─ ... asset/reserves conditions
STEP_05  Credit Evaluation              ─ ... credit conditions
STEP_06  Property & Appraisal Evaluation─ ... property/appraisal/collateral conditions
STEP_07  Title/Insurance/Compliance/ID  ─ ... remaining conditions
STEP_08  Aggregation & HIL Packaging    ─ Merge verdicts, derive status, flag review, build final output
```

### Key Design Decisions

- **Agentic, not rule-coded**: Steps 03–07 use the LLM to reason over evidence text
  rather than hard-coded checks, mirroring `predicted-conditions`.
- **Hybrid cheap filter**: STEP_02 runs a deterministic category/keyword/token
  matcher first, then the LLM refines the candidate map — the agentic version of
  the original app's "cheap filter".
- **Dynamic tool scoping & plan injection**: Each step only sees its own tools and
  plan (`plans/step_XX_*.md`), reducing context cost and out-of-scope tool calls.
- **Message summarization**: Completed-step messages are compressed before each LLM
  call (see `agent.py:_summarize_completed_steps`).
- **Normalization layer**: All categories, verdicts, and evaluation fields are
  coerced to a canonical schema in `tools/shared/normalize.py` regardless of how
  the LLM formats them.
- **Human-in-the-loop gating**: STEP_08 flags low-confidence, partial, unfulfilled,
  and ambiguous verdicts as `needs_human_review`.

## Inputs

Passed as raw strings (the agent parses them itself):

| Input | Format | Description |
|-------|--------|-------------|
| `conditions_json` | JSON list | Conditions to evaluate (`id`, `label`, `body`, `category`, ...) |
| `evidence_json` | JSON list | Evidence docs (`id`, `file_name`, `detected_document_type`, `document_summary`, `document_text`) |
| `loan_json` | JSON (optional) | Loan/borrower context |

### Cloud / LangGraph invocation

```json
POST /threads/{thread_id}/runs

{
  "assistant_id": "conditions-evaluator",
  "input": {
    "conditions_json": "<raw conditions JSON string>",
    "evidence_json": "<raw evidence JSON string>",
    "loan_json": "<optional loan JSON string>"
  }
}
```

The agent auto-generates its own instruction prompt and defaults to `STEP_00`, so
callers only need to send data. The final result is in thread state under
`final_output`.

## Output

```json
{
  "scenario_summary": { "loan": {}, "counts": {}, "conditions_by_group": {} },
  "evaluations": [
    {
      "condition_id": "COND-001",
      "label": "Most recent 30 days of paystubs",
      "category": "income",
      "result": "Fulfilled",
      "confidence": 92,
      "short_reason": "Two consecutive 2026 paystubs show employer, borrower, and YTD earnings.",
      "satisfied_points": ["Covers a 30-day period", "Shows YTD earnings"],
      "missing_or_unclear_points": [],
      "evidence_used": ["DOC-PAYSTUB1", "DOC-PAYSTUB2"],
      "recommended_next_action": "None — condition met.",
      "overall_status": "fulfilled",
      "needs_human_review": false
    }
  ],
  "stats": {
    "total_conditions": 7,
    "needs_human_review": 4,
    "by_result": { "Fulfilled": 3, "Partially Fulfilled": 1, "Unfulfilled": 2, "Needs Review": 1 },
    "by_overall_status": {},
    "by_category": {}
  }
}
```

### Verdict values

| Value | Meaning |
|-------|---------|
| `Fulfilled` | Evidence fully satisfies the condition |
| `Partially Fulfilled` | Some required documents/data present, set incomplete |
| `Unfulfilled` | Not satisfied, or no relevant evidence provided |
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
│   ├── step_00_intake.md ... step_08_aggregation.md
│
├── tools/
│   ├── __init__.py           # Exports ALL_TOOLS
│   ├── general.py            # write_todo, save_step_report, get_workflow_status
│   ├── intake_tools.py       # STEP_00
│   ├── extraction_tools.py   # STEP_01
│   ├── matching_tools.py     # STEP_02
│   ├── evaluation_tools.py   # STEP_03–07 (shared getter + per-category storers)
│   ├── aggregation_tools.py  # STEP_08
│   └── shared/
│       ├── normalize.py      # Canonical categories/verdicts/fields + HIL gating
│       ├── matching.py       # Deterministic cheap-filter matcher
│       └── evaluation.py     # Category context builder + evaluation storage
│
└── data/input/               # Sample conditions + evidence
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
