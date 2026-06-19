"""
aggregation_tools.py — Tools for STEP_07: Aggregation & HIL Packaging.

Merges every per-category evaluation, derives an overall status and a
needs_human_review flag per condition, then assembles the final output report.
"""

from __future__ import annotations

from collections import Counter

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command
from typing_extensions import Annotated

from tools.shared.normalize import VALID_EVAL_GROUPS, derive_overall_status


def _collect_evaluations(module_outputs: dict) -> dict[str, dict]:
    """Flatten all per-group evaluations into condition_id -> evaluation."""
    merged: dict[str, dict] = {}
    for key in VALID_EVAL_GROUPS:
        mod = module_outputs.get(key, {}) or {}
        for ev in mod.get("evaluations", []) or []:
            cid = ev.get("condition_id")
            if cid:
                merged[cid] = ev
    return merged


@tool
def merge_evaluations(
    manual_review_threshold: float = 50.0,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
    state: Annotated[dict, InjectedState] = None,
) -> Command:
    """
    Merge evaluations from all category steps, attach overall_status and
    needs_human_review, and back-fill any condition that was never evaluated
    (no candidate evidence) as Unfulfilled / needs human review.

    Args:
        manual_review_threshold: confidence below which an item is flagged for
                                 human review (0-100).
    """
    s = state or {}
    conditions = s.get("conditions", []) or []
    evals_by_cid = _collect_evaluations(s.get("module_outputs", {}) or {})

    cond_by_id = {c.get("id"): c for c in conditions}
    merged: list[dict] = []

    for cond in conditions:
        cid = cond.get("id")
        ev = evals_by_cid.get(cid)
        if ev is None:
            ev = {
                "condition_id": cid,
                "category": cond.get("category", "other"),
                "result": "Unfulfilled",
                "confidence": 0.0,
                "short_reason": "No candidate evidence was matched to this condition.",
                "satisfied_points": [],
                "missing_or_unclear_points": ["No evidence submitted/matched for this condition."],
                "evidence_used": [],
                "recommended_next_action": "Request supporting documentation from the borrower.",
            }
        status = derive_overall_status(ev, manual_review_threshold)
        record = {
            **ev,
            "label": cond.get("label"),
            "body": cond.get("body"),
            "priority": cond.get("priority"),
            "eval_group": cond.get("eval_group"),
            **status,
        }
        merged.append(record)

    # Stable sort: needs_human_review first, then by result severity.
    _result_rank = {"Unfulfilled": 0, "Needs Review": 1, "Partially Fulfilled": 2, "Fulfilled": 3}
    merged.sort(key=lambda r: (not r["needs_human_review"], _result_rank.get(r["result"], 1)))

    hr = sum(1 for r in merged if r["needs_human_review"])
    return Command(update={
        "module_outputs": {"merged": {"merged_evaluations": merged}},
        "messages": [ToolMessage(
            f"Merged {len(merged)} evaluation(s); {hr} flagged for human review.",
            tool_call_id=tool_call_id,
        )],
    })


@tool
def generate_final_output(
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
    state: Annotated[dict, InjectedState] = None,
) -> Command:
    """
    Assemble the final output JSON: scenario summary, per-condition evaluations,
    and aggregate stats. Stores it under state['final_output'].
    """
    s = state or {}
    mo = s.get("module_outputs", {}) or {}
    merged = mo.get("merged", {}).get("merged_evaluations", []) or []

    by_result = Counter(r.get("result") for r in merged)
    by_category = Counter(r.get("category") for r in merged)
    by_status = Counter(r.get("overall_status") for r in merged)
    needs_review = sum(1 for r in merged if r.get("needs_human_review"))

    final = {
        "scenario_summary": s.get("eval_scenario", {}),
        "evaluations": merged,
        "stats": {
            "total_conditions": len(merged),
            "needs_human_review": needs_review,
            "by_result": dict(by_result),
            "by_overall_status": dict(by_status),
            "by_category": dict(by_category),
        },
    }

    return Command(update={
        "final_output": final,
        "messages": [ToolMessage(
            "Final output assembled. "
            f"{final['stats']['total_conditions']} conditions evaluated; "
            f"results={dict(by_result)}; "
            f"{needs_review} need human review.",
            tool_call_id=tool_call_id,
        )],
    })
