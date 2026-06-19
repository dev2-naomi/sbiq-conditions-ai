"""
evaluation.py — Shared logic for the per-category evaluation steps (02-06).

Each evaluation step is a thin wrapper: it loads the conditions for its
evaluation group (with their candidate documents) and stores the LLM's
per-condition verdicts into module_outputs under that group's key.
"""

from __future__ import annotations

from langchain_core.messages import ToolMessage
from langgraph.types import Command

from tools.shared.normalize import normalize_evaluations

# Module-output storage key per evaluation group (group name == key).
GROUP_DEFAULT_CATEGORY = {
    "income": "income",
    "assets": "assets",
    "credit": "credit",
    "property": "property",
    "other": "other",
}

_TEXT_CAP = 8000  # cap document text per doc to keep context bounded


def build_category_context(state: dict, eval_group: str) -> dict:
    """
    Assemble the conditions belonging to `eval_group` together with the full
    text of each condition's candidate documents.
    """
    conditions: list[dict] = state.get("conditions", []) or []
    documents: list[dict] = state.get("evidence", []) or []
    candidate_map: dict = state.get("candidate_map", {}) or {}
    docs_by_id = {e.get("id"): e for e in documents}

    targets = [c for c in conditions if c.get("eval_group") == eval_group]

    context_conditions = []
    for cond in targets:
        cid = cond.get("id")
        candidates = candidate_map.get(cid, []) or []
        ev_blocks = []
        for cand in candidates:
            eid = cand.get("evidence_id") if isinstance(cand, dict) else cand
            doc = docs_by_id.get(eid)
            if not doc:
                continue
            text = doc.get("document_text", "") or ""
            if len(text) > _TEXT_CAP:
                text = text[:_TEXT_CAP] + "...[truncated]"
            ev_blocks.append({
                "evidence_id": doc.get("id"),
                "file_name": doc.get("file_name"),
                "detected_document_type": doc.get("detected_document_type"),
                "document_summary": doc.get("document_summary"),
                "document_text": text,
                "match_confidence": cand.get("confidence") if isinstance(cand, dict) else None,
                "match_source": cand.get("source") if isinstance(cand, dict) else None,
            })
        context_conditions.append({
            "condition_id": cid,
            "label": cond.get("label"),
            "body": cond.get("body"),
            "raw_text": cond.get("raw_text"),
            "category": cond.get("category"),
            "stage": cond.get("stage"),
            "candidate_documents": ev_blocks,
        })

    return {
        "eval_group": eval_group,
        "condition_count": len(context_conditions),
        "conditions": context_conditions,
    }


def store_evaluations_command(
    eval_group: str,
    evaluations: list[dict],
    tool_call_id: str,
) -> Command:
    """Normalize and persist evaluations into the group's module_outputs slot."""
    default_cat = GROUP_DEFAULT_CATEGORY.get(eval_group, "other")
    norm = normalize_evaluations(evaluations, default_category=default_cat)

    results = [e.get("result") for e in norm]
    return Command(update={
        "module_outputs": {eval_group: {"evaluations": norm, "eval_group": eval_group}},
        "messages": [ToolMessage(
            f"Stored {len(norm)} {eval_group} evaluation(s): {results}",
            tool_call_id=tool_call_id,
        )],
    })
