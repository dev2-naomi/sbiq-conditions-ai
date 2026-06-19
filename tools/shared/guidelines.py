"""
guidelines.py — NQMF Underwriting Guidelines loader.

Parses guidelines.md into searchable sections and provides structured
lookup by heading name, keyword search, and rule extraction.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

_GUIDELINES_PATH = Path(__file__).parent.parent.parent / "data" / "guidelines.md"

_KNOWN_SECTIONS: dict[str, str] = {
    "GENERAL UNDERWRITING REQUIREMENTS": "general",
    "OCCUPANCY TYPES": "general",
    "TRANSACTION TYPES": "general",
    "FULL DOCUMENTATION": "income",
    "EMPLOYMENT": "income",
    "RATIOS AND QUALIFYING – FULL AND ALT DOC": "income",
    "ALTERNATIVE DOCUMENTATION (ALT DOC)": "income",
    "DSCR RATIOS AND RENTAL INCOME REQUIREMENTS": "income",
    "DSCR PRODUCT TERMS": "income",
    "DSCR PROGRAMS": "income",
    "ITIN": "income",
    "ITIN – DOCUMENTATION REQUIREMENTS": "income",
    "ITIN - ELIGIBILITY": "income",
    "FOREIGN NATIONALS": "income",
    "SECOND LIEN": "income",
    "SECOND LIEN SELECT SENIOR LIEN QUALIFYING TERMS": "income",
    "TEXAS HOME EQUITY LOANS (CASH-OUT REFI TEXAS)": "title_closing",
    "ASSETS": "assets",
    "RESERVES": "assets",
    "CREDIT": "credit",
    "HOUSING HISTORY": "credit",
    "HOUSING EVENTS AND PRIOR BANKRUPTCY": "credit",
    "LIABILITIES": "credit",
    "APPRAISALS": "property_appraisal",
    "PROPERTY CONSIDERATIONS": "property_appraisal",
    "PROPERTY TYPES": "property_appraisal",
    "CONDOMINIUMS - GENERAL": "property_appraisal",
    "WARRANTABLE CONDOMINIUMS": "property_appraisal",
    "NON-WARRANTABLE CONDOMINIUMS": "property_appraisal",
    "COOPERATIVES (CO-OP)": "property_appraisal",
    "PROPERTY INSURANCE": "title_closing",
    "TITLE INSURANCE": "title_closing",
    "COMPLIANCE": "compliance",
    "BORROWER ELIGIBILITY": "compliance",
    "VESTING AND OWNERSHIP": "compliance",
}

# ───────────────────────────────────────────────────────────────────────────
# Parsed section dataclass
# ───────────────────────────────────────────────────────────────────────────

_HEADING_BOLD = re.compile(r"^\*\*([A-Z][A-Z \-–/&',()0-9]+)\*\*")
_HEADING_CAPS = re.compile(r"^([A-Z][A-Z \-–/&',()0-9]{4,})\s*\.{0,100}\s*\d*\s*$")
_PAGE_LINE = re.compile(r"^Page\s+\*\*\d+\*\*\s+of\s+\*\*\d+\*\*")
_GUIDELINE_FOOTER = re.compile(r"^NQM Funding, LLC Underwriting Guidelines")


class _Section:
    __slots__ = ("heading", "level", "line_start", "line_end", "body")

    def __init__(self, heading: str, level: int, line_start: int, line_end: int, body: str):
        self.heading = heading
        self.level = level
        self.line_start = line_start
        self.line_end = line_end
        self.body = body


# ───────────────────────────────────────────────────────────────────────────
# GuidelinesDocument — singleton
# ───────────────────────────────────────────────────────────────────────────

class GuidelinesDocument:
    """In-memory parsed representation of the NQMF guidelines markdown."""

    def __init__(self, filepath: str | Path | None = None):
        self.filepath = Path(filepath) if filepath else _GUIDELINES_PATH
        self._raw_lines: list[str] = []
        self._sections: list[_Section] = []
        self._heading_index: dict[str, list[_Section]] = {}
        self._major_keys = {self._normalize(k) for k in _KNOWN_SECTIONS}
        self._load_and_parse()

    @staticmethod
    def _normalize(text: str) -> str:
        text = text.upper().strip()
        text = re.sub(r"[^A-Z0-9 ]", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    def _load_and_parse(self):
        with open(self.filepath, "r", encoding="utf-8") as f:
            self._raw_lines = f.readlines()

        heading_positions: list[tuple[int, str, int]] = []
        for idx, line in enumerate(self._raw_lines):
            stripped = line.strip()
            if not stripped or "....." in stripped:
                continue
            if _PAGE_LINE.match(stripped) or _GUIDELINE_FOOTER.match(stripped):
                continue
            m = _HEADING_BOLD.match(stripped)
            if m:
                heading_positions.append((idx, m.group(1).strip().rstrip("."), 1))
                continue
            m = _HEADING_CAPS.match(stripped)
            if m:
                heading_positions.append((idx, m.group(1).strip().rstrip("."), 2))

        for i, (line_idx, heading, level) in enumerate(heading_positions):
            next_line = heading_positions[i + 1][0] if i + 1 < len(heading_positions) else len(self._raw_lines)
            body = "".join(self._raw_lines[line_idx:next_line])
            section = _Section(heading, level, line_idx + 1, next_line, body)
            self._sections.append(section)
            key = self._normalize(heading)
            self._heading_index.setdefault(key, []).append(section)

    # ── Public API ────────────────────────────────────────────────────

    def get_section(self, heading: str) -> list[_Section]:
        key = self._normalize(heading)
        if key in self._heading_index:
            return self._heading_index[key]
        results = []
        for k, secs in self._heading_index.items():
            if key in k or k in key:
                results.extend(secs)
        return results

    def get_sections_expanded(self, heading: str) -> list[_Section]:
        """
        Return the requested section plus any related sub-sections.

        Headings in this document are flat (no real nesting levels), so a parent
        heading like "CREDIT" carries almost no text — the substance lives in
        sibling leaf headings ("CREDIT REPORT", "CREDIT INQUIRIES", ...). This
        returns, in document order, every section whose heading contains all of
        the requested tokens, so callers get the full topic, not just the stub.
        """
        key = self._normalize(heading)
        tokens = [t for t in key.split(" ") if t]
        if not tokens:
            return []

        # If the requested heading is a known "major" chapter, return the whole
        # chapter: every section from it up to (but excluding) the next major.
        if key in self._major_keys:
            start = next(
                (i for i, s in enumerate(self._sections) if self._normalize(s.heading) == key),
                None,
            )
            if start is not None:
                chapter = [self._sections[start]]
                for s in self._sections[start + 1:]:
                    if self._normalize(s.heading) in self._major_keys:
                        break
                    chapter.append(s)
                if any(len(s.body.strip()) > len(s.heading) + 5 for s in chapter):
                    return chapter

        # Otherwise gather every section whose heading contains all requested tokens.
        matched = [
            s for s in self._sections
            if self._normalize(s.heading) == key
            or all(t in self._normalize(s.heading) for t in tokens)
        ]
        if matched:
            return matched
        # Fall back to the looser bidirectional-substring matcher.
        return self.get_section(heading)

    def get_section_text(self, heading: str) -> str:
        sections = self.get_section(heading)
        if sections:
            return "\n".join(s.body for s in sections)
        return ""

    def get_rule_text(self, heading: str, keyword: str) -> str | None:
        sections = self.get_section(heading)
        for section in sections:
            paragraphs = re.split(r"\n\s*\n", section.body)
            for para in paragraphs:
                if keyword.lower() in para.lower():
                    return para.strip()
        return None

    def search(self, query: str, *, case_insensitive: bool = True) -> list[dict]:
        flags = re.IGNORECASE if case_insensitive else 0
        pattern = re.compile(re.escape(query), flags)
        results = []
        for section in self._sections:
            matches = list(pattern.finditer(section.body))
            if matches:
                start = max(0, matches[0].start() - 200)
                end = min(len(section.body), matches[0].end() + 200)
                results.append({
                    "heading": section.heading,
                    "line_start": section.line_start,
                    "match_count": len(matches),
                    "snippet": section.body[start:end].strip(),
                })
        return results

    def list_headings(self) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for s in self._sections:
            if s.heading not in seen:
                seen.add(s.heading)
                result.append(s.heading)
        return result


# ───────────────────────────────────────────────────────────────────────────
# Singleton accessor
# ───────────────────────────────────────────────────────────────────────────

_instance: GuidelinesDocument | None = None


def _get_guidelines(filepath: str | Path | None = None) -> GuidelinesDocument:
    global _instance
    if _instance is None or (filepath and Path(filepath) != _instance.filepath):
        _instance = GuidelinesDocument(filepath)
    return _instance


# ───────────────────────────────────────────────────────────────────────────
# Public functions (called by tools)
# ───────────────────────────────────────────────────────────────────────────


_MAX_SECTION_CHARS = 24000


def load_sections(section_names: list[str]) -> str:
    """
    Load guideline content for the requested section names.

    Returns actual guideline text extracted from guidelines.md. For each requested
    heading the requested section plus its related sub-sections are returned (the
    document is flat, so parent headings on their own carry almost no text). Output
    is capped to keep the reference reasonably sized.
    """
    if not section_names:
        return ""

    doc = _get_guidelines()
    parts: list[str] = []
    seen_headings: set[str] = set()
    for name in section_names:
        sections = doc.get_sections_expanded(name)
        bodies: list[str] = []
        for s in sections:
            marker = f"{s.heading}@{s.line_start}"
            if marker in seen_headings:
                continue
            seen_headings.add(marker)
            bodies.append(s.body.strip())
        if bodies:
            parts.append("\n\n".join(bodies))
        else:
            parts.append(f"[Section '{name}' not found in guidelines]")
    text = "\n\n---\n\n".join(parts)
    if len(text) > _MAX_SECTION_CHARS:
        text = text[:_MAX_SECTION_CHARS] + "\n\n[...truncated; request a more specific section...]"
    return text


def load_full_guidelines() -> str:
    """Load the complete guidelines file."""
    if _GUIDELINES_PATH.exists():
        return _GUIDELINES_PATH.read_text(encoding="utf-8")
    return "[GUIDELINES NOT FOUND]"


def search_guidelines(query: str) -> list[dict]:
    """Full-text search across all guideline sections."""
    doc = _get_guidelines()
    return doc.search(query)


def get_rule_for_section(section_name: str, keyword: str) -> str | None:
    """Find a specific rule paragraph in a section by keyword."""
    doc = _get_guidelines()
    return doc.get_rule_text(section_name, keyword)


def build_guideline_trace(section_names: list[str], keyword: str) -> list[dict]:
    """Build a guideline_trace array by searching sections for a keyword."""
    doc = _get_guidelines()
    traces: list[dict] = []
    for section in section_names:
        rule = doc.get_rule_text(section, keyword)
        if rule:
            traces.append({"section": section, "requirement": rule[:500]})
    if not traces and section_names:
        traces.append({
            "section": section_names[0],
            "requirement": f"Refer to {section_names[0]} section for {keyword} requirements.",
        })
    return traces
