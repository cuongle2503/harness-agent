"""Unit tests for Phase 6 deployment modules — CLI, server, multi-tenant."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from harness_agent.deployment.cli import CLIAgent, CLIAgentConfig, create_cli_agent
from harness_agent.deployment.multi_tenant import (
    TenantAgentManager,
    TenantManagerConfig,
)
from harness_agent.deployment.server import (
    AgentRequest,
    AgentResponse,
    HealthResponse,
    ServerConfig,
    create_server_app,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Ensure a fake API key is set so ChatDeepSeek can be instantiated.
# The dataclass default_factory=AgentModelSelection captures the class at
# definition time, so patching AgentModelSelection alone doesn't intercept
# the factory.  Patching ChatDeepSeek at the package level works because
# to_langchain_model uses `from langchain_deepseek import ChatDeepSeek`.
_LLM_PATCH_PATH = "langchain_deepseek.ChatDeepSeek"


@pytest.fixture(autouse=True)
def _set_fake_api_key(monkeypatch) -> None:
    """Inject a fake DEEPSEEK_API_KEY so ChatDeepSeek validates."""
    monkeypatch.setitem(os.environ, "DEEPSEEK_API_KEY", "test-fake-key")


# ---------------------------------------------------------------------------
# CLI Agent tests
# ---------------------------------------------------------------------------


class TestCLIAgentConfig:
    """Tests for CLIAgentConfig dataclass."""

    def test_default_config(self) -> None:
        """Verify default CLIAgentConfig values."""
        config = CLIAgentConfig()
        assert config.assistant_id == "harness-agent-cli"
        assert config.enable_memory is True
        assert config.enable_skills is True
        assert config.sandbox_type == "docker"
        assert "git" in config.shell_allow_list
        assert "pytest" in config.shell_allow_list

    def test_custom_config(self) -> None:
        """Verify custom CLIAgentConfig overrides defaults."""
        config = CLIAgentConfig(
            assistant_id="my-agent",
            enable_memory=False,
            shell_allow_list=["ls", "cat"],
        )
        assert config.assistant_id == "my-agent"
        assert config.enable_memory is False
        assert config.shell_allow_list == ["ls", "cat"]


class TestCLIAgent:
    """Tests for the CLIAgent class."""

    def test_create_with_defaults(self, fake_llm) -> None:
        """CLIAgent can be created with default config."""
        with patch(_LLM_PATCH_PATH, return_value=fake_llm):
            agent = CLIAgent()
            assert agent is not None
            assert agent.config.assistant_id == "harness-agent-cli"

    def test_create_with_config(self, fake_llm) -> None:
        """CLIAgent can be created with a custom config."""
        config = CLIAgentConfig(assistant_id="test-cli")
        with patch(_LLM_PATCH_PATH, return_value=fake_llm):
            agent = CLIAgent(config=config)
            assert agent.config.assistant_id == "test-cli"

    def test_invoke_sync(self, fake_llm) -> None:
        """CLIAgent.invoke_sync returns a response string."""
        with patch(_LLM_PATCH_PATH, return_value=fake_llm):
            agent = CLIAgent()
            result = agent.invoke_sync("hello")
            assert isinstance(result, str)
            assert len(result) > 0

    @pytest.mark.asyncio
    async def test_invoke_async(self, fake_llm) -> None:
        """CLIAgent.invoke (async) returns a response string."""
        with patch(_LLM_PATCH_PATH, return_value=fake_llm):
            agent = CLIAgent()
            result = await agent.invoke("hello")
            assert isinstance(result, str)
            assert len(result) > 0

    @pytest.mark.asyncio
    async def test_invoke_with_thread_id(self, fake_llm) -> None:
        """CLIAgent tracks conversations by thread_id."""
        with patch(_LLM_PATCH_PATH, return_value=fake_llm):
            agent = CLIAgent()
            result = await agent.invoke("hello", thread_id="session-42")
            assert isinstance(result, str)


class TestCreateCLIAgent:
    """Tests for the create_cli_agent factory function."""

    def test_factory_returns_cli_agent(self, fake_llm) -> None:
        """create_cli_agent returns a CLIAgent instance."""
        with patch(_LLM_PATCH_PATH, return_value=fake_llm):
            agent = create_cli_agent()
            assert isinstance(agent, CLIAgent)

    def test_factory_accepts_config(self, fake_llm) -> None:
        """create_cli_agent accepts a CLIAgentConfig."""
        config = CLIAgentConfig(assistant_id="factory-test")
        with patch(_LLM_PATCH_PATH, return_value=fake_llm):
            agent = create_cli_agent(config=config)
            assert agent.config.assistant_id == "factory-test"


# ---------------------------------------------------------------------------
# Server tests
# ---------------------------------------------------------------------------


class TestServerConfig:
    """Tests for ServerConfig dataclass."""

    def test_default_config(self) -> None:
        """Verify default ServerConfig values."""
        config = ServerConfig()
        assert config.assistant_id == "harness-agent-prod"
        assert config.host == "127.0.0.1"
        assert config.port == 2024
        assert config.sandbox_type == "docker"
        assert config.auto_approve is False
        assert config.enable_memory is True

    def test_custom_config(self) -> None:
        """Verify custom ServerConfig overrides."""
        config = ServerConfig(
            assistant_id="custom-server",
            port=9090,
            auto_approve=True,
        )
        assert config.assistant_id == "custom-server"
        assert config.port == 9090
        assert config.auto_approve is True


class TestAgentRequest:
    """Tests for the AgentRequest Pydantic model."""

    def test_valid_request(self) -> None:
        """AgentRequest with valid messages."""
        req = AgentRequest(
            messages=[{"role": "user", "content": "hello"}],
            thread_id="test-1",
        )
        assert req.thread_id == "test-1"
        assert len(req.messages) == 1
        assert req.messages[0]["role"] == "user"

    def test_default_thread_id(self) -> None:
        """AgentRequest uses 'default' thread_id when not specified."""
        req = AgentRequest(
            messages=[{"role": "user", "content": "hi"}],
        )
        assert req.thread_id == "default"

    def test_messages_required(self) -> None:
        """AgentRequest requires messages field."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            AgentRequest()  # type: ignore[call-arg]


