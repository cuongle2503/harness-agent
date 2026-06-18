"""Server deployment mode (Step 6.3).

Provides a FastAPI HTTP server for production deployment of the agent.
Supports health checks, agent invocation, and graceful shutdown.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, HTTPException
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from harness_agent.config import AgentModelSelection
from harness_agent.core.agent import HarnessAgent

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

    messages: list[dict[str, Any]] = Field(
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
    """

    assistant_id: str = "harness-agent-prod"
    host: str = "127.0.0.1"
    port: int = 2024
    sandbox_type: str = "docker"
    auto_approve: bool = False
    shell_allow_list: list[str] | None = None
    enable_memory: bool = True
    model_selection: AgentModelSelection | None = None

    def __post_init__(self) -> None:
        if self.shell_allow_list is None:
            self.shell_allow_list = [
                "ls", "cat", "grep", "find",
                "python", "pip", "git",
            ]


# ---------------------------------------------------------------------------
# Agent pool (in-memory, single-tenant; multi-tenant uses TenantAgentManager)
# ---------------------------------------------------------------------------

_agent_pool: dict[str, HarnessAgent] = {}


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

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> Any:  # noqa: ARG001
        """Startup and shutdown lifecycle."""
        llm = model_sel.to_langchain_model(model_sel.orchestrator)
        agent = HarnessAgent(
            llm=llm,
            tools=[],
            system_prompt=(
                "You are a production coding assistant for the "
                "Harness Agent project."
            ),
        )
        _agent_pool[cfg.assistant_id] = agent
        logger.info(
            "Agent server '%s' ready on %s:%d",
            cfg.assistant_id,
            cfg.host,
            cfg.port,
        )
        yield
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

        run_config: RunnableConfig = {
            "configurable": {"thread_id": request.thread_id or "default"}
        }
        result = await agent.ainvoke(
            {"messages": request.messages},
            config=run_config,
        )

        messages = result.get("messages", [])
        content = messages[-1].content if messages else ""
        tokens_used = result.get("token_usage", {}).get("total_tokens", 0)

        return AgentResponse(
            content=str(content),
            thread_id=request.thread_id or "default",
            tokens_used=int(tokens_used),
        )

    return app
