"""Tests for custom middleware."""

from unittest.mock import MagicMock

from langchain.agents.middleware import AgentMiddleware

from harness_agent.monitoring.middleware import (
    StructuredLoggingMiddleware as LoggingMiddleware,
)


class TestLoggingMiddleware:
    """Tests for LoggingMiddleware."""

    def test_inherits_agent_middleware(self) -> None:
        middleware = LoggingMiddleware()
        assert isinstance(middleware, AgentMiddleware)

    def test_wrap_tool_call_passes_through(self) -> None:
        middleware = LoggingMiddleware()
        request = MagicMock()
        handler = MagicMock()
        expected = {"result": "success"}
        handler.return_value = expected

        result = middleware.wrap_tool_call(request, handler)

        handler.assert_called_once_with(request)
        assert result is expected

    def test_wrap_tool_call_does_not_modify_request(self) -> None:
        middleware = LoggingMiddleware()
        request = {"tool": "search", "args": {"query": "test"}}
        handler = MagicMock(return_value="result")

        middleware.wrap_tool_call(request, handler)

        # Request should be unchanged
        assert request["tool"] == "search"
        assert request["args"]["query"] == "test"


class TestMiddlewareIndependence:
    """Each middleware instance should be independent."""

    def test_multiple_instances(self) -> None:
        m1 = LoggingMiddleware()
        m2 = LoggingMiddleware()
        assert m1 is not m2

    def test_agent_middleware_abc_methods(self) -> None:
        """Verify AgentMiddleware has the expected interface."""
        middleware = LoggingMiddleware()
        # wrap_tool_call is the key method we use
        assert hasattr(middleware, "wrap_tool_call")
        assert callable(middleware.wrap_tool_call)
