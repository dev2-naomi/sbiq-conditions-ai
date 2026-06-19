"""
normalize.py — Canonical normalization for conditions, documents, verdicts.

Conditions arrive in the LOS (Encompass-style) export shape:

    {"condition": {"id": 5601, "name": "...", "prior_to": "Docs",
                   "data": {"Title": "...", "Description": "...", "Category": "Assets", ...},
                   "result_document_ids": [25988, ...], "related_category_ids": [...]}}

Documents arrive as the rack & stack (R&S) output produced upstream. Everything
passes through here so downstream steps use a stable schema.
"""

from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Categories & evaluation routing
# ---------------------------------------------------------------------------

# Canonical categories match the LOS condition taxonomy seen in production
# (Assets / Credit / Property / Income / Misc), collapsed to lowercase.
CANONICAL_CATEGORIES = ["income", "assets", "credit", "property", "other"]

_CATEGORY_ALIASES = {
    # income
    "income": "income",
    "employment": "income",
    "self_employment": "income",
    # assets
    "asset": "assets",
    "assets": "assets",
    "reserves": "assets",
    "funds": "assets",
    "funds_to_close": "assets",
    # credit (LOS bundles identity, housing history, undisclosed property here)
    "credit": "credit",
    "liabilities": "credit",
    "identity": "credit",
    "id": "credit",
    # property (LOS bundles appraisal, title, insurance, taxes, flood here)
    "property": "property",
    "appraisal": "property",
    "valuation": "property",
    "collateral": "property",
    "title": "property",
    "closing": "property",
    "insurance": "property",
    "hazard": "property",
    "flood": "property",
    # other / misc
    "misc": "other",
    "miscellaneous": "other",
    "compliance": "other",
    "disclosure": "other",
    "other": "other",
}

# Each canonical category maps directly to its evaluation step group.
EVAL_GROUPS = {c: c for c in CANONICAL_CATEGORIES}

VALID_EVAL_GROUPS = ["income", "assets", "credit", "property", "other"]


def normalize_category(raw: Any) -> str:
    if not raw:
        return "other"
    key = str(raw).strip().lower().replace(" ", "_").replace("/", "_")
    if key in _CATEGORY_ALIASES:
        return _CATEGORY_ALIASES[key]
    for alias, canonical in _CATEGORY_ALIASES.items():
        if alias in key:
            return canonical
    return "other"


def eval_group_for_category(category: str) -> str:
    return EVAL_GROUPS.get(normalize_category(category), "other")


# ---------------------------------------------------------------------------
# Verdict / result normalization
# ---------------------------------------------------------------------------

VALID_RESULTS = ["Fulfilled", "Partially Fulfilled", "Unfulfilled", "Needs Review"]

_RESULT_ALIASES = {
    "fulfilled": "Fulfilled",
    "satisfied": "Fulfilled",
    "met": "Fulfilled",
    "complete": "Fulfilled",
    "pass": "Fulfilled",
    "partially_fulfilled": "Partially Fulfilled",
    "partial": "Partially Fulfilled",
    "partially fulfilled": "Partially Fulfilled",
    "incomplete": "Partially Fulfilled",
    "unfulfilled": "Unfulfilled",
    "not_fulfilled": "Unfulfilled",
    "not fulfilled": "Unfulfilled",
    "fail": "Unfulfilled",
    "missing": "Unfulfilled",
    "needs_review": "Needs Review",
    "needs review": "Needs Review",
    "review": "Needs Review",
    "unclear": "Needs Review",
    "unknown": "Needs Review",
}


def normalize_result(raw: Any) -> str:
    if not raw:
        return "Needs Review"
    key = str(raw).strip().lower()
    if key in _RESULT_ALIASES:
        return _RESULT_ALIASES[key]
    for alias, canonical in _RESULT_ALIASES.items():
        if alias in key:
            return canonical
    return "Needs Review"


# ---------------------------------------------------------------------------
# Field coercion helpers
# ---------------------------------------------------------------------------


def _as_list(v: Any) -> list:
    if v is None:
        return []
    if isinstance(v, list):
        return v
    if isinstance(v, (str, int, float)):
        return [v]
    return list(v)


def _first(d: dict, *keys, default=None):
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return default


def _coerce_confidence(v: Any) -> float:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return 0.0
    if 0.0 <= n <= 1.0:
        n *= 100.0
    return max(0.0, min(100.0, round(n, 1)))


def _ids_to_str(values: Any) -> list[str]:
    return [str(v) for v in _as_list(values) if v not in (None, "")]


# ---------------------------------------------------------------------------
# Condition normalization (LOS / Encompass export shape)
# ---------------------------------------------------------------------------


