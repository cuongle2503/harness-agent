"""Config loader for .harness/config.yaml.

Reads and parses the harness configuration file into a HarnessConfig
dataclass with full validation. If no config file exists, returns a
fully-default HarnessConfig so the agent runs out of the box.

Plan: docs/guides/plans-phase-2/01-config-loader.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

# ── Default Middleware Order ──────────────────────────────────────────────
# When middleware_order is empty in config, HarnessBuilder uses this default
# 5-layer order. Source: docs/deep-agents/03-middleware.md

DEFAULT_MIDDLEWARE_ORDER: list[str] = [
    "TodoListMiddleware",          # Layer 1: Planning
    "MemoryMiddleware",            # Layer 1: Context
    "HumanInTheLoopMiddleware",    # Layer 2: Security
    "PIIMiddleware",               # Layer 2: Security
    "FilesystemMiddleware",        # Layer 3: Capabilities
    "SubAgentMiddleware",          # Layer 4: Execution
    "ShellToolMiddleware",         # Layer 4: Execution
    "SummarizationMiddleware",     # Layer 5: Context Management
    "ContextEditingMiddleware",    # Layer 5: Context Management
    "ModelFallbackMiddleware",     # Layer 6: Resilience
    "ToolRetryMiddleware",         # Layer 6: Resilience
]


# ── Data Classes ──────────────────────────────────────────────────────────


@dataclass
class BackendRouteConfig:
    """A single backend route mapping a path to a backend type.

    Attributes:
        path: Route path, e.g. "/memories/" or "/output/".
        backend: Backend type — one of "state", "store", "filesystem".
    """

    path: str
    backend: Literal["state", "store", "filesystem"]


@dataclass
class BackendConfig:
    """Backend routing configuration.

    Attributes:
        default: Default backend when no route matches.
        routes: Path → backend route mappings.
        output_dir: Directory for filesystem-backend output.
    """

    default: Literal["state", "store", "filesystem"] = "state"
    routes: list[BackendRouteConfig] = field(default_factory=list)
    output_dir: str = "/data/agent-output"


@dataclass
class MiddlewareParamConfig:
    """Parameters for a specific middleware.

    Attributes:
        middleware_name: Name of the middleware (e.g. "SummarizationMiddleware").
        params: Arbitrary key/value parameters for that middleware.
    """

    middleware_name: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class FeaturesConfig:
    """Feature flags for the harness."""

    enable_shell: bool = False
    enable_memory: bool = True
    enable_skills: bool = True
    sandbox_type: Literal["none", "docker"] = "none"


@dataclass
class SecurityConfig:
    """Security configuration."""

    shell_allow_list: list[str] = field(default_factory=list)
    interrupt_on: list[str] = field(default_factory=list)
    auto_approve: bool = False


@dataclass
class HarnessConfig:
    """Complete harness configuration loaded from .harness/config.yaml.

    Every field has a sensible default so a project only needs a single
    ``model: xxx`` line to get started.  Call ``validate()`` after loading
    to detect misconfigurations.

    Attributes:
        model: Default model for the main orchestrator agent.
        subagent_heavy_model: Model for heavy subagents (code, architect).
        subagent_light_model: Model for light subagents (researcher, reviewer).
        summarization_model: Model used by SummarizationMiddleware.
        middleware_order: Explicit middleware pipeline order (empty = default).
        middleware_params: Per-middleware parameter overrides.
        backend: Backend routing configuration.
        features: Feature flags.
        security: Security settings.
        system_prompt: Inline system-prompt override (takes priority over file).
        system_prompt_file: Path (relative to project root) to a .md system prompt.
        source_path: Filesystem path this config was loaded from (set by loader).
    """

    # Model
    model: str = "deepseek-v4-flash"
    subagent_heavy_model: str = "deepseek-v4-pro"
    subagent_light_model: str = "deepseek-v4-flash"
    summarization_model: str = "deepseek-v4-flash"

    # Middleware
    middleware_order: list[str] = field(default_factory=list)
    middleware_params: list[MiddlewareParamConfig] = field(default_factory=list)

    # Backend
    backend: BackendConfig = field(default_factory=BackendConfig)

    # Features
    features: FeaturesConfig = field(default_factory=FeaturesConfig)

    # Security
    security: SecurityConfig = field(default_factory=SecurityConfig)

    # System prompt override
    system_prompt: str | None = None
    system_prompt_file: str | None = None

    # Metadata (set by loader)
    source_path: str = ""

    # ── Class-level constants ──────────────────────────────────────────

    KNOWN_MIDDLEWARE: frozenset[str] = frozenset({
        "TodoListMiddleware",
        "MemoryMiddleware",
        "HumanInTheLoopMiddleware",
        "PIIMiddleware",
        "FilesystemMiddleware",
        "SubAgentMiddleware",
        "ShellToolMiddleware",
        "SummarizationMiddleware",
        "ContextEditingMiddleware",
        "ModelFallbackMiddleware",
        "ToolRetryMiddleware",
        "ToolCallLimitMiddleware",
        "ModelCallLimitMiddleware",
        "LLMToolSelectorMiddleware",
        "LLMToolEmulator",
        "FilesystemFileSearchMiddleware",
    })

    VALID_BACKENDS: frozenset[str] = frozenset({"state", "store", "filesystem"})

    # ── Validation ─────────────────────────────────────────────────────

    def validate(self) -> list[str]:
        """Validate the configuration and return a list of error messages.

        Returns:
            List of human-readable error strings.  An empty list means
            the config is valid.
        """
        errors: list[str] = []

        # Validate middleware_order: every name must be a known middleware
        for mw in self.middleware_order:
            if mw not in self.KNOWN_MIDDLEWARE:
                errors.append(
                    f"Unknown middleware '{mw}' in middleware_order. "
                    f"Known: {sorted(self.KNOWN_MIDDLEWARE)}"
                )

        # Validate backend routes
        for route in self.backend.routes:
            if route.backend not in self.VALID_BACKENDS:
                errors.append(
                    f"Invalid backend '{route.backend}' for route "
                    f"'{route.path}'. Valid: {sorted(self.VALID_BACKENDS)}"
                )

        # Validate sandbox_type
        if self.features.sandbox_type not in ("none", "docker"):
            errors.append(
                f"Invalid sandbox_type '{self.features.sandbox_type}'. "
                f"Valid: none, docker"
            )

        return errors


# ── Config Loader ─────────────────────────────────────────────────────────


class ConfigLoader:
    """Load and parse ``.harness/config.yaml`` into a ``HarnessConfig``.

    Gracefully falls back to defaults when no config file is present.

    Usage::

        loader = ConfigLoader(Path("my-project/.harness"))
        config = loader.load()
        errors = config.validate()
        if errors:
            for e in errors:
                print(f"❌ {e}")
    """

    def __init__(self, harness_dir: Path) -> None:
        """Create a loader for the given ``.harness/`` directory.

        Args:
            harness_dir: Path to the ``.harness/`` directory.
        """
        self.harness_dir = harness_dir
        self.config_path = harness_dir / "config.yaml"

    def exists(self) -> bool:
        """Check whether ``config.yaml`` exists inside ``.harness/``."""
        return self.config_path.exists()

    def load(self) -> HarnessConfig:
        """Load configuration from the YAML file.

        Returns:
            A ``HarnessConfig`` instance — always succeeds.  If no config
            file exists, returns a fully-defaulted config.

        Raises:
            ConfigParseError: If the file exists but contains invalid YAML.
        """
        if not self.exists():
            return HarnessConfig(source_path=str(self.config_path))

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            raise ConfigParseError(
                f"Failed to parse {self.config_path}: {e}"
            ) from e

        return self._parse(raw)

    def load_system_prompt(
        self, config: HarnessConfig, project_root: Path
    ) -> str | None:
        """Resolve the system prompt override, if any.

        Priority:
        1. ``config.system_prompt`` (inline string) — takes priority.
        2. ``config.system_prompt_file`` — loaded from disk (relative to
           *project_root*).
        3. Neither → ``None`` (use the built-in default).

        Args:
            config: The already-loaded ``HarnessConfig``.
            project_root: Root directory of the project (for resolving
                relative paths in ``system_prompt_file``).

        Returns:
            The system prompt string, or ``None`` if no override is configured.

        Raises:
            ConfigParseError: If ``system_prompt_file`` is set but the
                referenced file does not exist.
        """
        # Inline prompt takes priority
        if config.system_prompt:
            return config.system_prompt

        # Load from file
        if config.system_prompt_file:
            prompt_path = project_root / config.system_prompt_file
            if not prompt_path.exists():
                raise ConfigParseError(
                    f"system_prompt_file not found: {prompt_path}"
                )
            return prompt_path.read_text(encoding="utf-8")

        return None

    # ── Private helpers ─────────────────────────────────────────────────

    def _parse(self, raw: dict[str, Any]) -> HarnessConfig:
        """Parse a raw config dict into a ``HarnessConfig``."""
        return HarnessConfig(
            # Model
            model=raw.get("model", "deepseek-v4-flash"),
            subagent_heavy_model=raw.get(
                "subagent_heavy_model", "deepseek-v4-pro"
            ),
            subagent_light_model=raw.get(
                "subagent_light_model", "deepseek-v4-flash"
            ),
            summarization_model=raw.get(
                "summarization_model", "deepseek-v4-flash"
            ),

            # Middleware order
            middleware_order=raw.get("middleware_order", []),
            middleware_params=self._parse_middleware_params(
                raw.get("middleware_params", {})
            ),

            # Backend
            backend=self._parse_backend(raw.get("backend", {})),

            # Features
            features=self._parse_features(raw.get("features", {})),

            # Security
            security=self._parse_security(raw.get("security", {})),

            # System prompt
            system_prompt=raw.get("system_prompt"),
            system_prompt_file=raw.get("system_prompt_file"),

            source_path=str(self.config_path),
        )

    def _parse_middleware_params(
        self, raw: dict[str, Any]
    ) -> list[MiddlewareParamConfig]:
        """Parse ``middleware_params`` section."""
        return [
            MiddlewareParamConfig(middleware_name=name, params=params)
            for name, params in raw.items()
        ]

    def _parse_backend(self, raw: dict[str, Any]) -> BackendConfig:
        """Parse ``backend`` section."""
        routes_raw = raw.get("routes", {})
        routes = [
            BackendRouteConfig(path=path, backend=backend)
            for path, backend in routes_raw.items()
        ]
        return BackendConfig(
            default=raw.get("default", "state"),
            routes=routes,
            output_dir=raw.get("output_dir", "/data/agent-output"),
        )

    @staticmethod
    def _parse_features(raw: dict[str, Any]) -> FeaturesConfig:
        """Parse ``features`` section."""
        return FeaturesConfig(
            enable_shell=raw.get("enable_shell", False),
            enable_memory=raw.get("enable_memory", True),
            enable_skills=raw.get("enable_skills", True),
            sandbox_type=raw.get("sandbox_type", "none"),
        )

    @staticmethod
    def _parse_security(raw: dict[str, Any]) -> SecurityConfig:
        """Parse ``security`` section."""
        return SecurityConfig(
            shell_allow_list=raw.get("shell_allow_list", []),
            interrupt_on=raw.get("interrupt_on", []),
            auto_approve=raw.get("auto_approve", False),
        )


# ── Exceptions ────────────────────────────────────────────────────────────


class ConfigParseError(Exception):
    """Raised when ``.harness/config.yaml`` cannot be parsed."""
