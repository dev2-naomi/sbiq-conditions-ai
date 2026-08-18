#!/usr/bin/env bash
# Push .env secrets to GitHub Actions secrets/variables and create environments.
# Usage:
#   ./infra/sync_github_secrets.sh             # push from .env
#   ./infra/sync_github_secrets.sh --aws-cli   # also fill AWS_* from ~/.aws/credentials
#   ./infra/sync_github_secrets.sh --dry-run   # preview without writing

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$REPO_ROOT/.env"

DRY_RUN=false
AWS_CLI=false

for arg in "$@"; do
    case $arg in
        --dry-run) DRY_RUN=true ;;
        --aws-cli) AWS_CLI=true ;;
    esac
done

if [[ ! -f "$ENV_FILE" ]]; then
    echo "Error: $ENV_FILE not found"
    exit 1
fi

if ! command -v gh &>/dev/null; then
    echo "Error: gh CLI not installed. Run: brew install gh"
    exit 1
fi

if ! gh auth status &>/dev/null; then
    echo "Error: Not authenticated. Run: gh auth login"
    exit 1
fi

echo "=== Syncing secrets to GitHub ==="

SECRETS=(
    "API_KEY"
    "ANTHROPIC_API_KEY"
    "LANGSMITH_API_KEY"
    "ANTHROPIC_MODEL"
)

VARIABLES=(
    "LANGSMITH_DEV_PROJECT"
    "LANGSMITH_PROD_PROJECT"
    "CORS_ALLOW_ORIGINS"
)

declare -A ENV_VALUES
while IFS='=' read -r key value; do
    [[ -z "$key" || "$key" =~ ^# ]] && continue
    value="${value%\"}"
    value="${value#\"}"
    value="${value%\'}"
    value="${value#\'}"
    ENV_VALUES["$key"]="$value"
done < "$ENV_FILE"

if [[ "$AWS_CLI" == true ]]; then
    if command -v aws &>/dev/null; then
        AWS_ACCESS_KEY_ID=$(aws configure get aws_access_key_id 2>/dev/null || echo "")
        AWS_SECRET_ACCESS_KEY=$(aws configure get aws_secret_access_key 2>/dev/null || echo "")
        if [[ -n "$AWS_ACCESS_KEY_ID" ]]; then
            ENV_VALUES["AWS_ACCESS_KEY_ID"]="$AWS_ACCESS_KEY_ID"
            ENV_VALUES["AWS_SECRET_ACCESS_KEY"]="$AWS_SECRET_ACCESS_KEY"
            SECRETS+=("AWS_ACCESS_KEY_ID" "AWS_SECRET_ACCESS_KEY")
        fi
    fi
fi

for key in "${SECRETS[@]}"; do
    value="${ENV_VALUES[$key]:-}"
    if [[ -n "$value" ]]; then
        echo "Setting secret: $key"
        if [[ "$DRY_RUN" == false ]]; then
            echo "$value" | gh secret set "$key"
        fi
    else
        echo "Skipping secret: $key (empty)"
    fi
done

for key in "${VARIABLES[@]}"; do
    value="${ENV_VALUES[$key]:-}"
    if [[ -n "$value" ]]; then
        echo "Setting variable: $key = $value"
        if [[ "$DRY_RUN" == false ]]; then
            gh variable set "$key" --body "$value"
        fi
    else
        echo "Skipping variable: $key (empty)"
    fi
done

ENVIRONMENTS=("aws-dev" "aws-prod")

echo ""
echo "=== Creating GitHub environments ==="
for env in "${ENVIRONMENTS[@]}"; do
    echo "Creating environment: $env"
    if [[ "$DRY_RUN" == false ]]; then
        gh api -X PUT "repos/{owner}/{repo}/environments/$env" --silent 2>/dev/null || \
            echo "  (environment may already exist or requires admin access)"
    fi
done

echo "Restricting aws-prod to main branch..."
if [[ "$DRY_RUN" == false ]]; then
    gh api -X PUT "repos/{owner}/{repo}/environments/aws-prod" \
        -f deployment_branch_policy='{"protected_branches":false,"custom_branch_policies":true}' \
        --silent 2>/dev/null || true
    gh api -X POST "repos/{owner}/{repo}/environments/aws-prod/deployment-branch-policies" \
        -f name="main" \
        --silent 2>/dev/null || true
fi

if [[ "$DRY_RUN" == true ]]; then
    echo ""
    echo "(dry-run mode — no changes made)"
fi

echo ""
echo "=== Done ==="
