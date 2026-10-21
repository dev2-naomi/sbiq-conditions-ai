"""Cross-check a document against the loan.

Compared values:
- property address and loan number come from the loan file
- borrower / co-borrower names come from the borrower and coborrower inputs
- insurance coverage is compared to the loan amount
- a signer is compared to the borrowers on the loan

A mismatch names both sides. A missing value is its own reason. Both are written
into ``missing_or_unclear_points``. A check that the document does not carry, and
that the condition does not ask for, is left alone.
"""

from __future__ import annotations

import re
from typing import Any

from tools.shared.parties import _name_matches

_ADDRESS_KEYS = (
    "property_address", "propertyAddress", "address", "subject_property",
    "insured_property", "situs_address",
)
_LOAN_NUMBER_KEYS = (
    "loan_number", "loanNumber", "loan_no", "loan_num", "lender_loan_number",
)
_COVERAGE_KEYS = (
    "dwelling_coverage", "coverage_amount", "coverage_a", "insurance_coverage",
    "coverage",
)
_SIGNER_KEYS = ("signer", "signed_by", "signatory", "signature_name")
_SUBJECT_NAME_KEYS = (
    "insured", "named_insured", "name", "borrower", "borrower_name", "employee",
    "customer", "applicant", "account_holder", "entity_name", "vesting",
    "drawer", "received_from",
)
_SUBJECT_NAME_LIST_KEYS = ("borrowers", "applicants", "members", "employees")
_IGNORE_NAMES = {
    "", "unknown", "n/a", "na", "none", "null", "lender", "mortgagee",
    "loss payee", "isaoa", "atima",
}


