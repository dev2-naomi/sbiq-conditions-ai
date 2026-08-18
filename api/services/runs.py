"""Run execution services."""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, AsyncIterator, Dict, Optional

from api.platform.sse import format_sse
from api.registry import get_graph
from api.thread_store import ThreadStore

logger = logging.getLogger(__name__)


async def execute_run_wait(
    thread_id: str,
    run_id: str,
    input_data: Dict[str, Any],
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Execute a run and wait for completion."""
    graph = get_graph()
    run_config = {
        "configurable": {
            "thread_id": thread_id,
            **(config.get("configurable", {}) if config else {}),
        }
    }

    ThreadStore.update_run(thread_id, run_id, status="running")

    try:
        # Graph nodes are sync; run invoke off the event loop.
        result = await asyncio.to_thread(graph.invoke, input_data, run_config)
        ThreadStore.update_run(thread_id, run_id, status="success")
        return result
    except Exception as e:
        logger.error("Run %s failed: %s", run_id, e)
        ThreadStore.update_run(thread_id, run_id, status="error", error=str(e))
        raise


async def execute_run_stream(
    thread_id: str,
    run_id: str,
    input_data: Dict[str, Any],
    config: Optional[Dict[str, Any]] = None,
) -> AsyncIterator[str]:
    """Execute a run and stream events."""
    graph = get_graph()
    run_config = {
        "configurable": {
            "thread_id": thread_id,
            **(config.get("configurable", {}) if config else {}),
        }
    }

    yield format_sse("metadata", {"run_id": run_id, "thread_id": thread_id})

    ThreadStore.update_run(thread_id, run_id, status="running")

    try:
        # Sync graph.stream in a worker thread; pump events as they arrive.
        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def _produce() -> None:
            try:
                for event in graph.stream(input_data, run_config):
                    asyncio.run_coroutine_threadsafe(queue.put(("event", event)), loop).result()
                asyncio.run_coroutine_threadsafe(queue.put(("done", None)), loop).result()
            except Exception as exc:  # noqa: BLE001
                asyncio.run_coroutine_threadsafe(queue.put(("error", exc)), loop).result()

        threading.Thread(target=_produce, daemon=True).start()

        while True:
            kind, payload = await queue.get()
            if kind == "done":
                break
            if kind == "error":
                raise payload
            if ThreadStore.is_cancel_requested(thread_id, run_id):
                yield format_sse("error", {"message": "Run cancelled"})
                ThreadStore.update_run(thread_id, run_id, status="cancelled")
                return

            event = payload
            if isinstance(event, tuple) and len(event) == 2:
                node_name, state_update = event
                yield format_sse("values", {"node": node_name, "values": state_update})
            elif isinstance(event, dict):
                for node_name, state_update in event.items():
                    yield format_sse(
                        "values", {"node": node_name, "values": state_update}
                    )

        ThreadStore.update_run(thread_id, run_id, status="success")
        yield format_sse("end", {"status": "success"})

    except Exception as e:
        logger.error("Run %s failed: %s", run_id, e)
        ThreadStore.update_run(thread_id, run_id, status="error", error=str(e))
        yield format_sse("error", {"message": str(e)})


def execute_run_background(
    thread_id: str,
    run_id: str,
    input_data: Dict[str, Any],
    config: Optional[Dict[str, Any]] = None,
) -> None:
    """Execute a run in a background thread (for Lambda-only deployment)."""

    def run_in_thread():
        graph = get_graph()
        run_config = {
            "configurable": {
                "thread_id": thread_id,
                **(config.get("configurable", {}) if config else {}),
            }
        }

        ThreadStore.update_run(thread_id, run_id, status="running")

        try:
            graph.invoke(input_data, run_config)
            ThreadStore.update_run(thread_id, run_id, status="success")
        except Exception as e:
            logger.error("Background run %s failed: %s", run_id, e)
            ThreadStore.update_run(thread_id, run_id, status="error", error=str(e))

    thread = threading.Thread(target=run_in_thread, daemon=True)
    thread.start()
