"""AWS CDK stack for the SBIQ Conditions Evaluator (Lambda-only).

Architecture:
- Lambda Function URL = API front door (Platform-compatible FastAPI shim)
- DynamoDB = checkpoints + thread/run metadata
- Secrets Manager = credentials
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from aws_cdk import (
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
    aws_dynamodb as dynamodb,
    aws_ecr_assets as ecr_assets,
    aws_lambda as lambda_,
    aws_logs as logs,
    aws_secretsmanager as secretsmanager,
)
from constructs import Construct

REPO_ROOT = Path(__file__).resolve().parents[2]

IMAGE_EXCLUDE = [
    ".env",
    ".git",
    ".cursor",
    ".langgraph_api",
    "venv",
    ".venv",
    "infra",
    ".github",
    "docs",
    "tests",
    "cdk.out*",
    "logs",
    "tmp",
    "plans/*.md.bak",
    "sbiq-conditions-ai-documentation",
    "sbiq-conditions-ai-documentation.zip",
    "test_results*.json",
    "test_pipeline.py",
    "run_cloud.py",
    "**/__pycache__",
    "*.log",
    ".DS_Store",
    "output*.json",
]

SECRET_KEYS = [
    "API_KEY",
    "ANTHROPIC_API_KEY",
    "LANGSMITH_API_KEY",
    "LANGCHAIN_API_KEY",
    "LANGSMITH_PROJECT",
    "ANTHROPIC_MODEL",
]

OPTIONAL_PLAIN_ENV = [
    "LANGSMITH_TRACING",
]


def _deploy_env(name: str, default: str = "") -> str:
    """Read deploy-time env."""
    return os.environ.get(name, default)


class SbiqConditionsStack(Stack):
    def __init__(
        self, scope: Construct, construct_id: str, *, stage: str, **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        is_prod = stage == "prod"
        function_name = f"sbiq-conditions-ai-{stage}"

        checkpoint_table = dynamodb.Table(
            self,
            "CheckpointTable",
            table_name=f"sbiq-conditions-ai-checkpoints-{stage}",
            partition_key=dynamodb.Attribute(
                name="PK", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(name="SK", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN if is_prod else RemovalPolicy.DESTROY,
        )

        agent_secrets = secretsmanager.Secret(
            self,
            "AgentSecrets",
            secret_name=f"sbiq-conditions-ai-secrets-{stage}",
            description=(
                f"SBIQ Conditions Evaluator credentials ({stage}). "
                "Values are managed out-of-band via aws secretsmanager put-secret-value."
            ),
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template=json.dumps({key: "" for key in SECRET_KEYS}),
                generate_string_key="_cfn_placeholder",
                exclude_punctuation=True,
            ),
        )

        log_group = logs.LogGroup(
            self,
            "FunctionLogGroup",
            log_group_name=f"/aws/lambda/{function_name}",
            retention=(
                logs.RetentionDays.THREE_MONTHS
                if is_prod
                else logs.RetentionDays.ONE_WEEK
            ),
            removal_policy=RemovalPolicy.RETAIN if is_prod else RemovalPolicy.DESTROY,
        )

        environment = {
            "CHECKPOINT_TABLE_NAME": checkpoint_table.table_name,
            "AGENT_SECRETS_ARN": agent_secrets.secret_arn,
            "LANGSMITH_PROJECT": _deploy_env(
                f"LANGSMITH_{stage.upper()}_PROJECT", f"sbiq-conditions-ai-{stage}"
            ),
            "LANGSMITH_TRACING": _deploy_env("LANGSMITH_TRACING", "true"),
            "CORS_ALLOW_ORIGINS": _deploy_env("CORS_ALLOW_ORIGINS", "*"),
            "AWS_LWA_INVOKE_MODE": "response_stream",
            "AWS_LWA_READINESS_CHECK_PATH": "/health",
            "PORT": "8080",
        }
        for name in OPTIONAL_PLAIN_ENV:
            value = _deploy_env(name)
            if value:
                environment[name] = value

        agent_image = ecr_assets.DockerImageAsset(
            self,
            "AgentImage",
            directory=str(REPO_ROOT),
            file="api/Dockerfile",
            exclude=IMAGE_EXCLUDE,
            platform=ecr_assets.Platform.LINUX_ARM64,
        )

        agent_fn = lambda_.DockerImageFunction(
            self,
            "AgentFunction",
            function_name=function_name,
            description=f"SBIQ Conditions Evaluator LangGraph agent API ({stage})",
            code=lambda_.DockerImageCode.from_ecr(
                repository=agent_image.repository,
                tag_or_digest=agent_image.image_tag,
            ),
            memory_size=3008,
            timeout=Duration.seconds(900),
            architecture=lambda_.Architecture.ARM_64,
            environment=environment,
            log_group=log_group,
        )
        agent_fn.node.add_dependency(agent_image)

        checkpoint_table.grant_read_write_data(agent_fn)
        agent_secrets.grant_read(agent_fn)

        agent_fn.configure_async_invoke(retry_attempts=0)

        _cors_origins = [
            o.strip()
            for o in _deploy_env("CORS_ALLOW_ORIGINS", "*").split(",")
            if o.strip()
        ] or ["*"]

        function_url = agent_fn.add_function_url(
            auth_type=lambda_.FunctionUrlAuthType.NONE,
            invoke_mode=lambda_.InvokeMode.RESPONSE_STREAM,
            cors=lambda_.FunctionUrlCorsOptions(
                allowed_origins=_cors_origins,
                allowed_methods=[lambda_.HttpMethod.ALL],
                allowed_headers=[
                    "content-type",
                    "accept",
                    "authorization",
                    "x-api-key",
                    "x-auth-scheme",
                ],
                allow_credentials=False,
            ),
        )

        CfnOutput(self, "ApiUrl", value=function_url.url)
        CfnOutput(self, "CheckpointTableName", value=checkpoint_table.table_name)
        CfnOutput(self, "AgentSecretsArn", value=agent_secrets.secret_arn)
        CfnOutput(self, "LambdaFunctionName", value=agent_fn.function_name)
        CfnOutput(self, "Stage", value=stage)
