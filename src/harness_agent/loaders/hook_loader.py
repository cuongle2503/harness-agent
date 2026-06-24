"""Hook Loader — parse .harness/hooks/*.{sh,py} and register into EventBus.

Plan: docs/guides/plans-phase-2/05-hook-loader.md
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from importlib import util as importlib_util
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ── Hook Event Types ────────────────────────────────────────────────────────


class HookEvent(str, Enum):  # noqa: UP042
    """Events in the agent lifecycle that hooks can listen to."""

    SESSION_START = "session_start"
    SESSION_END = "session_end"
    PRE_TOOL_CALL = "pre_tool_call"
    POST_TOOL_CALL = "post_tool_call"
    PRE_LLM_CALL = "pre_llm_call"
    POST_LLM_CALL = "post_llm_call"
    ON_ERROR = "on_error"


# ── Context schemas (documented, not enforced at runtime) ────────────────────

CONTEXT_SCHEMAS: dict[HookEvent, dict[str, type]] = {
    HookEvent.SESSION_START: {
        "session_id": str,
        "project_root": str,
        "config": dict,
        "timestamp": str,
    },
    HookEvent.SESSION_END: {
        "session_id": str,
        "total_tokens": int,
        "tool_calls_count": int,
        "duration_ms": int,
        "success": bool,
    },
    HookEvent.PRE_TOOL_CALL: {
        "session_id": str,
        "tool_name": str,
        "tool_args": dict,
        "timestamp": str,
    },
    HookEvent.POST_TOOL_CALL: {
        "session_id": str,
        "tool_name": str,
        "tool_args": dict,
        "tool_result": str,
        "duration_ms": int,
        "success": bool,
    },
    HookEvent.PRE_LLM_CALL: {
        "session_id": str,
        "model": str,
        "messages_count": int,
        "timestamp": str,
    },
    HookEvent.POST_LLM_CALL: {
        "session_id": str,
        "model": str,
        "tokens_used": int,
        "duration_ms": int,
        "success": bool,
    },
    HookEvent.ON_ERROR: {
        "session_id": str,
        "error_type": str,
        "error_message": str,
        "traceback": str,
        "context": dict,
    },
}


# ── Hook Result ─────────────────────────────────────────────────────────────


@dataclass
class HookResult:
    """Result after firing hooks for an event.

    Attributes:
        allowed: Whether the operation should proceed (False = blocked).
        messages: Log messages from hooks.
        modified_context: Context modified by hooks (merged across all).
        errors: Non-blocking errors from hooks.
    """

    allowed: bool = True
    messages: list[str] = field(default_factory=list)
    modified_context: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


# ── Event Bus ───────────────────────────────────────────────────────────────


class EventBus:
    """Event bus for harness hooks.

    Register listeners for each HookEvent. When fire() is called,
    all listeners run sequentially in registration order.

    Usage::

        bus = EventBus()
        bus.on(HookEvent.PRE_TOOL_CALL, my_hook_function)
        result = bus.fire(HookEvent.PRE_TOOL_CALL, {"tool_name": "write_file"})
        if not result.allowed:
            print(f"Blocked: {result.messages}")
    """

    def __init__(self) -> None:
        self._listeners: dict[HookEvent, list[Callable[..., Any]]] = (
            defaultdict(list)
        )

    def on(self, event: HookEvent, listener: Callable[..., Any]) -> None:
        """Register a listener for an event.

        Args:
            event: The HookEvent to listen for.
            listener: Callable that receives (context: dict) and returns
                a dict or HookResult.
        """
        self._listeners[event].append(listener)
        logger.debug("Registered hook for %s: %s", event.value, listener)

    def fire(self, event: HookEvent, context: dict[str, Any]) -> HookResult:
        """Fire all registered listeners for an event.

        Runs sequentially. If a listener returns allowed=False, subsequent
        listeners are NOT called.

        Args:
            event: The event being fired.
            context: Context dict passed to listeners.

        Returns:
            Aggregated HookResult from all listeners.
        """
        result = HookResult()

        for listener in self._listeners.get(event, []):
            try:
                listener_result = listener(context)
                parsed = self._parse_listener_result(listener_result)

                if not parsed.allowed:
                    result.allowed = False
                    result.messages.extend(parsed.messages)
                    result.modified_context.update(parsed.modified_context)
                    result.errors.extend(parsed.errors)
                    break  # Stop the chain — don't run remaining listeners

                result.messages.extend(parsed.messages)
                result.modified_context.update(parsed.modified_context)
                result.errors.extend(parsed.errors)

            except Exception as e:
                logger.error("Hook error for %s: %s", event.value, e)
                result.errors.append(str(e))
                # Don't block — hook errors should never stop the agent

        return result

    @staticmethod
    def _parse_listener_result(raw: Any) -> HookResult:
        """Parse a listener return value into a HookResult."""
        if isinstance(raw, HookResult):
            return raw
        if isinstance(raw, dict):
            return HookResult(
                allowed=raw.get("allowed", True),
                messages=raw.get("messages", []),
                modified_context=raw.get("modified_context", {}),
                errors=raw.get("errors", []),
            )
        # If a listener returns nothing, treat as allowed
        return HookResult()

    @property
    def listener_count(self) -> int:
        """Total number of registered listeners."""
        return sum(len(v) for v in self._listeners.values())

    def clear(self) -> None:
        """Remove all registered listeners."""
        self._listeners.clear()


# ── Hook Info ────────────────────────────────────────────────────────────────


class HookInfo:
    """Basic information about a registered hook."""

    def __init__(
        self,
        name: str,
        event: str,
        language: str,
        size: int,
    ) -> None:
        self.name = name
        self.event = event
        self.language = language
        self.size = size

    def __repr__(self) -> str:
        return (
            f"HookInfo(name={self.name!r}, "
            f"event={self.event!r}, "
            f"language={self.language!r})"
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, HookInfo):
            return NotImplemented
        return (
            self.name == other.name
            and self.event == other.event
            and self.language == other.language
            and self.size == other.size
        )


# ── Hook Loader ─────────────────────────────────────────────────────────────


class HookLoader:
    """Load hooks from .harness/hooks/ and register them into an EventBus.

    Supports two hook types:
    - Shell scripts (.sh): receive context via HOOK_CONTEXT env var
    - Python modules (.py): must define ``def handle(context) -> dict``

    Usage::

        bus = EventBus()
        loader = HookLoader(Path("my-project/.harness"), bus)
        loaded = loader.load_all()
        # Hooks are now registered on the bus
    """

    # Map file stem → HookEvent
    EVENT_MAP: dict[str, HookEvent] = {
        "session_start": HookEvent.SESSION_START,
        "session_end": HookEvent.SESSION_END,
        "pre_tool_call": HookEvent.PRE_TOOL_CALL,
        "post_tool_call": HookEvent.POST_TOOL_CALL,
        "pre_llm_call": HookEvent.PRE_LLM_CALL,
        "post_llm_call": HookEvent.POST_LLM_CALL,
        "on_error": HookEvent.ON_ERROR,
    }

    def __init__(self, harness_dir: Path, event_bus: EventBus | None = None) -> None:
        """Create a hook loader for the given ``.harness/`` directory.

        Args:
            harness_dir: Path to the ``.harness/`` directory.
            event_bus: The EventBus to register hooks into (optional for
                read-only operations like list_hooks).
        """
        self.hooks_dir = harness_dir / "hooks"
        self.event_bus = event_bus

    @property
    def exists(self) -> bool:
        """Check whether the hooks/ directory exists."""
        return self.hooks_dir.is_dir()

    def list_hooks(self) -> list[HookInfo]:
        """List information about all available hooks (without loading them).

        Returns:
            List of HookInfo with name, event, language, and size.
            Empty list if the hooks directory does not exist.
        """
        if not self.exists:
            return []

        result: list[HookInfo] = []
        for file in sorted(self.hooks_dir.iterdir()):
            if file.is_dir():
                continue

            event = self._file_to_event(file.stem)
            event_name = event.value if event else "unknown"

            if file.suffix == ".sh":
                language = "shell"
            elif file.suffix == ".py":
                language = "python"
            else:
                language = file.suffix.lstrip(".")

            result.append(
                HookInfo(
                    name=file.stem,
                    event=event_name,
                    language=language,
                    size=file.stat().st_size,
                )
            )
        return result

    def load_all(self) -> list[str]:
        """Scan .harness/hooks/ and register all hooks into the EventBus.

        Idempotent — subsequent calls skip already-loaded hooks.

        Returns:
            List of hook file names that were successfully loaded.
        """
        if not self.exists:
            return []

        if self.event_bus is None:
            logger.warning(
                "No EventBus provided — hooks found but not registered"
            )
            return []

        # Track loaded files to make subsequent calls idempotent
        if not hasattr(self, "_loaded_files"):
            self._loaded_files: set[str] = set()

        loaded: list[str] = []
        for file in sorted(self.hooks_dir.iterdir()):
            if file.is_dir():
                continue

            # Skip already-loaded files (idempotent)
            if file.name in self._loaded_files:
                continue

            event = self._file_to_event(file.stem)
            if event is None:
                logger.warning(
                    "Unknown hook event: %s (expected one of: %s)",
                    file.stem,
                    list(self.EVENT_MAP.keys()),
                )
                continue

            executor = self._create_executor(file)
            if executor is not None:
                self.event_bus.on(event, executor)
                loaded.append(file.name)
                self._loaded_files.add(file.name)
                logger.info(
                    "Loaded hook: %s → %s", file.name, event.value
                )

        return loaded

    def _file_to_event(self, stem: str) -> HookEvent | None:
        """Map a file stem to a HookEvent."""
        return self.EVENT_MAP.get(stem)

    def _create_executor(self, file: Path) -> Callable[..., Any] | None:
        """Create an executor function from a .sh or .py file."""
        if file.suffix == ".sh":
            return self._create_shell_executor(file)
        elif file.suffix == ".py":
            return self._create_python_executor(file)
        else:
            logger.warning("Unsupported hook type: %s", file.suffix)
            return None

    @staticmethod
    def _create_shell_executor(file: Path) -> Callable[..., Any]:
        """Create a shell hook executor.

        The shell script receives context via the HOOK_CONTEXT env var
        as a JSON string. Exit code 0 = allow, non-zero = block.
        """

        def executor(context: dict[str, Any]) -> dict[str, Any]:
            env = {**os.environ, "HOOK_CONTEXT": json.dumps(context)}
            try:
                result = subprocess.run(
                    ["bash", str(file)],
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                return {
                    "allowed": result.returncode == 0,
                    "messages": [
                        line
                        for line in (
                            result.stdout + result.stderr
                        ).splitlines()
                        if line.strip()
                    ],
                }
            except subprocess.TimeoutExpired:
                return {
                    "allowed": True,  # Timeout does not block
                    "messages": [f"Hook {file.name} timed out (30s)"],
                }

        return executor

    @staticmethod
    def _create_python_executor(file: Path) -> Callable[..., Any] | None:
        """Create a Python hook executor.

        The Python module must define a ``handle(context)`` function.
        """
        try:
            spec = importlib_util.spec_from_file_location(
                f"harness_hook_{file.stem}", file
            )
            if spec is None or spec.loader is None:
                logger.error("Cannot load hook: %s", file)
                return None

            module = importlib_util.module_from_spec(spec)
            spec.loader.exec_module(module)

            if not hasattr(module, "handle"):
                logger.error(
                    "Python hook %s missing handle(context) function", file
                )
                return None

            handle = module.handle
            if not callable(handle):
                logger.error(
                    "Python hook %s: 'handle' is not callable", file
                )
                return None

            return handle

        except Exception as e:
            logger.error("Failed to load hook %s: %s", file, e)
            return None
