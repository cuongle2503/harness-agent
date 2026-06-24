"""Integration tests for HarnessBuilder.

Plan: docs/guides/plans-phase-2/06-harness-builder.md §6 — Testing Plan
"""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from harness_agent.loaders.harness_builder import (
    HarnessBuilder,
    HarnessBuildError,
)

# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def empty_project(tmp_path: Path) -> Path:
    """Create a project directory without .harness/."""
    project = tmp_path / "empty-project"
    project.mkdir()
    return project


@pytest.fixture
def project_with_empty_harness(tmp_path: Path) -> Path:
    """Create a project with an empty .harness/ directory."""
    project = tmp_path / "empty-harness"
    project.mkdir()
    (project / ".harness").mkdir()
    return project


@pytest.fixture
def project_with_config_only(tmp_path: Path) -> Path:
    """Create a project with only config.yaml."""
    project = tmp_path / "config-only"
    project.mkdir()
    harness_dir = project / ".harness"
    harness_dir.mkdir()
    (harness_dir / "config.yaml").write_text("model: deepseek-v4-flash\n")
    return project


@pytest.fixture
def project_with_skills(tmp_path: Path) -> Path:
    """Create a project with skills/."""
    project = tmp_path / "skills-project"
    project.mkdir()
    harness_dir = project / ".harness"
    harness_dir.mkdir()
    skills_dir = harness_dir / "skills"
    skills_dir.mkdir()
    (skills_dir / "test-skill.md").write_text("# Test Skill\n\n...")
    return project


@pytest.fixture
def project_with_rules(tmp_path: Path) -> Path:
    """Create a project with rules/."""
    project = tmp_path / "rules-project"
    project.mkdir()
    harness_dir = project / ".harness"
    harness_dir.mkdir()
    rules_dir = harness_dir / "rules"
    rules_dir.mkdir()
    (rules_dir / "test-rule.md").write_text("# Test Rule\n\n...")
    return project


@pytest.fixture
def project_with_subagents(tmp_path: Path) -> Path:
    """Create a project with subagents/."""
    project = tmp_path / "subagents-project"
    project.mkdir()
    harness_dir = project / ".harness"
    harness_dir.mkdir()
    subs_dir = harness_dir / "subagents"
    subs_dir.mkdir()
    (subs_dir / "test-agent.yaml").write_text(
        "name: test-agent\n"
        "description: A test subagent.\n"
        "system_prompt: You are a test agent.\n"
    )
    return project


@pytest.fixture
def project_with_hooks(tmp_path: Path) -> Path:
    """Create a project with hooks/."""
    project = tmp_path / "hooks-project"
    project.mkdir()
    harness_dir = project / ".harness"
    harness_dir.mkdir()
    hooks_dir = harness_dir / "hooks"
    hooks_dir.mkdir()
    (hooks_dir / "session_start.sh").write_text(
        "#!/bin/bash\necho 'start'\nexit 0\n"
    )
    return project


@pytest.fixture
def full_harness_project(tmp_path: Path) -> Path:
    """Create a project with a full .harness/ setup."""
    project = tmp_path / "full-project"
    project.mkdir()
    harness_dir = project / ".harness"
    harness_dir.mkdir()
    (harness_dir / "config.yaml").write_text("model: deepseek-v4-flash\n")

    skills_dir = harness_dir / "skills"
    skills_dir.mkdir()
    (skills_dir / "test-skill.md").write_text("# Test Skill\n\n...")

    rules_dir = harness_dir / "rules"
    rules_dir.mkdir()
    (rules_dir / "test-rule.md").write_text("# Test Rule\n\n...")

    subs_dir = harness_dir / "subagents"
    subs_dir.mkdir()
    (subs_dir / "test-agent.yaml").write_text(
        "name: test-agent\n"
        "description: A test subagent.\n"
        "system_prompt: You are a test agent.\n"
    )

    hooks_dir = harness_dir / "hooks"
    hooks_dir.mkdir()
    (hooks_dir / "session_start.sh").write_text(
        "#!/bin/bash\necho 'start'\nexit 0\n"
    )

    return project


# ── Mock helpers ──────────────────────────────────────────────────────────


def _make_mock_agent() -> mock.MagicMock:
    """Create a mock CompiledStateGraph."""
    return mock.MagicMock()


def _make_mock_model() -> mock.MagicMock:
    """Create a mock BaseChatModel."""
    return mock.MagicMock()


# ── Common mock setup for build tests ─────────────────────────────────────


