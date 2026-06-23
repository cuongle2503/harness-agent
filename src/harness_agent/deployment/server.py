"""Server deployment mode (Step 6.3).

Provides a FastAPI HTTP server for production deployment of the agent.
Supports health checks, agent invocation, and graceful shutdown.
"""

from __future__ import annotations

import logging
import time as _time_module
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from harness_agent.config import AgentModelSelection
from harness_agent.core.agent import HarnessAgent
from harness_agent.loaders.config_loader import ConfigLoader
from harness_agent.loaders.harness_builder import HarnessBuilder
from harness_agent.loaders.hook_loader import (
    EventBus,
    HookEvent,
    HookLoader,
)
from harness_agent.loaders.rule_loader import RuleLoader
from harness_agent.loaders.skill_loader import SkillLoader
from harness_agent.loaders.subagent_loader import SubAgentLoader
from harness_agent.monitoring.dashboard import (
    HealthDashboardResponse,
    MetricsResponse,
    build_dashboard_response,
)
from harness_agent.monitoring.metrics import AgentMetrics
from harness_agent.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class AgentMessage(BaseModel):
    """A single chat message."""

    role: str = Field(..., description="Message role: user, assistant, system")
    content: str = Field(..., description="Message content")


class AgentRequest(BaseModel):
    """Request body for agent invocation."""

    messages: list[AgentMessage] = Field(
        ..., description="List of chat messages"
    )
    thread_id: str | None = Field(
        "default", description="Session thread identifier"
    )


class AgentResponse(BaseModel):
    """Response body from agent invocation."""

    content: str = Field(..., description="Agent response text")
    thread_id: str = Field(..., description="Session thread identifier")
    tokens_used: int = Field(0, description="Total tokens used in this turn")


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = Field(..., description="Service status")
    agent_id: str = Field(..., description="Agent identifier")
    sandbox_type: str = Field(..., description="Sandbox configuration")


# ---------------------------------------------------------------------------
# Server configuration
# ---------------------------------------------------------------------------


@dataclass
class ServerConfig:
    """Configuration for the agent HTTP server.

    Attributes:
        assistant_id: Unique identifier for this agent instance.
        host: Bind address for the HTTP server.
        port: Bind port for the HTTP server.
        sandbox_type: Sandbox environment (docker, local, none).
        auto_approve: Whether to auto-approve tool calls.
        shell_allow_list: Whitelist of allowed shell commands.
        enable_memory: Toggle cross-session memory.
        model_selection: Agent model selection.
        max_tool_iterations: Max tool-calling loop iterations per turn.
    """

    assistant_id: str = "harness-agent-prod"
    host: str = "127.0.0.1"
    port: int = 2024
    sandbox_type: str = "docker"
    auto_approve: bool = False
    shell_allow_list: list[str] | None = None
    enable_memory: bool = True
    model_selection: AgentModelSelection | None = None
    max_tool_iterations: int = 50
    harness_dir: str = ""

    def __post_init__(self) -> None:
        if self.shell_allow_list is None:
            self.shell_allow_list = [
                "ls", "cat", "grep", "find",
                "python", "pip", "git",
            ]


# ---------------------------------------------------------------------------
# Agent pool (in-memory, single-tenant; multi-tenant uses TenantAgentManager)
# ---------------------------------------------------------------------------

_agent_pool: dict[str, Any] = {}
_agent_metrics: AgentMetrics = AgentMetrics()
_tool_history: list[dict[str, Any]] = []
_activity_log: list[dict[str, Any]] = []
_MAX_HISTORY = 200
_session_metrics: dict[str, dict[str, Any]] = {}


