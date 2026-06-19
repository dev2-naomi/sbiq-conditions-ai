"""
evaluation_tools.py — Tools for STEP_03..STEP_07: per-category fulfillment.

`get_conditions_to_evaluate` is shared across all evaluation steps; each step
has its own thin `store_*_evaluations` tool that enforces the correct storage
slot. The LLM does the underwriting reasoning between the two calls.
"""

from __future__ import annotations

from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command
from typing_extensions import Annotated

from tools.shared.evaluation import build_category_context, store_evaluations_command


@tool
def get_conditions_to_evaluate(
    category: str,
    state: Annotated[dict, InjectedState] = None,
) -> dict:
    """
    Load the conditions for an evaluation group together with the full text of
    each condition's candidate evidence documents, so you can decide fulfillment.

    Args:
        category: the evaluation group — one of "income", "assets", "credit",
                  "property", "title_compliance".
    """
    s = state or {}
    return build_category_context(s, (category or "").strip().lower())


@tool
def store_income_evaluations(
    evaluations: list,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
    state: Annotated[dict, InjectedState] = None,
) -> Command:
    """
    Store per-condition income evaluations.

    Args:
        evaluations: list of objects, one per condition, each with:
            condition_id, result ("Fulfilled"|"Partially Fulfilled"|
            "Unfulfilled"|"Needs Review"), confidence (0-100), short_reason,
            satisfied_points[], missing_or_unclear_points[], evidence_used[],
            recommended_next_action.
    """
    return store_evaluations_command("income", evaluations, tool_call_id)


@tool
def store_assets_evaluations(
    evaluations: list,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
    state: Annotated[dict, InjectedState] = None,
) -> Command:
    """
    Store per-condition asset/reserves evaluations. Schema matches
    store_income_evaluations.
    """
    return store_evaluations_command("assets", evaluations, tool_call_id)


@tool
def store_credit_evaluations(
    evaluations: list,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
    state: Annotated[dict, InjectedState] = None,
) -> Command:
    """
    Store per-condition credit evaluations. Schema matches
    store_income_evaluations.
    """
    return store_evaluations_command("credit", evaluations, tool_call_id)


@tool
def store_property_evaluations(
    evaluations: list,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
    state: Annotated[dict, InjectedState] = None,
) -> Command:
    """
    Store per-condition property/appraisal/collateral evaluations. Schema
    matches store_income_evaluations.
    """
    return store_evaluations_command("property", evaluations, tool_call_id)


@tool
def store_title_compliance_evaluations(
    evaluations: list,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
    state: Annotated[dict, InjectedState] = None,
) -> Command:
    """
    Store per-condition title/insurance/compliance/identity/other evaluations.
    Schema matches store_income_evaluations.
    """
    return store_evaluations_command("title_compliance", evaluations, tool_call_id)
