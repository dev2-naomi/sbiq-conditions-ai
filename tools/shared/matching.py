"""
matching.py — Deterministic candidate matching between conditions and documents.

This is the cheap, fast pre-filter that proposes which submitted documents could
satisfy which conditions, before the LLM does qualitative triage.

Two signals:
  1. AUTHORITATIVE — each condition's `result_document_ids` are the documents the
     borrower actually submitted/attached for that condition upstream. These are
     near-certain candidates.
  2. HEURISTIC — category-aware document-type keywords + token overlap, used to
     surface plausible matches the upstream linkage may have missed.
"""

from __future__ import annotations

import re
from typing import Any

# Document-type keywords associated with each condition category (5 groups).
_CATEGORY_DOC_KEYWORDS = {
    "income": [
        "paystub", "pay stub", "w-2", "w2", "1099", "voe", "verification of employment",
        "tax return", "1040", "schedule c", "schedule e", "schedule k-1", "k-1",
        "profit and loss", "p&l", "bank statement income", "cpa letter",
        "operating agreement", "business license", "award letter", "pension",
        "social security", "1008", "1003",
    ],
    "assets": [
        "bank statement", "asset statement", "statement", "401k", "ira", "brokerage",
        "gift letter", "reserves", "deposit", "retirement account", "evod",
        "earnest money", "title receipt",
    ],
    "credit": [
        "credit report", "credit", "tradeline", "letter of explanation", "loe",
        "verification of rent", "vor", "verification of mortgage", "vom",
        "housing history", "cancelled check", "driver", "license", "passport",
        "identification", "closing disclosure", "cd",
    ],
    "property": [
        "appraisal", "valuation", "1004", "1007", "1073", "rent schedule",
        "inspection", "flood cert", "flood certification", "hazard", "insurance",
        "declaration", "title commitment", "cpl", "purchase agreement", "tax bill",
        "property tax", "deed", "survey", "preliminary title", "chain of title",
    ],
    "other": ["1008", "1003", "loan estimate", "disclosure"],
}

_STOPWORDS = {
    "the", "a", "an", "of", "to", "and", "or", "for", "in", "on", "is", "are",
    "be", "must", "with", "provide", "borrower", "loan", "condition", "please",
    "required", "require", "show", "showing", "all", "most", "recent", "copy",
    "copies", "document", "documents", "this", "that", "from", "by", "as", "if",
    "corr", "client", "letter", "within", "days", "date", "will",
}


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {w for w in words if len(w) > 2 and w not in _STOPWORDS}


def _doc_blob(doc: dict) -> str:
    """Searchable text for a document: type/summary + structured extracted fields.

    R&S gives us the document type (category name) and structured extracted fields
    rather than raw OCR, so the blob is built from those (field keys + values)."""
    parts = [str(doc.get(k, "")) for k in ("file_name", "detected_document_type", "document_summary")]
    fields = doc.get("extracted_fields") or {}
    if isinstance(fields, dict):
        for k, v in fields.items():
            parts.append(str(k))
            parts.append(str(v))
    return " ".join(parts).lower()


def score_pair(condition: dict, doc: dict) -> tuple[float, str]:
    """Heuristic score that `doc` satisfies `condition`. Returns (0-100, reason)."""
    category = condition.get("category", "other")
    cond_text = " ".join(str(condition.get(k, "")) for k in ("label", "body", "raw_text"))
    cond_tokens = _tokens(cond_text)
    doc_blob = _doc_blob(doc)
    doc_tokens = _tokens(doc_blob)

    reasons: list[str] = []
    score = 0.0

    kw_hits = [kw for kw in _CATEGORY_DOC_KEYWORDS.get(category, []) if kw in doc_blob]
    if kw_hits:
        score += 45.0
        reasons.append(f"doc type matches {category} keywords: {kw_hits[:3]}")

    direct = [kw for kw in _CATEGORY_DOC_KEYWORDS.get(category, []) if kw in cond_text.lower()]
    direct_in_doc = [kw for kw in direct if kw in doc_blob]
    if direct_in_doc:
        score += 25.0
        reasons.append(f"condition references documents present in evidence: {direct_in_doc[:3]}")

    overlap = cond_tokens & doc_tokens
    if overlap:
        score += min(30.0, len(overlap) * 6.0)
        reasons.append(f"shared terms: {sorted(overlap)[:5]}")

    confidence = max(0.0, min(100.0, round(score, 1)))
    return confidence, ("; ".join(reasons) if reasons else "no strong signal")


def deterministic_match(
    conditions: list[dict],
    documents: list[dict],
    threshold: float = 30.0,
) -> dict[str, list[dict]]:
    """
    Build a candidate map: condition_id -> list of candidate entries
    {evidence_id, confidence, reason, source}.

    Authoritative `result_document_ids` links are always included (source=
    "result_document_ids"); heuristic matches at/above `threshold` are added
    (source="heuristic"), excluding duplicates.
    """
    docs_by_id = {str(d.get("id")): d for d in documents}
    candidate_map: dict[str, list[dict]] = {}

    for cond in conditions:
        cid = cond.get("id")
        if not cid:
            continue
        matches: list[dict] = []
        linked_ids = set()

        # 1) Authoritative pre-links from upstream submission.
        for rid in cond.get("result_document_ids", []) or []:
            doc = docs_by_id.get(str(rid))
            if doc:
                matches.append({
                    "evidence_id": doc.get("id"),
                    "confidence": 100.0,
                    "reason": "submitted/attached for this condition (result_document_ids)",
                    "source": "result_document_ids",
                })
                linked_ids.add(str(doc.get("id")))

        # 2) Heuristic matches (skip already-linked docs).
        for doc in documents:
            if str(doc.get("id")) in linked_ids:
                continue
            conf, reason = score_pair(cond, doc)
            if conf >= threshold:
                matches.append({
                    "evidence_id": doc.get("id"),
                    "confidence": conf,
                    "reason": reason,
                    "source": "heuristic",
                })

        matches.sort(key=lambda m: m["confidence"], reverse=True)
        candidate_map[cid] = matches

    return candidate_map
