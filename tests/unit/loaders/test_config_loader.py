"""Tests for ConfigLoader and HarnessConfig.

Plan: docs/guides/plans-phase-2/01-config-loader.md §6 — Testing Plan
"""

from __future__ import annotations

from pathlib import Path

import pytest

from harness_agent.loaders.config_loader import (
    DEFAULT_MIDDLEWARE_ORDER,
    BackendConfig,
    BackendRouteConfig,
    ConfigLoader,
    ConfigParseError,
    FeaturesConfig,
    HarnessConfig,
    MiddlewareParamConfig,
    SecurityConfig,
)

# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def temp_harness_dir(tmp_path: Path) -> Path:
    """Create a temporary .harness/ directory."""
    harness_dir = tmp_path / ".harness"
    harness_dir.mkdir()
    return harness_dir


@pytest.fixture
def minimal_config_yaml(temp_harness_dir: Path) -> Path:
    """Write a minimal config.yaml with only the model field."""
    config = temp_harness_dir / "config.yaml"
    config.write_text("model: deepseek-v4-flash\n")
    return temp_harness_dir


@pytest.fixture
def full_config_yaml(temp_harness_dir: Path) -> Path:
    """Write a full config.yaml exercising all sections."""
    config = temp_harness_dir / "config.yaml"
    config.write_text("""\
model: deepseek-v4-pro
subagent_heavy_model: deepseek-v4-pro
subagent_light_model: deepseek-v4-flash
summarization_model: deepseek-v4-flash
middleware_order:
  - TodoListMiddleware
  - MemoryMiddleware
  - HumanInTheLoopMiddleware
  - PIIMiddleware
  - FilesystemMiddleware
  - SubAgentMiddleware
  - ShellToolMiddleware
  - SummarizationMiddleware
  - ContextEditingMiddleware
  - ModelFallbackMiddleware
  - ToolRetryMiddleware
middleware_params:
  SummarizationMiddleware:
    trigger:
      - fraction
      - 0.85
    keep:
      - fraction
      - 0.10
  ToolRetryMiddleware:
    max_retries: 3
backend:
  default: state
  routes:
    /memories/: store
    /policies/: store
    /output/: filesystem
  output_dir: /custom/output
features:
  enable_shell: false
  enable_memory: true
  enable_skills: true
  sandbox_type: none
security:
  shell_allow_list:
    - ls
    - cat
    - grep
  interrupt_on:
    - write_file
    - execute_command
  auto_approve: false
system_prompt: null
system_prompt_file: null
""")
    return temp_harness_dir


# ── Happy-path tests ──────────────────────────────────────────────────────


