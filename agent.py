"""
agent.py — Main orchestrator agent for the Conditions Evaluator.

Entry point referenced by langgraph.json:
    "conditions-evaluator": "./agent.py:agent"

Architecture (mirrors the predicted-conditions engine):
- Single ReAct agent loop using LangGraph StateGraph (orchestrator <-> tools).
- Dynamic tool scoping: only the current step's tools (+ general tools) are
  bound before each LLM invocation.
- Dynamic plan injection: the current step's plan markdown is injected as a
  transient system message (not persisted in history).
- Message summarization: completed-step messages are compressed into a compact
  summary before each LLM call, keeping only the current step in full detail.

Purpose: given loan CONDITIONS and uploaded EVIDENCE documents, evaluate whether
each condition is Fulfilled / Partially Fulfilled / Unfulfilled / Needs Review.
"""

from __future__ import annotations

import os
from typing import Annotated, Any, Literal

from typing_extensions import NotRequired, TypedDict

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt.tool_node import ToolNode

from step_loader import load_system_prompt, resolve_plan_for_step, resolve_tools_for_step
from tools import ALL_TOOLS


# ---------------------------------------------------------------------------
# Custom reducers
# ---------------------------------------------------------------------------


def _merge_dicts(old: dict | None, new: dict | None) -> dict:
    if old is None:
        old = {}
    if new is None:
        return old
    merged = dict(old)
    for k, v in new.items():
        if k in merged and isinstance(merged[k], dict) and isinstance(v, dict):
            merged[k] = _merge_dicts(merged[k], v)
        else:
            merged[k] = v
    return merged


def _append_list(old: list | None, new: list | None) -> list:
    return (old or []) + (new or [])


def _last_value(old: Any, new: Any) -> Any:  # noqa: ARG001
    return new


# ---------------------------------------------------------------------------
# State schema
# ---------------------------------------------------------------------------


class EvaluatorState(TypedDict, total=False):
    # ---- Input fields ----
    conditions_json: str       # Raw JSON list of conditions to evaluate
    evidence_json: str         # Raw JSON list of evidence documents
    loan_json: str             # Optional raw JSON loan scenario / borrower context
    env: str                   # "Test" | "Prod"

    # ---- Message history ----
    messages: Annotated[list[BaseMessage], add_messages]

    # ---- Internal fields ----
    eval_scenario: Annotated[NotRequired[dict], _merge_dicts]
    conditions: Annotated[NotRequired[list], _last_value]
    evidence: Annotated[NotRequired[list], _last_value]
    candidate_map: Annotated[NotRequired[dict], _merge_dicts]
    module_outputs: Annotated[NotRequired[dict], _merge_dicts]
    todos: Annotated[NotRequired[list], _append_list]
    current_step: Annotated[NotRequired[str], _last_value]
    step_reports: Annotated[NotRequired[dict], _merge_dicts]
    final_output: Annotated[NotRequired[dict], _last_value]
    dev_mode: NotRequired[dict]


# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------

_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-5")
_SYSTEM_PROMPT = load_system_prompt()

_llm_kwargs: dict = {
    "model": _MODEL,
    "max_tokens": 16384,
}
if "opus" in _MODEL:
    _llm_kwargs["thinking"] = {"type": "enabled", "budget_tokens": 8192}

_llm = ChatAnthropic(**_llm_kwargs)


# ---------------------------------------------------------------------------
# Default initial prompt (used when caller sends only data, no messages)
# ---------------------------------------------------------------------------

_DEFAULT_INITIAL_PROMPT = (
    "Execute the FULL Conditions Evaluation workflow from STEP_00 through STEP_08.\n\n"
    "You MUST complete ALL steps in sequence. Do NOT stop after a single step.\n"
    "Do NOT output a summary between steps — just call the tools, then call "
    "save_step_report to advance.\n\n"
    "Step sequence:\n"
    "  STEP_00: parse_conditions, parse_evidence, build_eval_scenario\n"
    "  STEP_01: get_evidence_for_extraction, store_evidence_classifications\n"
    "  STEP_02: deterministic_candidate_match, store_candidate_matches\n"
    "  STEP_03: get_conditions_to_evaluate('income'), store_income_evaluations\n"
    "  STEP_04: get_conditions_to_evaluate('assets'), store_assets_evaluations\n"
    "  STEP_05: get_conditions_to_evaluate('credit'), store_credit_evaluations\n"
    "  STEP_06: get_conditions_to_evaluate('property'), store_property_evaluations\n"
    "  STEP_07: get_conditions_to_evaluate('title_compliance'), store_title_compliance_evaluations\n"
    "  STEP_08: merge_evaluations, generate_final_output\n\n"
    "For STEP_03 through STEP_07: first load the category's conditions and their "
    "candidate evidence, then reason as a senior underwriter over the evidence text "
    "to decide fulfillment for each condition. Produce one evaluation per condition "
    "with result, confidence, satisfied_points, missing_or_unclear_points, and "
    "recommended_next_action.\n"
    "If a category has no conditions, immediately call save_step_report and move on."
)


# ---------------------------------------------------------------------------
# Message summarization
# ---------------------------------------------------------------------------

_STEP_SAVE_REPORT_PATTERN = "Step report saved for "


def _extract_step_from_tool_message(msg: ToolMessage) -> str | None:
    content = msg.content if isinstance(msg.content, str) else ""
    if _STEP_SAVE_REPORT_PATTERN in content:
        after = content.split(_STEP_SAVE_REPORT_PATTERN, 1)[1]
        return after.split(".")[0].strip()
    return None