def _first_field(fields: dict, keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in fields and fields[key] not in (None, ""):
            return fields[key]
    return None


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        parts = [
            value.get(k) for k in ("street", "address", "line1", "city", "state", "zip")
            if value.get(k)
        ]
        if parts:
            return " ".join(str(p) for p in parts)
        name = value.get("name") or value.get("full_name")
        return str(name).strip() if name else ""
    return str(value).strip()


def _norm_address(value: Any) -> str:
    text = _as_text(value).lower()
    text = text.replace(",", " ")
    text = re.sub(r"[.#]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _addresses_match(a: Any, b: Any) -> bool:
    na, nb = _norm_address(a), _norm_address(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
    return len(shorter) >= 8 and shorter in longer


def _norm_loan_number(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", _as_text(value).lower())


def _loan_numbers_match(a: Any, b: Any) -> bool:
    na, nb = _norm_loan_number(a), _norm_loan_number(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
    return len(shorter) >= 4 and longer.endswith(shorter)


def _money(value: Any) -> float | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    digits = re.sub(r"[^\d.]", "", str(value))
    if not digits or digits == ".":
        return None
    try:
        return float(digits)
    except ValueError:
        return None


def _format_money(value: Any) -> str:
    raw = _as_text(value)
    if raw and any(ch in raw for ch in "$€£"):
        return raw
    amount = _money(value)
    if amount is None:
        return raw
    if amount == int(amount):
        return f"${int(amount):,}"
    return f"${amount:,.2f}"


def _person_names(value: Any) -> list[str]:
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, dict):
        first = value.get("first_name") or value.get("firstName") or value.get("first")
        last = value.get("last_name") or value.get("lastName") or value.get("last")
        if first or last:
            full = " ".join(str(x) for x in (first, last) if x).strip()
            return [full] if full else []
        for key in ("name", "full_name", "employee"):
            if value.get(key):
                return _person_names(value.get(key))
    return []


def _subject_names(fields: dict) -> list[str]:
    names: list[str] = []
    for key in _SUBJECT_NAME_KEYS:
        if key in fields:
            names.extend(_person_names(fields[key]))
    for key in _SUBJECT_NAME_LIST_KEYS:
        val = fields.get(key)
        if isinstance(val, list):
            for item in val:
                if isinstance(item, dict):
                    names.extend(_person_names(item.get("name") or item.get("employee") or item))
                else:
                    names.extend(_person_names(item))
    seen: set[str] = set()
    out: list[str] = []
    for name in names:
        key = re.sub(r"\s+", " ", name.strip().lower())
        if key in _IGNORE_NAMES or key in seen:
            continue
        seen.add(key)
        out.append(name.strip())
    return out


def _party_names(parties: list[dict]) -> list[str]:
    out: list[str] = []
    for party in parties or []:
        name = (party or {}).get("name")
        if name and str(name).strip():
            out.append(str(name).strip())
    return out


def _matches_any_party(name: str, party_names: list[str]) -> bool:
    return any(_name_matches(name, party) for party in party_names)


def _party_list(party_names: list[str]) -> str:
    quoted = [f'"{name}"' for name in party_names]
    if len(quoted) == 1:
        return f"the loan borrower is {quoted[0]}"
    if len(quoted) == 2:
        return f"the loan borrowers are {quoted[0]} and {quoted[1]}"
    return "the loan borrowers are " + ", ".join(quoted[:-1]) + f", and {quoted[-1]}"


def _condition_text(condition: dict) -> str:
    return " ".join(
        str(condition.get(key) or "") for key in ("label", "body", "raw_text")
    ).lower()


def _condition_requires_coverage(condition: dict) -> bool:
    text = _condition_text(condition)
    return any(token in text for token in ("coverage", "hazard", "insurance", "dwelling"))


def _condition_asks_for_address(condition: dict) -> bool:
    return "address" in _condition_text(condition)


def _condition_asks_for_loan_number(condition: dict) -> bool:
    return "loan number" in _condition_text(condition)


def _condition_asks_for_name(condition: dict) -> bool:
    text = _condition_text(condition)
    return any(token in text for token in ("borrower name", "entity name", "in the name"))


def _condition_asks_for_signer(condition: dict) -> bool:
    text = _condition_text(condition)
    return any(token in text for token in ("signer", "signed", "signature", "execute"))


def _key_state(fields: dict, keys: tuple[str, ...]) -> str:
    """``present`` when a key has a value, ``empty`` when a key is blank, else ``absent``."""
    seen = False
    for key in keys:
        if key not in fields:
            continue
        seen = True
        val = fields[key]
        if val is None or val == "" or val == []:
            continue
        if isinstance(val, str) and not val.strip():
            continue
        return "present"
    return "empty" if seen else "absent"


def _coverage_value(fields: dict) -> Any:
    return _first_field(fields, _COVERAGE_KEYS)


def document_mismatches(
    doc: dict,
    loan: dict,
    parties: list[dict],
    condition: dict,
) -> list[str]:
    """Mismatch sentences for one document. Empty when nothing conflicts."""
    fields = doc.get("extracted_fields") or {}
    if not isinstance(fields, dict):
        return []
    loan = loan or {}
    reasons: list[str] = []

    doc_address = _first_field(fields, _ADDRESS_KEYS)
    loan_address = loan.get("property_address")
    address_state = _key_state(fields, _ADDRESS_KEYS)
    if doc_address and loan_address and not _addresses_match(doc_address, loan_address):
        reasons.append(
            "Property address does not match: the document shows "
            f'"{_as_text(doc_address)}" and the loan file shows "{_as_text(loan_address)}".'
        )
    elif doc_address and not loan_address:
        reasons.append(
            "Property address is missing: the loan file does not show a property address "
            f'and the document shows "{_as_text(doc_address)}".'
        )
    elif not doc_address and loan_address and (
        address_state == "empty" or _condition_asks_for_address(condition)
    ):
        reasons.append(
            "Property address is missing: the document does not show a property address."
        )

    doc_loan_no = _first_field(fields, _LOAN_NUMBER_KEYS)
    loan_no = loan.get("loan_number")
    loan_no_state = _key_state(fields, _LOAN_NUMBER_KEYS)
    if doc_loan_no and loan_no and not _loan_numbers_match(doc_loan_no, loan_no):
        reasons.append(
            "Loan number does not match: the document shows "
            f'"{_as_text(doc_loan_no)}" and the loan file shows "{_as_text(loan_no)}".'
        )
    elif doc_loan_no and not loan_no:
        reasons.append(
            "Loan number is missing: the loan file does not show a loan number "
            f'and the document shows "{_as_text(doc_loan_no)}".'
        )
    elif not doc_loan_no and loan_no and (
        loan_no_state == "empty" or _condition_asks_for_loan_number(condition)
    ):
        reasons.append(
            "Loan number is missing: the document does not show a loan number."
        )

    party_names = _party_names(parties)
    subject_names = _subject_names(fields)
    name_state = _key_state(fields, _SUBJECT_NAME_KEYS + _SUBJECT_NAME_LIST_KEYS)
    if subject_names and party_names and not any(
        _matches_any_party(name, party_names) for name in subject_names
    ):
        shown = ", ".join(f'"{name}"' for name in subject_names)
        reasons.append(
            f"Borrower name does not match: the document shows {shown} and {_party_list(party_names)}."
        )
    elif subject_names and not party_names:
        shown = ", ".join(f'"{name}"' for name in subject_names)
        reasons.append(
            f"Borrower name is missing: the loan does not show a borrower and the document shows {shown}."
        )
    elif not subject_names and party_names and (
        name_state == "empty" or _condition_asks_for_name(condition)
    ):
        reasons.append(
            "Borrower name is missing: the document does not show a borrower or entity name."
        )

    signer = _first_field(fields, _SIGNER_KEYS)
    signer_text = _as_text(signer)
    signer_state = _key_state(fields, _SIGNER_KEYS)
    if signer_text and party_names and not _matches_any_party(signer_text, party_names):
        reasons.append(
            "Signer is not a borrower on the loan: the document is signed by "
            f'"{signer_text}" and {_party_list(party_names)}.'
        )
    elif signer_text and not party_names:
        reasons.append(
            "Signer is missing: the loan does not show a borrower and the document is signed by "
            f'"{signer_text}".'
        )
    elif not signer_text and (signer_state == "empty" or _condition_asks_for_signer(condition)):
        reasons.append("Signer is missing: the document does not show a signer.")

    if _condition_requires_coverage(condition):
        coverage_raw = _coverage_value(fields)
        coverage = _money(coverage_raw)
        loan_amount = _money(loan.get("loan_amount"))
        if coverage is not None and loan_amount is not None and coverage < loan_amount:
            reasons.append(
                "Coverage is too low: the document shows "
                f"{_format_money(coverage_raw)} and the loan amount is {_format_money(loan_amount)}."
            )
        elif coverage is not None and loan_amount is None:
            reasons.append(
                "Coverage amount is missing: the loan file does not show a loan amount "
                f"and the document shows {_format_money(coverage_raw)}."
            )
        elif coverage is None:
            reasons.append(
                "Coverage amount is missing: the document does not show a coverage amount."
            )

    return reasons


def _docs_for_condition(
    condition_id: str,
    documents: list[dict],
    candidate_map: dict,
    evidence_used: list[str],
) -> list[dict]:
    by_id = {str(doc.get("id")): doc for doc in documents if doc.get("id") not in (None, "")}
    ids = [str(eid) for eid in evidence_used if str(eid) in by_id]
    if not ids:
        for cand in candidate_map.get(condition_id, []) or []:
            eid = cand.get("evidence_id") if isinstance(cand, dict) else cand
            if eid not in (None, "") and str(eid) in by_id and str(eid) not in ids:
                ids.append(str(eid))
    return [by_id[eid] for eid in ids]


def blocking_mismatches(
    condition: dict,
    documents: list[dict],
    candidate_map: dict,
    evidence_used: list[str],
    loan: dict,
    parties: list[dict],
) -> list[str]:
    """Reasons that keep this condition from being satisfied.

    A check blocks only when every examined document that has the value fails it.
    One document that matches the loan clears that check.
    """
    docs = _docs_for_condition(
        str(condition.get("id") or ""), documents, candidate_map, evidence_used
    )
    if not docs:
        return []

    per_doc = [document_mismatches(doc, loan, parties, condition) for doc in docs]
    if not any(per_doc):
        return []

    failed: dict[str, list[str]] = {}
    for reasons in per_doc:
        for reason in reasons:
            key = reason.split(":", 1)[0]
            bucket = failed.setdefault(key, [])
            if reason not in bucket:
                bucket.append(reason)

    passes = _passed_checks(docs, loan, parties, condition)
    out: list[str] = []
    for key, reasons in failed.items():
        if key in passes:
            continue
        out.extend(reasons)
    return out


def _passed_checks(
    docs: list[dict],
    loan: dict,
    parties: list[dict],
    condition: dict,
) -> set[str]:
    """Check titles a document cleared because it had the value and it matched."""
    cleared: set[str] = set()
    party_names = _party_names(parties)
    for doc in docs:
        fields = doc.get("extracted_fields") or {}
        if not isinstance(fields, dict):
            continue
        doc_address = _first_field(fields, _ADDRESS_KEYS)
        if doc_address and loan.get("property_address") and _addresses_match(doc_address, loan.get("property_address")):
            cleared.update({"Property address does not match", "Property address is missing"})
        doc_loan_no = _first_field(fields, _LOAN_NUMBER_KEYS)
        if doc_loan_no and loan.get("loan_number") and _loan_numbers_match(doc_loan_no, loan.get("loan_number")):
            cleared.update({"Loan number does not match", "Loan number is missing"})
        names = _subject_names(fields)
        if names and party_names and any(_matches_any_party(name, party_names) for name in names):
            cleared.update({"Borrower name does not match", "Borrower name is missing"})
        signer = _as_text(_first_field(fields, _SIGNER_KEYS))
        if signer and party_names and _matches_any_party(signer, party_names):
            cleared.update({"Signer is not a borrower on the loan", "Signer is missing"})
        if _condition_requires_coverage(condition):
            coverage = _money(_coverage_value(fields))
            loan_amount = _money(loan.get("loan_amount"))
            if coverage is not None and loan_amount is not None and coverage >= loan_amount:
                cleared.update({"Coverage is too low", "Coverage amount is missing"})
    return cleared


def apply_crosscheck(evaluation: dict, reasons: list[str]) -> dict:
    """Record mismatch reasons and keep a clean Fulfilled verdict from standing."""
    if not reasons:
        return evaluation
    missing = list(evaluation.get("missing_or_unclear_points") or [])
    for reason in reasons:
        if reason not in missing:
            missing.append(reason)
    evaluation["missing_or_unclear_points"] = missing

    short = (evaluation.get("short_reason") or "").strip()
    for reason in reasons:
        if reason not in short:
            short = f"{short} {reason}".strip() if short else reason
    evaluation["short_reason"] = short

    if evaluation.get("result") == "Fulfilled":
        evaluation["result"] = "Partially Fulfilled"
    return evaluation
