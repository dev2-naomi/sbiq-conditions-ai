"""
matching_tools.py — Tools for STEP_01: Candidate Matching (cheap filter).

Produces a condition -> candidate-document map. Each condition's upstream
result_document_ids are authoritative pre-links; a deterministic keyword pass
supplements them, and the LLM confirms/refines before storing the final map.
"""

from __future__ import annotations

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command
from typing_extensions import Annotated

from tools.shared.matching import deterministic_match


@tool
def deterministic_candidate_match(
    threshold: float = 30.0,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
    state: Annotated[dict, InjectedState] = None,
) -> dict:
    """
    Run candidate matching over all conditions and submitted documents. Combines
    authoritative result_document_ids pre-links with a heuristic keyword/token
    matcher. Returns proposed candidates per condition for you to review. This
    does NOT decide fulfillment — only plausibility.

    Args:
        threshold: minimum heuristic confidence (0-100) for a doc to be a candidate.
                   (Authoritative result_document_ids links are always included.)
    """
    s = state or {}
    conditions = s.get("conditions", []) or []
    documents = s.get("evidence", []) or []
    proposed = deterministic_match(conditions, documents, threshold=threshold)

    total = sum(len(v) for v in proposed.values())
    unmatched = [cid for cid, v in proposed.items() if not v]
    return {
        "proposed_candidate_map": proposed,
        "total_candidate_links": total,
        "conditions_without_candidates": unmatched,
        "note": "Conditions with no candidates likely have no submitted documents and "
                "will evaluate as Unfulfilled. Review the proposals, add/remove links "
                "using your judgment, then call store_candidate_matches with the final map.",
    }


@tool
def store_candidate_matches(
    candidate_map: dict,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
    state: Annotated[dict, InjectedState] = None,
) -> Command:
    """
    Store the final condition -> candidate-document map after your triage.

    Args:
        candidate_map: dict of condition_id -> list of candidate entries. Each
                       entry may be a plain document id string or an object
                       {evidence_id, confidence, reason, source}.
    """
    normalized: dict[str, list] = {}
    total = 0
    for cid, cands in (candidate_map or {}).items():
        entries = []
        for cand in cands or []:
            if isinstance(cand, str):
                entries.append({"evidence_id": cand, "confidence": None, "reason": "llm_match", "source": "llm"})
            elif isinstance(cand, dict) and cand.get("evidence_id"):
                entries.append({
                    "evidence_id": cand.get("evidence_id"),
                    "confidence": cand.get("confidence"),
                    "reason": cand.get("reason", "llm_match"),
                    "source": cand.get("source", "llm"),
                })
        normalized[cid] = entries
        total += len(entries)

    return Command(update={
        "candidate_map": normalized,
        "messages": [ToolMessage(
            f"Stored candidate map: {len(normalized)} condition(s), {total} total link(s).",
            tool_call_id=tool_call_id,
        )],
    })