def _summarize_completed_steps(
    messages: list[BaseMessage],
    current_step: str | None,
    step_reports: dict,
) -> list[BaseMessage]:
    """
    Compress messages from completed steps into a single summary message.

    Keeps the first HumanMessage (initial instructions) and all messages from
    the current step in full detail. Everything in between is replaced by a
    compact summary built from step_reports.
    """
    if not messages or not current_step or not step_reports:
        return messages

    boundary_idx = -1
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        if isinstance(msg, ToolMessage):
            step_id = _extract_step_from_tool_message(msg)
            if step_id and step_id != current_step:
                boundary_idx = i
                break

    if boundary_idx < 3:
        return messages

    # Extend boundary forward to include sibling ToolMessages of the same batch.
    boundary_tm = messages[boundary_idx]
    if isinstance(boundary_tm, ToolMessage) and hasattr(boundary_tm, "tool_call_id"):
        parent_ids: set[str] = set()
        for i in range(boundary_idx - 1, -1, -1):
            msg = messages[i]
            if isinstance(msg, AIMessage) and msg.tool_calls:
                ids = {tc.get("id", "") for tc in msg.tool_calls}
                if boundary_tm.tool_call_id in ids:
                    parent_ids = ids
                    break
            elif isinstance(msg, ToolMessage):
                continue
            else:
                break
        if parent_ids:
            for i in range(boundary_idx + 1, len(messages)):
                msg = messages[i]
                if isinstance(msg, ToolMessage) and hasattr(msg, "tool_call_id") and msg.tool_call_id in parent_ids:
                    boundary_idx = i
                elif not isinstance(msg, ToolMessage):
                    break

    summary_lines = ["[COMPLETED STEPS SUMMARY]", ""]
    for step_id, report in sorted(step_reports.items()):
        summary_text = report.get("summary", "No summary.")
        if len(summary_text) > 300:
            summary_text = summary_text[:300] + "..."
        summary_lines.append(f"## {step_id}: {summary_text}")
    summary_lines.append("")
    summary = "\n".join(summary_lines)

    first_human = None
    for msg in messages:
        if isinstance(msg, HumanMessage):
            first_human = msg
            break

    current_step_messages = messages[boundary_idx + 1:]

    needed_tool_call_ids: set[str] = set()
    for msg in current_step_messages:
        if isinstance(msg, ToolMessage) and hasattr(msg, "tool_call_id"):
            needed_tool_call_ids.add(msg.tool_call_id)
    for msg in current_step_messages:
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for tc in msg.tool_calls:
                needed_tool_call_ids.discard(tc.get("id", ""))

    prefix_messages: list[BaseMessage] = []
    if needed_tool_call_ids:
        for i in range(boundary_idx, -1, -1):
            msg = messages[i]
            if isinstance(msg, AIMessage) and msg.tool_calls:
                ids_in_msg = {tc.get("id", "") for tc in msg.tool_calls}
                if ids_in_msg & needed_tool_call_ids:
                    prefix_messages.insert(0, msg)
                    kept_ids = {
                        m.tool_call_id for m in current_step_messages
                        if isinstance(m, ToolMessage) and hasattr(m, "tool_call_id")
                    }
                    for j in range(i + 1, boundary_idx + 1):
                        m2 = messages[j]
                        if (
                            isinstance(m2, ToolMessage)
                            and hasattr(m2, "tool_call_id")
                            and m2.tool_call_id in ids_in_msg
                            and m2.tool_call_id not in kept_ids
                        ):
                            prefix_messages.append(m2)
                    needed_tool_call_ids -= ids_in_msg
                    if not needed_tool_call_ids:
                        break

    result: list[BaseMessage] = []
    if first_human:
        result.append(first_human)
    result.append(SystemMessage(content=summary))
    result.extend(prefix_messages)
    result.extend(current_step_messages)

    return result


# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------


def orchestrator_node(state: EvaluatorState) -> dict:
    """Main ReAct node: scope tools, inject plan, summarize, invoke the LLM."""
    step_tools = resolve_tools_for_step(state)
    llm_with_tools = _llm.bind_tools(step_tools)

    messages: list[BaseMessage] = list(state.get("messages", []))
    current_step = state.get("current_step") or "STEP_00"
    step_reports = state.get("step_reports", {})

    has_human = any(isinstance(m, HumanMessage) for m in messages)
    if not has_human:
        messages = [HumanMessage(content=_DEFAULT_INITIAL_PROMPT)] + messages

    messages = _summarize_completed_steps(messages, current_step, step_reports)

    plan = resolve_plan_for_step(state)
    system_parts: list[str] = []
    if plan:
        system_parts.append(f"[CURRENT STEP PLAN]\n\n{plan}")

    non_system: list[BaseMessage] = []
    for msg in messages:
        if isinstance(msg, SystemMessage):
            system_parts.append(msg.content if isinstance(msg.content, str) else str(msg.content))
        else:
            non_system.append(msg)

    if system_parts:
        injected = [SystemMessage(content="\n\n---\n\n".join(system_parts))] + non_system
    elif not non_system:
        injected = [SystemMessage(content=_SYSTEM_PROMPT)]
    else:
        injected = non_system

    response: AIMessage = llm_with_tools.invoke(injected)
    return {"messages": [response]}


def should_continue(state: EvaluatorState) -> Literal["tools", "end"]:
    messages = state.get("messages", [])
    if not messages:
        return "end"
    last = messages[-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "tools"
    return "end"


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

_tool_node = ToolNode(ALL_TOOLS)

_builder = StateGraph(EvaluatorState)
_builder.add_node("orchestrator", orchestrator_node)
_builder.add_node("tools", _tool_node)

_builder.set_entry_point("orchestrator")
_builder.add_conditional_edges(
    "orchestrator",
    should_continue,
    {"tools": "tools", "end": END},
)
_builder.add_edge("tools", "orchestrator")

agent = _builder.compile().with_config({"recursion_limit": 150})
