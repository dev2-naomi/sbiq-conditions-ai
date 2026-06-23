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
from tools.shared.ocr import first_pages

# Module-output storage key per evaluation group (group name == key).
GROUP_DEFAULT_CATEGORY = {
    "income": "income",
    "assets": "assets",
    "credit": "credit",
    "property": "property",
    "other": "other",
}

_EVAL_PREVIEW_PAGES = 4  # OCR pages to surface per candidate doc during evaluation


def build_category_context(state: dict, eval_group: str) -> dict:
    """
    Assemble the conditions belonging to `eval_group` together with their
    candidate documents. Each candidate carries the document type, its structured
    extracted fields (the R&S output), and an OCR preview (first pages). The agent
    can call `get_document_ocr` to read the full OCR when the preview is insufficient.
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
            block = {
                "evidence_id": doc.get("id"),
                "document_type": doc.get("detected_document_type"),
                "document_summary": doc.get("document_summary"),
                "extracted_fields": doc.get("extracted_fields") or {},
                "match_confidence": cand.get("confidence") if isinstance(cand, dict) else None,
                "match_source": cand.get("source") if isinstance(cand, dict) else None,
            }
            # Surface an OCR preview (first pages); full OCR via get_document_ocr.
            pages = doc.get("ocr_pages") or []
            if pages:
                block["ocr_preview"] = first_pages(pages, n=_EVAL_PREVIEW_PAGES)
                block["ocr_total_pages"] = len(pages)
            ev_blocks.append(block)
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


def _candidate_ids_for(candidate_map: dict, condition_id: str) -> list[str]:
    """Evidence ids matched to a condition during STEP_01, in match order."""
    out: list[str] = []
    for cand in candidate_map.get(condition_id, []) or []:
        eid = cand.get("evidence_id") if isinstance(cand, dict) else cand
        if eid not in (None, "") and str(eid) not in out:
            out.append(str(eid))
    return out


def store_evaluations_command(
    eval_group: str,
    evaluations: list[dict],
    tool_call_id: str,
    state: dict | None = None,
) -> Command:
    """Normalize and persist evaluations into the group's module_outputs slot.

    Safety net: if the model omitted ``evidence_used`` for a condition, backfill it
    from the STEP_01 candidate matches so the stored verdict still links to the
    documents that were examined.
    """
    default_cat = GROUP_DEFAULT_CATEGORY.get(eval_group, "other")
    norm = normalize_evaluations(evaluations, default_category=default_cat)

    candidate_map = (state or {}).get("candidate_map", {}) or {}
    for ev in norm:
        if not ev.get("evidence_used"):
            backfill = _candidate_ids_for(candidate_map, ev.get("condition_id", ""))
            if backfill:
                ev["evidence_used"] = backfill

    results = [e.get("result") for e in norm]
    return Command(update={
        "module_outputs": {eval_group: {"evaluations": norm, "eval_group": eval_group}},
        "messages": [ToolMessage(
            f"Stored {len(norm)} {eval_group} evaluation(s): {results}",
            tool_call_id=tool_call_id,
        )],
    })