def normalize_condition(raw: dict) -> dict:
    if not isinstance(raw, dict):
        return {}

    # Unwrap {"condition": {...}}
    if isinstance(raw.get("condition"), dict):
        raw = raw["condition"]

    data = raw.get("data") if isinstance(raw.get("data"), dict) else {}

    category_raw = _first(data, "Category") or _first(raw, "category", "condition_category", default="other")
    category = normalize_category(category_raw)

    cond = {
        "id": str(_first(raw, "id", "condition_id", "conditionId", default="")
                  or _first(data, "ID", default="")),
        "label": _first(data, "Title") or _first(raw, "label", "title", "name", default=None),
        "body": _first(data, "Description") or _first(raw, "body", "description", "text", default=""),
        "raw_text": _first(raw, "raw_text", "rawText", default="") or _first(raw, "name", default=""),
        "category": category,
        "eval_group": eval_group_for_category(category),
        "stage": _first(data, "PriorTo") or _first(raw, "prior_to", "stage", default="informational"),
        "priority": _first(raw, "priority", default="normal"),
        "status": _first(data, "Status") or _first(raw, "status", default="Added"),
        "for_role": _first(data, "ForRole", default=None),
        # Documents the borrower already submitted/attached for this condition.
        "result_document_ids": _ids_to_str(_first(raw, "result_document_ids", "resultDocumentIds", default=[])),
        "related_category_ids": _ids_to_str(_first(raw, "related_category_ids", "relatedCategoryIds", default=[])),
        "loan_id": _first(raw, "loan_id", "loanId", default=None),
    }

    if not cond["raw_text"]:
        cond["raw_text"] = cond["body"]
    if not cond["id"]:
        base = (cond["label"] or cond["body"] or "condition")[:40]
        cond["id"] = "COND-" + re.sub(r"[^A-Za-z0-9]+", "-", base).strip("-").upper()
    return cond


def normalize_conditions(raw_list: Any) -> list[dict]:
    return [normalize_condition(c) for c in _as_list(raw_list) if isinstance(c, dict)]


# ---------------------------------------------------------------------------
# Document (rack & stack output) normalization
# ---------------------------------------------------------------------------


def normalize_document(raw: dict) -> dict:
    if not isinstance(raw, dict):
        return {}
    text = _first(
        raw, "document_text", "documentText", "extracted_text", "extractedText",
        "ocr_text", "text", "fullText", "full_text", "content", default="",
    )
    doc = {
        "id": str(_first(raw, "id", "document_id", "documentId", "doc_id", "result_document_id", default="")),
        "file_name": _first(raw, "file_name", "fileName", "name", "title", default="unknown"),
        "detected_document_type": _first(
            raw, "detected_document_type", "detectedDocumentType", "document_type",
            "documentType", "doc_type", "type", "classification", default="",
        ),
        "document_summary": _first(raw, "document_summary", "documentSummary", "summary", default=""),
        "document_text": text,
        "page_count": _first(raw, "page_count", "pageCount", "pages", default=1),
    }
    if not doc["id"]:
        base = (doc["file_name"] or "doc")[:30]
        doc["id"] = "DOC-" + re.sub(r"[^A-Za-z0-9]+", "-", base).strip("-").upper()
    return doc


def normalize_documents(raw_list: Any) -> list[dict]:
    return [normalize_document(e) for e in _as_list(raw_list) if isinstance(e, dict)]


# ---------------------------------------------------------------------------
# Evaluation result normalization
# ---------------------------------------------------------------------------


def normalize_evaluation(raw: dict, default_category: str = "other") -> dict:
    if not isinstance(raw, dict):
        return {}
    return {
        "condition_id": str(_first(raw, "condition_id", "conditionId", "id", default="")),
        "category": normalize_category(_first(raw, "category", default=default_category)),
        "result": normalize_result(_first(raw, "result", "verdict", "status", default="Needs Review")),
        "confidence": _coerce_confidence(_first(raw, "confidence", "score", default=0)),
        "short_reason": _first(raw, "short_reason", "reason", "explanation", default=""),
        "satisfied_points": _as_list(_first(raw, "satisfied_points", "satisfied", default=[])),
        "missing_or_unclear_points": _as_list(
            _first(raw, "missing_or_unclear_points", "missing", "unclear", default=[])
        ),
        "evidence_used": _ids_to_str(_first(raw, "evidence_used", "evidence_ids", "evidenceIds", default=[])),
        "recommended_next_action": _first(
            raw, "recommended_next_action", "next_action", "recommendation", default=""
        ),
        # Guideline section(s) consulted to justify the verdict (for auditability).
        "guideline_refs": _as_list(_first(raw, "guideline_refs", "guideline_sections", "guidelines", default=[])),
    }


def normalize_evaluations(raw_list: Any, default_category: str = "other") -> list[dict]:
    out = []
    for e in _as_list(raw_list):
        if isinstance(e, dict):
            ev = normalize_evaluation(e, default_category)
            if ev.get("condition_id"):
                out.append(ev)
    return out


# ---------------------------------------------------------------------------
# Overall condition status derivation (AI status -> needs human review flag)
# ---------------------------------------------------------------------------


def derive_overall_status(evaluation: dict, manual_review_threshold: float = 50.0) -> dict:
    """
    Derive an overall status and a needs_human_review flag from a normalized
    evaluation, mirroring the human-in-the-loop gating of the reference app.
    """
    result = evaluation.get("result", "Needs Review")
    confidence = float(evaluation.get("confidence", 0) or 0)

    needs_human_review = (
        result in ("Needs Review", "Partially Fulfilled", "Unfulfilled")
        or confidence < manual_review_threshold
    )

    if result == "Fulfilled" and not needs_human_review:
        overall = "fulfilled"
    elif result == "Partially Fulfilled":
        overall = "partially_fulfilled"
    elif result == "Unfulfilled":
        overall = "unfulfilled"
    else:
        overall = "needs_human_review"

    return {
        "overall_status": overall,
        "needs_human_review": needs_human_review,
    }