class _MetricsCallback(BaseCallbackHandler):
    """LangChain callback that records per-tool latency and LLM calls."""

    def __init__(self, metrics: AgentMetrics) -> None:
        super().__init__()
        self._metrics = metrics
        self._tool_starts: dict[UUID, tuple[float, str, str]] = {}
        self.llm_call_count: int = 0
        self.tool_call_count: int = 0

    def on_llm_start(
        self, serialized: dict[str, Any], prompts: list[str], *,
        run_id: UUID, **kwargs: Any,
    ) -> None:
        """Count each LLM API call the agent makes."""
        self.llm_call_count += 1

    def on_tool_start(
        self, serialized: dict[str, Any], input_str: str, *,
        run_id: UUID, **kwargs: Any,
    ) -> None:
        tool_name = serialized.get("name", "unknown")
        self.tool_call_count += 1
        self._tool_starts[run_id] = (_time_module.monotonic(), tool_name, input_str)
        _activity_log.append({
            "type": "tool_start", "name": tool_name,
            "input": input_str[:200] if input_str else "",
            "time": _time_module.time(),
        })
        if len(_activity_log) > _MAX_HISTORY:
            _activity_log.pop(0)

    def on_tool_end(
        self, output: Any, *, run_id: UUID, **kwargs: Any,
    ) -> None:
        entry = self._tool_starts.pop(run_id, None)
        if entry is not None:
            t0, tool_name, input_str = entry
            elapsed_ms = (_time_module.monotonic() - t0) * 1000
            output_str = str(output)[:500] if output else ""
            self._metrics.record_tool_call(
                tool_name, elapsed_ms, success=True
            )
            _tool_history.append({
                "name": tool_name,
                "input": input_str[:200] if input_str else "",
                "output": output_str,
                "latency_ms": round(elapsed_ms, 2),
                "success": True,
                "timestamp": _time_module.time(),
            })
            if len(_tool_history) > _MAX_HISTORY:
                _tool_history.pop(0)
            _activity_log.append({
                "type": "tool_end", "name": tool_name,
                "output": output_str[:200],
                "latency_ms": round(elapsed_ms, 2),
                "success": True, "time": _time_module.time(),
            })
            if len(_activity_log) > _MAX_HISTORY:
                _activity_log.pop(0)

    def on_tool_error(
        self, error: BaseException, *, run_id: UUID, **kwargs: Any,
    ) -> None:
        entry = self._tool_starts.pop(run_id, None)
        if entry is not None:
            t0, tool_name, input_str = entry
            elapsed_ms = (_time_module.monotonic() - t0) * 1000
            self._metrics.record_tool_call(
                tool_name, elapsed_ms, success=False
            )
            _tool_history.append({
                "name": tool_name,
                "input": input_str[:200] if input_str else "",
                "output": str(error)[:500],
                "latency_ms": round(elapsed_ms, 2),
                "success": False,
                "timestamp": _time_module.time(),
            })
            if len(_tool_history) > _MAX_HISTORY:
                _tool_history.pop(0)
            _activity_log.append({
                "type": "tool_end", "name": tool_name,
                "output": str(error)[:200],
                "latency_ms": round(elapsed_ms, 2),
                "success": False, "time": _time_module.time(),
            })
            if len(_activity_log) > _MAX_HISTORY:
                _activity_log.pop(0)


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


