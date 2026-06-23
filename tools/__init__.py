"""
tools package — exports ALL_TOOLS for the orchestrator and step_loader.

Tool scoping per step is handled at the LLM layer by step_loader using the
registry; the ToolNode receives every tool so any scoped subset can execute.
"""

from __future__ import annotations

from tools.general import get_workflow_status, save_step_report, write_todo
from tools.intake_tools import build_eval_scenario, parse_conditions, parse_documents
from tools.matching_tools import (
    deterministic_candidate_match,
    get_document_ocr,
    store_candidate_matches,
)
from tools.evaluation_tools import (
    get_conditions_to_evaluate,
    load_guideline_sections,
    store_assets_evaluations,
    store_credit_evaluations,
    store_income_evaluations,
    store_other_evaluations,
    store_property_evaluations,
)
from tools.aggregation_tools import generate_final_output, merge_evaluations

# General (always available)
GENERAL_TOOLS = [write_todo, save_step_report, get_workflow_status]

# Per-step
STEP_00_TOOLS = [parse_conditions, parse_documents, build_eval_scenario]
STEP_01_TOOLS = [deterministic_candidate_match, get_document_ocr, store_candidate_matches]
STEP_02_TOOLS = [get_conditions_to_evaluate, get_document_ocr, load_guideline_sections, store_income_evaluations]
STEP_03_TOOLS = [get_conditions_to_evaluate, get_document_ocr, load_guideline_sections, store_assets_evaluations]
STEP_04_TOOLS = [get_conditions_to_evaluate, get_document_ocr, load_guideline_sections, store_credit_evaluations]
STEP_05_TOOLS = [get_conditions_to_evaluate, get_document_ocr, load_guideline_sections, store_property_evaluations]
STEP_06_TOOLS = [get_conditions_to_evaluate, get_document_ocr, load_guideline_sections, store_other_evaluations]
STEP_07_TOOLS = [merge_evaluations, generate_final_output]

ALL_TOOLS = [
    *GENERAL_TOOLS,
    *STEP_00_TOOLS,
    *STEP_01_TOOLS,
    # get_conditions_to_evaluate / get_document_ocr / load_guideline_sections are shared across 02-06.
    get_conditions_to_evaluate,
    get_document_ocr,
    load_guideline_sections,
    store_income_evaluations,
    store_assets_evaluations,
    store_credit_evaluations,
    store_property_evaluations,
    store_other_evaluations,
    *STEP_07_TOOLS,
]

# De-duplicate while preserving order (some tools appear in multiple step lists).
_seen: set[str] = set()
_unique: list = []
for _t in ALL_TOOLS:
    if _t.name not in _seen:
        _seen.add(_t.name)
        _unique.append(_t)
ALL_TOOLS = _unique
