"""State management services."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from api.platform.models import StateResponse
from api.registry import get_graph, get_graph_checkpointer


def _serialize_snapshot(snapshot) -> StateResponse:
    """Convert a LangGraph StateSnapshot to API response format."""
    if snapshot is None:
        return StateResponse(values={}, next=[])

    checkpoint = None
    parent_checkpoint = None

    if hasattr(snapshot, "config") and snapshot.config:
        cfg = snapshot.config.get("configurable", {})
        if cfg.get("checkpoint_id"):
            checkpoint = {
                "checkpoint_id": cfg.get("checkpoint_id"),
                "checkpoint_ns": cfg.get("checkpoint_ns", ""),
            }

    if hasattr(snapshot, "parent_config") and snapshot.parent_config:
        pcfg = snapshot.parent_config.get("configurable", {})
        if pcfg.get("checkpoint_id"):
            parent_checkpoint = {
                "checkpoint_id": pcfg.get("checkpoint_id"),
                "checkpoint_ns": pcfg.get("checkpoint_ns", ""),
            }

    values = {}
    if hasattr(snapshot, "values") and snapshot.values:
        values = dict(snapshot.values)

    next_nodes = []
    if hasattr(snapshot, "next") and snapshot.next:
        next_nodes = list(snapshot.next)

    tasks = []
    if hasattr(snapshot, "tasks") and snapshot.tasks:
        for task in snapshot.tasks:
            tasks.append(
                {
                    "id": getattr(task, "id", None),
                    "name": getattr(task, "name", None),
                    "interrupts": getattr(task, "interrupts", []),
                }
            )

    return StateResponse(
        values=values,
        next=next_nodes,
        checkpoint=checkpoint,
        parent_checkpoint=parent_checkpoint,
        tasks=tasks,
    )


def get_thread_state(thread_id: str) -> Optional[StateResponse]:
    """Get current state for a thread."""
    graph = get_graph()
    config = {"configurable": {"thread_id": thread_id}}

    try:
        snapshot = graph.get_state(config)
        if snapshot is None:
            return None
        return _serialize_snapshot(snapshot)
    except Exception:
        return None


def get_thread_history(thread_id: str, limit: int = 10) -> List[StateResponse]:
    """Get state history for a thread."""
    graph = get_graph()
    config = {"configurable": {"thread_id": thread_id}}

    history = []
    try:
        for i, snapshot in enumerate(graph.get_state_history(config)):
            if i >= limit:
                break
            history.append(_serialize_snapshot(snapshot))
    except Exception:
        pass

    return history
