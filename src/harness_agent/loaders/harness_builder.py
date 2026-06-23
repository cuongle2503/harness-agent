"""Harness Builder — kết nối tất cả loaders thành agent từ .harness/.

Plan: docs/guides/plans-phase-2/06-harness-builder.md
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from deepagents import create_deep_agent
from deepagents.backends import (
    CompositeBackend,
    FilesystemBackend,
    StateBackend,
    StoreBackend,
)
from deepagents.middleware.filesystem import FilesystemMiddleware
from deepagents.middleware.memory import MemoryMiddleware
from deepagents.middleware.subagents import SubAgentMiddleware
from deepagents.middleware.summarization import SummarizationMiddleware
from langchain.agents.middleware import (
    ContextEditingMiddleware,
    HumanInTheLoopMiddleware,
    ModelFallbackMiddleware,
    PIIMiddleware,
    ShellToolMiddleware,
    TodoListMiddleware,
    ToolRetryMiddleware,
)
from langchain_core.language_models import BaseChatModel
from langgraph.graph.state import CompiledStateGraph

from harness_agent.config import AgentModelSelection
from harness_agent.loaders.config_loader import ConfigLoader, HarnessConfig
from harness_agent.loaders.hook_loader import EventBus, HookLoader
from harness_agent.loaders.rule_loader import RuleLoader
from harness_agent.loaders.skill_loader import SkillLoader
from harness_agent.loaders.subagent_loader import SubAgentLoader
from harness_agent.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

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
        self.agent: CompiledStateGraph | None = None

    # ── Public API ──────────────────────────────────────────────────────

    def build(self) -> CompiledStateGraph:
        """Build the agent from ``.harness/`` configuration.

        Returns:
            A CompiledStateGraph ready for invoke/stream.

        Raises:
            HarnessBuildError: If the config is invalid.
        """
        logger.info("Building harness from: %s", self.harness_dir)

        # Step 1: Load & validate config
        self.config = self._load_and_validate_config()

        # Step 2: Load hooks (before other steps so hooks can intercept)
        self.hook_loader.load_all()

        # Step 3: Build backend from config
        backend = self._build_backend()

        # Step 4: Load subagents from .harness/subagents/
        subagent_defs = self.subagent_loader.load_all()

        # Step 5: Collect memory sources from skills + rules
        memory_sources = self._collect_memory_sources()
        skill_sources = self.skill_loader.get_memory_sources()

        # Step 6: Resolve models
        main_model = self._resolve_model(self.config.model)
        summarization_model = self._resolve_model(
            self.config.summarization_model
        )

        # Step 7: Build middleware pipeline
        middleware = self._build_middleware_pipeline(
            backend=backend,
            subagent_defs=subagent_defs,
            memory_sources=memory_sources,
            summarization_model=summarization_model,
        )

        # Step 8: Build system prompt
        system_prompt = self._build_system_prompt()

        # Step 9: Create agent
        self.agent = create_deep_agent(
            model=main_model,
            middleware=middleware,
            backend=backend,
            system_prompt=system_prompt,
            subagents=subagent_defs if subagent_defs else None,
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
                f"Invalid .harness/config.yaml:\n"
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
            return FilesystemBackend(root_dir=output_dir, virtual_mode=True)
        else:  # state (default)
            return StateBackend()

    def _collect_memory_sources(self) -> list[str]:
        """Collect all memory sources from skills + rules."""
        sources: list[str] = []
        sources.extend(self.skill_loader.get_memory_sources())
        sources.extend(self.rule_loader.get_memory_sources())
        return sources

    def _resolve_model(self, model_name: str) -> BaseChatModel:
        """Resolve a model name to a BaseChatModel instance."""
        from langchain_deepseek import ChatDeepSeek

        return ChatDeepSeek(model=model_name, temperature=0.0)  # type: ignore[call-arg]

    def _build_middleware_pipeline(
        self,
        backend: CompositeBackend,
        subagent_defs: list[dict[str, Any]],
        memory_sources: list[str],
        summarization_model: BaseChatModel,
    ) -> list[Any]:
        """Build the middleware pipeline from config or defaults.

        Maps middleware names to instances. Uses ``middleware_order``
        from config if specified, otherwise ``DEFAULT_MIDDLEWARE_ORDER``.
        """
        assert self.config is not None
        order = self.config.middleware_order or DEFAULT_MIDDLEWARE_ORDER

        # Middleware name → factory function
        factories: dict[str, Any] = {
            "TodoListMiddleware": lambda: TodoListMiddleware(),
            "MemoryMiddleware": lambda: MemoryMiddleware(
                backend=backend,
                sources=memory_sources,
            ),
            "HumanInTheLoopMiddleware": lambda: HumanInTheLoopMiddleware(
                interrupt_on={},
            ),
            "PIIMiddleware": lambda: PIIMiddleware(pii_type="email"),
            "FilesystemMiddleware": lambda: FilesystemMiddleware(
                backend=backend
            ),
            "SubAgentMiddleware": lambda: (
                SubAgentMiddleware(
                    backend=backend,
                    subagents=subagent_defs,
                )
                if subagent_defs
                else None
            ),
            "ShellToolMiddleware": lambda: ShellToolMiddleware(),
            "SummarizationMiddleware": lambda: SummarizationMiddleware(
                model=summarization_model,
                backend=backend,
                trigger=("tokens", 120_000),
                keep=("messages", 20),
            ),
            "ContextEditingMiddleware": lambda: ContextEditingMiddleware(),
            "ModelFallbackMiddleware": lambda: ModelFallbackMiddleware(
                "deepseek-v4-pro",
                "deepseek-v4-flash",
            ),
            "ToolRetryMiddleware": lambda: ToolRetryMiddleware(),
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
        """Build system prompt from config override or default."""
        assert self.config is not None

        custom_prompt = self.config_loader.load_system_prompt(
            self.config, self.project_root
        )
        if custom_prompt:
            return custom_prompt

        return self._default_system_prompt()

    @staticmethod
    def _default_system_prompt() -> str:
        """Default system prompt when no custom one is configured."""
        return """You are a helpful AI assistant.

## Core Responsibilities
- Understand user requests and execute them accurately
- Use available tools to accomplish tasks
- Delegate complex tasks to subagents when appropriate

## Workflow
1. Analyze the user's request
2. Plan the approach using write_todos if needed
3. Execute using tools or delegate to subagents
4. Synthesize results and respond clearly

## Quality Standards
- Be thorough and accurate
- Cite sources when providing factual information
- Ask clarifying questions when requirements are unclear

## Memory
You have access to persistent memory. Save important preferences
and learnings for future sessions.
"""
