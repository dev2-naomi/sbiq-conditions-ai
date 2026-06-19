"""
evaluation_tools.py — Tools for STEP_02..STEP_06: per-category fulfillment.

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
from tools.shared.guidelines import load_sections


@tool
def get_conditions_to_evaluate(
    category: str,
    state: Annotated[dict, InjectedState] = None,
) -> dict:
    """
    Load the conditions for an evaluation group together with each condition's
    candidate documents — every candidate's document_type and its structured
    extracted_fields (and raw text only if available) — so you can decide
    fulfillment.

    Args:
        category: the evaluation group — one of "income", "assets", "credit",
                  "property", "other".
    """
    s = state or {}
    return build_category_context(s, (category or "").strip().lower())


@tool
def load_guideline_sections(
    section_names: list,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
    state: Annotated[dict, InjectedState] = None,
) -> str:
    """
    Load NQMF underwriting guideline text for the given section headings, as a
    REFERENCE to clarify a condition's acceptance criteria or document-validity
    standards (e.g. how many months/years are required, recency windows, required
    schedules/signatures, acceptable document substitutes, reserve standards).

    Use this only when the condition text is ambiguous or you need the standard a
    document must meet. The CONDITION TEXT is always primary — never use the
    guidelines to invent requirements the condition did not ask for.

    Example section names (must match guideline headings): "ASSETS",
    "ASSET DOCUMENTATION", "QUALIFIED ASSETS", "CREDIT", "HOUSING HISTORY",
    "LIABILITIES", "FULL DOCUMENTATION", "EMPLOYMENT", "ALTERNATIVE DOCUMENTATION
    (ALT DOC)", "APPRAISALS", "PROPERTY INSURANCE", "HAZARD INSURANCE",
    "TITLE INSURANCE", "CHAIN OF TITLE", "PROPERTY CONSIDERATIONS", "COMPLIANCE",
    "BORROWER ELIGIBILITY". (If a heading isn't found, you'll get a not-found note.)

    Args:
        section_names: list of guideline section headings to load.
    """
    return load_sections(list(section_names or []))


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
    Store per-condition credit evaluations (includes identity, housing history,
    undisclosed property). Schema matches store_income_evaluations.
    """
    return store_evaluations_command("credit", evaluations, tool_call_id)


@tool
def store_property_evaluations(
    evaluations: list,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
    state: Annotated[dict, InjectedState] = None,
) -> Command:
    """
    Store per-condition property evaluations (appraisal, title, insurance, taxes,
    purchase agreement, flood). Schema matches store_income_evaluations.
    """
    return store_evaluations_command("property", evaluations, tool_call_id)


@tool
def store_other_evaluations(
    evaluations: list,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
    state: Annotated[dict, InjectedState] = None,
) -> Command:
    """
    Store per-condition miscellaneous/other evaluations. Schema matches
    store_income_evaluations.
    """
    return store_evaluations_command("other", evaluations, tool_call_id)
