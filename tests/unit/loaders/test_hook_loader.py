"""Tests for HookLoader.

Plan: docs/guides/plans-phase-2/05-hook-loader.md §6.2 — HookLoader Testing Plan
"""

from __future__ import annotations

from pathlib import Path

import pytest

from harness_agent.loaders.hook_loader import EventBus, HookEvent, HookLoader

# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def event_bus() -> EventBus:
    """Create a fresh EventBus for each test."""
    return EventBus()


@pytest.fixture
def temp_harness_dir(tmp_path: Path) -> Path:
    """Create a temporary .harness/ directory."""
    harness_dir = tmp_path / ".harness"
    harness_dir.mkdir()
    return harness_dir


@pytest.fixture
def hooks_dir_with_shell(temp_harness_dir: Path) -> Path:
    """Create .harness/hooks/ with a shell hook."""
    hooks_dir = temp_harness_dir / "hooks"
    hooks_dir.mkdir()
    (hooks_dir / "pre_tool_call.sh").write_text(
        "#!/bin/bash\n"
        'echo "Running pre_tool_call"\n'
        'echo "tool: $(echo $HOOK_CONTEXT | python3 -c \\"import sys,json; print(json.load(sys.stdin)[\'tool_name\'])\\")"\n'
        "exit 0\n"
    )
    return temp_harness_dir


@pytest.fixture
def hooks_dir_with_python(temp_harness_dir: Path) -> Path:
    """Create .harness/hooks/ with a Python hook."""
    hooks_dir = temp_harness_dir / "hooks"
    hooks_dir.mkdir()
    (hooks_dir / "session_start.py").write_text(
        "def handle(context):\n"
        "    return {'allowed': True, 'messages': ['session started']}\n"
    )
    return temp_harness_dir


@pytest.fixture
def hooks_dir_with_mixed(temp_harness_dir: Path) -> Path:
    """Create .harness/hooks/ with mixed valid and invalid files."""
    hooks_dir = temp_harness_dir / "hooks"
    hooks_dir.mkdir()
    (hooks_dir / "session_start.sh").write_text(
        "#!/bin/bash\necho 'start'\nexit 0\n"
    )
    (hooks_dir / "session_end.py").write_text(
        "def handle(context):\n    return {'allowed': True, 'messages': ['end']}\n"
    )
    (hooks_dir / "readme.txt").write_text("not a hook")
    (hooks_dir / "unknown_event.py").write_text(
        "def handle(context):\n    return {'allowed': True}\n"
    )
    return temp_harness_dir


# ── Tests ───────────────────────────────────────────────────────────────────


class TestHookLoaderExists:
    """Tests for HookLoader.exists property."""

    def test_no_hooks_dir(
        self, temp_harness_dir: Path, event_bus: EventBus
    ) -> None:
        """When hooks/ does not exist, exists returns False."""
        loader = HookLoader(temp_harness_dir, event_bus)
        assert loader.exists is False

    def test_empty_hooks_dir(
        self, temp_harness_dir: Path, event_bus: EventBus
    ) -> None:
        """When hooks/ exists but is empty, exists returns True."""
        (temp_harness_dir / "hooks").mkdir()
        loader = HookLoader(temp_harness_dir, event_bus)
        assert loader.exists is True


