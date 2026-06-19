"""
normalize.py — Canonical normalization for conditions, evidence, verdicts.

The LLM (and upstream systems) format fields inconsistently. Everything passes
through here so downstream steps and the final output use a stable schema.
"""

from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Categories & evaluation routing
# ---------------------------------------------------------------------------

# Canonical condition categories (matches the reference conditions-ai taxonomy).
CANONICAL_CATEGORIES = [
    "income", "assets", "credit", "appraisal", "title",
    "insurance", "identity", "collateral", "other",
]

_CATEGORY_ALIASES = {
    "income": "income",
    "employment": "income",
    "asset": "assets",
    "assets": "assets",
    "reserves": "assets",
    "funds": "assets",
    "credit": "credit",
    "liabilities": "credit",
    "appraisal": "appraisal",
    "property": "appraisal",
    "valuation": "appraisal",
    "collateral": "collateral",
    "title": "title",
    "closing": "title",
    "vesting": "title",
    "insurance": "insurance",
    "hazard": "insurance",
    "flood": "insurance",
    "identity": "identity",
    "id": "identity",
    "borrower": "identity",
    "compliance": "other",
    "disclosure": "other",
    "other": "other",
    "misc": "other",
}

# Maps a canonical category to the evaluation step group that handles it.
EVAL_GROUPS = {
    "income": "income",
    "assets": "assets",
    "credit": "credit",
    "appraisal": "property",
    "collateral": "property",
    "title": "title_compliance",
    "insurance": "title_compliance",
    "identity": "title_compliance",
    "other": "title_compliance",
}

VALID_EVAL_GROUPS = ["income", "assets", "credit", "property", "title_compliance"]


def normalize_category(raw: Any) -> str:
    if not raw:
        return "other"
    key = str(raw).strip().lower().replace(" ", "_").replace("/", "_")
    if key in _CATEGORY_ALIASES:
        return _CATEGORY_ALIASES[key]
    # Fall back to substring match (e.g. "property_appraisal")
    for alias, canonical in _CATEGORY_ALIASES.items():
        if alias in key:
            return canonical
    return "other"


def eval_group_for_category(category: str) -> str:
    return EVAL_GROUPS.get(normalize_category(category), "title_compliance")


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


# ---------------------------------------------------------------------------
# Condition normalization
# ---------------------------------------------------------------------------


def normalize_condition(raw: dict) -> dict:
    if not isinstance(raw, dict):
        return {}
    category = normalize_category(_first(raw, "category", "condition_category", default="other"))
    cond = {
        "id": str(_first(raw, "id", "condition_id", "conditionId", default="")),
        "label": _first(raw, "label", "title", "name", default=None),
        "body": _first(raw, "body", "description", "text", "condition_text", default=""),
        "raw_text": _first(raw, "raw_text", "rawText", "raw", default=""),
        "category": category,
        "eval_group": eval_group_for_category(category),
        "stage": _first(raw, "stage", default="informational"),
        "priority": _first(raw, "priority", default="normal"),
    }
    if not cond["raw_text"]:
        cond["raw_text"] = cond["body"]
    if not cond["id"]:
        # Stable fallback id from the label/body
        base = (cond["label"] or cond["body"] or "condition")[:40]
        cond["id"] = "COND-" + re.sub(r"[^A-Za-z0-9]+", "-", base).strip("-").upper()
    return cond


def normalize_conditions(raw_list: Any) -> list[dict]:
    return [normalize_condition(c) for c in _as_list(raw_list) if isinstance(c, dict)]


# ---------------------------------------------------------------------------
# Evidence normalization
# ---------------------------------------------------------------------------


def normalize_evidence(raw: dict) -> dict:
    if not isinstance(raw, dict):
        return {}
    text = _first(raw, "document_text", "documentText", "text", "fullText", "full_text", default="")
    doc = {
        "id": str(_first(raw, "id", "evidence_id", "evidenceId", default="")),
        "file_name": _first(raw, "file_name", "fileName", "name", default="unknown"),
        "detected_document_type": _first(
            raw, "detected_document_type", "detectedDocumentType", "document_type", "type", default=""
        ),
        "document_summary": _first(raw, "document_summary", "documentSummary", "summary", default=""),
        "document_text": text,
        "page_count": _first(raw, "page_count", "pageCount", default=1),
    }
    if not doc["id"]:
        base = (doc["file_name"] or "doc")[:30]
        doc["id"] = "DOC-" + re.sub(r"[^A-Za-z0-9]+", "-", base).strip("-").upper()
    return doc


def normalize_evidence_list(raw_list: Any) -> list[dict]:
    return [normalize_evidence(e) for e in _as_list(raw_list) if isinstance(e, dict)]


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
        "evidence_used": _as_list(_first(raw, "evidence_used", "evidence_ids", "evidenceIds", default=[])),
        "recommended_next_action": _first(
            raw, "recommended_next_action", "next_action", "recommendation", default=""
        ),
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
    Given a normalized evaluation, derive an overall status and a
    needs_human_review flag using confidence + result, mirroring the
    HIL (human-in-the-loop) gating from the reference evaluator.
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
    elif result == "Fulfilled" and needs_human_review:
        overall = "needs_human_review"
    else:
        overall = "needs_human_review"

    return {
        "overall_status": overall,
        "needs_human_review": needs_human_review,
    }
