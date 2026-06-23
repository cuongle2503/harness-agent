"""Harness Builder — kết nối tất cả loaders thành agent từ .harness/.

Plan: docs/guides/plans-phase-2/06-harness-builder.md
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from langchain_core.language_models import BaseChatModel

from harness_agent.config import AgentModelSelection
from harness_agent.loaders.config_loader import ConfigLoader, HarnessConfig
from harness_agent.loaders.hook_loader import EventBus, HookLoader
from harness_agent.loaders.rule_loader import RuleLoader
from harness_agent.loaders.skill_loader import SkillLoader
from harness_agent.loaders.subagent_loader import SubAgentLoader
from harness_agent.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

# Optional deepagents imports — only needed when create_deep_agent is used
try:
    from deepagents import create_deep_agent  # noqa: F811
    from deepagents.backends import (  # noqa: F811
        CompositeBackend,
        FilesystemBackend,
        StateBackend,
        StoreBackend,
    )
    _DEEPAGENTS_AVAILABLE = True
except ImportError:  # pragma: no cover
    _DEEPAGENTS_AVAILABLE = False

try:
    from langchain.agents.middleware import (  # noqa: F811
        ContextEditingMiddleware,
        ModelFallbackMiddleware,
        PIIMiddleware,
        ShellToolMiddleware,
        ToolRetryMiddleware,
    )
    _LANGCHAIN_MIDDLEWARE_AVAILABLE = True
except ImportError:  # pragma: no cover
    _LANGCHAIN_MIDDLEWARE_AVAILABLE = False

# Default middleware order (5-layer principle from 03-middleware.md)
DEFAULT_MIDDLEWARE_ORDER = [
    "TodoListMiddleware",        # Layer 1: Planning
    "MemoryMiddleware",          # Layer 1: Context
    "HumanInTheLoopMiddleware",  # Layer 2: Security
    "PIIMiddleware",             # Layer 2: Security
    "FilesystemMiddleware",      # Layer 3: Capabilities
    "SubAgentMiddleware",        # Layer 4: Execution
    "ShellToolMiddleware",       # Layer 4: Execution
    "SummarizationMiddleware",   # Layer 5: Context Management
    "ContextEditingMiddleware",  # Layer 5: Context Management
    "ModelFallbackMiddleware",   # Layer 6: Resilience
    "ToolRetryMiddleware",       # Layer 6: Resilience
]


class HarnessBuildError(Exception):
    """Raised when the harness cannot be built from .harness/ config."""


class HarnessBuilder:
    """Build an agent from a project's ``.harness/`` directory.

    This is the **single entry point** for creating agents. Everything the
    agent needs is loaded from the ``.harness/`` folder in the project.

    Usage::

        builder = HarnessBuilder(Path("my-project/"))
        agent = builder.build()
        result = agent.invoke({
            "messages": [{"role": "user", "content": "..."}]
        })
    """

    def __init__(
        self,
        project_root: Path,
        *,
        tool_registry: ToolRegistry | None = None,
        model_selection: AgentModelSelection | None = None,
    ) -> None:
        """Create a builder for the given project.

        Args:
            project_root: Root directory of the project (must contain
                or may contain a ``.harness/`` subdirectory).
            tool_registry: Optional pre-configured ToolRegistry.
            model_selection: Optional pre-configured AgentModelSelection.
                When provided, used by ``_resolve_model`` to create models
                via the configured provider/factory instead of always
                defaulting to ``ChatDeepSeek``.
        """
        self.project_root = project_root.resolve()
        self.harness_dir = self.project_root / ".harness"
        self.tool_registry = tool_registry or ToolRegistry()
        self.model_selection = model_selection or AgentModelSelection()

        # Sub-components
        self.event_bus = EventBus()
        self.config_loader = ConfigLoader(self.harness_dir)
        self.skill_loader = SkillLoader(self.harness_dir)
        self.rule_loader = RuleLoader(self.harness_dir)
        self.subagent_loader = SubAgentLoader(
            self.harness_dir, self.tool_registry
        )
        self.hook_loader = HookLoader(self.harness_dir, self.event_bus)

        # Results (set after build())
        self.config: HarnessConfig | None = None
        self.agent: Any = None  # CompiledStateGraph | None

    # ── Public API ──────────────────────────────────────────────────────

    def load_config(self) -> HarnessConfig:
        """Load and validate harness configuration without building the agent.

        This is a lightweight alternative to ``build()`` — it loads config,
        hooks, and collects memory sources, but does NOT require
        ``create_deep_agent`` from the ``deepagents`` package.

        Returns:
            The validated HarnessConfig.

        Raises:
            HarnessBuildError: If the config is invalid.
        """
        logger.info("Loading harness config from: %s", self.harness_dir)

        # Step 1: Load & validate config
        self.config = self._load_and_validate_config()

        # Step 2: Load hooks (so they're registered before agent starts)
        self.hook_loader.load_all()

        return self.config

    def get_memory_sources(self) -> list[str]:
        """Return memory source paths from **rules only**.

        Rules are always-loaded context handled by MemoryMiddleware.
        Skills use ``get_skill_sources()`` for progressive disclosure
        via SkillsMiddleware.

        Returns:
            List of file paths to rule markdown files.
        """
        return self.rule_loader.get_memory_sources()

    def get_skill_sources(self) -> list[str]:
        """Return skill source paths for progressive disclosure.

        Skills use SkillsMiddleware: only name + description are
        loaded at start; the full body is loaded on-demand when the
        task matches the skill description.

        Returns:
            List of file paths to skill markdown files.
        """
        return self.skill_loader.get_memory_sources()

    def get_subagent_defs(self) -> list[dict[str, Any]]:
        """Return subagent definitions from ``.harness/subagents/``.

        Returns:
            List of subagent definition dicts ready for
            ``create_deep_agent(subagents=...)``.
        """
        return self.subagent_loader.load_all()

    def get_system_prompt(self) -> str:
        """Build and return the system prompt from harness config.

        Returns:
            System prompt string resolved from config overrides
            or the built-in default.
        """
        return self._build_system_prompt()

    def build(
        self, *, model: Any = None, summarization_model: Any = None
    ) -> Any:
        """Build the agent from ``.harness/`` configuration.

        Args:
            model: Optional pre-created BaseChatModel. When provided,
                this model is used directly instead of creating a new
                one via ``_resolve_model``. Pass the already-initialized
                LLM from the caller to avoid API key issues.
            summarization_model: Optional pre-created summarization model.

        Returns:
            A CompiledStateGraph ready for invoke/stream when
            ``deepagents`` is available, otherwise raises HarnessBuildError.

        Raises:
            HarnessBuildError: If ``deepagents`` is not installed or the
                config is invalid.
        """
        if not _DEEPAGENTS_AVAILABLE:
            raise HarnessBuildError(
                "deepagents package is required for HarnessBuilder.build(). "
                "Install it with: pip install deepagents"
            )

        logger.info("Building harness from: %s", self.harness_dir)

        # Step 1: Load & validate config
        self.config = self._load_and_validate_config()

        # Step 2: Load hooks (before other steps so hooks can intercept)
        self.hook_loader.load_all()

        # Step 3: Build backend from config
        backend = self._build_backend()

        # Step 4: Load subagents from .harness/subagents/
        subagent_defs = self.subagent_loader.load_all()

        # Step 5: Collect sources — rules (always-loaded) and
        # skills (progressive disclosure) are handled by different
        # middleware: MemoryMiddleware for rules, SkillsMiddleware for skills.
        rule_sources = self.rule_loader.get_memory_sources()
        skill_sources = self.skill_loader.get_memory_sources()

        # Convert absolute paths to backend-relative paths.
        # create_deep_agent expects POSIX paths relative to the backend's
        # root_dir. When using FilesystemBackend, this maps to the project_root.
        _rel = lambda p: str(Path(p).resolve().relative_to(self.project_root))
        rule_sources = [_rel(p) for p in rule_sources]
        # Skill sources are directory paths (Agent Skills spec).
        # SkillsMiddleware scans them for */SKILL.md files.
        skill_sources = [_rel(p) for p in skill_sources]

        # Step 6: Resolve models — use pre-created models if provided
        main_model = model or self._resolve_model(self.config.model)
        sum_model = summarization_model or self._resolve_model(
            self.config.summarization_model
        )

        # Step 7: Build middleware pipeline (excludes MemoryMiddleware,
        # SkillsMiddleware, and SubAgentMiddleware — those are auto-created
        # by create_deep_agent from the `memory=`, `skills=`, and
        # `subagents=` parameters below).
        middleware = self._build_middleware_pipeline(
            backend=backend,
            subagent_defs=subagent_defs,
            memory_sources=rule_sources + skill_sources,
            summarization_model=sum_model,
        )

        # Step 8: Build system prompt
        system_prompt = self._build_system_prompt()

        # Step 9: Create agent
        # NOTE: Do NOT pass MemoryMiddleware, SkillsMiddleware, or
        # SubAgentMiddleware in the `middleware` list — create_deep_agent
        # auto-creates them from the corresponding parameters below.
        # Passing both causes "Please remove duplicate middleware instances."
        self.agent = create_deep_agent(
            model=main_model,
            middleware=middleware,
            backend=backend,
            system_prompt=system_prompt,
            subagents=subagent_defs if subagent_defs else None,
            memory=rule_sources if rule_sources else None,
            skills=skill_sources if skill_sources else None,
        )

        logger.info("Harness built successfully")
        return self.agent

    # ── Private: Build Steps ────────────────────────────────────────────

    def _load_and_validate_config(self) -> HarnessConfig:
        """Load config and validate. Raise on errors."""
        config = self.config_loader.load()
        errors = config.validate()
        if errors:
            raise HarnessBuildError(
                "Invalid .harness/config.yaml:\n"
                + "\n".join(f"  - {e}" for e in errors)
            )
        return config

    def _build_backend(self) -> CompositeBackend:
        """Build a CompositeBackend from config."""
        assert self.config is not None
        cfg = self.config.backend
        routes: dict[str, Any] = {}

        for route in cfg.routes:
            backend = self._backend_for_name(route.backend, cfg.output_dir)
            routes[route.path] = backend

        default_backend = self._backend_for_name(cfg.default, cfg.output_dir)

        return CompositeBackend(default=default_backend, routes=routes)

    @staticmethod
    def _backend_for_name(name: str, output_dir: str) -> Any:
        """Map a backend name to an instance."""
        if name == "store":
            return StoreBackend(file_format="v2")
        elif name == "filesystem":
            # virtual_mode=False allows both absolute and relative paths.
            # With virtual_mode=True, absolute paths that match root_dir
            # are NOT stripped, causing path_not_found on real files.
            return FilesystemBackend(root_dir=output_dir, virtual_mode=False)
        else:  # state (default)
            return StateBackend()

    def _collect_memory_sources(self) -> list[str]:
        """Collect all memory sources from skills + rules (legacy).

        Prefer ``get_memory_sources()`` (rules only) and
        ``get_skill_sources()`` (skills only) for new code.
        """
        sources: list[str] = []
        sources.extend(self.skill_loader.get_memory_sources())
        sources.extend(self.rule_loader.get_memory_sources())
        return sources

    def _resolve_model(self, model_name: str) -> BaseChatModel:
        """Resolve a model name to a BaseChatModel instance.

        Uses ``self.model_selection.to_langchain_model()`` when a
        model_selection was provided, falling back to a direct
        ``ChatDeepSeek`` constructor for backward compatibility.
        """
        if self.model_selection is not None:
            from harness_agent.config import ModelConfig

            model_config = ModelConfig(
                model_id=model_name,
                provider="deepseek",
                temperature=0.0,
                purpose="HarnessBuilder resolved model",
            )
            try:
                return self.model_selection.to_langchain_model(model_config)
            except Exception:
                logger.warning(
                    "model_selection.to_langchain_model() failed for %s, "
                    "falling back to ChatDeepSeek",
                    model_name,
                )

        # Fallback for when no model_selection or when it fails
        from langchain_deepseek import ChatDeepSeek

        return ChatDeepSeek(model=model_name, temperature=0.0)  # type: ignore[call-arg]

    def _build_middleware_pipeline(
        self,
        backend: CompositeBackend,  # noqa: ARG002
        subagent_defs: list[dict[str, Any]],  # noqa: ARG002
        memory_sources: list[str],  # noqa: ARG002
        summarization_model: BaseChatModel,  # noqa: ARG002
    ) -> list[Any]:
        """Build the middleware pipeline from config or defaults.

        Maps middleware names to instances. Uses ``middleware_order``
        from config if specified, otherwise ``DEFAULT_MIDDLEWARE_ORDER``.
        """
        assert self.config is not None
        order = self.config.middleware_order or DEFAULT_MIDDLEWARE_ORDER

        # Middleware name → factory function.
        #
        # IMPORTANT: create_deep_agent auto-creates these middleware:
        #   TodoListMiddleware, FilesystemMiddleware, SummarizationMiddleware,
        #   PatchToolCallsMiddleware, AnthropicPromptCachingMiddleware,
        #   SkillsMiddleware (from `skills=` param),
        #   SubAgentMiddleware (from `subagents=` param),
        #   MemoryMiddleware (from `memory=` param),
        #   HumanInTheLoopMiddleware (from `interrupt_on=` param).
        #
        # Only middleware NOT auto-created should be included here.
        # Duplicate middleware names cause "Please remove duplicate middleware
        # instances." from create_agent.
        factories: dict[str, Any] = {
            # ── Auto-created by create_deep_agent → skip ──
            "TodoListMiddleware": lambda: None,
            "MemoryMiddleware": lambda: None,
            "HumanInTheLoopMiddleware": lambda: None,
            "FilesystemMiddleware": lambda: None,
            "SubAgentMiddleware": lambda: None,
            "SummarizationMiddleware": lambda: None,
            # ── User-added middleware (NOT auto-created) ──
            "PIIMiddleware": (
                lambda: PIIMiddleware(pii_type="email")
                if _LANGCHAIN_MIDDLEWARE_AVAILABLE else None
            ),
            "ShellToolMiddleware": (
                lambda: ShellToolMiddleware()
                if _LANGCHAIN_MIDDLEWARE_AVAILABLE else None
            ),
            "ContextEditingMiddleware": (
                lambda: ContextEditingMiddleware()
                if _LANGCHAIN_MIDDLEWARE_AVAILABLE else None
            ),
            "ModelFallbackMiddleware": (
                lambda: ModelFallbackMiddleware(
                    "deepseek-v4-pro", "deepseek-v4-flash"
                )
                if _LANGCHAIN_MIDDLEWARE_AVAILABLE else None
            ),
            "ToolRetryMiddleware": (
                lambda: ToolRetryMiddleware()
                if _LANGCHAIN_MIDDLEWARE_AVAILABLE else None
            ),
            # Placeholders for middleware not yet fully implemented
            "ToolCallLimitMiddleware": lambda: None,
            "ModelCallLimitMiddleware": lambda: None,
            "LLMToolSelectorMiddleware": lambda: None,
            "LLMToolEmulator": lambda: None,
            "FilesystemFileSearchMiddleware": lambda: None,
        }

        pipeline: list[Any] = []
        for mw_name in order:
            factory = factories.get(mw_name)
            if factory is None:
                logger.warning(
                    "Unknown middleware '%s', skipping", mw_name
                )
                continue
            instance = factory()
            if instance is not None:
                pipeline.append(instance)

        return pipeline

    def _build_system_prompt(self) -> str:
        """Build system prompt from config override or default.

        Dynamically includes available skills from
        ``.harness/skills/`` when no custom prompt is configured.
        """
        assert self.config is not None

        custom_prompt = self.config_loader.load_system_prompt(
            self.config, self.project_root
        )
        if custom_prompt:
            return custom_prompt

        return self._build_default_system_prompt()

    def _build_default_system_prompt(self) -> str:
        """Build a default system prompt that includes harness components.

        Lists available skills with name + description so the LLM
        knows what procedural workflows are available and can invoke
        them when the task matches.
        """
        parts: list[str] = [
            "You are a helpful AI assistant.",
            "",
            "## Core Responsibilities",
            "- Understand user requests and execute them accurately",
            "- Use available tools to accomplish tasks",
            "- Delegate complex tasks to subagents when appropriate",
            "- Apply relevant skills when the task matches their description",
            "",
            "## Workflow",
            "1. Analyze the user's request",
            "2. Check if any available skill below matches the task",
            "3. If a skill matches, follow its instructions precisely",
            "4. Plan the approach using write_todos if needed",
            "5. Execute using tools or delegate to subagents",
            "6. Synthesize results and respond clearly",
        ]

        # ── Available Skills ──────────────────────────────────────
        skill_list = self.skill_loader.list_skills()
        if skill_list:
            parts.append("")
            parts.append("## Available Skills")
            parts.append(
                "When a user request matches a skill's description, "
                "follow that skill's instructions exactly. Skills "
                "provide step-by-step workflows for specific tasks."
            )
            parts.append("")
            for sk in skill_list:
                name = sk.name or sk.path
                desc = sk.description or "No description"
                parts.append(f"- **{name}**: {desc}")

        # ── Available Subagents ────────────────────────────────────
        subagent_list = self.subagent_loader.list_subagents()
        if subagent_list:
            parts.append("")
            parts.append("## Available Subagents")
            parts.append(
                "Use the `task` tool with `subagent_type` set to one "
                "of the names below to delegate work. Each subagent "
                "runs in an isolated context with its own tools."
            )
            parts.append("")
            for sa in subagent_list:
                name = sa.name or "unnamed"
                desc = sa.description or "No description"
                parts.append(f"- **{name}**: {desc}")

        # ── Quality Standards ─────────────────────────────────────
        parts.extend([
            "",
            "## Quality Standards",
            "- Be thorough and accurate",
            "- Cite sources when providing factual information",
            "- Ask clarifying questions when requirements are unclear",
            "",
            "## Memory",
            "You have access to persistent memory. Save important "
            "preferences and learnings for future sessions.",
        ])

        return "\n".join(parts)
