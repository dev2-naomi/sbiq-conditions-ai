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
    return {
        "conditions_json": conditions,
        "documents_json": documents,
        "eligibility_json": eligibility,
        "loan_file_xml": "",
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

    data = build_input()
    conditions = normalize_conditions(json.loads(data["conditions_json"]))
    docs_raw = json.loads(data["documents_json"])
    documents = normalize_documents(docs_raw.get("documents", docs_raw))
    candidate_map = deterministic_match(conditions, documents)

    print(f"Parsed {len(conditions)} conditions, {len(documents)} submitted docs.\n")
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

    print("\nOffline structural check passed.")
    return 0


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
