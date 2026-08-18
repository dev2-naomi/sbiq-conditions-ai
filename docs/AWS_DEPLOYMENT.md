# SBIQ Conditions Evaluator — AWS Deployment

Lambda-only deployment following the Fintor
[`AWS_DEPLOYMENT_PLAYBOOK.md`](https://github.com/FintorAI/monte-carlo-intelligence/blob/main/AWS_DEPLOYMENT_PLAYBOOK.md)
pattern (same as LG-DISCLOSURE-SUBMISSION / monte-carlo-intelligence).

P99 latency is well under Lambda's 900s limit, so Fargate is not used.

## Live endpoints

| Stage | Function URL |
|-------|----------------|
| **dev** | `https://c5n4xqskyfk2ollrqdvbdscekm0cuapj.lambda-url.us-east-2.on.aws/` |
| **prod** | `https://4ptmhkbnvvyfh2gqb6yq47ib7a0vihoo.lambda-url.us-east-2.on.aws/` |

Auth: `x-api-key: $API_KEY` (value in local `.env`, never commit it).  
Assistant id: `conditions-evaluator`.

## Prerequisites

- AWS CLI credentials for account `828351637694` (override with `SBIQ_AWS_ACCOUNT_ID`)
- Docker running
- CDK: `npm install -g aws-cdk`
- Python 3.11+

## First deploy (dev)

```bash
cp env.example .env   # if needed; keep ANTHROPIC_API_KEY + LANGSMITH_API_KEY
./infra/deploy.sh dev
./infra/smoke_test_aws.sh dev
```

`deploy.sh` auto-generates and **persists to `.env`**: `API_KEY`, `LANGSMITH_*_PROJECT`, `CORS_ALLOW_ORIGINS`.

Full run against the Function URL:

```bash
source .env
LANGGRAPH_CLOUD_URL="$(jq -r '.["SbiqConditionsStack-dev"].ApiUrl' output-dev.json)" \
  python run_cloud.py --wait --api-key "$API_KEY" --state
```

## Prod

```bash
./infra/deploy.sh prod
./infra/smoke_test_aws.sh prod
```

## CI/CD

```bash
./infra/sync_github_secrets.sh --dry-run
./infra/sync_github_secrets.sh --aws-cli   # pushes secrets + creates aws-dev / aws-prod
```

- Push to `dev` → `SbiqConditionsStack-dev`
- Push to `main` → `SbiqConditionsStack-prod`

## Client cutover

Point the LangGraph SDK / REST client at the Function URL and send `x-api-key: $API_KEY`.
Assistant id remains `conditions-evaluator`. Details in [`FRONTEND_INTEGRATION.md`](FRONTEND_INTEGRATION.md).