class TestHookLoaderLoadAll:
    """Tests for HookLoader.load_all()."""

    def test_no_hooks_dir_returns_empty(
        self, temp_harness_dir: Path, event_bus: EventBus
    ) -> None:
        """When hooks/ does not exist, load_all() returns []."""
        loader = HookLoader(temp_harness_dir, event_bus)
        assert loader.load_all() == []

    def test_empty_hooks_dir_returns_empty(
        self, temp_harness_dir: Path, event_bus: EventBus
    ) -> None:
        """When hooks/ is empty, load_all() returns []."""
        (temp_harness_dir / "hooks").mkdir()
        loader = HookLoader(temp_harness_dir, event_bus)
        assert loader.load_all() == []

    def test_load_shell_hook(
        self, hooks_dir_with_shell: Path, event_bus: EventBus
    ) -> None:
        """A .sh file is loaded and registered into the bus."""
        loader = HookLoader(hooks_dir_with_shell, event_bus)
        loaded = loader.load_all()
        assert loaded == ["pre_tool_call.sh"]
        assert event_bus.listener_count == 1

    def test_load_python_hook(
        self, hooks_dir_with_python: Path, event_bus: EventBus
    ) -> None:
        """A .py file with handle() is loaded and registered."""
        loader = HookLoader(hooks_dir_with_python, event_bus)
        loaded = loader.load_all()
        assert loaded == ["session_start.py"]
        assert event_bus.listener_count == 1

    def test_python_hook_missing_handle(
        self, temp_harness_dir: Path, event_bus: EventBus
    ) -> None:
        """A .py file without handle() is skipped."""
        hooks_dir = temp_harness_dir / "hooks"
        hooks_dir.mkdir()
        (hooks_dir / "session_start.py").write_text(
            "def not_handle():\n    pass\n"
        )
        loader = HookLoader(temp_harness_dir, event_bus)
        loaded = loader.load_all()
        assert loaded == []  # Skipped because missing handle()
        assert event_bus.listener_count == 0

    def test_unsupported_extension(
        self, temp_harness_dir: Path, event_bus: EventBus
    ) -> None:
        """Files with unsupported extensions (.txt, .yaml) are skipped."""
        hooks_dir = temp_harness_dir / "hooks"
        hooks_dir.mkdir()
        (hooks_dir / "session_start.txt").write_text("not a hook")
        (hooks_dir / "session_start.yaml").write_text("key: value")
        loader = HookLoader(temp_harness_dir, event_bus)
        loaded = loader.load_all()
        assert loaded == []

    def test_unknown_event_name(
        self, temp_harness_dir: Path, event_bus: EventBus
    ) -> None:
        """File with a name that doesn't map to HookEvent is skipped."""
        hooks_dir = temp_harness_dir / "hooks"
        hooks_dir.mkdir()
        (hooks_dir / "my_custom_event.py").write_text(
            "def handle(context):\n    return {'allowed': True}\n"
        )
        loader = HookLoader(temp_harness_dir, event_bus)
        loaded = loader.load_all()
        assert loaded == []  # Skipped because "my_custom_event" is unknown

    def test_mixed_hooks(
        self, hooks_dir_with_mixed: Path, event_bus: EventBus
    ) -> None:
        """Mix of valid/invalid files → only valid ones are loaded."""
        loader = HookLoader(hooks_dir_with_mixed, event_bus)
        loaded = loader.load_all()
        # session_start.sh + session_end.py are valid
        # readme.txt has unsupported extension
        # unknown_event.py has an unknown event name
        assert len(loaded) == 2
        assert "session_start.sh" in loaded
        assert "session_end.py" in loaded


class TestHookLoaderShellExecution:
    """Tests for shell hook execution behavior."""

    def test_shell_hook_execution(
        self, hooks_dir_with_shell: Path, event_bus: EventBus
    ) -> None:
        """A shell hook runs and returns output."""
        loader = HookLoader(hooks_dir_with_shell, event_bus)
        loader.load_all()
        result = event_bus.fire(
            HookEvent.PRE_TOOL_CALL, {"tool_name": "write_file"}
        )
        assert result.allowed is True
        assert any("pre_tool_call" in m for m in result.messages)

    def test_shell_hook_blocks(
        self, temp_harness_dir: Path, event_bus: EventBus
    ) -> None:
        """A shell hook that exits non-zero blocks execution."""
        hooks_dir = temp_harness_dir / "hooks"
        hooks_dir.mkdir()
        (hooks_dir / "pre_tool_call.sh").write_text(
            "#!/bin/bash\necho 'BLOCKED'\nexit 1\n"
        )
        loader = HookLoader(temp_harness_dir, event_bus)
        loader.load_all()
        result = event_bus.fire(
            HookEvent.PRE_TOOL_CALL, {"tool_name": "rm"}
        )
        assert result.allowed is False
        assert any("BLOCKED" in m for m in result.messages)


class TestHookLoaderPythonExecution:
    """Tests for Python hook execution behavior."""

    def test_python_hook_execution(
        self, hooks_dir_with_python: Path, event_bus: EventBus
    ) -> None:
        """A Python hook runs and returns its result."""
        loader = HookLoader(hooks_dir_with_python, event_bus)
        loader.load_all()
        result = event_bus.fire(
            HookEvent.SESSION_START, {"session_id": "abc"}
        )
        assert result.allowed is True
        assert "session started" in result.messages

    def test_python_hook_can_block(
        self, temp_harness_dir: Path, event_bus: EventBus
    ) -> None:
        """A Python hook can return allowed=False to block."""
        hooks_dir = temp_harness_dir / "hooks"
        hooks_dir.mkdir()
        (hooks_dir / "pre_llm_call.py").write_text(
            "def handle(context):\n"
            "    return {'allowed': False, 'messages': ['no llm calls']}\n"
        )
        loader = HookLoader(temp_harness_dir, event_bus)
        loader.load_all()
        result = event_bus.fire(HookEvent.PRE_LLM_CALL, {"model": "gpt-4"})
        assert result.allowed is False
        assert "no llm calls" in result.messages
