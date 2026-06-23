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
    candidate documents — every candidate's document_type, its structured
    extracted_fields, and an ocr_preview (first OCR pages). Call get_document_ocr
    for the full OCR when the preview is insufficient — so you can decide fulfillment.

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
        evaluations: list of objects, one per condition. EVERY field is required:
            - condition_id (str): the condition's id.
            - result (str): "Fulfilled"|"Partially Fulfilled"|"Unfulfilled"|"Needs Review".
            - confidence (number 0-100): your confidence in the verdict. ALWAYS set a
              real number — never omit it (a missing confidence is treated as 0 and
              forces human review).
            - short_reason (str): one-sentence justification.
            - satisfied_points (list[str]), missing_or_unclear_points (list[str]).
            - evidence_used (list[str]): the evidence_id(s) of the candidate documents
              you actually relied on. ALWAYS list the ids you cited in your reasoning;
              do not leave this empty when you used a document.
            - recommended_next_action (str).
            - guideline_refs (list[str]): any guideline sections you consulted.
    """
    return store_evaluations_command("income", evaluations, tool_call_id, state)


@tool
def store_assets_evaluations(
    evaluations: list,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
    state: Annotated[dict, InjectedState] = None,
) -> Command:
    """
    Store per-condition asset/reserves evaluations. Schema matches
    store_income_evaluations (every field required, including a real numeric
    confidence and the evidence_used ids you relied on).
    """
    return store_evaluations_command("assets", evaluations, tool_call_id, state)


@tool
def store_credit_evaluations(
    evaluations: list,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
    state: Annotated[dict, InjectedState] = None,
) -> Command:
    """
    Store per-condition credit evaluations (includes identity, housing history,
    undisclosed property). Schema matches store_income_evaluations (every field
    required, including a real numeric confidence and the evidence_used ids).
    """
    return store_evaluations_command("credit", evaluations, tool_call_id, state)


@tool
def store_property_evaluations(
    evaluations: list,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
    state: Annotated[dict, InjectedState] = None,
) -> Command:
    """
    Store per-condition property evaluations (appraisal, title, insurance, taxes,
    purchase agreement, flood). Schema matches store_income_evaluations (every field
    required, including a real numeric confidence and the evidence_used ids).
    """
    return store_evaluations_command("property", evaluations, tool_call_id, state)


@tool
def store_other_evaluations(
    evaluations: list,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
    state: Annotated[dict, InjectedState] = None,
) -> Command:
    """
    Store per-condition miscellaneous/other evaluations. Schema matches
    store_income_evaluations (every field required, including a real numeric
    confidence and the evidence_used ids).
    """
    return store_evaluations_command("other", evaluations, tool_call_id, state)
