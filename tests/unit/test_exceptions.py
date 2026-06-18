"""Tests for the exception hierarchy (ADR-009)."""

import pickle

import pytest

from harness_agent.core.exceptions import (
    AgentExecutionError,
    HarnessError,
    SubagentTimeoutError,
    ToolExecutionError,
    ToolNotFoundError,
)


class TestHarnessError:
    """Tests for the base HarnessError."""

    def test_can_raise_and_catch(self) -> None:
        with pytest.raises(HarnessError):
            raise HarnessError("test error")

    def test_string_representation(self) -> None:
        exc = HarnessError("test error")
        assert str(exc) == "test error"

    def test_is_exception_subclass(self) -> None:
        assert issubclass(HarnessError, Exception)


class TestToolNotFoundError:
    """Tests for ToolNotFoundError."""

    def test_raises_with_tool_name(self) -> None:
        with pytest.raises(ToolNotFoundError) as exc_info:
            raise ToolNotFoundError("web_search")
        assert exc_info.value.tool_name == "web_search"

    def test_inherits_from_harness_error(self) -> None:
        assert issubclass(ToolNotFoundError, HarnessError)

    def test_message_contains_tool_name(self) -> None:
        exc = ToolNotFoundError("my_tool")
        assert "my_tool" in str(exc)

    def test_message_has_severity_tag(self) -> None:
        exc = ToolNotFoundError("my_tool")
        assert "[FATAL]" in str(exc)

    def test_multiple_instances_independent(self) -> None:
        exc1 = ToolNotFoundError("tool_a")
        exc2 = ToolNotFoundError("tool_b")
        assert exc1.tool_name != exc2.tool_name
        assert exc1.tool_name == "tool_a"
        assert exc2.tool_name == "tool_b"


class TestAgentExecutionError:
    """Tests for AgentExecutionError."""

    def test_raises_with_agent_id_and_original(self) -> None:
        original = ValueError("something went wrong")
        with pytest.raises(AgentExecutionError) as exc_info:
            raise AgentExecutionError("main_agent", original)
        assert exc_info.value.agent_id == "main_agent"
        assert exc_info.value.original_error is original

    def test_inherits_from_harness_error(self) -> None:
        assert issubclass(AgentExecutionError, HarnessError)

    def test_message_contains_context(self) -> None:
        original = RuntimeError("API error")
        exc = AgentExecutionError("researcher", original)
        assert "researcher" in str(exc)
        assert "API error" in str(exc)

    def test_message_has_severity_tag(self) -> None:
        exc = AgentExecutionError("agent", Exception("fail"))
        assert "[ERROR]" in str(exc)


class TestSubagentTimeoutError:
    """Tests for SubagentTimeoutError."""

    def test_raises_with_agent_id(self) -> None:
        with pytest.raises(SubagentTimeoutError) as exc_info:
            raise SubagentTimeoutError("researcher")
        assert exc_info.value.agent_id == "researcher"
        assert exc_info.value.timeout_seconds is None

    def test_raises_with_timeout(self) -> None:
        with pytest.raises(SubagentTimeoutError) as exc_info:
            raise SubagentTimeoutError("researcher", timeout_seconds=60.0)
        assert exc_info.value.timeout_seconds == 60.0
        assert "60.0s" in str(exc_info.value)

    def test_inherits_from_harness_error(self) -> None:
        assert issubclass(SubagentTimeoutError, HarnessError)

    def test_message_has_severity_tag(self) -> None:
        exc = SubagentTimeoutError("sub", timeout_seconds=30.0)
        assert "[WARN]" in str(exc)

    def test_message_without_timeout(self) -> None:
        exc = SubagentTimeoutError("sub")
        assert "timed out" in str(exc)
        assert "after" not in str(exc)


class TestToolExecutionError:
    """Tests for ToolExecutionError."""

    def test_raises_with_tool_name_and_original(self) -> None:
        original = RuntimeError("tool internal error")
        with pytest.raises(ToolExecutionError) as exc_info:
            raise ToolExecutionError("execute_python", original)
        assert exc_info.value.tool_name == "execute_python"
        assert exc_info.value.original_error is original

    def test_inherits_from_harness_error(self) -> None:
        assert issubclass(ToolExecutionError, HarnessError)

    def test_message_contains_context(self) -> None:
        original = ValueError("invalid input")
        exc = ToolExecutionError("web_search", original)
        assert "web_search" in str(exc)
        assert "invalid input" in str(exc)

    def test_message_has_severity_tag(self) -> None:
        exc = ToolExecutionError("tool", Exception("fail"))
        assert "[ERROR]" in str(exc)

    def test_chain_from_original(self) -> None:
        original = RuntimeError("root cause")
        try:
            raise ToolExecutionError("my_tool", original) from original
        except ToolExecutionError as exc:
            assert exc.__cause__ is original


class TestErrorHierarchy:
    """Verify all custom exceptions follow the hierarchy."""

    @pytest.mark.parametrize(
        "exc_class",
        [
            ToolNotFoundError,
            AgentExecutionError,
            SubagentTimeoutError,
            ToolExecutionError,
        ],
    )
    def test_all_inherit_from_harness_error(
        self, exc_class: type[Exception]
    ) -> None:
        assert issubclass(exc_class, HarnessError)

    @pytest.mark.parametrize(
        "exc_class",
        [
            HarnessError,
            ToolNotFoundError,
            AgentExecutionError,
            SubagentTimeoutError,
            ToolExecutionError,
        ],
    )
    def test_all_inherit_from_exception(
        self, exc_class: type[Exception]
    ) -> None:
        assert issubclass(exc_class, Exception)


class TestErrorPickling:
    """Exceptions must be picklable for LangGraph serialization."""

    @pytest.mark.parametrize(
        "exc",
        [
            HarnessError("base error"),
            ToolNotFoundError("missing_tool"),
            SubagentTimeoutError("sub", timeout_seconds=45.0),
        ],
    )
    def test_pickle_roundtrip(self, exc: HarnessError) -> None:
        pickled = pickle.dumps(exc)
        restored = pickle.loads(pickled)
        assert type(restored) is type(exc)

    def test_pickle_agent_execution_error(self) -> None:
        """AgentExecutionError wraps another exception — pickle round-trips the message."""
        exc = AgentExecutionError("agent1", ValueError("oops"))
        pickled = pickle.dumps(exc)
        restored = pickle.loads(pickled)
        assert isinstance(restored, AgentExecutionError)
        assert restored.agent_id == "agent1"

    def test_pickle_tool_execution_error(self) -> None:
        """ToolExecutionError wraps another exception — pickle round-trips the message."""
        exc = ToolExecutionError("tool_x", RuntimeError("fail"))
        pickled = pickle.dumps(exc)
        restored = pickle.loads(pickled)
        assert isinstance(restored, ToolExecutionError)
        assert restored.tool_name == "tool_x"
