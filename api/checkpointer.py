"""DynamoDB checkpointer setup for AWS deployment."""

from __future__ import annotations

import os
from typing import Optional

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver


def get_checkpointer() -> Optional[BaseCheckpointSaver]:
    """Build the appropriate checkpointer based on environment.

    - AWS (CHECKPOINT_TABLE_NAME set): DynamoDB
    - Local with CHECKPOINT_IN_MEMORY=true: MemorySaver
    - Otherwise: None (stateless)
    """
    table_name = os.environ.get("CHECKPOINT_TABLE_NAME")

    if table_name:
        from langgraph_checkpoint_aws import DynamoDBSaver

        return DynamoDBSaver(table_name=table_name)

    if os.environ.get("CHECKPOINT_IN_MEMORY", "").lower() == "true":
        return MemorySaver()

    return None
