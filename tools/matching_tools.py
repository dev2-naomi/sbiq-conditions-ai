"""
matching_tools.py — Tools for STEP_01: Candidate Matching.

Most conditions arrive WITHOUT pre-linked documents (result_document_ids is usually
empty), so this step actively associates submitted documents to conditions. The
tool returns a matching workspace — every condition plus the full document
inventory (type + extracted fields) and a cheap deterministic shortlist — and the
LLM decides the final condition -> candidate-document map.
"""

from __future__ import annotations

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command
from typing_extensions import Annotated

from tools.shared.matching import deterministic_match
from tools.shared.ocr import PREVIEW_PAGES, first_pages, full_text
from tools.shared.parties import doc_matches_condition_party

_FIELD_VALUE_CAP = 200


def _compact_fields(fields: dict) -> dict:
    """Trim long field values so the inventory stays context-friendly."""
    out: dict = {}
    for k, v in (fields or {}).items():
        if isinstance(v, str) and len(v) > _FIELD_VALUE_CAP:
            out[k] = v[:_FIELD_VALUE_CAP] + "..."
        else:
            out[k] = v
    return out


@tool
def deterministic_candidate_match(
    threshold: float = 20.0,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
    state: Annotated[dict, InjectedState] = None,
) -> dict:
    """
    Build the matching workspace for associating documents to conditions. Returns:
      - `conditions`: each condition's label/body/category, its authoritative
        `prelinked_document_ids` (result_document_ids — usually empty), and a cheap
        `proposed_candidates` shortlist (keyword/field heuristic — a HINT only).
      - `document_inventory`: EVERY submitted document with its `document_type`,
        `extracted_fields`, and an `ocr_preview` (first ~2 OCR pages). When the
        preview is inconclusive, call `get_document_ocr` to read more pages or the
        full OCR before deciding relevance.

    You then decide the real map and pass it to `store_candidate_matches`. This is
    triage (plausibility), NOT a fulfillment decision.

    Args:
        threshold: minimum heuristic confidence (0-100) for the proposed shortlist.
                   Kept low for recall. (Authoritative pre-links are always included.)
    """
    s = state or {}
    conditions = s.get("conditions", []) or []
    documents = s.get("evidence", []) or []
    parties = s.get("parties", []) or []
    multi_party = len(parties) > 1
    docs_by_id = {str(d.get("id")): d for d in documents}
    proposed = deterministic_match(conditions, documents, threshold=threshold)

    inventory = []
    for d in documents:
        pages = d.get("ocr_pages") or []
        entry = {
            "evidence_id": d.get("id"),
            "document_type": d.get("detected_document_type"),
            "extracted_fields": _compact_fields(d.get("extracted_fields") or {}),
            "ocr_preview": first_pages(pages, n=PREVIEW_PAGES) if pages else "",
            "ocr_total_pages": len(pages),
        }
        if multi_party:
            entry["party_tags"] = d.get("party_tags") or []
        inventory.append(entry)

    conditions_view = []
    for c in conditions:
        cid = c.get("id")
        # Drop heuristic proposals that belong to the other party (keep
        # authoritative result_document_ids links regardless).
        shortlist = []
        for cand in proposed.get(cid, []):
            doc = docs_by_id.get(str(cand.get("evidence_id")))
            if (
                cand.get("source") == "result_document_ids"
                or doc is None
                or doc_matches_condition_party(doc, c, parties)
            ):
                shortlist.append(cand)
        view = {
            "condition_id": cid,
            "label": c.get("label"),
            "body": c.get("body"),
            "category": c.get("category"),
            "prelinked_document_ids": c.get("result_document_ids", []) or [],
            "proposed_candidates": shortlist,
        }
        if multi_party:
            view["target_parties"] = c.get("target_parties") or []
        conditions_view.append(view)

    total = sum(len(v["proposed_candidates"]) for v in conditions_view)
    note = (
        "Pre-links are usually empty — actively match each condition against "
        "the document_inventory using document_type, extracted_fields AND the "
        "ocr_preview. Read each candidate's first OCR pages to confirm the "
        "document is within the condition's context; escalate to "
        "get_document_ocr(full=True) only when the preview is inconclusive. "
        "Prefer recall. Then call store_candidate_matches with "
        "{condition_id: [evidence_id, ...]}."
    )
    result = {
        "conditions": conditions_view,
        "document_inventory": inventory,
        "total_documents": len(documents),
        "total_proposed_links": total,
        "note": note,
    }
    if multi_party:
        result["parties"] = [
            {"name": p["name"], "tag": p["tag"], "role": p["role"]} for p in parties
        ]
        result["party_note"] = (
            "This loan has multiple parties. Only match a document to a condition "
            "when their parties overlap: a condition's `target_parties` must "
            "intersect a document's `party_tags`. Loan-level documents and generic "
            "conditions are tagged for ALL parties and match anyone. Cross-party "
            "links (e.g. the borrower's VOE for a co-borrower condition) are dropped "
            "when the map is stored."
        )
    return result