class TestLoadDefaults:
    """ConfigLoader.load() returns defaults when no config file exists."""

    def test_load_defaults_when_no_file(self, temp_harness_dir: Path) -> None:
        """No config.yaml → HarnessConfig with all defaults."""
        loader = ConfigLoader(temp_harness_dir)
        assert not loader.exists()

        config = loader.load()
        assert config.model == "deepseek-v4-flash"
        assert config.subagent_heavy_model == "deepseek-v4-pro"
        assert config.subagent_light_model == "deepseek-v4-flash"
        assert config.summarization_model == "deepseek-v4-flash"
        assert config.middleware_order == []
        assert config.middleware_params == []
        assert config.backend.default == "state"
        assert config.features.enable_shell is False
        assert config.features.enable_memory is True
        assert config.security.auto_approve is False
        assert config.system_prompt is None
        assert config.system_prompt_file is None

    def test_load_defaults_when_no_harness_dir(self, tmp_path: Path) -> None:
        """No .harness/ directory at all → HarnessConfig defaults."""
        harness_dir = tmp_path / ".harness"
        # Don't create it
        assert not harness_dir.exists()

        loader = ConfigLoader(harness_dir)
        config = loader.load()
        assert config.model == "deepseek-v4-flash"

    def test_load_minimal_config(self, minimal_config_yaml: Path) -> None:
        """Only 'model:' specified → model is set, rest are defaults."""
        loader = ConfigLoader(minimal_config_yaml)
        assert loader.exists()

        config = loader.load()
        assert config.model == "deepseek-v4-flash"
        assert config.subagent_heavy_model == "deepseek-v4-pro"  # default
        assert config.middleware_order == []  # default

    def test_load_full_config(self, full_config_yaml: Path) -> None:
        """Full config.yaml → all fields parsed correctly."""
        loader = ConfigLoader(full_config_yaml)
        config = loader.load()

        # Model
        assert config.model == "deepseek-v4-pro"
        assert config.subagent_heavy_model == "deepseek-v4-pro"
        assert config.subagent_light_model == "deepseek-v4-flash"
        assert config.summarization_model == "deepseek-v4-flash"

        # Middleware order
        assert config.middleware_order[:3] == [
            "TodoListMiddleware",
            "MemoryMiddleware",
            "HumanInTheLoopMiddleware",
        ]
        assert len(config.middleware_order) == 11

        # Middleware params
        assert len(config.middleware_params) == 2
        summarization = next(
            p for p in config.middleware_params
            if p.middleware_name == "SummarizationMiddleware"
        )
        assert summarization.params == {
            "trigger": ["fraction", 0.85],
            "keep": ["fraction", 0.10],
        }
        retry = next(
            p for p in config.middleware_params
            if p.middleware_name == "ToolRetryMiddleware"
        )
        assert retry.params == {"max_retries": 3}

        # Backend
        assert config.backend.default == "state"
        assert config.backend.output_dir == "/custom/output"
        route_paths = {r.path for r in config.backend.routes}
        assert route_paths == {"/memories/", "/policies/", "/output/"}

        # Features
        assert config.features.enable_shell is False
        assert config.features.enable_memory is True
        assert config.features.sandbox_type == "none"

        # Security
        assert config.security.shell_allow_list == ["ls", "cat", "grep"]
        assert config.security.interrupt_on == ["write_file", "execute_command"]
        assert config.security.auto_approve is False

    def test_middleware_params_parsed(self, temp_harness_dir: Path) -> None:
        """middleware_params section → parsed into MiddlewareParamConfig list."""
        config_file = temp_harness_dir / "config.yaml"
        config_file.write_text("""\
model: deepseek-v4-flash
middleware_params:
  ToolRetryMiddleware:
    max_retries: 5
  SummarizationMiddleware:
    trigger:
      - fraction
      - 0.90
""")

        loader = ConfigLoader(temp_harness_dir)
        config = loader.load()

        assert len(config.middleware_params) == 2
        names = {p.middleware_name for p in config.middleware_params}
        assert names == {"ToolRetryMiddleware", "SummarizationMiddleware"}


# ── Error-path tests ──────────────────────────────────────────────────────


class TestConfigParseError:
    """ConfigLoader raises ConfigParseError for invalid YAML."""

    def test_load_invalid_yaml(self, temp_harness_dir: Path) -> None:
        """YAML syntax error → ConfigParseError."""
        config_file = temp_harness_dir / "config.yaml"
        config_file.write_text("model: [unclosed\n")  # invalid YAML

        loader = ConfigLoader(temp_harness_dir)
        with pytest.raises(ConfigParseError, match="Failed to parse"):
            loader.load()


class TestValidate:
    """HarnessConfig.validate() detects misconfigurations."""

    def test_validate_valid_config(self) -> None:
        """Valid config → validate() returns empty list."""
        config = HarnessConfig(
            model="deepseek-v4-flash",
            middleware_order=["TodoListMiddleware", "MemoryMiddleware"],
        )
        assert config.validate() == []

    def test_validate_valid_config_all_defaults(self) -> None:
        """All-default config → validate() returns empty list."""
        config = HarnessConfig()
        assert config.validate() == []

    def test_validate_unknown_middleware(self) -> None:
        """Unknown middleware name → error returned."""
        config = HarnessConfig(
            middleware_order=["TodoListMiddleware", "NotARealMiddleware"],
        )
        errors = config.validate()
        assert len(errors) == 1
        assert "Unknown middleware 'NotARealMiddleware'" in errors[0]

    def test_validate_invalid_backend(self) -> None:
        """Invalid backend type in route → error returned."""
        config = HarnessConfig(
            backend=BackendConfig(
                routes=[
                    BackendRouteConfig(path="/data/", backend="redis"),  # type: ignore[arg-type]
                ],
            ),
        )
        errors = config.validate()
        assert len(errors) == 1
        assert "Invalid backend 'redis'" in errors[0]

    def test_validate_invalid_sandbox_type(self) -> None:
        """Invalid sandbox_type → error returned."""
        config = HarnessConfig(
            features=FeaturesConfig(sandbox_type="kubernetes"),  # type: ignore[arg-type]
        )
        errors = config.validate()
        assert len(errors) >= 1
        assert any("sandbox_type" in e for e in errors)


# ── System prompt tests ───────────────────────────────────────────────────


