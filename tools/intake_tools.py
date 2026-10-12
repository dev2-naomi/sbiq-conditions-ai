"""
intake_tools.py — Tools for STEP_00: Intake & Normalization.

Inputs (preconditions-style, already in state):
- conditions_json   : conditions to evaluate (LOS/Encompass export shape)
- documents_json    : rack & stack (R&S) output — the documents the borrower submitted
- loan_file_xml     : loan scenario object (JSON object or JSON string). Required
                      keys are always populated; ReservesMonths and
                      FirstTimeHomeBuyer may be omitted. A legacy MISMO XML
                      string is still accepted.
- eligibility_json  : eligibility engine output (optional)
- borrower          : primary borrower identity (optional; dict or name string)
- coborrower        : co-borrower identity (optional; empty ⇒ single-party loan)
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
from tools.shared.ocr import merge_ocr_artifacts
from tools.shared.parties import (
    assign_doc_parties,
    condition_target_parties,
    resolve_parties,
)


def _loads(raw, default):
    if raw is None or raw == "":
        return default
    if isinstance(raw, (list, dict)):
        return raw
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        pass
    # Tolerate a leading log/prefix line (e.g. Encompass exports that arrive as
    # "... INFO - Raw conditions: [ ... ]"): retry from the first JSON bracket.
    if isinstance(raw, str):
        for opener, closer in (("[", "]"), ("{", "}")):
            start = raw.find(opener)
            end = raw.rfind(closer)
            if 0 <= start < end:
                try:
                    return json.loads(raw[start : end + 1])
                except (json.JSONDecodeError, TypeError):
                    continue
    return default


def _party_input(raw):
    """Coerce a borrower/coborrower input into a dict/string resolve_parties accepts.

    Accepts a dict, a JSON string ('{"first_name": ...}'), or a plain name string
    ("John Q Borrower"). Empty values become None (single-party / fallback path).
    """
    if raw is None or raw == "" or raw == {}:
        return None
    if isinstance(raw, dict):
        return raw or None
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return None
        if s[0] in "{[":
            try:
                return json.loads(s) or None
            except (json.JSONDecodeError, TypeError):
                return s
        return s
    return raw


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
    the documents the borrower submitted, already classified into a category and
    indexed into structured extracted fields (metadata) upstream. Per-document OCR
    text — referenced by the manifest's top-level `artifacts` (type "ocr") and
    assumed dereferenced/inlined upstream — is merged onto each document and split
    into pages for relevance triage + evaluation. Stored in state for downstream steps.
    """
    s = state or {}
    raw = _loads(s.get("documents_json"), [])

    artifacts: list = []
    if isinstance(raw, dict):
        artifacts = raw.get("artifacts") or []
        raw = raw.get("documents", raw.get("evidence", raw.get("items", [])))

    raw_docs = raw if isinstance(raw, list) else []
    if artifacts:
        raw_docs = merge_ocr_artifacts(raw_docs, artifacts)

    documents = normalize_documents(raw_docs)

    types = Counter(d.get("detected_document_type") or "unclassified" for d in documents)
    with_ocr = sum(1 for d in documents if d.get("has_ocr"))
    return Command(update={
        "evidence": documents,
        "messages": [ToolMessage(
            f"Parsed {len(documents)} submitted document(s). Types: {dict(types)}. "
            f"{with_ocr} document(s) have OCR text.",
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


# Always present on the loan-scenario object. The last two may be omitted.
_LOAN_FILE_FIELDS = (
    ("fico", ("FicoScore", "FICO", "fico")),
    ("ltv", ("LTV", "ltv")),
    ("dti", ("DTI", "dti")),
    ("loan_amount", ("LoanAmount", "loan_amount")),
    ("property_value", ("PropertyValue", "property_value")),
    ("property_type", ("PropertyType", "property_type")),
    ("occupancy", ("Occupancy", "occupancy")),
    ("loan_purpose", ("LoanPurpose", "loan_purpose")),
    ("income_doc_type", ("IncomeDocType", "income_doc_type")),
    ("channel", ("Channel", "channel")),
    ("borrower_type", ("BorrowerType", "borrower_type")),
    ("citizenship", ("Citizenship", "citizenship")),
    ("property_state", ("State", "property_state")),
    ("county", ("County", "county")),
    ("loan_type", ("LoanType", "loan_type")),
)
_LOAN_FILE_OPTIONAL = (
    ("reserves_months", ("ReservesMonths", "reserves_months")),
    ("first_time_home_buyer", ("FirstTimeHomeBuyer", "first_time_home_buyer")),
)


def _present(sources: list[dict], keys: tuple[str, ...]):
    """First non-empty value across sources. 0 and False count as present."""
    for src in sources:
        if not isinstance(src, dict):
            continue
        for key in keys:
            if key not in src:
                continue
            val = src[key]
            if val is None or val == "":
                continue
            return val
    return None


def _parse_loan_file(raw) -> tuple[dict, dict]:
    """Parse loan_file_xml into (loan fields, legacy MISMO scenario).

    Accepts a dict, a JSON string of that dict, or a legacy MISMO XML string.
    A single extra wrapping object is unwrapped when it holds the loan fields.
    """
    if raw is None or raw == "":
        return {}, {}
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return {}, {}
        if text.startswith("<"):
            return {}, _light_xml_scenario(text)
        raw = _loads(text, {})
    if not isinstance(raw, dict):
        return {}, {}
    if "FicoScore" not in raw and "LTV" not in raw:
        nested = [
            v for v in raw.values()
            if isinstance(v, dict) and ("FicoScore" in v or "LTV" in v)
        ]
        if len(nested) == 1:
            raw = nested[0]
    return raw, {}


def _loan_from_sources(loan_file: dict, app_data: dict, xml_scenario: dict) -> dict:
    """Loan-level facts. The loan file wins; eligibility fills gaps when sent."""
    sources = [loan_file, app_data]
    loan = {}
    for out, keys in _LOAN_FILE_FIELDS:
        val = _present(sources, keys)
        if val is not None:
            loan[out] = val
    for out, keys in _LOAN_FILE_OPTIONAL:
        val = _present(sources, keys)
        if val is not None:
            loan[out] = val
    if not loan.get("property_state") and xml_scenario.get("property_state"):
        loan["property_state"] = xml_scenario["property_state"]
    city = _present([app_data], ("City", "city")) or xml_scenario.get("property_city")
    if city:
        loan["property_city"] = city
    return loan


@tool
def build_eval_scenario(
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
    state: Annotated[dict, InjectedState] = None,
) -> Command:
    """
    Build a compact evaluation scenario summary from the parsed conditions and
    documents plus the loan scenario (loan_file_xml). eligibility_json is
    optional and is used for eligible programs and as a fallback for any loan
    field the loan file does not carry.

    Also resolves the loan's parties (primary borrower + optional co-borrower) and
    stamps each document with the party tag(s) it belongs to (`party_tags`) and each
    condition with the party tag(s) it applies to (`target_parties`), so STEP_01 can
    scope candidate documents per party. For single-borrower loans this is a no-op.
    """
    s = state or {}
    conditions = s.get("conditions", []) or []
    documents = s.get("evidence", []) or []

    eligibility = _loads(s.get("eligibility_json"), {})
    if not isinstance(eligibility, dict):
        eligibility = {}
    app_data = eligibility.get("application_data") if isinstance(eligibility.get("application_data"), dict) else {}
    eligible_programs = eligibility.get("eligible_programs") or eligibility.get("eligiblePrograms") or []

    loan_file, xml_scenario = _parse_loan_file(s.get("loan_file_xml"))
    loan_facts = _loan_from_sources(loan_file, app_data, xml_scenario)

    # ---- Party resolution + attribution ----
    parties = resolve_parties(
        borrower=_party_input(s.get("borrower")),
        coborrower=_party_input(s.get("coborrower")),
        eligibility=eligibility,
        xml_scenario=xml_scenario,
    )
    multi_party = len(parties) > 1

    documents = [{**d, "party_tags": assign_doc_parties(d, parties)} for d in documents]
    conditions = [{**c, "target_parties": condition_target_parties(c, parties)} for c in conditions]

    borrowers_view = [
        {"name": p["name"], "role": p["role"], "tag": p["tag"]} for p in parties
    ]

    scenario = {
        "loan": {
            "loan_id": conditions[0].get("loan_id") if conditions else None,
            "borrower_name": (parties[0]["name"] if parties else None)
            or app_data.get("BorrowerName") or xml_scenario.get("borrower_name"),
            **loan_facts,
        },
        "borrowers": borrowers_view,
        "eligible_programs": eligible_programs,
        "counts": {
            "conditions": len(conditions),
            "submitted_documents": len(documents),
            "parties": len(parties),
        },
        "conditions_by_group": dict(Counter(c.get("eval_group") for c in conditions)),
        "document_types": dict(Counter(d.get("detected_document_type") or "unclassified" for d in documents)),
    }

    party_note = ""
    if multi_party:
        co = next((p for p in parties if p["tag"] == "coborrower"), None)
        party_note = (
            f" Parties: borrower={parties[0]['name']}"
            + (f", coborrower={co['name']}." if co else ".")
            + " Documents and conditions tagged per party for scoping."
        )

    return Command(update={
        "eval_scenario": scenario,
        "conditions": conditions,
        "evidence": documents,
        "parties": parties,
        "messages": [ToolMessage(
            "Built evaluation scenario: "
            f"{scenario['counts']['conditions']} conditions, "
            f"{scenario['counts']['submitted_documents']} documents. "
            f"Groups: {scenario['conditions_by_group']}. "
            f"Eligible programs: {eligible_programs}." + party_note,
            tool_call_id=tool_call_id,
        )],
    })
