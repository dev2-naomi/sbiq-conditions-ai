"""Threads API routes."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException

from api.platform.models import StateResponse, ThreadCreate, ThreadResponse, ThreadSearch
from api.services.state import get_thread_history, get_thread_state
from api.thread_store import ThreadStore

router = APIRouter(tags=["threads"])


@router.post("/threads")
async def create_thread(body: ThreadCreate) -> ThreadResponse:
    """Create a new thread."""
    thread = ThreadStore.create_thread(metadata=body.metadata)
    return ThreadResponse(**thread)


@router.post("/threads/search")
async def search_threads(body: ThreadSearch) -> List[ThreadResponse]:
    """Search threads."""
    threads = ThreadStore.search_threads(
        metadata_filter=body.metadata,
        limit=body.limit,
        offset=body.offset,
    )
    return [ThreadResponse(**t) for t in threads]


@router.get("/threads/{thread_id}")
async def get_thread(thread_id: str) -> ThreadResponse:
    """Get thread by ID."""
    thread = ThreadStore.get_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    return ThreadResponse(**thread)


@router.get("/threads/{thread_id}/state")
async def get_state(thread_id: str) -> StateResponse:
    """Get current state for a thread."""
    state = get_thread_state(thread_id)
    if state is None:
        return StateResponse(values={}, next=[])
    return state


@router.post("/threads/{thread_id}/history")
async def get_history(
    thread_id: str,
    body: Optional[Dict[str, Any]] = None,
) -> List[StateResponse]:
    """Get state history for a thread."""
    limit = (body or {}).get("limit", 10)
    return get_thread_history(thread_id, limit=limit)
