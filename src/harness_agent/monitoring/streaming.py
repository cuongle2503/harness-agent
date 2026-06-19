"""Multi-mode streaming configuration and event routing.

Phase 7.1 — Routes agent stream events to the monitoring system.
See: docs/guides/plans/07-monitoring.md §7.1
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from harness_agent.monitoring.config import StreamingConfig
from harness_agent.monitoring.metrics import AgentMetrics


@dataclass
class StreamEvent:
    """A routed stream event for monitoring consumption.

    Attributes:
        event_type: Event classification — "token", "node_complete",
            "task_event", or "custom_event".
        mode: The stream mode that produced this event.
        data: Raw event payload.
        metadata: Additional context (thread_id, node name, etc.).
    """

    event_type: str
    mode: str
    data: Any
    metadata: dict[str, Any]


async def route_stream_to_monitoring(
    stream: AsyncIterator[tuple[str, Any]],
    _config: StreamingConfig,
    _metrics: AgentMetrics,
) -> AsyncIterator[StreamEvent]:
    """Route a multi-mode agent stream into monitoring events.

    Consumes an async iterator of ``(mode, data)`` tuples from
    ``agent.astream()`` and yields ``StreamEvent`` objects suitable
    for consumption by the monitoring dashboard, metrics collector,
    and logging middleware.

    Args:
        stream: Async iterator from ``agent.astream()``.
        config: Streaming configuration (modes, subgraphs, version).
        metrics: AgentMetrics collector (updated for task events).

    Yields:
        StreamEvent for each meaningful stream event.
    """
    async for mode, data in stream:
        event = _classify_event(mode, data)
        if event is not None:
            yield event


def _classify_event(mode: str, data: Any) -> StreamEvent | None:
    """Classify a raw ``(mode, data)`` pair into a StreamEvent.

    Returns None for unrecognized modes.
    """
    if mode == "messages":
        token: Any
        metadata: dict[str, Any]
        if isinstance(data, tuple):
            token, metadata = data
        else:
            token, metadata = data, {}
        return StreamEvent(
            event_type="token",
            mode="messages",
            data=token,
            metadata=metadata if isinstance(metadata, dict) else {},
        )
    if mode == "updates":
        node_name = (
            list(data.keys())[0]
            if isinstance(data, dict) and data
            else "unknown"
        )
        return StreamEvent(
            event_type="node_complete",
            mode="updates",
            data=data,
            metadata={"node": node_name},
        )
    if mode == "tasks":
        return StreamEvent(
            event_type="task_event",
            mode="tasks",
            data=data,
            metadata={},
        )
    if mode == "custom":
        return StreamEvent(
            event_type="custom_event",
            mode="custom",
            data=data,
            metadata={},
        )
    return None
