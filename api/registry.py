"""Agent registry — provides compiled graph instances."""

from __future__ import annotations

from typing import Optional

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph

from api.checkpointer import get_checkpointer

_graph: Optional[CompiledStateGraph] = None
_checkpointer: Optional[BaseCheckpointSaver] = None


def get_graph() -> CompiledStateGraph:
    """Get or build the compiled agent graph with checkpointer."""
    global _graph, _checkpointer

    if _graph is not None:
        return _graph

    _checkpointer = get_checkpointer()

    from agent import build_graph

    _graph = build_graph(checkpointer=_checkpointer)

    return _graph


def get_graph_checkpointer() -> Optional[BaseCheckpointSaver]:
    """Return the checkpointer used by the graph (call after get_graph)."""
    return _checkpointer


ASSISTANT_ID = "conditions-evaluator"
ASSISTANT_NAME = "SBIQ Conditions Evaluator"