def create_server_app(
    config: ServerConfig | None = None,
) -> FastAPI:
    """Create a configured FastAPI application for the agent server.

    Args:
        config: Server configuration. Uses defaults when None.

    Returns:
        A FastAPI application ready to serve.
    """
    cfg = config or ServerConfig()

    if cfg.model_selection is None:
        cfg.model_selection = AgentModelSelection()

    # Extract to local so mypy can narrow the non-None type
    model_sel = cfg.model_selection

    _server_start_time = _time_module.monotonic()
    _memory_store: dict[str, Any] = {}
    _server_event_bus = EventBus()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> Any:  # noqa: ARG001
        """Startup and shutdown lifecycle.

        When ``harness_dir`` is set and contains a valid ``.harness/``
        directory, uses ``HarnessBuilder`` to create the agent with full
        MemoryMiddleware (progressive disclosure for skills/rules) and
        SubAgentMiddleware (task tool for subagents).

        Falls back to basic ``HarnessAgent`` when no harness is configured.
        """
        from harness_agent.tools.basic_tools import BASIC_TOOLS

        harness_dir = Path(cfg.harness_dir) if cfg.harness_dir else None
        harness_available = (
            harness_dir is not None and (harness_dir / ".harness").is_dir()
        )

        if harness_available and harness_dir is not None:
            # ── Use HarnessBuilder for full middleware support ──
            try:
                tool_registry = ToolRegistry()
                for t in BASIC_TOOLS:
                    tool_registry.register(t)

                builder = HarnessBuilder(
                    harness_dir,
                    tool_registry=tool_registry,
                    model_selection=model_sel,
                )
                graph = builder.build()
                _agent_pool[cfg.assistant_id] = graph
                _server_event_bus_ref = builder.event_bus

                # Load hooks for server lifecycle
                HookLoader(
                    harness_dir / ".harness", _server_event_bus
                ).load_all()

                logger.info(
                    "Agent server '%s' (harness mode) ready on %s:%d",
                    cfg.assistant_id,
                    cfg.host,
                    cfg.port,
                )
            except Exception as e:
                logger.warning(
                    "HarnessBuilder failed (%s), falling back to basic agent", e
                )
                harness_available = False

        if not harness_available:
            # ── Basic HarnessAgent (no .harness/ or builder failed) ──
            llm = model_sel.to_langchain_model(model_sel.orchestrator)

            # Resolve system prompt from harness config if available
            system_prompt = (
                "You are a production coding assistant for the "
                "Harness Agent project."
            )
            if harness_dir is not None:
                harness_path = harness_dir / ".harness"
                if harness_path.is_dir():
                    try:
                        config_loader = ConfigLoader(harness_path)
                        hconfig = config_loader.load()
                        custom = config_loader.load_system_prompt(
                            hconfig, harness_dir
                        )
                        if custom:
                            system_prompt = custom
                    except Exception as e:
                        logger.warning(
                            "Failed to load system prompt from %s: %s",
                            harness_path,
                            e,
                        )

            agent = HarnessAgent(
                llm=llm,
                tools=BASIC_TOOLS,
                system_prompt=system_prompt,
                max_tool_iterations=cfg.max_tool_iterations,
            )
            _agent_pool[cfg.assistant_id] = agent
            _server_event_bus_ref = _server_event_bus

            logger.info(
                "Agent server '%s' (basic mode) ready on %s:%d",
                cfg.assistant_id,
                cfg.host,
                cfg.port,
            )

        # Fire session_start hooks
        _server_event_bus_ref.fire(
            HookEvent.SESSION_START,
            {
                "session_id": cfg.assistant_id,
                "project_root": str(harness_dir) if harness_dir else "",
                "config": {
                    "model": getattr(model_sel.orchestrator, "model_id", "?"),
                },
                "timestamp": _time_module.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", _time_module.gmtime()
                ),
            },
        )

        yield

        # Fire session_end hooks
        _server_event_bus_ref.fire(
            HookEvent.SESSION_END,
            {
                "session_id": cfg.assistant_id,
                "total_tokens": int(_agent_metrics.total_tokens),
                "tool_calls_count": _agent_metrics.tool_calls,
                "duration_ms": int(
                    (_time_module.monotonic() - _server_start_time) * 1000
                ),
                "success": True,
            },
        )

        _agent_pool.pop(cfg.assistant_id, None)
        logger.info("Agent server '%s' shut down", cfg.assistant_id)

    app = FastAPI(
        lifespan=lifespan,
        title="Harness Agent Server",
        version="0.1.0",
        description="Production HTTP API for the Harness Agent framework.",
    )

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------

    @app.get("/health", response_model=HealthResponse)
    async def health_check() -> HealthResponse:
        """Health check endpoint."""
        if cfg.assistant_id not in _agent_pool:
            raise HTTPException(
                status_code=503, detail="Agent not ready"
            )
        return HealthResponse(
            status="healthy",
            agent_id=cfg.assistant_id,
            sandbox_type=cfg.sandbox_type,
        )

    @app.post("/agent/invoke", response_model=AgentResponse)
    async def invoke_agent(request: AgentRequest) -> AgentResponse:
        """Invoke the agent with a set of messages.

        Args:
            request: The agent request containing messages and thread_id.

        Returns:
            The agent's response.

        Raises:
            HTTPException 503: If the agent is not yet initialized.
        """
        agent = _agent_pool.get(cfg.assistant_id)
        if agent is None:
            raise HTTPException(
                status_code=503, detail="Agent not ready"
            )

        _agent_metrics.record_task_start()
        turn_start = _time_module.monotonic()
        thread_id = request.thread_id or "default"

        # Log user message
        user_content = str(request.messages[-1].content) if request.messages else ""
        _activity_log.append({
            "type": "user_msg", "content": user_content[:200],
            "thread": thread_id, "time": _time_module.monotonic(),
        })
        if len(_activity_log) > _MAX_HISTORY:
            _activity_log.pop(0)

        # Use callback to capture per-tool latency
        metrics_callback = _MetricsCallback(_agent_metrics)
        run_config: RunnableConfig = {
            "configurable": {"thread_id": thread_id},
            "callbacks": [metrics_callback],
        }

        # Log LLM call start
        _activity_log.append({
            "type": "llm_start", "model": model_sel.orchestrator.model_id,
            "time": _time_module.monotonic(),
        })
        if len(_activity_log) > _MAX_HISTORY:
            _activity_log.pop(0)

        result = await agent.ainvoke(
            {"messages": [m.model_dump() for m in request.messages]},
            config=run_config,
        )

        turn_elapsed_ms = (_time_module.monotonic() - turn_start) * 1000

        messages = result.get("messages", [])
        content = messages[-1].content if messages else ""

        # Extract token usage from AIMessage usage_metadata
        tokens_used = 0
        tokens_input = 0
        tokens_output = 0
        from langchain_core.messages import AIMessage as AIMessageCls
        for msg in messages:
            if isinstance(msg, AIMessageCls):
                um = getattr(msg, "usage_metadata", None) or {}
                tokens_used += um.get("total_tokens", 0)
                tokens_input += um.get("input_tokens", 0)
                tokens_output += um.get("output_tokens", 0)
                if not tokens_used:
                    tokens_used += um.get("input_tokens", 0) + um.get("output_tokens", 0)

        # Record model call metrics
        _agent_metrics.record_model_call(
            latency_ms=turn_elapsed_ms,
            success=True,
            tokens=int(tokens_used),
            input_tokens=int(tokens_input),
            output_tokens=int(tokens_output),
        )

        _agent_metrics.record_task_complete(turn_elapsed_ms)

        # Count tool calls this turn
        tool_count = sum(
            1 for m in messages
            if getattr(m, "tool_call_id", None) is not None
        )

        # Record per-session (per-thread) metrics
        # Use callback counters for accurate LLM/tool call counts
        actual_llm_calls = metrics_callback.llm_call_count
        actual_tool_calls = metrics_callback.tool_call_count
        sess = _session_metrics.get(thread_id)
        if sess is None:
            sess = {
                "thread_id": thread_id,
                "input_tokens": 0,
                "output_tokens": 0,
                "api_calls": 0,
                "tool_calls": 0,
                "turns": 0,
                "created_at": _time_module.time(),
            }
            _session_metrics[thread_id] = sess
        sess["input_tokens"] += int(tokens_input)
        sess["output_tokens"] += int(tokens_output)
        sess["api_calls"] += actual_llm_calls
        sess["tool_calls"] += actual_tool_calls
        sess["turns"] += 1
        sess["last_active"] = _time_module.monotonic()

        # Log completion
        _activity_log.append({
            "type": "turn_end", "tokens": int(tokens_used),
            "latency_ms": round(turn_elapsed_ms, 1),
            "tool_calls": tool_count,
            "time": _time_module.monotonic(),
        })
        if len(_activity_log) > _MAX_HISTORY:
            _activity_log.pop(0)

        # Persist to memory store
        _memory_store[thread_id] = _memory_store.get(thread_id, []) + [
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": str(content)},
        ]

        return AgentResponse(
            content=str(content),
            thread_id=thread_id,
            tokens_used=int(tokens_used),
        )

    @app.get("/metrics", response_model=MetricsResponse)
    async def get_metrics() -> MetricsResponse:
        """Expose all agent observability metrics in JSON.

        Returns all 9 key metrics plus percentile distributions.
        """
        data = _agent_metrics.to_dict()
        return MetricsResponse(**data)

    @app.get("/tool-history")
    async def get_tool_history(count: int = 20) -> list[dict[str, Any]]:
        """Return recent tool calls with name, input, output, and latency.

        Args:
            count: Max number of recent tool calls to return (default 20).
        """
        return _tool_history[-count:]

    @app.get("/activity")
    async def get_activity(count: int = 50) -> list[dict[str, Any]]:
        """Return recent activity events for real-time diagram.

        Events include: user_msg, llm_start, tool_start/tool_end,
        turn_end, system_prompt, etc.

        Args:
            count: Max number of recent events (default 50).
        """
        return _activity_log[-count:]

    @app.get("/sessions")
    async def get_sessions() -> list[dict[str, Any]]:
        """Return per-session (per-thread) metrics.

        Each entry includes thread_id, input/output tokens, API calls,
        tool calls, turn count, created_at, and last_active timestamp.
        """
        return sorted(
            _session_metrics.values(),
            key=lambda s: s.get("last_active", 0),
            reverse=True,
        )

    @app.get("/dashboard", response_model=HealthDashboardResponse)
    async def get_dashboard() -> HealthDashboardResponse:
        """Health dashboard with all 8 panels.

        Panels: Agent Status, Request Rate, Error Rate, Latency,
        Token Usage, Subagent Activity, HITL Status, Memory Usage.
        """
        uptime = _time_module.monotonic() - _server_start_time
        return build_dashboard_response(
            metrics=_agent_metrics,
            uptime_seconds=uptime,
            memory_item_count=sum(len(v) for v in _memory_store.values()),
        )

    @app.get("/ui", response_class=HTMLResponse)
    async def dashboard_ui() -> HTMLResponse:
        """Serve the AIDLC monitoring dashboard UI.

        Returns the single-page web dashboard with real-time metrics,
        tool call feed, and chat interface.
        """
        ui_dir = Path(__file__).resolve().parent / "ui"
        html_path = ui_dir / "dashboard.html"
        if not html_path.exists():
            raise HTTPException(
                status_code=404, detail="Dashboard UI not found"
            )
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))

    @app.get("/ui/activity", response_class=HTMLResponse)
    async def activity_ui() -> HTMLResponse:
        """Serve the real-time activity trace page."""
        ui_dir = Path(__file__).resolve().parent / "ui"
        html_path = ui_dir / "activity.html"
        if not html_path.exists():
            raise HTTPException(status_code=404, detail="Activity UI not found")
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))

    # ── Harness Info Endpoints ──────────────────────────────────────────

    # Initialize loaders from harness_dir if provided
    _harness_path = (
        Path(cfg.harness_dir) if cfg.harness_dir else Path(".harness")
    )
    _skill_loader = SkillLoader(_harness_path)
    _rule_loader = RuleLoader(_harness_path)
    _tool_registry = ToolRegistry()
    _subagent_loader = SubAgentLoader(_harness_path, _tool_registry)
    _hook_loader = HookLoader(_harness_path)

    @app.get("/harness")
    async def get_harness_registry() -> dict[str, Any]:
        """Return a combined registry of all harness components.

        Includes skills, rules, hooks, and subagents found in the
        .harness/ directory.
        """
        return {
            "skills": [
                {"name": s.name, "size": s.size}
                for s in _skill_loader.list_skills()
            ],
            "rules": [
                {"name": r.name, "path": r.relative_path, "size": r.size}
                for r in _rule_loader.list_rules()
            ],
            "hooks": [
                {"name": h.name, "event": h.event, "language": h.language}
                for h in _hook_loader.list_hooks()
            ],
            "subagents": [
                {
                    "name": s.name,
                    "description": s.description,
                    "source_file": s.source_file,
                    "tool_count": s.tool_count,
                }
                for s in _subagent_loader.list_subagents()
            ],
        }

    @app.get("/skills")
    async def get_skills() -> list[dict[str, Any]]:
        """List all skills from .harness/skills/."""
        return [
            {"name": s.name, "size": s.size}
            for s in _skill_loader.list_skills()
        ]

    @app.get("/rules")
    async def get_rules() -> list[dict[str, Any]]:
        """List all rules from .harness/rules/."""
        return [
            {"name": r.name, "path": r.relative_path, "size": r.size}
            for r in _rule_loader.list_rules()
        ]

    @app.get("/hooks")
    async def get_hooks() -> list[dict[str, Any]]:
        """List all hooks from .harness/hooks/."""
        return [
            {"name": h.name, "event": h.event, "language": h.language}
            for h in _hook_loader.list_hooks()
        ]

    @app.get("/subagents")
    async def get_subagents() -> list[dict[str, Any]]:
        """List all subagents from .harness/subagents/."""
        return [
            {
                "name": s.name,
                "description": s.description,
                "source_file": s.source_file,
                "tool_count": s.tool_count,
            }
            for s in _subagent_loader.list_subagents()
        ]

    return app


def main() -> None:
    """Entry point for the agent server.

    Automatically loads .env and starts uvicorn.
    Usage: python -m harness_agent.deployment.server
    """
    import os
    from pathlib import Path

    # Load .env
    env_paths = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parent.parent.parent.parent / ".env",
    ]
    for env_path in env_paths:
        if env_path.exists():
            from dotenv import load_dotenv

            load_dotenv(env_path)
            break

    import uvicorn

    host = os.environ.get("HARNESS_HOST", "127.0.0.1")
    port = int(os.environ.get("HARNESS_PORT", "2024"))

    uvicorn.run(
        "harness_agent.deployment.server:create_server_app",
        host=host,
        port=port,
        factory=True,
        reload=False,
    )


if __name__ == "__main__":
    main()