def _setup_build_mocks(builder: HarnessBuilder) -> mock.MagicMock:
    """Set up mocks so builder.build() succeeds without external deps.

    Returns the mock create_deep_agent function.
    """
    mock_create = mock.patch.object(
        builder.__class__, "_resolve_model",
        return_value=_make_mock_model(),
    )
    mock_create.start()

    return mock_create


# ── Tests ─────────────────────────────────────────────────────────────────


class TestHarnessBuilderInit:
    """Tests for HarnessBuilder.__init__()."""

    def test_builder_with_no_harness_dir(self, empty_project: Path) -> None:
        """Builder can be created even when .harness/ does not exist."""
        builder = HarnessBuilder(empty_project)
        assert builder.harness_dir == empty_project / ".harness"
        assert builder.config_loader.exists() is False
        assert builder.skill_loader.exists is False
        assert builder.rule_loader.exists is False
        assert builder.subagent_loader.exists is False
        assert builder.hook_loader.exists is False

    def test_builder_with_empty_harness_dir(
        self, project_with_empty_harness: Path
    ) -> None:
        """Builder detects .harness/ exists but loaders have empty dirs."""
        builder = HarnessBuilder(project_with_empty_harness)
        assert builder.harness_dir.is_dir()
        assert builder.config_loader.exists() is False
        assert builder.skill_loader.exists is False

    def test_builder_creates_event_bus(self, empty_project: Path) -> None:
        """Each builder creates its own EventBus."""
        builder = HarnessBuilder(empty_project)
        assert builder.event_bus is not None
        assert builder.event_bus.listener_count == 0


