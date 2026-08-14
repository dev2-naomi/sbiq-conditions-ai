"""
parties.py — Borrower / co-borrower resolution and per-party attribution.

A loan can have a primary borrower and (optionally) a co-borrower. Conditions and
submitted documents are frequently party-specific — a "verify employment for the
Co-Borrower" condition must be satisfied by the *co-borrower's* VOE, not the
borrower's — yet the raw inputs carry no structural party flag. This module makes
party attribution explicit and deterministic:

  1. ``resolve_parties`` — identify the parties from the (authoritative) borrower /
     coborrower input, falling back to the eligibility engine output and then the
     MISMO XML. Returns at most one primary + one co-borrower.
  2. ``assign_doc_parties`` — read the person name(s) off each document's extracted
     fields and fuzzy-match them to a party. Unnamed (loan-level) or unmatched
     documents go to *all* parties, so they're never dropped.
  3. ``condition_target_parties`` — read a condition's title/body for an explicit
     party name or a distinguishing role phrase ("Co-Borrower") to decide which
     party it applies to. Generic conditions apply to *all* parties.
  4. ``doc_matches_condition_party`` — the scoping predicate used in STEP_01 so a
     condition only ever gets candidate documents belonging to its party.

Everything degrades safely: with fewer than two parties (the common single-borrower
loan) every predicate is a no-op and behavior is unchanged.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

# ---------------------------------------------------------------------------
# Name normalization & fuzzy matching
# ---------------------------------------------------------------------------

_NAME_RATIO_THRESHOLD = 0.82


def _norm_name(name: Any) -> str:
    """Lowercase, drop punctuation (apostrophes/hyphens/commas), collapse spaces."""
    if not name:
        return ""
    s = str(name).lower().replace(",", " ")
    s = re.sub(r"[^a-z0-9 ]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def _tokens(name: Any) -> list[str]:
    return [t for t in _norm_name(name).split() if t]


def _name_matches(a: Any, b: Any, threshold: float = _NAME_RATIO_THRESHOLD) -> bool:
    """True when two person names plausibly refer to the same person.

    Matches on any of: exact normalized equality; ≥2 shared whole tokens (first AND
    last name — a single shared surname is intentionally NOT enough, so two family
    members with the same last name don't collide); a high whole-string similarity
    ratio (typo tolerant); or first-and-last tokens that are each individually close
    (handles "Isral" vs "Israel").
    """
    na, nb = _norm_name(a), _norm_name(b)
    if not na or not nb:
        return False
    if na == nb:
        return True

    ta, tb = _tokens(na), _tokens(nb)
    shared = set(ta) & set(tb)
    if len(shared) >= 2:
        return True

    if SequenceMatcher(None, na, nb).ratio() >= threshold:
        return True

    # First + last must BOTH be close — guards against a shared surname alone.
    if ta and tb:
        first_close = SequenceMatcher(None, ta[0], tb[0]).ratio() >= threshold
        last_close = SequenceMatcher(None, ta[-1], tb[-1]).ratio() >= threshold
        if first_close and last_close:
            return True
    return False


def _split_name(name: str) -> tuple[str, str]:
    """(first, last) from a full-name string; middle names/initials are dropped."""
    toks = str(name or "").split()
    if not toks:
        return "", ""
    if len(toks) == 1:
        return toks[0], ""
    return toks[0], toks[-1]


# ---------------------------------------------------------------------------
# Party resolution
# ---------------------------------------------------------------------------

_UNKNOWN = {"", "unknown", "n/a", "na", "none", "null"}


def _party_from_obj(obj: Any) -> dict | None:
    """Build a party {name, first_name, last_name} from a dict or plain string."""
    first = last = full = ""
    if isinstance(obj, str):
        full = obj.strip()
        first, last = _split_name(full)
    elif isinstance(obj, dict):
        first = str(obj.get("first_name") or obj.get("firstName") or obj.get("first") or "").strip()
        last = str(obj.get("last_name") or obj.get("lastName") or obj.get("last") or "").strip()
        full = str(obj.get("name") or obj.get("full_name") or obj.get("fullName") or "").strip()
        if not full:
            full = " ".join(x for x in (first, last) if x)
        if not first and not last:
            first, last = _split_name(full)
    if not full or _norm_name(full) in _UNKNOWN:
        return None
    return {"name": full, "first_name": first, "last_name": last}


def _eligibility_party(app_data: dict, *, co: bool) -> dict | None:
    """Pull a borrower/co-borrower identity out of eligibility application_data."""
    if not isinstance(app_data, dict):
        return None
    prefix_variants = (
        ("CoBorrower", "co_borrower", "coborrower") if co else ("Borrower", "borrower")
    )
    for pref in prefix_variants:
        for fk, lk in ((f"{pref}FirstName", f"{pref}LastName"),
                       (f"{pref}_first_name", f"{pref}_last_name")):
            first = app_data.get(fk)
            last = app_data.get(lk)
            if first or last:
                p = _party_from_obj({"first_name": first, "last_name": last})
                if p:
                    return p
        for nk in (f"{pref}Name", f"{pref}_name"):
            if app_data.get(nk):
                p = _party_from_obj(app_data.get(nk))
                if p:
                    return p
    return None


def resolve_parties(
    borrower: Any = None,
    coborrower: Any = None,
    eligibility: dict | None = None,
    xml_scenario: dict | None = None,
) -> list[dict]:
    """Resolve the loan's parties: one primary + at most one distinct co-borrower.

    Identity resolution order (primary): explicit ``borrower`` input →
    eligibility ``application_data`` → MISMO XML borrower_name. Co-borrower:
    explicit ``coborrower`` input → eligibility co-borrower fields. A co-borrower is
    only added when its normalized name differs from the primary's.

    Returns a list of ``{name, first_name, last_name, role, tag}``; ``tag`` is
    ``"borrower"`` or ``"coborrower"``. Empty when no primary can be resolved.
    """
    app_data = eligibility.get("application_data") if isinstance(eligibility, dict) else {}
    if not isinstance(app_data, dict):
        app_data = {}
    xml_scenario = xml_scenario or {}

    primary = (
        _party_from_obj(borrower)
        or _eligibility_party(app_data, co=False)
        or _party_from_obj(app_data.get("BorrowerName"))
        or _party_from_obj(xml_scenario.get("borrower_name"))
    )
    if not primary:
        return []

    parties = [{**primary, "role": "borrower", "tag": "borrower"}]

    co = _party_from_obj(coborrower) or _eligibility_party(app_data, co=True)
    if co and _norm_name(co["name"]) != _norm_name(primary["name"]):
        parties.append({**co, "role": "coborrower", "tag": "coborrower"})

    return parties


# ---------------------------------------------------------------------------
# Document → party assignment
# ---------------------------------------------------------------------------

# Scalar-ish extracted-field keys that carry a person's name.
_NAME_FIELDS = (
    "employee", "customer", "insured", "borrower", "applicant", "account_holder",
    "name", "full_name", "borrower_name", "drawer", "received_from", "member",
    "vesting", "payer",
)
# List-valued extracted-field keys whose entries carry person names.
_NAME_LIST_FIELDS = ("borrowers", "applicants", "members", "employees", "employments")


def _person_names_from_obj(obj: Any) -> list[str]:
    """Extract candidate person-name string(s) from a scalar/dict field value."""
    if isinstance(obj, str):
        s = obj.strip()
        return [s] if s else []
    if isinstance(obj, dict):
        first = obj.get("firstName") or obj.get("first_name") or obj.get("first")
        last = obj.get("lastName") or obj.get("last_name") or obj.get("last")
        if first or last:
            full = " ".join(str(x) for x in (first, last) if x).strip()
            return [full] if full else []
        for k in ("name", "full_name", "employee", "customer", "insured"):
            if obj.get(k) is not None:
                names = _person_names_from_obj(obj.get(k))
                if names:
                    return names
    return []


def doc_party_names(doc: dict) -> list[str]:
    """All person names carried in a document's extracted fields (deduped)."""
    fields = doc.get("extracted_fields") or {}
    if not isinstance(fields, dict):
        return []
    names: list[str] = []
    for key in _NAME_FIELDS:
        if key in fields:
            names += _person_names_from_obj(fields[key])
    for key in _NAME_LIST_FIELDS:
        val = fields.get(key)
        if isinstance(val, list):
            for item in val:
                if key == "employments" and isinstance(item, dict):
                    names += _person_names_from_obj(item.get("employee") or item)
                else:
                    names += _person_names_from_obj(item)
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        norm = _norm_name(n)
        if norm and norm not in seen:
            seen.add(norm)
            out.append(n)
    return out


def _all_tags(parties: list[dict]) -> list[str]:
    return [p["tag"] for p in parties]


def assign_doc_parties(doc: dict, parties: list[dict]) -> list[str]:
    """Return the party tag(s) a document belongs to.

    - Fewer than 2 parties → every party (no-op single-borrower case).
    - Document names no person → all parties (loan-level: appraisal, title, flood…).
    - Names person(s) matching known parties → only those parties.
    - Names someone but matches NO known party → all parties (never dropped).
    """
    if len(parties) < 2:
        return _all_tags(parties)

    names = doc_party_names(doc)
    if not names:
        return _all_tags(parties)

    matched: set[str] = set()
    for nm in names:
        for p in parties:
            if _name_matches(nm, p["name"]):
                matched.add(p["tag"])
    if matched:
        return [p["tag"] for p in parties if p["tag"] in matched]
    return _all_tags(parties)


# ---------------------------------------------------------------------------
# Condition → party attribution
# ---------------------------------------------------------------------------

# A distinguishing co-borrower reference.
_CO_RE = re.compile(r"\bco[\s\-]?(?:borrower|applicant|signer)s?\b", re.IGNORECASE)

# Primary-borrower TARGETING markers (deliberately excludes bare, generic
# "borrower" usage like "the borrower must provide…", which is not party-specific).
_PRIMARY_MARKERS = re.compile(
    r"for (?:the )?borrower\b"
    r"|\bborrower['\u2019]s\b"          # possessive only ("borrower's"), NOT plural "borrowers"
    r"|\(borrower\)"
    r"|\bborrower\s*:"
    r"|[-\u2013\u2014]\s*borrower\b"
    r"|\bprimary borrower\b"
    r"|\bmain borrower\b"
    r"|\bborrower\s*#?\s*1\b",
    re.IGNORECASE,
)


def _name_in_text(party: dict, toks: set[str]) -> bool:
    """Party named in text: require BOTH first and last name tokens when known."""
    first = _norm_name(party.get("first_name"))
    last = _norm_name(party.get("last_name"))
    if first and last:
        return first in toks and last in toks
    if last:
        return last in toks
    if first:
        return first in toks
    return False


def condition_target_parties(condition: dict, parties: list[dict]) -> list[str]:
    """Which party tag(s) a condition applies to.

    Precedence: an explicit party NAME in the condition text wins. Otherwise a
    distinguishing role phrase is used ("Co-Borrower" → co-borrower; a primary
    targeting marker → borrower; both → both). Generic conditions (no party signal)
    apply to ALL parties.
    """
    if len(parties) < 2:
        return _all_tags(parties)

    text = " ".join(
        str(condition.get(k, "")) for k in ("label", "body", "raw_text")
    ).lower()
    toks = set(re.findall(r"[a-z0-9]+", text))

    matched = {p["tag"] for p in parties if _name_in_text(p, toks)}
    if matched:
        return [p["tag"] for p in parties if p["tag"] in matched]

    tags = set(_all_tags(parties))
    has_co = bool(_CO_RE.search(text)) and "coborrower" in tags
    # Strip co-borrower phrases before checking for a primary-only marker so
    # "co-borrower's" doesn't read as a primary "borrower's".
    text_wo_co = _CO_RE.sub(" ", text)
    has_primary = bool(_PRIMARY_MARKERS.search(text_wo_co)) and "borrower" in tags

    role_matched: list[str] = []
    if has_co:
        role_matched.append("coborrower")
    if has_primary:
        role_matched.append("borrower")
    if role_matched:
        return [p["tag"] for p in parties if p["tag"] in set(role_matched)]

    return _all_tags(parties)


# ---------------------------------------------------------------------------
# Candidate scoping predicate (STEP_01)
# ---------------------------------------------------------------------------


def doc_matches_condition_party(
    doc: dict, condition: dict, parties: list[dict]
) -> bool:
    """True when a document's party tag(s) overlap the condition's party target(s).

    No-op (always True) for single-party loans. Defaults are over-inclusive: a doc
    or condition with no explicit party resolves to *all* parties, so it always
    overlaps — only clearly cross-party pairs are excluded.
    """
    if len(parties) < 2:
        return True
    all_tags = set(_all_tags(parties))
    doc_tags = set(doc.get("party_tags") or all_tags)
    cond_tags = set(condition.get("target_parties") or all_tags)
    return bool(doc_tags & cond_tags)
