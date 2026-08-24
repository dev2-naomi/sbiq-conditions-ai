#!/usr/bin/env bash
# Smoke test the deployed API.
# Usage: ./infra/smoke_test_aws.sh [dev|prod]

set -euo pipefail

STAGE="${1:-dev}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

OUTPUT_FILE="$REPO_ROOT/output-$STAGE.json"

if [[ ! -f "$OUTPUT_FILE" ]]; then
    echo "Error: $OUTPUT_FILE not found. Run deploy.sh first."
    exit 1
fi

API_URL=$(jq -r ".\"SbiqConditionsStack-$STAGE\".ApiUrl // empty" "$OUTPUT_FILE")
if [[ -z "$API_URL" ]]; then
    echo "Error: ApiUrl not found in $OUTPUT_FILE"
    exit 1
fi

# Load stage key from .env: API_KEY_DEV / API_KEY_PROD, else API_KEY
if [[ -f "$REPO_ROOT/.env" ]]; then
    eval "$(
        python3 - "$REPO_ROOT/.env" "$STAGE" <<'PY'
import pathlib, shlex, sys
env, stage = pathlib.Path(sys.argv[1]), sys.argv[2].upper()
vals = {}
for line in env.read_text().splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    vals[k.strip()] = v
key = vals.get(f"API_KEY_{stage}") or vals.get("API_KEY") or ""
print(f"export API_KEY={shlex.quote(key)}")
PY
    )"
fi

AUTH_HEADER=()
if [[ -n "${API_KEY:-}" ]]; then
    AUTH_HEADER=(-H "x-api-key: $API_KEY")
fi

echo "=== Smoke testing $STAGE ==="
echo "API URL: $API_URL"

# Health check (retries for cold start)
echo -n "Health check... "
HEALTH="FAILED"
for _ in 1 2 3 4 5 6 7 8 9 10; do
    HEALTH=$(curl -sf "${API_URL}health" || echo "FAILED")
    if [[ "$HEALTH" == *"ok"* ]]; then
        break
    fi
    sleep 3
done
if [[ "$HEALTH" == *"ok"* ]]; then
    echo "OK"
else
    echo "FAILED: $HEALTH"
    exit 1
fi

# Assistants search
echo -n "Assistants search... "
ASSISTANTS=$(curl -sf -X POST "${API_URL}assistants/search" \
    -H "Content-Type: application/json" \
    "${AUTH_HEADER[@]}" \
    -d '{}' || echo "FAILED")
if [[ "$ASSISTANTS" == *"conditions-evaluator"* ]]; then
    echo "OK"
else
    echo "FAILED: $ASSISTANTS"
    exit 1
fi

# Create thread
echo -n "Create thread... "
THREAD=$(curl -sf -X POST "${API_URL}threads" \
    -H "Content-Type: application/json" \
    "${AUTH_HEADER[@]}" \
    -d '{}' || echo "FAILED")
THREAD_ID=$(echo "$THREAD" | python3 -c "import json,sys; print(json.load(sys.stdin).get('thread_id',''))" 2>/dev/null || echo "")
if [[ -n "$THREAD_ID" ]]; then
    echo "OK ($THREAD_ID)"
else
    echo "FAILED: $THREAD"
    exit 1
fi

# Get thread
echo -n "Get thread... "
GOT=$(curl -sf "${API_URL}threads/${THREAD_ID}" \
    "${AUTH_HEADER[@]}" || echo "FAILED")
if [[ "$GOT" == *"$THREAD_ID"* ]]; then
    echo "OK"
else
    echo "FAILED: $GOT"
    exit 1
fi

echo "=== All smoke tests passed ==="
