"""
extraction_tools.py — Tools for STEP_01: Document Extraction & Classification.

If evidence already arrives classified (detected_document_type + summary present),
this step is a near no-op. When type/summary are missing, the LLM reads the
document text and supplies them via store_evidence_classifications.
"""

from __future__ import annotations

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command
from typing_extensions import Annotated

_TEXT_PREVIEW = 4000


@tool
def get_evidence_for_extraction(
    state: Annotated[dict, InjectedState] = None,
) -> dict:
    """
    Return evidence documents and a flag for which ones still need a
    detected_document_type and/or document_summary. Use the document_text to
    classify the ones flagged as needing extraction.
    """
    s = state or {}
    evidence = s.get("evidence", []) or []
    out = []
    for doc in evidence:
        text = doc.get("document_text", "") or ""
        needs = not (doc.get("detected_document_type") and doc.get("document_summary"))
        out.append({
            "evidence_id": doc.get("id"),
            "file_name": doc.get("file_name"),
            "detected_document_type": doc.get("detected_document_type") or None,
            "document_summary": doc.get("document_summary") or None,
            "needs_extraction": needs,
            "text_preview": text[:_TEXT_PREVIEW] + ("...[truncated]" if len(text) > _TEXT_PREVIEW else ""),
        })
    pending = sum(1 for d in out if d["needs_extraction"])
    return {"evidence": out, "needs_extraction_count": pending, "total": len(out)}


@tool
def store_evidence_classifications(
    classifications: list,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
    state: Annotated[dict, InjectedState] = None,
) -> Command:
    """
    Apply document type + summary classifications back onto the evidence list.

    Args:
        classifications: list of {evidence_id, detected_document_type, document_summary}.
                         Only documents you classify need to be included.
    """
    s = state or {}
    evidence = [dict(e) for e in (s.get("evidence", []) or [])]
    by_id = {e.get("id"): e for e in evidence}

    applied = 0
    for c in classifications or []:
        if not isinstance(c, dict):
            continue
        eid = c.get("evidence_id") or c.get("id")
        doc = by_id.get(eid)
        if not doc:
            continue
        if c.get("detected_document_type"):
            doc["detected_document_type"] = c["detected_document_type"]
        if c.get("document_summary"):
            doc["document_summary"] = c["document_summary"]
        applied += 1

    return Command(update={
        "evidence": evidence,
        "messages": [ToolMessage(
            f"Applied {applied} evidence classification(s).",
            tool_call_id=tool_call_id,
        )],
    })
