"""
test_pipeline.py — Local runner for the Conditions Evaluator.

Usage:
    # Full agentic run (requires ANTHROPIC_API_KEY + network):
    python test_pipeline.py

    # Offline structural check (no API key/network needed): exercises the
    # deterministic intake + candidate matching + merge plumbing only.
    python test_pipeline.py --offline
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent
INPUT_DIR = ROOT / "data" / "input"


def build_input() -> dict:
    conditions = (INPUT_DIR / "sample_conditions.json").read_text(encoding="utf-8")
    documents = (INPUT_DIR / "sample_documents.json").read_text(encoding="utf-8")
    eligibility = (INPUT_DIR / "sample_eligibility.json").read_text(encoding="utf-8")
    loan_file = (INPUT_DIR / "sample_loan_file.json").read_text(encoding="utf-8")
    return {
        "conditions_json": conditions,
        "documents_json": documents,
        "eligibility_json": eligibility,
        "loan_file_xml": loan_file,
        # Party identities (optional). The bundled sample is a single-borrower loan;
        # leave `coborrower` empty. Pass a dict or a plain name string.
        "borrower": "John Q Borrower",
        "coborrower": "",
        "env": "Test",
    }


def run_offline() -> int:
    """Exercise the deterministic layer without invoking the LLM."""
    from tools.shared.matching import deterministic_match
    from tools.shared.normalize import (
        derive_overall_status,
        normalize_conditions,
        normalize_documents,
    )
    from tools.shared.ocr import merge_ocr_artifacts

    data = build_input()
    conditions = normalize_conditions(json.loads(data["conditions_json"]))
    docs_raw = json.loads(data["documents_json"])
    raw_docs = docs_raw.get("documents", docs_raw)
    raw_docs = merge_ocr_artifacts(raw_docs, docs_raw.get("artifacts", []))
    documents = normalize_documents(raw_docs)
    candidate_map = deterministic_match(conditions, documents)

    with_ocr = sum(1 for d in documents if d.get("has_ocr"))
    print(f"Parsed {len(conditions)} conditions, {len(documents)} submitted docs "
          f"({with_ocr} with OCR).\n")
    print("Evaluation groups:",
          {c["id"]: c["eval_group"] for c in conditions}, "\n")
    print("Candidate matches (deterministic cheap filter):")
    for cid, cands in candidate_map.items():
        names = [(c["evidence_id"], c["confidence"]) for c in cands]
        print(f"  {cid}: {names}")

    # Simulate the merge step's back-fill: nothing evaluated yet -> all unfulfilled.
    print("\nSimulated merge (no LLM verdicts -> back-filled):")
    for cond in conditions:
        ev = {
            "condition_id": cond["id"],
            "result": "Unfulfilled" if not candidate_map.get(cond["id"]) else "Needs Review",
            "confidence": 0.0,
        }
        status = derive_overall_status(ev)
        print(f"  {cond['id']}: {ev['result']} -> {status['overall_status']} "
              f"(needs_human_review={status['needs_human_review']})")

    run_party_check()

    print("\nOffline structural check passed.")
    return 0


def run_party_check() -> None:
    """Exercise borrower / co-borrower resolution + attribution deterministically.

    Uses a synthetic 2-party scenario (two same-surname parties, an input typo, and
    a shared loan-level doc) to prove resolution, per-document assignment, per-
    condition targeting, and candidate scoping all route correctly.
    """
    from tools.shared.parties import (
        assign_doc_parties,
        condition_target_parties,
        doc_matches_condition_party,
        resolve_parties,
    )

    print("\n=== Party resolution & attribution (synthetic co-borrower) ===")

    # Note the deliberate typo in the borrower input ("Isral") — resolution keeps it
    # as authoritative; fuzzy matching still ties the VVOE (spelled "Israel") to it.
    parties = resolve_parties(
        borrower={"first_name": "Isral", "last_name": "Ortiz"},
        coborrower={"first_name": "Natalya", "last_name": "Ortiz"},
    )
    print("Parties:", [(p["tag"], p["name"]) for p in parties])

    docs = [
        {"id": "D_VVOE", "detected_document_type": "Written VOE",
         "extracted_fields": {"employee": "Israel Ortiz", "employer": "Acme Co"}},
        {"id": "D_VOI", "detected_document_type": "Verification of Income",
         "extracted_fields": {"borrowers": [{"firstName": "Natalya", "lastName": "Ortiz"}]}},
        {"id": "D_APPRAISAL", "detected_document_type": "Appraisal",
         "extracted_fields": {"property_address": "1 Main St"}},
    ]
    for d in docs:
        d["party_tags"] = assign_doc_parties(d, parties)
        print(f"  doc {d['id']:12s} -> party_tags={d['party_tags']}")

    conds = [
        {"id": "C_BORR_VOE", "label": "Income: VVOE for Borrower",
         "body": "Provide a written VOE for the Borrower."},
        {"id": "C_COBORR_VOE", "label": "Income: VOI for Co-Borrower",
         "body": "Provide verification of income for the Co-Borrower."},
        {"id": "C_APPRAISAL", "label": "Property: Appraisal",
         "body": "Provide a full interior appraisal (1004)."},
    ]
    for c in conds:
        c["target_parties"] = condition_target_parties(c, parties)
        matches = [d["id"] for d in docs if doc_matches_condition_party(d, c, parties)]
        print(f"  cond {c['id']:14s} target={c['target_parties']} "
              f"-> eligible docs={matches}")

    # Assertions: the borrower VOE and co-borrower VOI must NOT cross parties.
    voe = next(c for c in conds if c["id"] == "C_BORR_VOE")
    voi = next(c for c in conds if c["id"] == "C_COBORR_VOE")
    appr = next(c for c in conds if c["id"] == "C_APPRAISAL")
    dmap = {d["id"]: d for d in docs}
    assert doc_matches_condition_party(dmap["D_VVOE"], voe, parties)
    assert not doc_matches_condition_party(dmap["D_VOI"], voe, parties)
    assert doc_matches_condition_party(dmap["D_VOI"], voi, parties)
    assert not doc_matches_condition_party(dmap["D_VVOE"], voi, parties)
    # Loan-level appraisal is available to any party's condition.
    assert doc_matches_condition_party(dmap["D_APPRAISAL"], appr, parties)
    print("Party routing assertions passed (no borrower<->co-borrower leakage).")


def run_full() -> int:
    from agent import agent

    data = build_input()
    print("Invoking agent (this calls the LLM and may take several minutes)...\n")
    result = agent.invoke(data)

    final = result.get("final_output")
    if not final:
        print("No final_output produced. Last messages:")
        for m in result.get("messages", [])[-3:]:
            print("-", getattr(m, "content", m))
        return 1

    print(json.dumps(final, indent=2))
    out_path = ROOT / "test_results"
    out_path.mkdir(exist_ok=True)
    (out_path / "last_run.json").write_text(json.dumps(final, indent=2), encoding="utf-8")
    print(f"\nSaved to {out_path / 'last_run.json'}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true",
                        help="Run the deterministic layer only (no LLM).")
    args = parser.parse_args()
    return run_offline() if args.offline else run_full()


if __name__ == "__main__":
    sys.exit(main())
