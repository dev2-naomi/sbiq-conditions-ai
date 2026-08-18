"""Load secrets from AWS Secrets Manager at cold start.

Must be called before importing any module that captures env vars at import time.
"""

from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)

_loaded = False


def load_secrets() -> None:
    """Fetch secrets from Secrets Manager and inject into os.environ."""
    global _loaded
    if _loaded:
        return
    _loaded = True

    secret_arn = os.environ.get("AGENT_SECRETS_ARN")
    if not secret_arn:
        logger.info("AGENT_SECRETS_ARN not set — skipping Secrets Manager load (local dev)")
        return

    try:
        import boto3

        client = boto3.client("secretsmanager")
        response = client.get_secret_value(SecretId=secret_arn)
        secrets = json.loads(response["SecretString"])

        for key, value in secrets.items():
            if key.startswith("_"):
                continue
            if value:
                os.environ.setdefault(key, value)
                logger.debug("Loaded secret: %s", key)

        logger.info("Loaded %d secrets from Secrets Manager", len(secrets))
    except Exception as e:
        logger.error("Failed to load secrets from %s: %s", secret_arn, e)
        raise
