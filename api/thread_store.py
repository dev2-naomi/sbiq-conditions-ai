"""Thread and run metadata storage backed by DynamoDB.

Uses the same table as the checkpointer, with a different PK prefix.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import boto3
from boto3.dynamodb.conditions import Key

from api.registry import ASSISTANT_ID


def _get_table():
    """Get DynamoDB table resource."""
    table_name = os.environ.get("CHECKPOINT_TABLE_NAME")
    if not table_name:
        raise RuntimeError("CHECKPOINT_TABLE_NAME not set")
    dynamodb = boto3.resource("dynamodb")
    return dynamodb.Table(table_name)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dynamodb_safe(value: Any) -> Any:
    """Convert values so boto3 DynamoDB can serialize them.

    Nested agent inputs often contain floats (e.g. OCR confidence). DynamoDB
    rejects Python float — use Decimal, or JSON-stringify large blobs.
    """
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: _dynamodb_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_dynamodb_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_dynamodb_safe(v) for v in value]
    return value


def _json_blob(value: Any) -> str:
    """Store arbitrary JSON as a string to avoid float/size map issues."""
    return json.dumps(value if value is not None else {}, default=str)


class ThreadStore:
    """Manage thread and run records in DynamoDB."""

    @staticmethod
    def create_thread(metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Create a new thread record."""
        table = _get_table()
        thread_id = str(uuid.uuid4())
        now = _now_iso()

        item = {
            "PK": f"THREAD#{thread_id}",
            "SK": "META",
            "thread_id": thread_id,
            "created_at": now,
            "updated_at": now,
            "metadata": _dynamodb_safe(metadata or {}),
        }
        table.put_item(Item=item)

        return {
            "thread_id": thread_id,
            "created_at": now,
            "updated_at": now,
            "metadata": metadata or {},
        }

    @staticmethod
    def get_thread(thread_id: str) -> Optional[Dict[str, Any]]:
        """Get thread by ID."""
        table = _get_table()
        response = table.get_item(Key={"PK": f"THREAD#{thread_id}", "SK": "META"})
        item = response.get("Item")
        if not item:
            return None
        return {
            "thread_id": item["thread_id"],
            "created_at": item["created_at"],
            "updated_at": item["updated_at"],
            "metadata": item.get("metadata", {}),
        }

    @staticmethod
    def search_threads(
        metadata_filter: Optional[Dict[str, Any]] = None,
        limit: int = 10,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Search threads (scan with filter)."""
        table = _get_table()

        # Simple scan — fine for low volume
        response = table.scan(
            FilterExpression=Key("SK").eq("META") & Key("PK").begins_with("THREAD#"),
            Limit=limit + offset,
        )

        threads = []
        for item in response.get("Items", [])[offset : offset + limit]:
            threads.append(
                {
                    "thread_id": item["thread_id"],
                    "created_at": item["created_at"],
                    "updated_at": item["updated_at"],
                    "metadata": item.get("metadata", {}),
                }
            )

        return threads

    @staticmethod
    def create_run(
        thread_id: str,
        assistant_id: str = ASSISTANT_ID,
        input_data: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a new run record."""
        table = _get_table()
        run_id = str(uuid.uuid4())
        now = _now_iso()

        item = {
            "PK": f"THREAD#{thread_id}",
            "SK": f"RUN#{run_id}",
            "run_id": run_id,
            "thread_id": thread_id,
            "assistant_id": assistant_id,
            "status": "pending",
            "created_at": now,
            "updated_at": now,
            # Store as JSON strings — sample inputs contain floats DynamoDB rejects
            "input": _json_blob(input_data),
            "config": _json_blob(config),
        }
        table.put_item(Item=item)

        return {
            "run_id": run_id,
            "thread_id": thread_id,
            "assistant_id": assistant_id,
            "status": "pending",
            "created_at": now,
            "updated_at": now,
        }

    @staticmethod
    def get_run(thread_id: str, run_id: str) -> Optional[Dict[str, Any]]:
        """Get run by ID."""
        table = _get_table()
        response = table.get_item(
            Key={"PK": f"THREAD#{thread_id}", "SK": f"RUN#{run_id}"}
        )
        item = response.get("Item")
        if not item:
            return None
        return {
            "run_id": item["run_id"],
            "thread_id": item["thread_id"],
            "assistant_id": item.get("assistant_id", ASSISTANT_ID),
            "status": item["status"],
            "created_at": item["created_at"],
            "updated_at": item["updated_at"],
            "error": item.get("error"),
        }

    @staticmethod
    def update_run(
        thread_id: str,
        run_id: str,
        status: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        """Update run status."""
        table = _get_table()
        update_expr = "SET updated_at = :now"
        expr_values: Dict[str, Any] = {":now": _now_iso()}
        expr_names: Dict[str, str] = {}

        if status:
            update_expr += ", #status = :status"
            expr_values[":status"] = status
            expr_names["#status"] = "status"
        if error is not None:
            update_expr += ", #error = :error"
            expr_values[":error"] = error
            expr_names["#error"] = "error"

        update_kwargs: Dict[str, Any] = {
            "Key": {"PK": f"THREAD#{thread_id}", "SK": f"RUN#{run_id}"},
            "UpdateExpression": update_expr,
            "ExpressionAttributeValues": expr_values,
        }
        if expr_names:
            update_kwargs["ExpressionAttributeNames"] = expr_names

        table.update_item(**update_kwargs)

    @staticmethod
    def list_runs(thread_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """List runs for a thread."""
        table = _get_table()
        response = table.query(
            KeyConditionExpression=Key("PK").eq(f"THREAD#{thread_id}")
            & Key("SK").begins_with("RUN#"),
            Limit=limit,
            ScanIndexForward=False,
        )

        runs = []
        for item in response.get("Items", []):
            runs.append(
                {
                    "run_id": item["run_id"],
                    "thread_id": item["thread_id"],
                    "assistant_id": item.get("assistant_id", ASSISTANT_ID),
                    "status": item["status"],
                    "created_at": item["created_at"],
                    "updated_at": item["updated_at"],
                    "error": item.get("error"),
                }
            )

        return runs

    @staticmethod
    def request_cancel(thread_id: str, run_id: str) -> None:
        """Set cancel_requested flag on a run."""
        table = _get_table()
        table.update_item(
            Key={"PK": f"THREAD#{thread_id}", "SK": f"RUN#{run_id}"},
            UpdateExpression="SET cancel_requested = :val, updated_at = :now",
            ExpressionAttributeValues={":val": True, ":now": _now_iso()},
        )

    @staticmethod
    def is_cancel_requested(thread_id: str, run_id: str) -> bool:
        """Check if cancellation was requested for a run."""
        table = _get_table()
        response = table.get_item(
            Key={"PK": f"THREAD#{thread_id}", "SK": f"RUN#{run_id}"},
            ProjectionExpression="cancel_requested",
        )
        item = response.get("Item", {})
        return bool(item.get("cancel_requested"))
