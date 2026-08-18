"""Server-Sent Events utilities for streaming responses."""

from __future__ import annotations

import json
from typing import Any, AsyncIterator, Dict


def format_sse(event: str, data: Any) -> str:
    """Format a single SSE message."""
    if isinstance(data, (dict, list)):
        data_str = json.dumps(data)
    else:
        data_str = str(data)
    return f"event: {event}\ndata: {data_str}\n\n"


async def stream_graph_events(
    events: AsyncIterator[Dict[str, Any]],
    thread_id: str,
    run_id: str,
) -> AsyncIterator[str]:
    """Convert graph stream events to SSE format."""
    yield format_sse("metadata", {"run_id": run_id, "thread_id": thread_id})

    async for event in events:
        if isinstance(event, tuple) and len(event) == 2:
            node_name, state_update = event
            yield format_sse(
                "values",
                {"node": node_name, "values": state_update},
            )
        elif isinstance(event, dict):
            yield format_sse("values", event)

    yield format_sse("end", {"status": "completed"})
