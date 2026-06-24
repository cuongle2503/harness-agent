"""Tests for EventBus.

Plan: docs/guides/plans-phase-2/05-hook-loader.md §6.1 — EventBus Testing Plan
"""

from __future__ import annotations

from typing import Any

from harness_agent.loaders.hook_loader import EventBus, HookEvent, HookResult

# ── Helper: simple listener factory ─────────────────────────────────────────


def _listener_allow(msg: str = "ok") -> Any:
    """Create a listener that always returns allowed=True."""
    def fn(context: dict[str, Any]) -> dict[str, Any]:
        return {"allowed": True, "messages": [msg]}
    return fn


def _listener_block(msg: str = "blocked") -> Any:
    """Create a listener that returns allowed=False."""
    def fn(context: dict[str, Any]) -> dict[str, Any]:
        return {"allowed": False, "messages": [msg]}
    return fn


def _listener_modify(key: str, value: Any) -> Any:
    """Create a listener that modifies context."""
    def fn(context: dict[str, Any]) -> dict[str, Any]:
        return {"allowed": True, "modified_context": {key: value}}
    return fn


def _listener_raise(error_msg: str = "boom") -> Any:
    """Create a listener that raises an exception."""
    def fn(context: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError(error_msg)
    return fn


# ── Tests ───────────────────────────────────────────────────────────────────


class TestEventBusRegister:
    """Tests for EventBus.on() — registering listeners."""

    def test_register_listener(self) -> None:
        """on() registers a listener for an event."""
        bus = EventBus()
        listener = _listener_allow()
        bus.on(HookEvent.PRE_TOOL_CALL, listener)
        assert bus.listener_count == 1

    def test_register_multiple_listeners_same_event(self) -> None:
        """Multiple listeners can be registered for the same event."""
        bus = EventBus()
        bus.on(HookEvent.PRE_TOOL_CALL, _listener_allow("a"))
        bus.on(HookEvent.PRE_TOOL_CALL, _listener_allow("b"))
        bus.on(HookEvent.PRE_TOOL_CALL, _listener_allow("c"))
        assert bus.listener_count == 3

    def test_register_multiple_events(self) -> None:
        """Listeners can be registered for different events."""
        bus = EventBus()
        bus.on(HookEvent.SESSION_START, _listener_allow("start"))
        bus.on(HookEvent.SESSION_END, _listener_allow("end"))
        bus.on(HookEvent.ON_ERROR, _listener_allow("error"))
        assert bus.listener_count == 3


class TestEventBusFire:
    """Tests for EventBus.fire() — firing events."""

    def test_fire_calls_listener(self) -> None:
        """fire() calls the registered listener with context."""
        bus = EventBus()
        received: dict[str, Any] = {}

        def capture(ctx: dict[str, Any]) -> dict[str, Any]:
            received.update(ctx)
            return {"allowed": True}

        bus.on(HookEvent.PRE_TOOL_CALL, capture)
        result = bus.fire(HookEvent.PRE_TOOL_CALL, {"tool_name": "read_file"})

        assert result.allowed is True
        assert received["tool_name"] == "read_file"

    def test_fire_multiple_listeners(self) -> None:
        """3 listeners → all are called sequentially."""
        bus = EventBus()
        called: list[str] = []

        def make(name: str) -> Any:
            def fn(ctx: dict[str, Any]) -> dict[str, Any]:
                called.append(name)
                return {"allowed": True, "messages": [name]}
            return fn

        bus.on(HookEvent.SESSION_START, make("first"))
        bus.on(HookEvent.SESSION_START, make("second"))
        bus.on(HookEvent.SESSION_START, make("third"))

        result = bus.fire(HookEvent.SESSION_START, {})
        assert result.allowed is True
        assert called == ["first", "second", "third"]
        assert result.messages == ["first", "second", "third"]

    def test_block_stops_chain(self) -> None:
        """Listener 1 returns allowed=False → listener 2 is not called."""
        bus = EventBus()
        called: list[str] = []

        def make(name: str, allowed: bool) -> Any:
            def fn(ctx: dict[str, Any]) -> dict[str, Any]:
                called.append(name)
                return {"allowed": allowed, "messages": [name]}
            return fn

        bus.on(HookEvent.PRE_TOOL_CALL, make("blocker", False))
        bus.on(HookEvent.PRE_TOOL_CALL, make("never_called", True))

        result = bus.fire(HookEvent.PRE_TOOL_CALL, {})
        assert result.allowed is False
        assert called == ["blocker"]  # second listener never called

    def test_fire_no_listeners(self) -> None:
        """Fire event with no listeners → returns default HookResult."""
        bus = EventBus()
        result = bus.fire(HookEvent.SESSION_END, {"session_id": "x"})
        assert result.allowed is True
        assert result.messages == []
        assert result.modified_context == {}
        assert result.errors == []


class TestEventBusErrorHandling:
    """Tests for EventBus error handling."""

    def test_listener_error_non_blocking(self) -> None:
        """Listener throws → error added to result.errors, execution continues."""
        bus = EventBus()
        called: list[str] = []

        def good(ctx: dict[str, Any]) -> dict[str, Any]:
            called.append("good")
            return {"allowed": True, "messages": ["ok"]}

        def bad(ctx: dict[str, Any]) -> dict[str, Any]:
            raise RuntimeError("something went wrong")

        bus.on(HookEvent.ON_ERROR, bad)
        bus.on(HookEvent.ON_ERROR, good)

        result = bus.fire(HookEvent.ON_ERROR, {})
        assert result.allowed is True  # error does not block
        assert len(result.errors) == 1
        assert "something went wrong" in result.errors[0]
        assert "good" in called  # second listener was called

    def test_listener_error_added_to_errors(self) -> None:
        """Listener exception message is captured in result.errors."""
        bus = EventBus()

        def bad(ctx: dict[str, Any]) -> dict[str, Any]:
            raise ValueError("invalid state")

        bus.on(HookEvent.ON_ERROR, bad)
        result = bus.fire(HookEvent.ON_ERROR, {})
        assert len(result.errors) == 1
        assert "invalid state" in result.errors[0]


class TestEventBusParseResult:
    """Tests for EventBus._parse_listener_result()."""

    def test_parse_dict_result(self) -> None:
        """Listener returns a dict → parsed into HookResult."""
        bus = EventBus()

        def listener(ctx: dict[str, Any]) -> dict[str, Any]:
            return {
                "allowed": True,
                "messages": ["hello"],
                "modified_context": {"key": "val"},
            }

        bus.on(HookEvent.SESSION_START, listener)
        result = bus.fire(HookEvent.SESSION_START, {})
        assert result.allowed is True
        assert result.messages == ["hello"]
        assert result.modified_context == {"key": "val"}

    def test_parse_hookresult(self) -> None:
        """Listener returns a HookResult → kept as-is."""
        bus = EventBus()

        def listener(ctx: dict[str, Any]) -> HookResult:
            return HookResult(
                allowed=False,
                messages=["nope"],
                modified_context={"reason": "test"},
                errors=[],
            )

        bus.on(HookEvent.PRE_TOOL_CALL, listener)
        result = bus.fire(HookEvent.PRE_TOOL_CALL, {})
        assert result.allowed is False
        assert result.messages == ["nope"]
        assert result.modified_context == {"reason": "test"}

    def test_parse_none_result(self) -> None:
        """Listener returns None → treated as allowed with no messages."""
        bus = EventBus()

        def listener(ctx: dict[str, Any]) -> None:
            return None

        bus.on(HookEvent.SESSION_START, listener)
        result = bus.fire(HookEvent.SESSION_START, {})
        assert result.allowed is True
        assert result.messages == []


class TestEventBusLifecycle:
    """Tests for EventBus lifecycle methods."""

    def test_listener_count(self) -> None:
        """5 listeners across events → listener_count == 5."""
        bus = EventBus()
        for i in range(5):
            bus.on(HookEvent.PRE_TOOL_CALL, _listener_allow(str(i)))
        assert bus.listener_count == 5

    def test_clear_removes_all(self) -> None:
        """clear() → listener_count == 0."""
        bus = EventBus()
        bus.on(HookEvent.SESSION_START, _listener_allow("a"))
        bus.on(HookEvent.SESSION_END, _listener_allow("b"))
        assert bus.listener_count == 2
        bus.clear()
        assert bus.listener_count == 0

    def test_clear_then_fire_no_effect(self) -> None:
        """After clear(), fire() has no listeners to call."""
        bus = EventBus()
        bus.on(HookEvent.PRE_TOOL_CALL, _listener_allow("x"))
        bus.clear()
        result = bus.fire(HookEvent.PRE_TOOL_CALL, {})
        assert result.allowed is True
        assert result.messages == []


class TestEventBusModifiedContext:
    """Tests for context modification merging."""

    def test_modified_context_merged(self) -> None:
        """2 listeners modify context → merged into result."""
        bus = EventBus()
        bus.on(HookEvent.SESSION_START, _listener_modify("a", 1))
        bus.on(HookEvent.SESSION_START, _listener_modify("b", 2))

        result = bus.fire(HookEvent.SESSION_START, {})
        assert result.allowed is True
        assert result.modified_context == {"a": 1, "b": 2}

    def test_modified_context_override(self) -> None:
        """Later listener can override earlier context modifications."""
        bus = EventBus()
        bus.on(HookEvent.SESSION_START, _listener_modify("key", "first"))
        bus.on(HookEvent.SESSION_START, _listener_modify("key", "second"))

        result = bus.fire(HookEvent.SESSION_START, {})
        assert result.modified_context == {"key": "second"}