class TestAgentResponse:
    """Tests for the AgentResponse Pydantic model."""

    def test_valid_response(self) -> None:
        """AgentResponse with all fields."""
        resp = AgentResponse(
            content="Hello, world!",
            thread_id="test-1",
            tokens_used=42,
        )
        assert resp.content == "Hello, world!"
        assert resp.thread_id == "test-1"
        assert resp.tokens_used == 42

    def test_default_tokens(self) -> None:
        """AgentResponse defaults tokens_used to 0."""
        resp = AgentResponse(content="OK", thread_id="x")
        assert resp.tokens_used == 0


class TestHealthResponse:
    """Tests for the HealthResponse Pydantic model."""

    def test_healthy_response(self) -> None:
        """HealthResponse for a healthy state."""
        resp = HealthResponse(
            status="healthy",
            agent_id="harness-agent-prod",
            sandbox_type="docker",
        )
        assert resp.status == "healthy"
        assert resp.agent_id == "harness-agent-prod"


class TestCreateServerApp:
    """Tests for the FastAPI app factory."""

    def test_creates_fastapi_app(self) -> None:
        """create_server_app returns a FastAPI instance."""
        from fastapi import FastAPI

        app = create_server_app()
        assert isinstance(app, FastAPI)
        assert app.title == "Harness Agent Server"

    def test_health_check_returns_response(self) -> None:
        """Health check returns a valid HTTP response."""
        from fastapi.testclient import TestClient

        app = create_server_app()
        client = TestClient(app)
        response = client.get("/health")
        # Lifespan may or may not have run; accept both states
        assert response.status_code in (200, 503)

    def test_openapi_schema(self) -> None:
        """Verify the OpenAPI schema includes expected endpoints."""
        from fastapi.testclient import TestClient

        app = create_server_app()
        client = TestClient(app)
        schema = client.get("/openapi.json").json()

        paths = schema.get("paths", {})
        assert "/health" in paths
        assert "/agent/invoke" in paths


