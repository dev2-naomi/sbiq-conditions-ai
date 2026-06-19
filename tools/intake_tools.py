"""
intake_tools.py — Tools for STEP_00: Intake & Normalization.
"""

from __future__ import annotations

import json
from collections import Counter

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command
from typing_extensions import Annotated

from tools.shared.normalize import normalize_conditions, normalize_evidence_list


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
    Parse and normalize the raw conditions list from the input (conditions_json).
    Normalizes category, derives the evaluation group for each condition, and
    stores the result in state for downstream steps.
    """
    s = state or {}
    raw = _loads(s.get("conditions_json"), [])
    # Accept either a bare list or an object with a "conditions" key.
    if isinstance(raw, dict):
        raw = raw.get("conditions", raw.get("items", []))
    conditions = normalize_conditions(raw)

    by_group = Counter(c["eval_group"] for c in conditions)
    by_category = Counter(c["category"] for c in conditions)

    return Command(update={
        "conditions": conditions,
        "messages": [ToolMessage(
            f"Parsed {len(conditions)} condition(s). "
            f"By group: {dict(by_group)}. By category: {dict(by_category)}.",
            tool_call_id=tool_call_id,
        )],
    })


@tool
def parse_evidence(
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
    state: Annotated[dict, InjectedState] = None,
) -> Command:
    """
    Parse and normalize the raw evidence document list from the input
    (evidence_json) and store it in state for downstream steps.
    """
    s = state or {}
    raw = _loads(s.get("evidence_json"), [])
    if isinstance(raw, dict):
        raw = raw.get("evidence", raw.get("documents", raw.get("items", [])))
    evidence = normalize_evidence_list(raw)

    names = [e.get("file_name") for e in evidence]
    return Command(update={
        "evidence": evidence,
        "messages": [ToolMessage(
            f"Parsed {len(evidence)} evidence document(s): {names}",
            tool_call_id=tool_call_id,
        )],
    })


@tool
def build_eval_scenario(
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
    state: Annotated[dict, InjectedState] = None,
) -> Command:
    """
    Build a compact evaluation scenario summary from the parsed conditions,
    evidence, and the optional loan_json (borrower/loan context). This summary
    frames the downstream evaluation.
    """
    s = state or {}
    conditions = s.get("conditions", []) or []
    evidence = s.get("evidence", []) or []
    loan = _loads(s.get("loan_json"), {})
    if not isinstance(loan, dict):
        loan = {}

    scenario = {
        "loan": {
            "loan_number": loan.get("loanNumber") or loan.get("loan_number"),
            "borrower_name": loan.get("borrowerName") or loan.get("borrower_name"),
            "property_address": loan.get("propertyAddress") or loan.get("property_address"),
            "loan_amount": loan.get("loanAmount") or loan.get("loan_amount"),
            "loan_type": loan.get("loanType") or loan.get("loan_type"),
        },
        "counts": {
            "conditions": len(conditions),
            "evidence_documents": len(evidence),
        },
        "conditions_by_group": dict(Counter(c.get("eval_group") for c in conditions)),
        "conditions_by_category": dict(Counter(c.get("category") for c in conditions)),
        "evidence_types": dict(Counter(e.get("detected_document_type") or "unclassified" for e in evidence)),
    }

    return Command(update={
        "eval_scenario": scenario,
        "messages": [ToolMessage(
            "Built evaluation scenario: "
            f"{scenario['counts']['conditions']} conditions, "
            f"{scenario['counts']['evidence_documents']} documents. "
            f"Groups: {scenario['conditions_by_group']}.",
            tool_call_id=tool_call_id,
        )],
    })
