"""
intake_tools.py — Tools for STEP_00: Intake & Normalization.

Inputs (preconditions-style, already in state):
- conditions_json   : conditions to evaluate (LOS/Encompass export shape)
- documents_json    : rack & stack (R&S) output — the documents the borrower submitted
- loan_file_xml     : MISMO XML loan scenario (optional context)
- eligibility_json  : eligibility engine output (optional context)
"""

from __future__ import annotations

import json
import re
from collections import Counter

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command
from typing_extensions import Annotated

from tools.shared.normalize import normalize_conditions, normalize_documents


def _loads(raw, default):
    if raw is None or raw == "":
        return default
    if isinstance(raw, (list, dict)):
        return raw
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return default


@tool
def parse_conditions(
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
    state: Annotated[dict, InjectedState] = None,
) -> Command:
    """
    Parse and normalize the raw conditions list (conditions_json). Handles the
    LOS/Encompass export shape ({"condition": {"data": {...}, ...}}), normalizes
    each condition's category, derives its evaluation group, and preserves the
    upstream result_document_ids that link submitted documents to the condition.
    """
    s = state or {}
    raw = _loads(s.get("conditions_json"), [])
    if isinstance(raw, dict):
        raw = raw.get("conditions", raw.get("items", []))
    conditions = normalize_conditions(raw)

    by_group = Counter(c["eval_group"] for c in conditions)
    with_docs = sum(1 for c in conditions if c.get("result_document_ids"))

    return Command(update={
        "conditions": conditions,
        "messages": [ToolMessage(
            f"Parsed {len(conditions)} condition(s). By group: {dict(by_group)}. "
            f"{with_docs} condition(s) have pre-linked submitted documents.",
            tool_call_id=tool_call_id,
        )],
    })


@tool
def parse_documents(
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
    state: Annotated[dict, InjectedState] = None,
) -> Command:
    """
    Parse and normalize the rack & stack (R&S) document output (documents_json):
    the documents the borrower submitted, already classified and OCR'd upstream.
    Stored in state for matching and evaluation.
    """
    s = state or {}
    raw = _loads(s.get("documents_json"), [])
    if isinstance(raw, dict):
        raw = raw.get("documents", raw.get("evidence", raw.get("items", [])))
    documents = normalize_documents(raw)

    types = Counter(d.get("detected_document_type") or "unclassified" for d in documents)
    return Command(update={
        "evidence": documents,
        "messages": [ToolMessage(
            f"Parsed {len(documents)} submitted document(s). Types: {dict(types)}",
            tool_call_id=tool_call_id,
        )],
    })


_XML_FIELDS = {
    "borrower_first": r"<(?:\w+:)?(?:FirstName)>([^<]+)<",
    "borrower_last": r"<(?:\w+:)?(?:LastName)>([^<]+)<",
    "property_city": r"<(?:\w+:)?(?:CityName)>([^<]+)<",
    "property_state": r"<(?:\w+:)?(?:StateCode)>([^<]+)<",
}


def _light_xml_scenario(xml: str) -> dict:
    """Best-effort, dependency-free extraction of a few MISMO fields."""
    out: dict = {}
    if not xml:
        return out
    for key, pat in _XML_FIELDS.items():
        m = re.search(pat, xml)
        if m:
            out[key] = m.group(1).strip()
    name = " ".join(x for x in [out.pop("borrower_first", None), out.pop("borrower_last", None)] if x)
    if name:
        out["borrower_name"] = name
    return out


@tool
def build_eval_scenario(
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
    state: Annotated[dict, InjectedState] = None,
) -> Command:
    """
    Build a compact evaluation scenario summary from the parsed conditions and
    documents plus the loan scenario (loan_file_xml) and eligibility output
    (eligibility_json). The eligibility application_data, when present, is the
    authoritative source for loan-level numbers.
    """
    s = state or {}
    conditions = s.get("conditions", []) or []
    documents = s.get("evidence", []) or []

    eligibility = _loads(s.get("eligibility_json"), {})
    if not isinstance(eligibility, dict):
        eligibility = {}
    app_data = eligibility.get("application_data") if isinstance(eligibility.get("application_data"), dict) else {}
    eligible_programs = eligibility.get("eligible_programs") or eligibility.get("eligiblePrograms") or []

    xml_scenario = _light_xml_scenario(s.get("loan_file_xml") or "")

    scenario = {
        "loan": {
            "loan_id": conditions[0].get("loan_id") if conditions else None,
            "borrower_name": app_data.get("BorrowerName") or xml_scenario.get("borrower_name"),
            "property_state": app_data.get("State") or xml_scenario.get("property_state"),
            "property_city": app_data.get("City") or xml_scenario.get("property_city"),
            "loan_amount": app_data.get("LoanAmount"),
            "ltv": app_data.get("LTV"),
            "fico": app_data.get("FICO"),
        },
        "eligible_programs": eligible_programs,
        "counts": {
            "conditions": len(conditions),
            "submitted_documents": len(documents),
        },
        "conditions_by_group": dict(Counter(c.get("eval_group") for c in conditions)),
        "document_types": dict(Counter(d.get("detected_document_type") or "unclassified" for d in documents)),
    }

    return Command(update={
        "eval_scenario": scenario,
        "messages": [ToolMessage(
            "Built evaluation scenario: "
            f"{scenario['counts']['conditions']} conditions, "
            f"{scenario['counts']['submitted_documents']} documents. "
            f"Groups: {scenario['conditions_by_group']}. "
            f"Eligible programs: {eligible_programs}.",
            tool_call_id=tool_call_id,
        )],
    })