class TestHarnessBuilderBuild:
    """Tests for HarnessBuilder.build() — mock create_deep_agent."""

    @mock.patch("harness_agent.loaders.harness_builder.create_deep_agent")
    def test_build_with_empty_harness_dir(
        self,
        mock_create: mock.MagicMock,
        project_with_empty_harness: Path,
    ) -> None:
        """Build succeeds with empty .harness/ → uses defaults."""
        mock_create.return_value = _make_mock_agent()
        builder = HarnessBuilder(project_with_empty_harness)
        # Mock model resolution and middleware building to avoid API key deps
        builder._resolve_model = lambda name: _make_mock_model()  # type: ignore[method-assign]
        builder._build_middleware_pipeline = lambda: []  # type: ignore[method-assign]

        agent = builder.build()

        assert agent is not None
        mock_create.assert_called_once()

    @mock.patch("harness_agent.loaders.harness_builder.create_deep_agent")
    def test_build_with_no_harness_dir(
        self,
        mock_create: mock.MagicMock,
        empty_project: Path,
    ) -> None:
        """Build succeeds without any .harness/ directory."""
        mock_create.return_value = _make_mock_agent()
        builder = HarnessBuilder(empty_project)
        builder._resolve_model = lambda name: _make_mock_model()  # type: ignore[method-assign]
        builder._build_middleware_pipeline = lambda: []  # type: ignore[method-assign]

        agent = builder.build()

        assert agent is not None
        mock_create.assert_called_once()

    @mock.patch("harness_agent.loaders.harness_builder.create_deep_agent")
    def test_build_with_config_only(
        self,
        mock_create: mock.MagicMock,
        project_with_config_only: Path,
    ) -> None:
        """Build with only config.yaml → config is parsed."""
        mock_create.return_value = _make_mock_agent()
        builder = HarnessBuilder(project_with_config_only)
        builder._resolve_model = lambda name: _make_mock_model()  # type: ignore[method-assign]
        builder._build_middleware_pipeline = lambda: []  # type: ignore[method-assign]

        agent = builder.build()

        assert agent is not None
        assert builder.config.model == "deepseek-v4-flash"

    @mock.patch("harness_agent.loaders.harness_builder.create_deep_agent")
    def test_build_with_skills(
        self,
        mock_create: mock.MagicMock,
        project_with_skills: Path,
    ) -> None:
        """Build with skills → skill paths go to skills= for progressive disclosure."""
        mock_create.return_value = _make_mock_agent()
        builder = HarnessBuilder(project_with_skills)
        builder._resolve_model = lambda name: _make_mock_model()  # type: ignore[method-assign]
        builder._build_middleware_pipeline = lambda: []  # type: ignore[method-assign]

        agent = builder.build()

        assert agent is not None
        call_kwargs = mock_create.call_args.kwargs
        # Skills go to skills= (SkillsMiddleware — progressive disclosure)
        assert call_kwargs["skills"] is not None
        assert len(call_kwargs["skills"]) == 1
        assert "test-skill.md" in call_kwargs["skills"][0]
        # Memory should be None (no rules in this fixture)
        assert call_kwargs["memory"] is None

    @mock.patch("harness_agent.loaders.harness_builder.create_deep_agent")
    def test_build_with_rules(
        self,
        mock_create: mock.MagicMock,
        project_with_rules: Path,
    ) -> None:
        """Build with rules → rule paths collected as memory sources."""
        mock_create.return_value = _make_mock_agent()
        builder = HarnessBuilder(project_with_rules)
        builder._resolve_model = lambda name: _make_mock_model()  # type: ignore[method-assign]
        builder._build_middleware_pipeline = lambda: []  # type: ignore[method-assign]

        agent = builder.build()

        assert agent is not None
        # Verify rules were collected via the public API
        rule_sources = builder.rule_loader.get_memory_sources()
        assert len(rule_sources) == 1
        assert "test-rule.md" in rule_sources[0]

    @mock.patch("harness_agent.loaders.harness_builder.create_deep_agent")
    def test_build_with_subagents(
        self,
        mock_create: mock.MagicMock,
        project_with_subagents: Path,
    ) -> None:
        """Build with subagents → subagent defs passed to create_deep_agent."""
        mock_create.return_value = _make_mock_agent()
        builder = HarnessBuilder(project_with_subagents)
        builder._resolve_model = lambda name: _make_mock_model()  # type: ignore[method-assign]
        builder._build_middleware_pipeline = lambda: []  # type: ignore[method-assign]

        agent = builder.build()

        assert agent is not None
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["subagents"] is not None
        assert len(call_kwargs["subagents"]) == 1
        assert call_kwargs["subagents"][0]["name"] == "test-agent"

    @mock.patch("harness_agent.loaders.harness_builder.create_deep_agent")
    def test_build_with_hooks(
        self,
        mock_create: mock.MagicMock,
        project_with_hooks: Path,
    ) -> None:
        """Build with hooks → hooks loaded into EventBus."""
        mock_create.return_value = _make_mock_agent()
        builder = HarnessBuilder(project_with_hooks)
        builder._resolve_model = lambda name: _make_mock_model()  # type: ignore[method-assign]
        builder._build_middleware_pipeline = lambda: []  # type: ignore[method-assign]

        agent = builder.build()

        assert agent is not None
        assert builder.event_bus.listener_count == 1

    @mock.patch("harness_agent.loaders.harness_builder.create_deep_agent")
    def test_build_full_harness(
        self,
        mock_create: mock.MagicMock,
        full_harness_project: Path,
    ) -> None:
        """Full .harness/ → all loaders contribute."""
        mock_create.return_value = _make_mock_agent()
        builder = HarnessBuilder(full_harness_project)
        builder._resolve_model = lambda name: _make_mock_model()  # type: ignore[method-assign]
        builder._build_middleware_pipeline = lambda: []  # type: ignore[method-assign]

        agent = builder.build()

        assert agent is not None
        assert builder.config.model == "deepseek-v4-flash"
        assert builder.event_bus.listener_count == 1

        call_kwargs = mock_create.call_args.kwargs
        # Rules → memory (always-loaded)
        assert call_kwargs["memory"] is not None
        assert len(call_kwargs["memory"]) == 1
        # Skills → skills (progressive disclosure)
        assert call_kwargs["skills"] is not None
        assert len(call_kwargs["skills"]) == 1
        # Subagents
        assert call_kwargs["subagents"] is not None
        assert len(call_kwargs["subagents"]) == 1


class TestHarnessBuilderErrors:
    """Tests for HarnessBuilder error handling."""

    def test_build_invalid_config_fails(self, tmp_path: Path) -> None:
        """Invalid config.yaml → HarnessBuildError."""
        project = tmp_path / "bad-config"
        project.mkdir()
        harness_dir = project / ".harness"
        harness_dir.mkdir()
        (harness_dir / "config.yaml").write_text(
            "model: deepseek-v4-flash\n"
            "middleware_order:\n"
            "  - NonExistentMiddleware\n"
        )

        builder = HarnessBuilder(project)
        with pytest.raises(HarnessBuildError, match="NonExistentMiddleware"):
            builder.build()

    def test_build_invalid_yaml_config_fails(self, tmp_path: Path) -> None:
        """Unparseable YAML → error propagated."""
        project = tmp_path / "bad-yaml"
        project.mkdir()
        harness_dir = project / ".harness"
        harness_dir.mkdir()
        (harness_dir / "config.yaml").write_text(
            "model: deepseek-v4-flash\n"
            "\tbad: indent with tab\n"
        )

        builder = HarnessBuilder(project)
        with pytest.raises((HarnessBuildError, Exception)):
            builder.build()


