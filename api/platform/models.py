"""Pydantic models for API requests/responses."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ThreadCreate(BaseModel):
    metadata: Optional[Dict[str, Any]] = None


class ThreadResponse(BaseModel):
    thread_id: str
    created_at: str
    updated_at: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ThreadSearch(BaseModel):
    metadata: Optional[Dict[str, Any]] = None
    limit: int = 10
    offset: int = 0


class RunCreate(BaseModel):
    assistant_id: Optional[str] = None
    input: Optional[Dict[str, Any]] = None
    config: Optional[Dict[str, Any]] = None
    stream_mode: Optional[List[str]] = None
    interrupt_before: Optional[List[str]] = None
    interrupt_after: Optional[List[str]] = None


class RunResponse(BaseModel):
    run_id: str
    thread_id: str
    assistant_id: str
    status: str
    created_at: str
    updated_at: str
    error: Optional[str] = None


class AssistantResponse(BaseModel):
    assistant_id: str
    name: str
    graph_id: str
    config: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str


class AssistantSearch(BaseModel):
    metadata: Optional[Dict[str, Any]] = None
    limit: int = 10
    offset: int = 0


class StateResponse(BaseModel):
    values: Dict[str, Any]
    next: List[str] = Field(default_factory=list)
    checkpoint: Optional[Dict[str, Any]] = None
    parent_checkpoint: Optional[Dict[str, Any]] = None
    tasks: List[Dict[str, Any]] = Field(default_factory=list)
