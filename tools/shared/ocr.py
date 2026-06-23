"""
ocr.py — Helpers for the document OCR text carried by the rack & stack manifest.

The upstream Tasktile manifest references OCR per document under a top-level
``artifacts`` array (``{"type": "ocr", "document_id": ..., "source": {...}}``),
where each reference points at a per-document OCR ``.txt`` blob. We assume that
text is **already dereferenced** by the time the manifest reaches this engine —
i.e. the OCR string is inlined onto the artifact (``text``/``content``) or onto
the document itself (``ocr_text``/``document_text``).

These helpers:
  - split a flat OCR string into pages (so we can read the first few pages first
    and escalate to the full text only when needed),
  - merge dereferenced ``artifacts`` OCR onto their documents by ``document_id``,
  - and produce capped previews for the matching workspace / evaluation context.
"""

from __future__ import annotations

import re
from typing import Any

# Default caps keep the agent's context bounded.
PREVIEW_PAGES = 2          # "first few pages" for the cheap relevance pass
PREVIEW_CHAR_CAP = 1500    # per-preview character cap
FULL_CHAR_CAP = 24000      # cap when the agent escalates to the full OCR

# Page-break markers commonly emitted by OCR engines when no form-feed is present.
_PAGE_MARKER = re.compile(
    r"\n?\s*[-=*_]{0,4}\s*(?:page|pg)\s*[:#]?\s*\d+\s*(?:of\s*\d+)?\s*[-=*_]{0,4}\s*\n",
    re.IGNORECASE,
)


def split_pages(text: str) -> list[str]:
    """Split a flat OCR string into page-sized chunks.

    Prefers the form-feed character (``\\f``) that most OCR exporters insert
    between pages; falls back to textual "Page N" markers; otherwise treats the
    whole string as a single page.
    """
    if not text:
        return []
    if "\f" in text:
        pages = [p for p in text.split("\f")]
    elif _PAGE_MARKER.search(text):
        pages = _PAGE_MARKER.split(text)
    else:
        pages = [text]
    cleaned = [p.strip() for p in pages if p and p.strip()]
    return cleaned or ([text.strip()] if text.strip() else [])


def _cap(text: str, char_cap: int) -> tuple[str, bool]:
    if char_cap and len(text) > char_cap:
        return text[:char_cap] + "…[truncated]", True
    return text, False


def first_pages(pages: list[str], n: int = PREVIEW_PAGES, char_cap: int = PREVIEW_CHAR_CAP) -> str:
    """Joined text of the first ``n`` OCR pages, capped to ``char_cap`` chars."""
    if not pages:
        return ""
    joined = "\n\n".join(pages[: max(1, n)])
    text, _ = _cap(joined, char_cap)
    return text


def full_text(pages: list[str], char_cap: int = FULL_CHAR_CAP) -> str:
    """All OCR pages joined, capped to ``char_cap`` chars."""
    if not pages:
        return ""
    text, _ = _cap("\n\n".join(pages), char_cap)
    return text


def _ocr_text_from_artifact(artifact: dict) -> str:
    """Pull the (already-dereferenced) OCR string off an artifact entry."""
    if not isinstance(artifact, dict):
        return ""
    for key in ("text", "content", "ocr_text", "ocr", "full_text", "value"):
        v = artifact.get(key)
        if isinstance(v, str) and v.strip():
            return v
    src = artifact.get("source")
    if isinstance(src, dict):
        for key in ("text", "content", "ocr_text"):
            v = src.get(key)
            if isinstance(v, str) and v.strip():
                return v
    return ""


def merge_ocr_artifacts(documents: list[dict], artifacts: list[dict]) -> list[dict]:
    """Attach dereferenced OCR text from ``artifacts`` onto their documents.

    Matches ``artifacts[].document_id`` to ``documents[].id``. Mutates and returns
    the documents list. Documents that already carry inline OCR are left untouched.
    """
    if not artifacts:
        return documents

    ocr_by_doc: dict[str, str] = {}
    for art in artifacts:
        if not isinstance(art, dict):
            continue
        if str(art.get("type", "ocr")).lower() not in ("ocr", "text", ""):
            continue
        doc_id = art.get("document_id") or art.get("documentId") or art.get("id")
        text = _ocr_text_from_artifact(art)
        if doc_id is not None and text:
            ocr_by_doc[str(doc_id)] = text

    if not ocr_by_doc:
        return documents

    for doc in documents:
        if not isinstance(doc, dict):
            continue
        doc_id = str(doc.get("id", "") or "")
        if doc_id in ocr_by_doc and not any(
            doc.get(k) for k in ("ocr_text", "document_text", "ocr", "full_text")
        ):
            doc["ocr_text"] = ocr_by_doc[doc_id]
    return documents
