"""Tests for SubAgentLoader.

Plan: docs/guides/plans-phase-2/04-subagent-loader.md §6 — Testing Plan
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from langchain_core.tools import BaseTool

from harness_agent.loaders.subagent_loader import (
    MiddlewareResolver,
    SubAgentInfo,
    SubAgentLoadError,
    SubAgentLoader,
)
from harness_agent.tools.registry import ToolRegistry


# ── Mock tool for testing ─────────────────────────────────────────────────


class _MockTool(BaseTool):
    """A mock BaseTool for testing tool resolution."""

    name: str = "mock_tool"
    description: str = "A mock tool for testing."

    def _run(self, *args: Any, **kwargs: Any) -> str:
        return "mock result"


def _make_mock_tool(name: str, description: str = "") -> _MockTool:
    """Create a mock tool with a given name."""
    tool = _MockTool()
    tool.name = name
    tool.description = description or f"Mock tool: {name}"
    return tool


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def temp_harness_dir(tmp_path: Path) -> Path:
    """Create a temporary .harness/ directory."""
    harness_dir = tmp_path / ".harness"
    harness_dir.mkdir()
    return harness_dir


@pytest.fixture
def tool_registry() -> ToolRegistry:
    """Create a ToolRegistry with mock tools registered."""
    registry = ToolRegistry()
    registry.register(_make_mock_tool("read_file", "Read a file"))
    registry.register(_make_mock_tool("grep", "Search files"))
    registry.register(_make_mock_tool("glob", "Find files"))
    return registry


@pytest.fixture
def subagents_dir_with_files(temp_harness_dir: Path) -> Path:
    """Create .harness/subagents/ with two valid .yaml files."""
    sub_dir = temp_harness_dir / "subagents"
    sub_dir.mkdir()
    (sub_dir / "code-reviewer.yaml").write_text(
        "name: code-reviewer\n"
        "description: Reviews code for bugs, security, and style issues.\n"
        "system_prompt: You are a thorough code reviewer.\n"
        "tools:\n"
        "  - read_file\n"
        "  - grep\n"
        "model: deepseek-v4-pro\n"
        "middleware:\n"
        "  - ContextEditingMiddleware\n"
        "  - ToolRetryMiddleware:\n"
        "      max_retries: 3\n"
    )
    (sub_dir / "api-tester.yaml").write_text(
        "name: api-tester\n"
        "description: Tests API endpoints.\n"
        "system_prompt: You test APIs thoroughly.\n"
        "tools:\n"
        "  - read_file\n"
        "model: deepseek-v4-flash\n"
    )
    (sub_dir / "readme.txt").write_text("not a subagent")
    return temp_harness_dir


# ── Tests: SubAgentLoader.exists ───────────────────────────────────────────


class TestSubAgentLoaderExists:
    """Tests for SubAgentLoader.exists property."""

    def test_no_subagents_dir(
        self, temp_harness_dir: Path, tool_registry: ToolRegistry
    ) -> None:
        """When subagents/ does not exist, exists returns False."""
        loader = SubAgentLoader(temp_harness_dir, tool_registry)
        assert loader.exists is False

    def test_empty_subagents_dir(
        self, temp_harness_dir: Path, tool_registry: ToolRegistry
    ) -> None:
        """When subagents/ exists but is empty, exists returns True."""
        (temp_harness_dir / "subagents").mkdir()
        loader = SubAgentLoader(temp_harness_dir, tool_registry)
        assert loader.exists is True


# ── Tests: SubAgentLoader.load_all ─────────────────────────────────────────


class TestSubAgentLoaderLoadAll:
    """Tests for SubAgentLoader.load_all()."""

    def test_no_subagents_dir_returns_empty(
        self, temp_harness_dir: Path, tool_registry: ToolRegistry
    ) -> None:
        """When subagents/ does not exist, load_all() returns []."""
        loader = SubAgentLoader(temp_harness_dir, tool_registry)
        assert loader.load_all() == []

    def test_empty_subagents_dir_returns_empty(
        self, temp_harness_dir: Path, tool_registry: ToolRegistry
    ) -> None:
        """When subagents/ is empty, load_all() returns []."""
        (temp_harness_dir / "subagents").mkdir()
        loader = SubAgentLoader(temp_harness_dir, tool_registry)
        assert loader.load_all() == []

    def test_load_minimal_subagent(
        self, temp_harness_dir: Path, tool_registry: ToolRegistry
    ) -> None:
        """A subagent with only required fields parses correctly."""
        sub_dir = temp_harness_dir / "subagents"
        sub_dir.mkdir()
        (sub_dir / "simple.yaml").write_text(
            "name: simple-reviewer\n"
            "description: Reviews code for basic issues.\n"
            "system_prompt: You are a code reviewer. Check for bugs.\n"
        )
        loader = SubAgentLoader(temp_harness_dir, tool_registry)
        definitions = loader.load_all()
        assert len(definitions) == 1
        d = definitions[0]
        assert d["name"] == "simple-reviewer"
        assert d["description"] == "Reviews code for basic issues."
        assert d["system_prompt"] == "You are a code reviewer. Check for bugs."
        assert d["tools"] == []
        assert d["model"] == "deepseek-v4-flash"
        assert d["middleware"] == []

    def test_load_full_subagent(
        self, subagents_dir_with_files: Path, tool_registry: ToolRegistry
    ) -> None:
        """A subagent with all fields parses correctly."""
        loader = SubAgentLoader(subagents_dir_with_files, tool_registry)

        # Register mock middleware classes so resolution succeeds
        class FakeContextEditing:
            pass

        class FakeToolRetry:
            def __init__(self, max_retries: int = 1) -> None:
                self.max_retries = max_retries

        loader.middleware_resolver.register(
            "ContextEditingMiddleware", FakeContextEditing
        )
        loader.middleware_resolver.register(
            "ToolRetryMiddleware", FakeToolRetry
        )

        definitions = loader.load_all()
        assert len(definitions) == 2
        # Sorted alphabetically: api-tester first, then code-reviewer
        names = [d["name"] for d in definitions]
        assert names == ["api-tester", "code-reviewer"]

        # Check api-tester (minimal)
        api = definitions[0]
        assert api["name"] == "api-tester"
        assert "Tests API" in api["description"]
        assert len(api["tools"]) == 1  # read_file only
        assert api["model"] == "deepseek-v4-flash"

        # Check code-reviewer (full)
        reviewer = definitions[1]
        assert reviewer["name"] == "code-reviewer"
        assert "Reviews code" in reviewer["description"]
        assert "thorough code reviewer" in reviewer["system_prompt"]
        assert len(reviewer["tools"]) == 2  # read_file, grep
        assert reviewer["model"] == "deepseek-v4-pro"
        assert len(reviewer["middleware"]) == 2  # ContextEditing + ToolRetry

    def test_load_multiple_subagents(
        self, subagents_dir_with_files: Path, tool_registry: ToolRegistry
    ) -> None:
        """3 files → 2 definitions (.txt is ignored)."""
        sub_dir = subagents_dir_with_files / "subagents"
        (sub_dir / "doc-writer.yaml").write_text(
            "name: doc-writer\n"
            "description: Writes documentation for code.\n"
            "system_prompt: You write clear and concise documentation.\n"
        )
        loader = SubAgentLoader(subagents_dir_with_files, tool_registry)

        # Register mock middleware so resolution succeeds for code-reviewer.yaml
        class FakeMW:
            def __init__(self, **kwargs: Any) -> None:
                self.kwargs = kwargs

        loader.middleware_resolver.register("ContextEditingMiddleware", FakeMW)
        loader.middleware_resolver.register("ToolRetryMiddleware", FakeMW)

        definitions = loader.load_all()
        assert len(definitions) == 3
        names = [d["name"] for d in definitions]
        assert names == ["api-tester", "code-reviewer", "doc-writer"]

    def test_missing_required_fields(
        self, temp_harness_dir: Path, tool_registry: ToolRegistry
    ) -> None:
        """Missing description → SubAgentLoadError."""
        sub_dir = temp_harness_dir / "subagents"
        sub_dir.mkdir()
        (sub_dir / "bad.yaml").write_text(
            "name: bad-subagent\n"
            "system_prompt: You are bad.\n"
        )
        loader = SubAgentLoader(temp_harness_dir, tool_registry)
        with pytest.raises(SubAgentLoadError, match="description"):
            loader.load_all()

    def test_unknown_tool(
        self, temp_harness_dir: Path, tool_registry: ToolRegistry
    ) -> None:
        """Tool not in registry → SubAgentLoadError."""
        sub_dir = temp_harness_dir / "subagents"
        sub_dir.mkdir()
        (sub_dir / "bad.yaml").write_text(
            "name: bad-subagent\n"
            "description: A subagent with unknown tools.\n"
            "system_prompt: You are bad.\n"
            "tools:\n"
            "  - nonexistent_tool\n"
        )
        loader = SubAgentLoader(temp_harness_dir, tool_registry)
        with pytest.raises(SubAgentLoadError, match="nonexistent_tool"):
            loader.load_all()

    def test_tool_resolved_correctly(
        self, temp_harness_dir: Path, tool_registry: ToolRegistry
    ) -> None:
        """Tool names resolve to correct BaseTool instances."""
        sub_dir = temp_harness_dir / "subagents"
        sub_dir.mkdir()
        (sub_dir / "ok.yaml").write_text(
            "name: ok-subagent\n"
            "description: A subagent with known tools.\n"
            "system_prompt: You are ok.\n"
            "tools:\n"
            "  - read_file\n"
            "  - grep\n"
        )
        loader = SubAgentLoader(temp_harness_dir, tool_registry)
        definitions = loader.load_all()
        tools = definitions[0]["tools"]
        assert len(tools) == 2
        tool_names = [t.name for t in tools]
        assert "read_file" in tool_names
        assert "grep" in tool_names

    def test_unknown_middleware(
        self, temp_harness_dir: Path, tool_registry: ToolRegistry
    ) -> None:
        """Middleware not in resolver → SubAgentLoadError."""
        sub_dir = temp_harness_dir / "subagents"
        sub_dir.mkdir()
        (sub_dir / "bad.yaml").write_text(
            "name: bad-subagent\n"
            "description: A subagent with unknown middleware.\n"
            "system_prompt: You are bad.\n"
            "middleware:\n"
            "  - UnknownMiddleware\n"
        )
        loader = SubAgentLoader(temp_harness_dir, tool_registry)
        with pytest.raises(SubAgentLoadError, match="UnknownMiddleware"):
            loader.load_all()

    def test_invalid_yaml_syntax(
        self, temp_harness_dir: Path, tool_registry: ToolRegistry
    ) -> None:
        """YAML syntax error → SubAgentLoadError."""
        sub_dir = temp_harness_dir / "subagents"
        sub_dir.mkdir()
        (sub_dir / "bad.yaml").write_text(
            "name: bad\n"
            "description: Broken YAML\n"
            "system_prompt: -\n"
            "  - invalid\n"
            "  tabs: \tbroken\n"
        )
        # This might parse but produce unexpected types
        loader = SubAgentLoader(temp_harness_dir, tool_registry)
        # The YAML here is actually valid but produces complex types
        # Let's create truly invalid YAML
        (sub_dir / "really-bad.yaml").write_text(
            "name: bad\n"
            "description: Broken YAML\n"
            "\tindent: with tab\n"
        )
        loader2 = SubAgentLoader(temp_harness_dir, tool_registry)
        with pytest.raises(SubAgentLoadError, match="Failed to parse"):
            loader2.load_all()

    def test_duplicate_subagent_names(
        self, temp_harness_dir: Path, tool_registry: ToolRegistry
    ) -> None:
        """Two files with same name → SubAgentLoadError."""
        sub_dir = temp_harness_dir / "subagents"
        sub_dir.mkdir()
        (sub_dir / "a-reviewer.yaml").write_text(
            "name: same-name\n"
            "description: First subagent with this name.\n"
            "system_prompt: You are a reviewer.\n"
        )
        (sub_dir / "b-reviewer.yaml").write_text(
            "name: same-name\n"
            "description: Second subagent with this name.\n"
            "system_prompt: You are also a reviewer.\n"
        )
        loader = SubAgentLoader(temp_harness_dir, tool_registry)
        with pytest.raises(SubAgentLoadError, match="Duplicate"):
            loader.load_all()

    def test_non_dict_yaml(
        self, temp_harness_dir: Path, tool_registry: ToolRegistry
    ) -> None:
        """YAML that produces a list, not a dict → SubAgentLoadError."""
        sub_dir = temp_harness_dir / "subagents"
        sub_dir.mkdir()
        (sub_dir / "list.yaml").write_text(
            "- item1\n"
            "- item2\n"
        )
        loader = SubAgentLoader(temp_harness_dir, tool_registry)
        with pytest.raises(SubAgentLoadError, match="expected a mapping"):
            loader.load_all()


# ── Tests: MiddlewareResolver ──────────────────────────────────────────────


class TestMiddlewareResolver:
    """Tests for MiddlewareResolver."""

    def test_middleware_simple_string(
        self, temp_harness_dir: Path, tool_registry: ToolRegistry
    ) -> None:
        """String format → instance with no params."""
        resolver = MiddlewareResolver()

        class FakeMiddleware:
            def __init__(self) -> None:
                self.initialized = True

        resolver.register("FakeMiddleware", FakeMiddleware)

        instances = resolver.resolve(["FakeMiddleware"], "test.yaml")
        assert len(instances) == 1
        assert isinstance(instances[0], FakeMiddleware)
        assert instances[0].initialized is True

    def test_middleware_with_params(
        self, temp_harness_dir: Path, tool_registry: ToolRegistry
    ) -> None:
        """Dict format → instance with params."""
        resolver = MiddlewareResolver()

        class FakeMiddleware:
            def __init__(self, max_retries: int = 1, timeout: float = 10.0) -> None:
                self.max_retries = max_retries
                self.timeout = timeout

        resolver.register("FakeMiddleware", FakeMiddleware)

        instances = resolver.resolve(
            [{"FakeMiddleware": {"max_retries": 5, "timeout": 30.0}}],
            "test.yaml",
        )
        assert len(instances) == 1
        assert isinstance(instances[0], FakeMiddleware)
        assert instances[0].max_retries == 5
        assert instances[0].timeout == 30.0

    def test_unknown_middleware_in_resolver(self) -> None:
        """Unknown middleware name → SubAgentLoadError."""
        resolver = MiddlewareResolver()
        with pytest.raises(SubAgentLoadError, match="UnknownMiddleware"):
            resolver.resolve(["UnknownMiddleware"], "test.yaml")

    def test_invalid_middleware_spec(self) -> None:
        """Non-string/dict spec → SubAgentLoadError."""
        resolver = MiddlewareResolver()
        with pytest.raises(SubAgentLoadError, match="Invalid middleware spec"):
            resolver.resolve([42], "test.yaml")  # type: ignore[list-item]


# ── Tests: SubAgentLoader.list_subagents ───────────────────────────────────


class TestSubAgentLoaderListSubagents:
    """Tests for SubAgentLoader.list_subagents()."""

    def test_list_subagents_returns_info(
        self, subagents_dir_with_files: Path, tool_registry: ToolRegistry
    ) -> None:
        """list_subagents() returns a list of SubAgentInfo objects."""
        loader = SubAgentLoader(subagents_dir_with_files, tool_registry)
        infos = loader.list_subagents()
        assert len(infos) == 2
        for info in infos:
            assert isinstance(info, SubAgentInfo)
            assert isinstance(info.name, str)
            assert isinstance(info.source_file, str)
            assert isinstance(info.description, str)
            assert isinstance(info.tool_count, int)

    def test_list_subagents_no_dir(
        self, temp_harness_dir: Path, tool_registry: ToolRegistry
    ) -> None:
        """list_subagents() when dir does not exist returns []."""
        loader = SubAgentLoader(temp_harness_dir, tool_registry)
        assert loader.list_subagents() == []

    def test_list_subagents_empty_dir(
        self, temp_harness_dir: Path, tool_registry: ToolRegistry
    ) -> None:
        """list_subagents() on empty dir returns []."""
        (temp_harness_dir / "subagents").mkdir()
        loader = SubAgentLoader(temp_harness_dir, tool_registry)
        assert loader.list_subagents() == []


# ── Tests: SubAgentInfo ────────────────────────────────────────────────────


class TestSubAgentInfo:
    """Tests for SubAgentInfo class."""

    def test_subagent_info_fields(self) -> None:
        """SubAgentInfo stores all fields correctly."""
        info = SubAgentInfo(
            name="code-reviewer",
            source_file="code-reviewer.yaml",
            description="Reviews code.",
            tool_count=2,
        )
        assert info.name == "code-reviewer"
        assert info.source_file == "code-reviewer.yaml"
        assert info.description == "Reviews code."
        assert info.tool_count == 2

    def test_repr_format(self) -> None:
        """SubAgentInfo.__repr__ shows name, source_file, tool_count."""
        info = SubAgentInfo(
            name="test",
            source_file="test.yaml",
            description="A test subagent.",
            tool_count=3,
        )
        r = repr(info)
        assert "name='test'" in r
        assert "source_file='test.yaml'" in r
        assert "tool_count=3" in r

    def test_equality(self) -> None:
        """Two SubAgentInfo with same fields are equal."""
        a = SubAgentInfo(name="x", source_file="x.yaml", description="desc", tool_count=1)
        b = SubAgentInfo(name="x", source_file="x.yaml", description="desc", tool_count=1)
        assert a == b

    def test_inequality(self) -> None:
        """Two SubAgentInfo with different fields are not equal."""
        a = SubAgentInfo(name="x", source_file="x.yaml", description="desc", tool_count=1)
        b = SubAgentInfo(name="y", source_file="y.yaml", description="desc2", tool_count=2)
        assert a != b

    def test_not_equal_to_other_type(self) -> None:
        """SubAgentInfo compared to a non-SubAgentInfo returns not equal."""
        info = SubAgentInfo(name="x", source_file="x.yaml", description="desc", tool_count=1)
        assert info != "not a subagent info"


# ── Tests: MiddlewareResolver.register ─────────────────────────────────────


class TestMiddlewareResolverRegister:
    """Tests for MiddlewareResolver.register()."""

    def test_register_multiple_classes(self) -> None:
        """Multiple middleware classes can be registered."""
        resolver = MiddlewareResolver()

        class MW1:
            pass

        class MW2:
            pass

        resolver.register("MW1", MW1)
        resolver.register("MW2", MW2)

        instances = resolver.resolve(["MW1", "MW2"], "test.yaml")
        assert len(instances) == 2
        assert isinstance(instances[0], MW1)
        assert isinstance(instances[1], MW2)

    def test_middleware_params_not_dict_raises(self) -> None:
        """Middleware params must be a dict."""
        resolver = MiddlewareResolver()

        class MW:
            pass

        resolver.register("MW", MW)

        with pytest.raises(SubAgentLoadError, match="must be a dict"):
            resolver.resolve([{"MW": "not_a_dict"}], "test.yaml")


# ── Tests: SubAgentLoader.load_all_graceful ──────────────────────────────


class TestSubAgentLoaderGraceful:
    """Tests for SubAgentLoader.load_all_graceful()."""

    def test_graceful_all_valid(
        self, temp_harness_dir: Path, tool_registry: ToolRegistry
    ) -> None:
        """All valid files → all loaded, no errors."""
        sub_dir = temp_harness_dir / "subagents"
        sub_dir.mkdir()
        (sub_dir / "agent-a.yaml").write_text(
            "name: agent-a\n"
            "description: First agent.\n"
            "system_prompt: You are agent A.\n"
        )
        (sub_dir / "agent-b.yaml").write_text(
            "name: agent-b\n"
            "description: Second agent.\n"
            "system_prompt: You are agent B.\n"
        )
        loader = SubAgentLoader(temp_harness_dir, tool_registry)
        defs, errors = loader.load_all_graceful()
        assert len(defs) == 2
        assert errors == []

    def test_graceful_partial_failure(
        self, temp_harness_dir: Path, tool_registry: ToolRegistry
    ) -> None:
        """One broken file → valid ones still load, error collected."""
        sub_dir = temp_harness_dir / "subagents"
        sub_dir.mkdir()
        (sub_dir / "good.yaml").write_text(
            "name: good-agent\n"
            "description: A valid subagent.\n"
            "system_prompt: You are helpful.\n"
        )
        (sub_dir / "bad.yaml").write_text(
            "name: bad-agent\n"
            "description: Missing system_prompt.\n"
        )
        loader = SubAgentLoader(temp_harness_dir, tool_registry)
        defs, errors = loader.load_all_graceful()
        assert len(defs) == 1
        assert defs[0]["name"] == "good-agent"
        assert len(errors) == 1
        assert "system_prompt" in errors[0]

    def test_graceful_duplicate_name_skipped(
        self, temp_harness_dir: Path, tool_registry: ToolRegistry
    ) -> None:
        """Duplicate names → second is skipped with error, first kept."""
        sub_dir = temp_harness_dir / "subagents"
        sub_dir.mkdir()
        (sub_dir / "a-agent.yaml").write_text(
            "name: dup-name\n"
            "description: First agent.\n"
            "system_prompt: You are first.\n"
        )
        (sub_dir / "b-agent.yaml").write_text(
            "name: dup-name\n"
            "description: Second agent.\n"
            "system_prompt: You are second.\n"
        )
        loader = SubAgentLoader(temp_harness_dir, tool_registry)
        defs, errors = loader.load_all_graceful()
        assert len(defs) == 1
        assert defs[0]["description"] == "First agent."
        assert len(errors) == 1
        assert "Duplicate" in errors[0]

    def test_graceful_no_dir(
        self, temp_harness_dir: Path, tool_registry: ToolRegistry
    ) -> None:
        """No subagents/ dir → empty results, no errors."""
        loader = SubAgentLoader(temp_harness_dir, tool_registry)
        defs, errors = loader.load_all_graceful()
        assert defs == []
        assert errors == []

    def test_graceful_all_broken(
        self, temp_harness_dir: Path, tool_registry: ToolRegistry
    ) -> None:
        """All files broken → empty defs, all errors collected."""
        sub_dir = temp_harness_dir / "subagents"
        sub_dir.mkdir()
        (sub_dir / "bad1.yaml").write_text(
            "name: missing-desc\n"
            "system_prompt: No description field.\n"
        )
        (sub_dir / "bad2.yaml").write_text(
            "not_a_valid_key: true\n"
        )
        loader = SubAgentLoader(temp_harness_dir, tool_registry)
        defs, errors = loader.load_all_graceful()
        assert len(defs) == 0
        assert len(errors) == 2
