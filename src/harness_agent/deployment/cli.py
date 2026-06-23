"""CLI agent deployment mode (Step 6.2).

Provides an interactive command-line agent for development and internal use.
Supports shell commands, MCP server integration, and memory persistence.
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from harness_agent.config import AgentModelSelection
from harness_agent.core.agent import DEFAULT_MAX_TOOL_ITERATIONS, HarnessAgent
from harness_agent.deployment.cli_commands import (
    CommandContext,
    dispatch_command,
    print_context_bar,
    print_memory,
    print_welcome,
)
from harness_agent.deployment.cli_metrics_bridge import (
    MetricsBridge,
    connect_metrics_aggregator,
)
from harness_agent.deployment.cli_streaming import (
    TurnContext,
    stream_turn_agent,
    stream_turn_graph,
)
from harness_agent.deployment.cli_terminal import Color, draw_chat_input
from harness_agent.loaders.config_loader import HarnessConfig
from harness_agent.loaders.harness_builder import HarnessBuilder
from harness_agent.loaders.hook_loader import EventBus, HookEvent
from harness_agent.memory.hybrid_memory import HybridMemory
from harness_agent.monitoring.metrics import AgentMetrics
from harness_agent.prompts import load_prompt
from harness_agent.security.sandbox import SandboxConfig
from harness_agent.tools.registry import ToolRegistry

# ===========================================================================
# CLI Agent configuration
# ===========================================================================


@dataclass
class CLIAgentConfig:
    """Configuration for the CLI agent deployment.

    Attributes:
        assistant_id: Unique identifier for this agent instance.
        system_prompt: System prompt injected into every conversation.
        shell_allow_list: Whitelist of allowed shell commands.
        enable_memory: Toggle cross-session memory persistence.
        enable_skills: Toggle skill system integration.
        sandbox_type: Sandbox environment type (docker, local, none).
        cwd: Working directory for shell commands.
        mcp_servers: MCP server configurations keyed by name.
        model_selection: Agent model selection (default: default AgentModelSelection).
        max_tool_iterations: Max tool-calling loop iterations per turn.
    """

    assistant_id: str = "harness-agent-cli"
    session_name: str = ""
    system_prompt: str = ""
    shell_allow_list: list[str] = field(default_factory=lambda: [
        "ls", "cat", "grep", "find",
        "python", "pip", "uv", "git",
        "pytest", "ruff", "mypy",
    ])
    enable_memory: bool = True
    enable_skills: bool = True
    monitoring_port: int = 2025
    sandbox_type: str = "docker"
    cwd: str = field(default_factory=os.getcwd)
    project_root: str = field(default_factory=os.getcwd)
    mcp_servers: dict[str, dict[str, Any]] = field(default_factory=dict)
    model_selection: AgentModelSelection = field(
        default_factory=AgentModelSelection
    )
    max_tool_iterations: int = DEFAULT_MAX_TOOL_ITERATIONS


# ===========================================================================
# CLI Agent class
# ===========================================================================


class CLIAgent:
    """Interactive CLI agent for development and internal use.

    Example:
        config = CLIAgentConfig()
        agent = CLIAgent(config)
        await agent.run_interactive()
    """

    def __init__(self, config: CLIAgentConfig | None = None) -> None:
        self.config = config or CLIAgentConfig()

        # Harness state (populated by _load_harness_if_present)
        self._harness_config: HarnessConfig | None = None
        self._harness_skill_sources: list[str] = []
        self._harness_rule_sources: list[str] = []
        self._harness_subagent_defs: list[dict[str, Any]] = []
        self._harness_builder: Any = None
        self._event_bus = EventBus()
        self._load_harness_if_present()

        # Initialize components
        self._llm = self._init_llm()
        self._sandbox = self._init_sandbox()
        self._graph: Any = None
        self._agent = self._init_agent()
        self._memory = HybridMemory()
        self._metrics = AgentMetrics()
        self._start_time = time.monotonic()
        self._session_id = ""
        self._bridge: MetricsBridge | None = None
        self._metrics_server: Any = None
        self._connect_metrics()
        self._init_debug_mode()

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def _init_sandbox(self) -> SandboxConfig | None:
        if self.config.sandbox_type == "docker":
            return SandboxConfig(
                sandbox_type="docker",
                shell_allow_list=self.config.shell_allow_list,
                auto_approve=False,
                interrupt_shell_only=True,
            )
        if self.config.sandbox_type == "none":
            return SandboxConfig.demo()
        return None

    @staticmethod
    def _init_debug_mode() -> None:
        from harness_agent.monitoring.debug import configure_debug_mode
        configure_debug_mode()

    def _load_harness_if_present(self) -> None:
        """Detect and load .harness/ configuration."""
        project_root = Path(self.config.project_root)
        harness_dir = project_root / ".harness"
        if not harness_dir.is_dir():
            return

        from harness_agent.tools.basic_tools import BASIC_TOOLS

        tool_registry = ToolRegistry()
        for t in BASIC_TOOLS:
            tool_registry.register(t)

        builder = HarnessBuilder(
            project_root,
            tool_registry=tool_registry,
            model_selection=self.config.model_selection,
        )
        self._harness_builder = builder

        try:
            self._harness_config = builder.load_config()
        except Exception as e:
            print(f"\n  {Color.warn(f'⚠ .harness/config.yaml error: {e}')}")
            return

        harness_cfg = self._harness_config
        if harness_cfg is None:
            return
        errors = harness_cfg.validate()
        if errors:
            print(f"\n  {Color.warn('⚠ .harness/config.yaml has issues:')}")
            for e in errors:
                print(f"    {Color.dim(f'- {e}')}")

        self._event_bus = builder.event_bus
        self._harness_skill_sources = builder.skill_loader.get_memory_sources()
        self._harness_rule_sources = builder.rule_loader.get_memory_sources()

        try:
            self._harness_subagent_defs, subagent_errors = (
                builder.subagent_loader.load_all_graceful()
            )
            for err in subagent_errors:
                print(f"  {Color.warn(f'⚠ Subagent: {err}')}")
        except Exception as e:
            print(f"  {Color.warn(f'⚠ Subagent loading failed: {e}')}")

    def _init_llm(self) -> BaseChatModel:
        from typing import cast

        model_config = self.config.model_selection.orchestrator

        if self._harness_config and self._harness_config.model:
            from harness_agent.config import ModelConfig
            model_config = ModelConfig(
                model_id=self._harness_config.model,
                provider="deepseek",
                temperature=0.0,
                purpose="Orchestrator (from .harness/config.yaml)",
            )

        return cast(
            BaseChatModel,
            self.config.model_selection.to_langchain_model(model_config),
        )

    def _init_agent(self) -> HarnessAgent:
        """Initialize agent — uses HarnessBuilder.build() when .harness/ present.

        Three-tier graceful degradation:
        - Tier 1: Graph path (deepagents installed, full features)
        - Tier 2: Enhanced agent (.harness/ loaded, skills/subagents in prompt)
        - Tier 3: Basic agent (no .harness/, plain HarnessAgent)
        """
        from harness_agent.tools.basic_tools import BASIC_TOOLS

        # Tier 1: Try graph path via deepagents
        if self._harness_builder is not None:
            try:
                self._graph = self._harness_builder.build(model=self._llm)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(
                    "HarnessBuilder.build() failed (deepagents missing or "
                    "config error): %s — falling back to enhanced agent", e
                )
                self._graph = None

        # Tier 2: Enhanced agent with skills/subagents injected
        if self._harness_builder is not None and self._graph is None:
            system_prompt = self._build_harness_system_prompt()
            rule_content = self._load_rule_content()
            if rule_content:
                system_prompt += "\n\n" + rule_content
            skill_summary = self._load_skill_summary()
            if skill_summary:
                system_prompt += "\n\n" + skill_summary

            tools: list[Any] = list(BASIC_TOOLS)
            if self._harness_subagent_defs:
                from harness_agent.tools.task_tool import create_task_tool
                task_tool = create_task_tool(
                    self._harness_subagent_defs, self._llm
                )
                tools.append(task_tool)

            return HarnessAgent(
                llm=self._llm,
                tools=tools,
                system_prompt=system_prompt,
                max_tool_iterations=self.config.max_tool_iterations,
            )

        # Tier 1 success: graph exists, create basic agent as programmatic fallback
        if self._graph is not None and self._harness_builder is not None:
            return HarnessAgent(
                llm=self._llm,
                tools=BASIC_TOOLS,
                system_prompt=self._harness_builder.get_system_prompt(),
                max_tool_iterations=self.config.max_tool_iterations,
            )

        # Tier 3: Basic agent (no .harness/)
        system_prompt = self.config.system_prompt
        if not system_prompt:
            system_prompt = load_prompt("main_agent")

        return HarnessAgent(
            llm=self._llm,
            tools=BASIC_TOOLS,
            system_prompt=system_prompt,
            max_tool_iterations=self.config.max_tool_iterations,
        )

    def _connect_metrics(self) -> None:
        """Connect to metrics aggregator."""
        harness_info = self._build_harness_info()
        bridge, session_id, server = connect_metrics_aggregator(
            port=self.config.monitoring_port,
            session_name=self.config.session_name,
            assistant_id=self.config.assistant_id,
            metrics=self._metrics,
            memory=self._memory,
            start_time=self._start_time,
            harness_info=harness_info,
        )
        self._bridge = bridge
        self._session_id = session_id
        self._metrics_server = server

    # ------------------------------------------------------------------
    # Harness info / system prompt helpers
    # ------------------------------------------------------------------

    def _build_harness_info(self) -> dict[str, Any]:
        """Build harness info dict for the UI."""
        info: dict[str, Any] = {
            "skills": [],
            "rules": [],
            "hooks": [],
            "subagents": [],
        }

        for src in self._harness_skill_sources:
            stem = Path(src).stem
            desc = ""
            if self._harness_builder is not None:
                for sk in self._harness_builder.skill_loader.list_skills():
                    if sk.path == src or sk.name == stem:
                        desc = sk.description or ""
                        break
            info["skills"].append({"name": stem, "description": desc})

        for src in self._harness_rule_sources:
            stem = Path(src).stem
            info["rules"].append({"name": stem, "path": src})

        if self._event_bus is not None:
            listeners = getattr(self._event_bus, "_listeners", {})
            for event, handlers in listeners.items():
                if handlers:
                    info["hooks"].append({"event": str(event.value)})

        for sa in self._harness_subagent_defs:
            info["subagents"].append({
                "name": sa.get("name", "unnamed"),
                "description": sa.get("description", ""),
            })

        return info

    def _load_skill_summary(self) -> str:
        """Load skill names + descriptions for system prompt injection."""
        if not self._harness_builder:
            return ""
        skills = self._harness_builder.skill_loader.list_skills()
        if not skills:
            return ""
        parts = [
            "## Available Skills",
            "When a task matches a skill's description, apply its workflow.",
            "",
        ]
        for sk in skills:
            parts.append(f"- **{sk.name}**: {sk.description}")
        return "\n".join(parts)

    def _load_rule_content(self) -> str:
        """Load rule markdown content for direct system prompt injection."""
        if not self._harness_builder:
            return ""
        sources = self._harness_rule_sources
        if not sources:
            return ""
        parts = ["## Rules (Always Active)", ""]
        for src in sources:
            try:
                content = Path(src).read_text(encoding="utf-8")
                parts.append(content.strip())
                parts.append("")
            except (OSError, UnicodeDecodeError):
                continue
        return "\n".join(parts) if len(parts) > 2 else ""

    def _build_harness_system_prompt(self) -> str:
        """Build a complete system prompt from .harness/ configuration."""
        parts: list[str] = [
            "You are a Harness Agent — an AI-powered software engineering "
            "assistant.",
            "",
            "## Core Responsibilities",
            "- Analyze user requests and plan multi-step tasks",
            "- Execute shell commands, read/write files, and search code",
            "- Synthesize results into clear, actionable responses",
            "- Learn from user feedback and save preferences",
            "",
            "## Available Tools",
            "- **read_file**, **write_file**, **edit_file** — File operations",
            "- **glob**, **grep** — Search files by pattern or content",
            "- **execute_command** — Run shell commands (tests, lint, git, etc.)",
        ]

        if self._harness_rule_sources:
            parts.append("")
            parts.append("## Rules (Always Active)")
            parts.append(
                "The following rules are **always loaded** into context "
                "for every session and every turn."
            )
            parts.append("")
            for rp in self._harness_rule_sources:
                rule_name = Path(rp).stem.replace("-", " ").title()
                parts.append(f"- **{rule_name}**")

        if self._harness_subagent_defs:
            parts.append("")
            parts.append("## Available Subagents")
            parts.append(
                "These subagents are **pre-configured** in "
                "``.harness/subagents/``. You can delegate tasks "
                "to them when appropriate."
            )
            parts.append("")
            for sub in self._harness_subagent_defs:
                name = sub["name"]
                desc = sub.get("description", "No description")
                model = sub.get("model", "?")
                tools = [t.name for t in sub.get("tools", [])]
                parts.append(
                    f"- **{name}** ({model}): {desc}\n"
                    f"  Tools: {', '.join(tools) if tools else 'none'}"
                )
        else:
            parts.append(
                "\n**No subagents are configured.** "
                "Handle all tasks directly with your available tools."
            )

        parts.extend([
            "",
            "## Workflow",
            "1. **Analyze** the user's request",
            "2. **Plan** multi-step tasks",
            "3. **Execute** using available tools",
            "4. **Synthesize** results into a clear response",
            "5. **Learn** — save user preferences to memory",
            "",
            "## Constraints",
            "- Never expose API keys, passwords, or secrets",
            "- Never hardcode secrets in source code",
            "- Never execute dangerous shell commands without user approval",
        ])

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Context builders
    # ------------------------------------------------------------------

    def _make_turn_context(self, thread_id: str) -> TurnContext:
        """Build a TurnContext for the current turn."""
        return TurnContext(
            thread_id=thread_id,
            bridge=self._bridge,
            metrics=self._metrics,
            event_bus=self._event_bus,
            llm=self._llm,
            harness_rule_sources=self._harness_rule_sources,
        )

    def _make_command_context(self) -> CommandContext:
        """Build a CommandContext for slash command dispatch."""
        return CommandContext(
            assistant_id=self.config.assistant_id,
            enable_memory=self.config.enable_memory,
            sandbox_type=self.config.sandbox_type,
            project_root=self.config.project_root,
            tools=self._agent._tools,
            llm=self._llm,
            memory=self._memory,
            metrics_server=self._metrics_server,
            harness_config=self._harness_config,
            harness_builder=self._harness_builder,
            harness_skill_sources=self._harness_skill_sources,
            harness_rule_sources=self._harness_rule_sources,
            harness_subagent_defs=self._harness_subagent_defs,
            event_bus=self._event_bus,
        )

    # ------------------------------------------------------------------
    # Streaming dispatch
    # ------------------------------------------------------------------

    async def _stream_turn(
        self, messages: list[BaseMessage], config: RunnableConfig
    ) -> tuple[str | None, list[BaseMessage]]:
        """Stream a single agent turn — dispatches to graph or agent path."""
        thread_id = config.get("configurable", {}).get("thread_id", "default")
        ctx = self._make_turn_context(thread_id)

        if self._graph is not None:
            return await stream_turn_graph(self._graph, messages, config, ctx)
        return await stream_turn_agent(
            self._agent, messages, config, ctx, self.config.max_tool_iterations
        )

    # ------------------------------------------------------------------
    # Interactive loop
    # ------------------------------------------------------------------

    async def run_interactive(self) -> None:
        """Run the interactive CLI loop with streaming and tool visibility."""
        thread_id = f"{self.config.assistant_id}-session"
        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}

        conversation_key = f"conversation:{thread_id}"
        saved = self._memory.get(conversation_key)
        history: list = saved if saved else []

        cmd_ctx = self._make_command_context()
        print_welcome(cmd_ctx, history)
        print_context_bar(cmd_ctx, history)

        # Fire session_start hooks
        self._event_bus.fire(
            HookEvent.SESSION_START,
            {
                "session_id": thread_id,
                "project_root": str(Path(self.config.project_root).resolve()),
                "config": {"model": getattr(self._llm, "model_name", "?")},
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
        )

        if self._bridge:
            if self._harness_rule_sources:
                self._bridge.activity(
                    "rule_applied",
                    name=f"{len(self._harness_rule_sources)} rules active",
                )
            if self._harness_skill_sources:
                self._bridge.activity(
                    "skill_used",
                    name=f"{len(self._harness_skill_sources)} skills available",
                )

        success = True
        try:
            while True:
                try:
                    user_input = draw_chat_input()
                except (EOFError, KeyboardInterrupt):
                    print("\nGoodbye!")
                    break

                if not user_input.strip():
                    continue

                # Slash commands
                if user_input.startswith("/"):
                    handled = await dispatch_command(
                        user_input, history, conversation_key, cmd_ctx
                    )
                    if handled == "exit":
                        break
                    saved = self._memory.get(conversation_key)
                    history = saved if saved else []
                    continue

                # Plain-text commands
                if user_input.lower() in ("exit", "quit"):
                    print("Goodbye!")
                    break
                if user_input.lower() == "help":
                    await dispatch_command("/help", history, conversation_key, cmd_ctx)
                    continue
                if user_input.lower() == "clear":
                    history = []
                    self._memory.delete(conversation_key)
                    print("Conversation cleared.")
                    continue
                if user_input.lower() == "memory":
                    print_memory(self._memory)
                    continue

                # Build messages and stream turn
                messages: list[BaseMessage] = [*history, HumanMessage(content=user_input)]

                if self._bridge:
                    self._bridge.activity(
                        "user_msg", content=user_input[:200], thread=thread_id
                    )

                self._metrics.record_task_start()
                turn_start = time.perf_counter()

                text_response, updated_msgs = await self._stream_turn(messages, config)

                turn_elapsed_ms = (time.perf_counter() - turn_start) * 1000
                self._metrics.record_task_complete(turn_elapsed_ms)

                if self._bridge:
                    self._bridge.activity(
                        "turn_end",
                        latency_ms=round(turn_elapsed_ms, 1),
                        thread=thread_id,
                    )
                    self._bridge.session(thread_id, turns=1)

                if text_response is None and updated_msgs:
                    for msg in reversed(updated_msgs):
                        if isinstance(msg, AIMessage):
                            text_response = str(msg.content) if msg.content else ""
                            break

                history.append(HumanMessage(content=user_input))
                if text_response is not None:
                    history.append(AIMessage(content=text_response))

                if self.config.enable_memory:
                    self._memory.store(conversation_key, history)
                    turn_key = f"turn:{thread_id}:{len(history)}"
                    self._memory.store(
                        turn_key,
                        {
                            "user": user_input,
                            "assistant": text_response or "(tool only)",
                        },
                    )

                if self._bridge:
                    self._bridge.push_metrics(self._metrics.to_dict())

        finally:
            self._event_bus.fire(
                HookEvent.SESSION_END,
                {
                    "session_id": thread_id,
                    "total_tokens": self._metrics.total_tokens,
                    "tool_calls_count": self._metrics.tool_calls,
                    "duration_ms": int(
                        (time.monotonic() - self._start_time) * 1000
                    ),
                    "success": success,
                },
            )

    # ------------------------------------------------------------------
    # Programmatic invocation (for tests)
    # ------------------------------------------------------------------

    def invoke_sync(self, user_input: str, thread_id: str = "default") -> str:
        """Synchronous single-turn invocation for testing."""
        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
        result = self._agent.invoke(
            {"messages": [{"role": "user", "content": user_input}]},
            config=config,
        )
        messages = result.get("messages", [])
        return messages[-1].content if messages else ""

    async def invoke(self, user_input: str, thread_id: str = "default") -> str:
        """Asynchronous single-turn invocation."""
        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
        result = await self._agent.ainvoke(
            {"messages": [{"role": "user", "content": user_input}]},
            config=config,
        )
        messages = result.get("messages", [])
        return messages[-1].content if messages else ""


# ===========================================================================
# Factory and entry point
# ===========================================================================


def create_cli_agent(
    config: CLIAgentConfig | None = None,
) -> CLIAgent:
    """Factory function to create a configured CLI agent."""
    return CLIAgent(config=config)


def main() -> None:
    """Entry point for the CLI agent."""
    from pathlib import Path

    env_paths = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parent.parent.parent.parent / ".env",
    ]
    for env_path in env_paths:
        if env_path.exists():
            from dotenv import load_dotenv
            load_dotenv(env_path)
            break

    config = CLIAgentConfig()
    agent = create_cli_agent(config)
    asyncio.run(agent.run_interactive())


if __name__ == "__main__":
    main()
