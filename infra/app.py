#!/usr/bin/env python3
"""CDK app entry point for SBIQ Conditions Evaluator."""

import os

import aws_cdk as cdk

from stacks.sbiq_conditions_stack import SbiqConditionsStack

# Pin account/region explicitly. CDK_DEFAULT_* are overwritten by the CDK CLI
# from the ambient AWS profile, so project-specific env vars are used instead.
KNOWN_ACCOUNT = "828351637694"
KNOWN_REGION = "us-east-2"

ACCOUNT = os.environ.get("SBIQ_AWS_ACCOUNT_ID", KNOWN_ACCOUNT)
REGION = os.environ.get("SBIQ_AWS_REGION", KNOWN_REGION)

print(f"[infra/app.py] Targeting account={ACCOUNT} region={REGION}")
if ACCOUNT != KNOWN_ACCOUNT or REGION != KNOWN_REGION:
    print(
        f"[infra/app.py] NOTE: overridden via SBIQ_AWS_ACCOUNT_ID/SBIQ_AWS_REGION "
        f"(default is account={KNOWN_ACCOUNT} region={KNOWN_REGION})"
    )

app = cdk.App()

stage = os.environ.get("STAGE", "dev")

SbiqConditionsStack(
    app,
    f"SbiqConditionsStack-{stage}",
    stage=stage,
    env=cdk.Environment(account=ACCOUNT, region=REGION),
)

app.synth()