class TestHarnessBuilderConfig:
    """Tests for HarnessBuilder configuration behavior."""

    @mock.patch("harness_agent.loaders.harness_builder.create_deep_agent")
    def test_default_middleware_order_used(
        self,
        mock_create: mock.MagicMock,
        empty_project: Path,
    ) -> None:
        """When no middleware_order in config, default is used."""
        mock_create.return_value = _make_mock_agent()
        builder = HarnessBuilder(empty_project)
        builder._resolve_model = lambda name: _make_mock_model()  # type: ignore[method-assign]
        builder._build_middleware_pipeline = lambda: []  # type: ignore[method-assign]

        builder.build()

        mock_create.assert_called_once()

    @mock.patch("harness_agent.loaders.harness_builder.create_deep_agent")
    def test_custom_system_prompt_from_file(
        self,
        mock_create: mock.MagicMock,
        tmp_path: Path,
    ) -> None:
        """system_prompt_file in config loads custom prompt from disk."""
        project = tmp_path / "custom-prompt"
        project.mkdir()
        harness_dir = project / ".harness"
        harness_dir.mkdir()

        (project / "prompt.md").write_text(
            "# Custom System Prompt\nBe helpful.\n"
        )
        (harness_dir / "config.yaml").write_text(
            "model: deepseek-v4-flash\n"
            "system_prompt_file: prompt.md\n"
        )

        mock_create.return_value = _make_mock_agent()
        builder = HarnessBuilder(project)
        builder._resolve_model = lambda name: _make_mock_model()  # type: ignore[method-assign]
        builder._build_middleware_pipeline = lambda: []  # type: ignore[method-assign]

        builder.build()

        call_kwargs = mock_create.call_args.kwargs
        assert "Be helpful" in call_kwargs["system_prompt"]


class TestHarnessBuilderLoadConfig:
    """Tests for HarnessBuilder.load_config() — lightweight loading."""

    def test_load_config_with_empty_harness(self, project_with_empty_harness: Path) -> None:
        """load_config() works even with empty .harness/."""
        builder = HarnessBuilder(project_with_empty_harness)
        config = builder.load_config()
        assert config is not None
        assert config.model == "deepseek-v4-flash"  # default

    def test_load_config_with_config_only(self, project_with_config_only: Path) -> None:
        """load_config() parses config.yaml."""
        builder = HarnessBuilder(project_with_config_only)
        config = builder.load_config()
        assert config.model == "deepseek-v4-flash"

    def test_load_config_with_no_harness_dir(self, empty_project: Path) -> None:
        """load_config() returns defaults when .harness/ doesn't exist."""
        builder = HarnessBuilder(empty_project)
        config = builder.load_config()
        assert config is not None
        assert config.model == "deepseek-v4-flash"

    def test_load_config_registers_hooks(self, project_with_hooks: Path) -> None:
        """load_config() loads hooks into the event bus."""
        builder = HarnessBuilder(project_with_hooks)
        builder.load_config()
        assert builder.event_bus.listener_count == 1

    def test_load_config_invalid_yaml_fails(self, tmp_path: Path) -> None:
        """load_config() raises on invalid YAML."""
        project = tmp_path / "bad-yaml"
        project.mkdir()
        harness_dir = project / ".harness"
        harness_dir.mkdir()
        (harness_dir / "config.yaml").write_text(
            "model: deepseek-v4-flash\n\tbad: tab indent\n"
        )
        builder = HarnessBuilder(project)
        with pytest.raises((HarnessBuildError, Exception)):
            builder.load_config()


