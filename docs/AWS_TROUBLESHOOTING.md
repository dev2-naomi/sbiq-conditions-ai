# AWS Troubleshooting — SBIQ Conditions Evaluator

Issues hit during the LangGraph Cloud → AWS Lambda migration (2026-08-18).
Also recorded in monte-carlo-intelligence `MIGRATION-CHECKLIST.md` (2026-08-18 addendum).

## DynamoDB rejects floats in run input

**Symptom:** `POST /threads/{id}/runs/wait` (or `/runs`) returns **500**. CloudWatch:

```text
TypeError: Float types are not supported. Use Decimal types instead.
```

Smoke tests still pass (`/health`, assistants, create thread) because they never
write the agent payload. Duration is often &lt;100ms — failure is at
`ThreadStore.create_run`, before the graph runs.

**Cause:** Sample / real inputs include JSON floats (e.g. document
`metadata.confidence: 0.9`). boto3 DynamoDB resource serialization cannot store
Python `float` in map attributes.

**Fix:** Store run `input` and `config` as JSON strings, not nested maps:

```python
item["input"] = json.dumps(input_data or {}, default=str)
item["config"] = json.dumps(config or {}, default=str)
```

For small metadata maps, recursively coerce floats with `Decimal(str(v))`.
Implemented in `api/thread_store.py`.

---

## `.env` keys silently missing from Secrets Manager

**Symptom:** After `./infra/deploy.sh`, verify shows:

```text
LANGSMITH_API_KEY: EMPTY
LANGCHAIN_API_KEY: EMPTY
```

Deploy may also warn `LANGSMITH_API_KEY not set — tracing will be disabled`
even though the key is present in `.env`. Agent still runs; LangSmith tracing does not.

**Cause:** Bash `while IFS='=' read -r key value` loading of `.env` can drop
some keys. CloudFormation success does not mean secrets are populated.

**Fix:**

1. Load `.env` with Python (see `infra/deploy.sh`).
2. Always run SET/EMPTY verification after `put-secret-value`.
3. Re-push if any required key is EMPTY:

```bash
# After fixing deploy.sh / .env, redeploy or put-secret-value again
./infra/deploy.sh dev
```

---

## Incomplete `infra/.venv`

**Symptom:**

```text
./infra/deploy.sh: line …: .venv/bin/activate: No such file or directory
```

**Cause:** `infra/.venv` exists as a directory but was never fully created
(interrupted `python3 -m venv`). The script only creates a venv when the
directory is missing.

**Fix:**

```bash
rm -rf infra/.venv
python3 -m venv infra/.venv
./infra/deploy.sh dev
```

---

## No remote `dev` branch

**Symptom:** GitHub Branches shows only `main`, but docs/CI refer to `dev` →
`SbiqConditionsStack-dev`.

**Cause:** First migration commits were pushed only to `main`. Local
`./infra/deploy.sh dev` still works; CI stage routing needs `origin/dev`.

**Fix:**

```bash
git checkout main && git pull
git checkout -B dev
git push -u origin dev
```

---

## Related

- [`AWS_DEPLOYMENT.md`](AWS_DEPLOYMENT.md) — deploy / endpoints
- monte-carlo `AWS_DEPLOYMENT_PLAYBOOK.md` — shared playbook troubleshooting table
- monte-carlo `MIGRATION-CHECKLIST.md` — § Addendum 2026-08-18
