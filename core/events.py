"""
Structured event system for the SDLC pipeline.

Events replace bare print/log calls and are consumable by:
  - The FastAPI SSE endpoint (real-time streaming to UI)
  - The logger (persisted to file)
  - Tests (event assertions)

Usage:
    emitter = EventEmitter()
    emitter.emit("step_started", step="compile", message="Running mvn compile")
    # subscribe:
    emitter.subscribe(lambda e: print(e))
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Dict, List, Optional


EVENT_TYPES = {
    "step_started",
    "step_completed",
    "step_failed",
    "step_skipped",
    "agent_started",
    "agent_completed",
    "agent_failed",
    "build_started",
    "build_failed",
    "build_succeeded",
    "tests_started",
    "tests_passed",
    "tests_failed",
    "quality_gate_passed",
    "quality_gate_failed",
    "pr_created",
    "commit_created",
    "graphrag_loaded",
    "pipeline_started",
    "pipeline_completed",
    "pipeline_failed",
    "log",
}


@dataclass
class PipelineEvent:
    event_type: str
    timestamp: float = field(default_factory=time.time)
    step: Optional[str] = None
    agent: Optional[str] = None
    status: Optional[str] = None   # success | failed | running | pending
    message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "step": self.step,
            "agent": self.agent,
            "status": self.status,
            "message": self.message,
            "data": self.data,
        }

    def to_sse(self) -> str:
        """Format as SSE data frame."""
        return f"data: {json.dumps(self.to_dict())}\n\n"


class EventEmitter:
    """Thread-safe, optionally async event bus."""

    def __init__(self):
        self._sync_listeners: List[Callable[[PipelineEvent], None]] = []
        self._async_queues: List[asyncio.Queue] = []
        self._history: List[PipelineEvent] = []

    def subscribe(self, listener: Callable[[PipelineEvent], None]) -> None:
        self._sync_listeners.append(listener)

    def subscribe_queue(self, queue: asyncio.Queue) -> None:
        """Subscribe an asyncio.Queue — used by SSE endpoint."""
        self._async_queues.append(queue)

    def unsubscribe_queue(self, queue: asyncio.Queue) -> None:
        self._async_queues = [q for q in self._async_queues if q is not queue]

    def emit(
        self,
        event_type: str,
        *,
        step: Optional[str] = None,
        agent: Optional[str] = None,
        status: Optional[str] = None,
        message: str = "",
        **data: Any,
    ) -> PipelineEvent:
        event = PipelineEvent(
            event_type=event_type,
            step=step,
            agent=agent,
            status=status,
            message=message,
            data=data,
        )
        self._history.append(event)
        for listener in self._sync_listeners:
            try:
                listener(event)
            except Exception:
                pass
        for queue in self._async_queues:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass
        return event

    def history(self) -> List[PipelineEvent]:
        return list(self._history)

    def history_dicts(self) -> List[Dict[str, Any]]:
        return [e.to_dict() for e in self._history]

    def clear_history(self) -> None:
        self._history.clear()


# Global emitter — shared between pipeline and API layer
_global_emitter = EventEmitter()


def get_emitter() -> EventEmitter:
    return _global_emitter


def reset_emitter() -> EventEmitter:
    global _global_emitter
    _global_emitter = EventEmitter()
    return _global_emitter
