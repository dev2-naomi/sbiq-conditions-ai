#!/usr/bin/env python3
"""Run the SBIQ Conditions Evaluator against LangGraph Cloud or AWS.

Usage:
    # Default LangGraph Cloud URL
    python run_cloud.py

    # AWS Lambda Function URL
    LANGGRAPH_CLOUD_URL=https://xxx.lambda-url.us-east-2.on.aws/ \\
      python run_cloud.py --api-key "$API_KEY" --wait

    # Custom sample payload
    python run_cloud.py --input data/samples/sample_run_request.json --wait
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import requests

DEFAULT_URL = os.environ.get(
    "LANGGRAPH_CLOUD_URL",
    "https://c5n4xqskyfk2ollrqdvbdscekm0cuapj.lambda-url.us-east-2.on.aws/",
)
API_KEY = (
    os.environ.get("API_KEY")
    or os.environ.get("LANGCHAIN_API_KEY")
    or os.environ.get("LANGSMITH_API_KEY")
    or ""
)
ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT = ROOT / "data" / "samples" / "sample_run_request.json"


def get_headers() -> dict:
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["x-api-key"] = API_KEY
    return headers


def create_thread(base_url: str) -> str:
    resp = requests.post(f"{base_url}/threads", headers=get_headers(), json={})
    resp.raise_for_status()
    return resp.json()["thread_id"]


def load_input(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if "input" in payload and isinstance(payload["input"], dict):
        return payload["input"]
    return payload


def run_stream(base_url: str, thread_id: str, input_data: dict, assistant_id: str):
    print(f"\n{'=' * 60}")
    print(f"Thread: {thread_id}")
    print(f"Assistant: {assistant_id}")
    print(f"{'=' * 60}\n")

    resp = requests.post(
        f"{base_url}/threads/{thread_id}/runs/stream",
        headers=get_headers(),
        json={"assistant_id": assistant_id, "input": input_data},
        stream=True,
        timeout=900,
    )
    resp.raise_for_status()

    for line in resp.iter_lines():
        if not line:
            continue
        line_str = line.decode("utf-8")
        if line_str.startswith("data:"):
            try:
                data = json.loads(line_str[5:].strip())
                print(f"[{datetime.now().strftime('%H:%M:%S')}] {json.dumps(data)[:500]}")
            except json.JSONDecodeError:
                print(line_str)
        elif line_str.startswith("event:"):
            print(f"\n--- {line_str[6:].strip()} ---")


def run_wait(base_url: str, thread_id: str, input_data: dict, assistant_id: str) -> dict:
    print(f"\n{'=' * 60}")
    print(f"Thread: {thread_id}")
    print(f"Assistant: {assistant_id}")
    print("Waiting for completion...")
    print(f"{'=' * 60}\n")

    resp = requests.post(
        f"{base_url}/threads/{thread_id}/runs/wait",
        headers=get_headers(),
        json={"assistant_id": assistant_id, "input": input_data},
        timeout=900,
    )
    resp.raise_for_status()
    result = resp.json()
    print(json.dumps(result, indent=2)[:4000])
    return result


def get_state(base_url: str, thread_id: str) -> dict:
    resp = requests.get(f"{base_url}/threads/{thread_id}/state", headers=get_headers())
    resp.raise_for_status()
    return resp.json()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run SBIQ Conditions Evaluator")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="JSON run payload")
    parser.add_argument("--assistant-id", default="conditions-evaluator")
    parser.add_argument("--stream", action="store_true", help="Stream mode")
    parser.add_argument("--wait", action="store_true", help="Wait mode (default)")
    parser.add_argument("--url", help="Override base URL")
    parser.add_argument("--api-key", help="Override API key (x-api-key)")
    parser.add_argument("--state", action="store_true", help="Print thread state after run")
    args = parser.parse_args()

    global API_KEY
    if args.api_key:
        API_KEY = args.api_key

    base_url = (args.url or DEFAULT_URL).rstrip("/")
    if not args.input.exists():
        print(f"Input file not found: {args.input}", file=sys.stderr)
        return 1

    input_data = load_input(args.input)
    thread_id = create_thread(base_url)

    if args.stream and not args.wait:
        run_stream(base_url, thread_id, input_data, args.assistant_id)
    else:
        run_wait(base_url, thread_id, input_data, args.assistant_id)

    if args.state:
        state = get_state(base_url, thread_id)
        values = state.get("values") or state
        final = values.get("final_output") if isinstance(values, dict) else None
        print("\n=== final_output ===")
        print(json.dumps(final or values, indent=2)[:8000])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