class TestLoadSystemPrompt:
    """ConfigLoader.load_system_prompt() resolves overrides."""

    def test_no_override_returns_none(self, temp_harness_dir: Path) -> None:
        """Neither inline nor file set → returns None."""
        loader = ConfigLoader(temp_harness_dir)
        config = HarnessConfig()
        result = loader.load_system_prompt(config, temp_harness_dir.parent)
        assert result is None

    def test_inline_prompt_takes_priority(
        self, temp_harness_dir: Path, tmp_path: Path
    ) -> None:
        """Inline system_prompt wins over system_prompt_file."""
        # Create a prompt file
        prompt_file = tmp_path / "custom_prompt.md"
        prompt_file.write_text("# File prompt")

        loader = ConfigLoader(temp_harness_dir)
        config = HarnessConfig(
            system_prompt="Inline prompt",
            system_prompt_file="custom_prompt.md",
        )
        result = loader.load_system_prompt(config, tmp_path)
        assert result == "Inline prompt"

    def test_load_system_prompt_from_file(
        self, temp_harness_dir: Path, tmp_path: Path
    ) -> None:
        """system_prompt_file → content loaded from disk."""
        prompt_file = tmp_path / "custom_prompt.md"
        prompt_file.write_text("# Custom System Prompt\n\nBe helpful.")

        loader = ConfigLoader(temp_harness_dir)
        config = HarnessConfig(system_prompt_file="custom_prompt.md")
        result = loader.load_system_prompt(config, tmp_path)
        assert result == "# Custom System Prompt\n\nBe helpful."

    def test_load_system_prompt_file_not_found(
        self, temp_harness_dir: Path, tmp_path: Path
    ) -> None:
        """system_prompt_file points to missing file → ConfigParseError."""
        loader = ConfigLoader(temp_harness_dir)
        config = HarnessConfig(system_prompt_file="nonexistent.md")
        with pytest.raises(ConfigParseError, match="system_prompt_file not found"):
            loader.load_system_prompt(config, tmp_path)


# ── DEFAULT_MIDDLEWARE_ORDER ──────────────────────────────────────────────


class TestDefaults:
    """Module-level defaults are correct."""

    def test_default_middleware_order_is_defined(self) -> None:
        """DEFAULT_MIDDLEWARE_ORDER contains known middleware layers."""
        assert len(DEFAULT_MIDDLEWARE_ORDER) == 11
        assert DEFAULT_MIDDLEWARE_ORDER[0] == "TodoListMiddleware"
        assert DEFAULT_MIDDLEWARE_ORDER[-1] == "ToolRetryMiddleware"
        # Every entry must be a known middleware
        known = HarnessConfig.KNOWN_MIDDLEWARE
        for mw in DEFAULT_MIDDLEWARE_ORDER:
            assert mw in known, f"{mw} not in KNOWN_MIDDLEWARE"


# ── Dataclass field tests ─────────────────────────────────────────────────


class TestBackendRouteConfig:
    """BackendRouteConfig dataclass."""

    def test_creation(self) -> None:
        route = BackendRouteConfig(path="/test/", backend="store")
        assert route.path == "/test/"
        assert route.backend == "store"


class TestMiddlewareParamConfig:
    """MiddlewareParamConfig dataclass."""

    def test_creation(self) -> None:
        mp = MiddlewareParamConfig(
            middleware_name="ToolRetryMiddleware",
            params={"max_retries": 3},
        )
        assert mp.middleware_name == "ToolRetryMiddleware"
        assert mp.params == {"max_retries": 3}


class TestFeaturesConfig:
    """FeaturesConfig defaults."""

    def test_defaults(self) -> None:
        fc = FeaturesConfig()
        assert fc.enable_shell is False
        assert fc.enable_memory is True
        assert fc.enable_skills is True
        assert fc.sandbox_type == "none"


class TestSecurityConfig:
    """SecurityConfig defaults."""

    def test_defaults(self) -> None:
        sc = SecurityConfig()
        assert sc.shell_allow_list == []
        assert sc.interrupt_on == []
        assert sc.auto_approve is False


class TestHarnessConfigDefaults:
    """HarnessConfig has sensible defaults."""

    def test_known_middleware_count(self) -> None:
        """KNOWN_MIDDLEWARE covers at least 16 middleware (plan specification)."""
        assert len(HarnessConfig.KNOWN_MIDDLEWARE) >= 16

    def test_valid_backends(self) -> None:
        """VALID_BACKENDS covers the three expected backend types."""
        assert {"state", "store", "filesystem"} == HarnessConfig.VALID_BACKENDS

    def test_source_path_default_empty(self) -> None:
        """source_path is empty string by default."""
        config = HarnessConfig()
        assert config.source_path == ""
