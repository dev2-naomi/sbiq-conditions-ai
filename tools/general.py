"""
general.py — General-purpose tools available at every step.
"""

from __future__ import annotations

import datetime
import json

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command
from typing_extensions import Annotated

_STEP_SEQUENCE = [
    "STEP_00", "STEP_01", "STEP_02", "STEP_03",
    "STEP_04", "STEP_05", "STEP_06", "STEP_07",
]


def _input_item_count(raw, *wrapper_keys) -> int:
    """Best-effort count of items in a raw input (list, JSON string, or wrapped dict)."""
    if raw is None or raw == "":
        return 0
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return 0
    if isinstance(raw, list):
        return len(raw)
    if isinstance(raw, dict):
        for key in wrapper_keys:
            if isinstance(raw.get(key), list):
                return len(raw[key])
    return 0


def _intake_gate(state: dict) -> list[str]:
    """
    Deterministic guard for STEP_00: the agent must actually RUN the intake tools
    (not just mark todos) before the step report is accepted. Returns a list of
    problems; an empty list means intake is complete.
    """
    s = state or {}
    problems: list[str] = []

    if not s.get("eval_scenario"):
        problems.append("build_eval_scenario has not run (eval_scenario missing from state)")

    if _input_item_count(s.get("conditions_json"), "conditions", "items") > 0 and not s.get("conditions"):
        problems.append("parse_conditions has not run (conditions_json has items but state.conditions is empty)")

    if _input_item_count(s.get("documents_json"), "documents", "evidence", "items") > 0 and not s.get("evidence"):
        problems.append("parse_documents has not run (documents_json has items but state.evidence is empty)")

    return problems


@tool
def write_todo(
    substep_id: str,
    name: str,
    status: str,
    note: str = "",
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
    state: Annotated[dict, InjectedState] = None,
) -> Command:
    """
    Track the status of a substep.

    Args:
        substep_id: The substep identifier (e.g. "0.1").
        name: Human-readable substep name.
        status: One of "pending", "in_progress", "completed", "skipped", "failed".
        note: Optional note about this substep's result or reason for status.
    """
    entry = {
        "substep_id": substep_id,
        "name": name,
        "status": status,
        "note": note,
        "updated_at": datetime.datetime.utcnow().isoformat(),
    }
    return Command(update={
        "todos": [entry],
        "messages": [ToolMessage(f"Todo '{substep_id}' set to {status}", tool_call_id=tool_call_id)],
    })


@tool
def save_step_report(
    step_id: str,
    summary: str,
    outputs: dict,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
    state: Annotated[dict, InjectedState] = None,
) -> Command:
    """
    Persist the findings for a completed step and advance to the next step.
    You MUST call this after completing each step's tools.

    Args:
        step_id: The step identifier (e.g. "STEP_00").
        summary: A one-paragraph plain-English summary of what this step found.
        outputs: Dict of key results produced by this step.
    """
    # Deterministic gate: STEP_00 cannot be closed unless the intake tools actually
    # ran. This prevents the agent from marking todos "completed" and saving the
    # report without populating conditions/evidence/eval_scenario in state.
    if step_id == "STEP_00":
        problems = _intake_gate(state)
        if problems:
            return Command(update={
                "messages": [ToolMessage(
                    "STEP_00 report rejected — intake is incomplete: "
                    + "; ".join(problems)
                    + ". You must actually CALL parse_conditions, parse_documents, then "
                    "build_eval_scenario (calling write_todo is not enough) before saving "
                    "the STEP_00 report. Call the missing tool(s) now, then retry "
                    "save_step_report.",
                    tool_call_id=tool_call_id,
                )],
            })

    report = {
        "step_id": step_id,
        "summary": summary,
        "outputs": outputs,
        "completed_at": datetime.datetime.utcnow().isoformat(),
    }

    idx = _STEP_SEQUENCE.index(step_id) if step_id in _STEP_SEQUENCE else -1
    if idx >= 0 and idx + 1 < len(_STEP_SEQUENCE):
        next_step = _STEP_SEQUENCE[idx + 1]
        msg = f"Step report saved for {step_id}. Advancing to {next_step}. Continue with {next_step} tools now."
    else:
        next_step = step_id
        msg = f"Step report saved for {step_id}. This is the final step."

    return Command(update={
        "step_reports": {step_id: report},
        "current_step": next_step,
        "messages": [ToolMessage(msg, tool_call_id=tool_call_id)],
    })


@tool
def get_workflow_status(
    state: Annotated[dict, InjectedState] = None,
) -> dict:
    """
    Return a summary of overall workflow progress: current step, completed steps,
    and pending todos.
    """
    s = state or {}
    return {
        "current_step": s.get("current_step"),
        "completed_steps": list(s.get("step_reports", {}).keys()),
        "todos": s.get("todos", []),
    }
