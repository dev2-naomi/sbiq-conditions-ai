"""DynamoDB checkpointer setup for AWS deployment."""

from __future__ import annotations

import os
from typing import Optional

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver


def get_checkpointer() -> Optional[BaseCheckpointSaver]:
    """Build the appropriate checkpointer based on environment.

    - AWS (CHECKPOINT_TABLE_NAME set): DynamoDB, compressed; checkpoints over 350 KB go to
      CHECKPOINT_S3_BUCKET when set (a DynamoDB item caps at 400 KB, and OCR-heavy
      documents_json is stored more than once in state)
    - Local with CHECKPOINT_IN_MEMORY=true: MemorySaver
    - Otherwise: None (stateless)
    """
    table_name = os.environ.get("CHECKPOINT_TABLE_NAME")

    if table_name:
        from langgraph_checkpoint_aws import DynamoDBSaver

        bucket = os.environ.get("CHECKPOINT_S3_BUCKET")
        return DynamoDBSaver(
            table_name=table_name,
            enable_checkpoint_compression=True,
            s3_offload_config={"bucket_name": bucket} if bucket else None,
        )

    if os.environ.get("CHECKPOINT_IN_MEMORY", "").lower() == "true":
        return MemorySaver()

    return None
