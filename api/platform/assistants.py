"""Assistants API routes."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from api.platform.models import AssistantResponse, AssistantSearch
from api.registry import ASSISTANT_ID, ASSISTANT_NAME

router = APIRouter(tags=["assistants"])

_now = datetime.now(timezone.utc).isoformat()

ASSISTANT = AssistantResponse(
    assistant_id=ASSISTANT_ID,
    name=ASSISTANT_NAME,
    graph_id="conditions-evaluator",
    config={},
    metadata={"description": "Underwriting conditions fulfillment evaluator"},
    created_at=_now,
    updated_at=_now,
)


@router.post("/assistants/search")
async def search_assistants(body: AssistantSearch) -> list[AssistantResponse]:
    """Return the single hardcoded assistant."""
    return [ASSISTANT]


@router.get("/assistants/{assistant_id}")
async def get_assistant(assistant_id: str) -> AssistantResponse:
    """Get assistant by ID."""
    return ASSISTANT
