"""Runs API routes."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from api.platform.models import RunCreate, RunResponse
from api.registry import ASSISTANT_ID
from api.services.runs import execute_run_stream, execute_run_wait
from api.thread_store import ThreadStore

router = APIRouter(tags=["runs"])


@router.post("/threads/{thread_id}/runs")
async def create_run(thread_id: str, body: RunCreate) -> RunResponse:
    """Create a background run (returns immediately, poll for status)."""
    thread = ThreadStore.get_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    run = ThreadStore.create_run(
        thread_id=thread_id,
        assistant_id=body.assistant_id or ASSISTANT_ID,
        input_data=body.input,
        config=body.config,
    )

    # Execute synchronously since Lambda runs are short enough
    from api.services.runs import execute_run_background

    execute_run_background(thread_id, run["run_id"], body.input or {}, body.config)

    return RunResponse(**run)


@router.post("/threads/{thread_id}/runs/wait")
async def create_run_wait(thread_id: str, body: RunCreate) -> RunResponse:
    """Create and wait for a run to complete."""
    thread = ThreadStore.get_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    run = ThreadStore.create_run(
        thread_id=thread_id,
        assistant_id=body.assistant_id or ASSISTANT_ID,
        input_data=body.input,
        config=body.config,
    )

    await execute_run_wait(thread_id, run["run_id"], body.input or {}, body.config)

    updated_run = ThreadStore.get_run(thread_id, run["run_id"])
    return RunResponse(**updated_run)


@router.post("/threads/{thread_id}/runs/stream")
async def create_run_stream(thread_id: str, body: RunCreate):
    """Create a run and stream events."""
    thread = ThreadStore.get_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    run = ThreadStore.create_run(
        thread_id=thread_id,
        assistant_id=body.assistant_id or ASSISTANT_ID,
        input_data=body.input,
        config=body.config,
    )

    return StreamingResponse(
        execute_run_stream(thread_id, run["run_id"], body.input or {}, body.config),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/threads/{thread_id}/runs")
async def list_runs(thread_id: str, limit: int = 10) -> List[RunResponse]:
    """List runs for a thread."""
    runs = ThreadStore.list_runs(thread_id, limit=limit)
    return [RunResponse(**r) for r in runs]


@router.get("/threads/{thread_id}/runs/{run_id}")
async def get_run(thread_id: str, run_id: str) -> RunResponse:
    """Get run by ID."""
    run = ThreadStore.get_run(thread_id, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return RunResponse(**run)


@router.post("/threads/{thread_id}/runs/{run_id}/cancel")
async def cancel_run(thread_id: str, run_id: str) -> RunResponse:
    """Request cancellation of a run."""
    run = ThreadStore.get_run(thread_id, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    ThreadStore.request_cancel(thread_id, run_id)
    ThreadStore.update_run(thread_id, run_id, status="cancelled")

    updated_run = ThreadStore.get_run(thread_id, run_id)
    return RunResponse(**updated_run)