@tool
def get_document_ocr(
    evidence_id: str,
    full: bool = False,
    max_pages: int = PREVIEW_PAGES,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
    state: Annotated[dict, InjectedState] = None,
) -> dict:
    """
    Fetch the OCR text for one document, to confirm whether it is relevant to (or
    satisfies) a condition. Read the first pages first; escalate to the full OCR
    only when those pages are inconclusive.

    Args:
        evidence_id: the document's evidence id (from the document_inventory /
                     candidate_documents).
        full: when True, return the full OCR text (capped); otherwise return only
              the first `max_pages` pages.
        max_pages: number of leading pages to return when `full` is False.
    """
    s = state or {}
    documents = s.get("evidence", []) or []
    doc = next((d for d in documents if str(d.get("id")) == str(evidence_id)), None)
    if not doc:
        return {"evidence_id": evidence_id, "error": "no document with that evidence_id"}

    pages = doc.get("ocr_pages") or []
    if not pages:
        return {
            "evidence_id": evidence_id,
            "document_type": doc.get("detected_document_type"),
            "ocr_available": False,
            "note": "No OCR text for this document; rely on extracted_fields.",
        }

    if full:
        text = full_text(pages)
        returned = "full"
    else:
        text = first_pages(pages, n=max_pages)
        returned = f"first_{min(max_pages, len(pages))}_pages"

    return {
        "evidence_id": evidence_id,
        "document_type": doc.get("detected_document_type"),
        "ocr_available": True,
        "total_pages": len(pages),
        "returned": returned,
        "ocr_text": text,
    }


@tool
def store_candidate_matches(
    candidate_map: dict,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
    state: Annotated[dict, InjectedState] = None,
) -> Command:
    """
    Store the final condition -> candidate-document map after your triage.

    On multi-party loans, cross-party links are dropped deterministically: a
    candidate is kept only when its document's `party_tags` overlap the condition's
    `target_parties` (loan-level docs / generic conditions default to all parties,
    so they're never dropped).

    Args:
        candidate_map: dict of condition_id -> list of candidate entries. Each
                       entry may be a plain document id string or an object
                       {evidence_id, confidence, reason, source}.
    """
    s = state or {}
    parties = s.get("parties", []) or []
    multi_party = len(parties) > 1
    cond_by_id = {c.get("id"): c for c in (s.get("conditions", []) or [])}
    docs_by_id = {str(d.get("id")): d for d in (s.get("evidence", []) or [])}

    normalized: dict[str, list] = {}
    total = 0
    dropped = 0
    for cid, cands in (candidate_map or {}).items():
        cond = cond_by_id.get(cid, {})
        entries = []
        for cand in cands or []:
            if isinstance(cand, str):
                entry = {"evidence_id": cand, "confidence": None, "reason": "llm_match", "source": "llm"}
            elif isinstance(cand, dict) and cand.get("evidence_id"):
                entry = {
                    "evidence_id": cand.get("evidence_id"),
                    "confidence": cand.get("confidence"),
                    "reason": cand.get("reason", "llm_match"),
                    "source": cand.get("source", "llm"),
                }
            else:
                continue
            if multi_party and entry.get("source") != "result_document_ids":
                doc = docs_by_id.get(str(entry["evidence_id"]))
                if doc is not None and not doc_matches_condition_party(doc, cond, parties):
                    dropped += 1
                    continue
            entries.append(entry)
        normalized[cid] = entries
        total += len(entries)

    msg = f"Stored candidate map: {len(normalized)} condition(s), {total} total link(s)."
    if dropped:
        msg += f" Dropped {dropped} cross-party link(s)."
    return Command(update={
        "candidate_map": normalized,
        "messages": [ToolMessage(msg, tool_call_id=tool_call_id)],
    })
