"""
matching.py — Deterministic candidate matching between conditions and evidence.

This is the cheap, fast pre-filter that proposes which evidence documents could
plausibly satisfy which conditions, before the LLM does qualitative triage. It
uses category-aware document-type keywords plus token overlap scoring.
"""

from __future__ import annotations

import re
from typing import Any

# Document-type keywords associated with each condition category. Used to give
# a document a head-start score when its detected type matches the category.
_CATEGORY_DOC_KEYWORDS = {
    "income": [
        "paystub", "pay stub", "w-2", "w2", "1099", "voe", "verification of employment",
        "tax return", "1040", "schedule c", "schedule e", "k-1", "profit and loss",
        "p&l", "bank statement", "award letter", "pension", "social security",
    ],
    "assets": [
        "bank statement", "asset", "statement", "401k", "ira", "brokerage",
        "gift letter", "reserves", "deposit", "retirement account",
    ],
    "credit": [
        "credit report", "credit", "tradeline", "letter of explanation", "loe",
        "verification of rent", "vor", "verification of mortgage", "vom", "housing history",
    ],
    "appraisal": [
        "appraisal", "valuation", "bpo", "1004", "1007", "rent schedule",
        "inspection", "property", "1025",
    ],
    "collateral": ["appraisal", "title", "deed", "survey", "property"],
    "title": [
        "title", "title commitment", "deed", "vesting", "closing disclosure", "cd",
        "settlement statement", "payoff", "escrow", "preliminary title",
    ],
    "insurance": [
        "insurance", "hazard", "hoi", "flood", "declaration page", "binder", "policy",
    ],
    "identity": [
        "driver license", "drivers license", "passport", "id", "identification",
        "social security card", "ssn", "patriot act",
    ],
    "other": [],
}

_STOPWORDS = {
    "the", "a", "an", "of", "to", "and", "or", "for", "in", "on", "is", "are",
    "be", "must", "with", "provide", "borrower", "loan", "condition", "please",
    "required", "require", "show", "showing", "all", "most", "recent", "copy",
    "copies", "document", "documents", "this", "that", "from", "by", "as", "if",
}


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {w for w in words if len(w) > 2 and w not in _STOPWORDS}


def _doc_blob(doc: dict) -> str:
    return " ".join(
        str(doc.get(k, ""))
        for k in ("file_name", "detected_document_type", "document_summary")
    ).lower()


def score_pair(condition: dict, doc: dict) -> tuple[float, str]:
    """
    Score how likely `doc` satisfies `condition`. Returns (confidence 0-100, reason).
    """
    category = condition.get("category", "other")
    cond_text = " ".join(
        str(condition.get(k, "")) for k in ("label", "body", "raw_text")
    )
    cond_tokens = _tokens(cond_text)
    doc_blob = _doc_blob(doc)
    doc_tokens = _tokens(doc_blob)

    reasons: list[str] = []
    score = 0.0

    # 1) Category doc-type keyword hit in the document blob.
    kw_hits = [kw for kw in _CATEGORY_DOC_KEYWORDS.get(category, []) if kw in doc_blob]
    if kw_hits:
        score += 45.0
        reasons.append(f"doc type matches {category} keywords: {kw_hits[:3]}")

    # 2) Condition keyword appears directly in the doc blob.
    direct = [kw for kw in _CATEGORY_DOC_KEYWORDS.get(category, []) if kw in cond_text.lower()]
    direct_in_doc = [kw for kw in direct if kw in doc_blob]
    if direct_in_doc:
        score += 25.0
        reasons.append(f"condition references documents present in evidence: {direct_in_doc[:3]}")

    # 3) Token overlap between condition and document.
    overlap = cond_tokens & doc_tokens
    if overlap:
        overlap_score = min(30.0, len(overlap) * 6.0)
        score += overlap_score
        reasons.append(f"shared terms: {sorted(overlap)[:5]}")

    confidence = max(0.0, min(100.0, round(score, 1)))
    reason = "; ".join(reasons) if reasons else "no strong signal"
    return confidence, reason


def deterministic_match(
    conditions: list[dict],
    evidence: list[dict],
    threshold: float = 30.0,
) -> dict[str, list[dict]]:
    """
    Build a candidate map: condition_id -> list of candidate evidence entries
    {evidence_id, confidence, reason} that score at/above `threshold`.
    """
    candidate_map: dict[str, list[dict]] = {}
    for cond in conditions:
        cid = cond.get("id")
        if not cid:
            continue
        matches: list[dict] = []
        for doc in evidence:
            conf, reason = score_pair(cond, doc)
            if conf >= threshold:
                matches.append({
                    "evidence_id": doc.get("id"),
                    "confidence": conf,
                    "reason": reason,
                })
        matches.sort(key=lambda m: m["confidence"], reverse=True)
        candidate_map[cid] = matches
    return candidate_map