class TestHarnessBuilderMemorySources:
    """Tests for HarnessBuilder.get_memory_sources()."""

    def test_get_memory_sources_empty(self, project_with_empty_harness: Path) -> None:
        """No sources when .harness/ has no skills or rules."""
        builder = HarnessBuilder(project_with_empty_harness)
        builder.load_config()
        sources = builder.get_memory_sources()
        assert sources == []

    def test_get_memory_sources_with_skills(self, project_with_skills: Path) -> None:
        """Skill paths are collected via get_skill_sources() (not memory)."""
        builder = HarnessBuilder(project_with_skills)
        builder.load_config()
        # Skills go to get_skill_sources() for progressive disclosure
        skill_sources = builder.get_skill_sources()
        assert len(skill_sources) == 1
        assert "test-skill.md" in skill_sources[0]
        # Rules should be empty (no rules in this fixture)
        assert builder.get_memory_sources() == []

    def test_get_memory_sources_with_rules(self, project_with_rules: Path) -> None:
        """Rule paths are collected as memory sources (rules only)."""
        builder = HarnessBuilder(project_with_rules)
        builder.load_config()
        sources = builder.get_memory_sources()
        assert len(sources) == 1
        assert "test-rule.md" in sources[0]
        # Skills should be empty (no skills in this fixture)
        assert builder.get_skill_sources() == []

    def test_get_memory_sources_combined(self, full_harness_project: Path) -> None:
        """Skills + rules are both collected via separated methods."""
        builder = HarnessBuilder(full_harness_project)
        builder.load_config()
        # New separated methods
        rule_sources = builder.get_memory_sources()
        skill_sources = builder.get_skill_sources()
        assert len(rule_sources) == 1   # rules only
        assert len(skill_sources) == 1  # skills only


class TestHarnessBuilderSubagentDefs:
    """Tests for HarnessBuilder.get_subagent_defs()."""

    def test_get_subagent_defs_empty(self, project_with_empty_harness: Path) -> None:
        """No subagents when none configured."""
        builder = HarnessBuilder(project_with_empty_harness)
        builder.load_config()
        defs = builder.get_subagent_defs()
        assert defs == []

    def test_get_subagent_defs_with_subagents(
        self, project_with_subagents: Path
    ) -> None:
        """Subagent defs are loaded from .harness/subagents/."""
        builder = HarnessBuilder(project_with_subagents)
        builder.load_config()
        defs = builder.get_subagent_defs()
        assert len(defs) == 1
        assert defs[0]["name"] == "test-agent"


class TestHarnessBuilderSystemPrompt:
    """Tests for HarnessBuilder.get_system_prompt()."""

    def test_get_system_prompt_default(self, project_with_empty_harness: Path) -> None:
        """Returns default system prompt when no override."""
        builder = HarnessBuilder(project_with_empty_harness)
        builder.load_config()
        prompt = builder.get_system_prompt()
        assert "helpful AI assistant" in prompt.lower() or "core responsibilities" in prompt.lower()

    def test_get_system_prompt_from_file(
        self, tmp_path: Path
    ) -> None:
        """Returns custom prompt when system_prompt_file is set."""
        project = tmp_path / "custom-prompt"
        project.mkdir()
        harness_dir = project / ".harness"
        harness_dir.mkdir()
        (project / "prompt.md").write_text("# Custom\nBe helpful.\n")
        (harness_dir / "config.yaml").write_text(
            "model: deepseek-v4-flash\nsystem_prompt_file: prompt.md\n"
        )
        builder = HarnessBuilder(project)
        builder.load_config()
        prompt = builder.get_system_prompt()
        assert "Be helpful" in prompt


class TestHarnessBuilderModelSelection:
    """Tests for HarnessBuilder model resolution with model_selection."""

    @mock.patch("harness_agent.loaders.harness_builder.create_deep_agent")
    def test_build_uses_model_selection(
        self,
        mock_create: mock.MagicMock,
        project_with_config_only: Path,
    ) -> None:
        """When model_selection is provided, it's used for model resolution."""
        from harness_agent.config import AgentModelSelection

        mock_create.return_value = mock.MagicMock()
        model_sel = AgentModelSelection()
        builder = HarnessBuilder(
            project_with_config_only, model_selection=model_sel
        )

        # Mock model resolution and middleware to avoid API key requirement
        builder._resolve_model = lambda name: mock.MagicMock()  # type: ignore[method-assign]
        builder._build_middleware_pipeline = lambda: []  # type: ignore[method-assign]

        builder.build()

        # Verify create_deep_agent was called with model_selection available
        mock_create.assert_called_once()
        assert builder.model_selection is model_sel


class TestHarnessBuilderGracefulDegradation:
    """Tests for graceful fallback when deepagents is not available."""

    @mock.patch(
        "harness_agent.loaders.harness_builder._DEEPAGENTS_AVAILABLE", False
    )
    def test_build_fails_without_deepagents(
        self, project_with_config_only: Path
    ) -> None:
        """build() raises HarnessBuildError when deepagents is missing."""
        builder = HarnessBuilder(project_with_config_only)
        from harness_agent.loaders.harness_builder import HarnessBuildError
        with pytest.raises(HarnessBuildError, match="deepagents"):
            builder.build()
