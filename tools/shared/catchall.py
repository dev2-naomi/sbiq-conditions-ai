"""Catch-all document categories 830 and 794.

These categories are buckets, not a document type. The category name is not a
reason to attach the file to a condition. A file in either category can be
evidence only when its OCR text, or an extracted field other than a person's
name, shows what the document actually is.
"""

from __future__ import annotations

from typing import Any

CATCHALL_CATEGORY_IDS = {"830", "794"}

# A name identifies whose file it is. It does not say the file is a mortgage
# history, a vesting document, approval terms, or anything else.
_IDENTITY_KEYS = {
    "borrower", "borrowers", "borrower_name", "coborrower", "coborrowers",
    "owner", "owners", "applicant", "applicants", "name", "signer",
    "signed_by", "signatory", "signature_name", "customer", "employee",
    "employees", "member", "members",
}


def is_catchall(doc: dict) -> bool:
    return str((doc or {}).get("category_id") or "").strip() in CATCHALL_CATEGORY_IDS


def _has_ocr(doc: dict) -> bool:
    if doc.get("has_ocr"):
        return True
    for page in doc.get("ocr_pages") or []:
        if isinstance(page, str) and page.strip():
            return True
    text = doc.get("document_text") or ""
    return isinstance(text, str) and bool(text.strip())


def _nonempty(value: Any) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict, tuple)):
        return bool(value)
    return True


def has_substantive_content(doc: dict) -> bool:
    """OCR text, or an extracted field that is not just a person's name."""
    if _has_ocr(doc):
        return True
    fields = doc.get("extracted_fields") or {}
    if not isinstance(fields, dict):
        return False
    for key, value in fields.items():
        if str(key).lower() in _IDENTITY_KEYS:
            continue
        if _nonempty(value):
            return True
    return False


def catchall_usable(doc: dict) -> bool:
    """False when a 830/794 document has nothing to judge it by, or only a name."""
    if not is_catchall(doc):
        return True
    return has_substantive_content(doc)