# ---------------------------------------------------------------------------
# Multi-tenant tests
# ---------------------------------------------------------------------------


class TestTenantManagerConfig:
    """Tests for TenantManagerConfig."""

    def test_default_config(self) -> None:
        """Verify default TenantManagerConfig."""
        config = TenantManagerConfig()
        assert config.base_port == 2024
        assert config.sandbox_type == "docker"
        assert config.enable_memory is True

    def test_custom_config(self) -> None:
        """Verify custom TenantManagerConfig."""
        config = TenantManagerConfig(
            base_port=3000,
            sandbox_type="local",
        )
        assert config.base_port == 3000
        assert config.sandbox_type == "local"


class TestTenantAgentManager:
    """Tests for TenantAgentManager."""

    def test_create_manager(self) -> None:
        """TenantAgentManager can be created."""
        manager = TenantAgentManager()
        assert manager.tenant_count == 0
        assert manager.active_tenants == []

    def test_get_agent_creates_tenant(self, fake_llm) -> None:
        """get_agent creates and returns an agent for a new tenant."""
        manager = TenantAgentManager()
        with patch(_LLM_PATCH_PATH, return_value=fake_llm):
            import asyncio

            agent = asyncio.run(manager.get_agent("tenant-a"))
            assert agent is not None
            assert manager.tenant_count == 1
            assert "tenant-a" in manager.active_tenants

    def test_get_agent_caches(self, fake_llm) -> None:
        """Second get_agent returns the same instance."""
        manager = TenantAgentManager()
        with patch(_LLM_PATCH_PATH, return_value=fake_llm):
            import asyncio

            agent1 = asyncio.run(manager.get_agent("tenant-a"))
            agent2 = asyncio.run(manager.get_agent("tenant-a"))
            assert agent1 is agent2
            assert manager.tenant_count == 1

    def test_multiple_tenants(self, fake_llm) -> None:
        """Multiple tenants get distinct agents."""
        manager = TenantAgentManager()
        with patch(_LLM_PATCH_PATH, return_value=fake_llm):
            import asyncio

            a1 = asyncio.run(manager.get_agent("tenant-a"))
            a2 = asyncio.run(manager.get_agent("tenant-b"))
            assert a1 is not a2
            assert manager.tenant_count == 2
            assert set(manager.active_tenants) == {"tenant-a", "tenant-b"}

    def test_is_active(self) -> None:
        """is_active returns True only for active tenants."""
        manager = TenantAgentManager()
        assert manager.is_active("tenant-x") is False

    @pytest.mark.asyncio
    async def test_cleanup_tenant(self, fake_llm) -> None:
        """cleanup_tenant removes the tenant and its agent."""
        manager = TenantAgentManager()
        with patch(_LLM_PATCH_PATH, return_value=fake_llm):
            await manager.get_agent("tenant-a")
            assert manager.tenant_count == 1

            await manager.cleanup_tenant("tenant-a")
            assert manager.tenant_count == 0
            assert manager.is_active("tenant-a") is False

    @pytest.mark.asyncio
    async def test_cleanup_nonexistent(self) -> None:
        """cleanup_tenant is safe for non-existent tenants."""
        manager = TenantAgentManager()
        await manager.cleanup_tenant("nonexistent")
        assert manager.tenant_count == 0

    @pytest.mark.asyncio
    async def test_cleanup_all(self, fake_llm) -> None:
        """cleanup_all removes all tenants."""
        manager = TenantAgentManager()
        with patch(_LLM_PATCH_PATH, return_value=fake_llm):
            await manager.get_agent("a")
            await manager.get_agent("b")
            await manager.get_agent("c")
            assert manager.tenant_count == 3

            await manager.cleanup_all()
            assert manager.tenant_count == 0

    def test_port_computation(self) -> None:
        """Port assignments are deterministic per tenant."""
        manager = TenantAgentManager()
        port1 = manager._compute_port("tenant-a")
        port2 = manager._compute_port("tenant-a")
        port3 = manager._compute_port("tenant-b")
        assert port1 == port2
        assert isinstance(port1, int)
        assert isinstance(port3, int)
