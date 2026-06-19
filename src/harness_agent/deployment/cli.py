"""CLI agent deployment mode (Step 6.2).

Provides an interactive command-line agent for development and internal use.
Supports shell commands, MCP server integration, and memory persistence.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import RunnableConfig

from harness_agent.config import AgentModelSelection
from harness_agent.core.agent import HarnessAgent
from harness_agent.security.sandbox import SandboxConfig


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
    """

    assistant_id: str = "harness-agent-cli"
    system_prompt: str = (
        "You are a helpful coding assistant for the Harness Agent project."
    )
    shell_allow_list: list[str] = field(default_factory=lambda: [
        "ls", "cat", "grep", "find",
        "python", "pip", "uv", "git",
        "pytest", "ruff", "mypy",
    ])
    enable_memory: bool = True
    enable_skills: bool = True
    sandbox_type: str = "docker"
    cwd: str = field(default_factory=os.getcwd)
    mcp_servers: dict[str, dict[str, Any]] = field(default_factory=dict)
    model_selection: AgentModelSelection = field(
        default_factory=AgentModelSelection
    )


class CLIAgent:
    """Interactive CLI agent for development and internal use.

    Example:
        config = CLIAgentConfig()
        agent = CLIAgent(config)
        await agent.run_interactive()
    """

    def __init__(self, config: CLIAgentConfig | None = None) -> None:
        self.config = config or CLIAgentConfig()
        self._llm = self._init_llm()
        self._sandbox = self._init_sandbox()
        self._agent = self._init_agent()
        self._init_debug_mode()

    def _init_llm(self) -> BaseChatModel:
        """Initialize the language model from config."""
        from typing import cast

        model_config = self.config.model_selection.orchestrator
        return cast(
            BaseChatModel,
            self.config.model_selection.to_langchain_model(model_config),
        )

    def _init_sandbox(self) -> SandboxConfig | None:
        """Initialize the sandbox if configured."""
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
        """Configure debug logging based on DEEPAGENTS_DEBUG env var."""
        from harness_agent.monitoring.debug import configure_debug_mode
        configure_debug_mode()

    def _init_agent(self) -> HarnessAgent:
        """Initialize the LangChain agent."""
        return HarnessAgent(
            llm=self._llm,
            tools=[],
            system_prompt=self.config.system_prompt,
        )

    async def run_interactive(self) -> None:
        """Run the interactive CLI loop."""
        config: RunnableConfig = {
            "configurable": {"thread_id": f"{self.config.assistant_id}-session"}
        }
        print(f"Harness Agent CLI — '{self.config.assistant_id}'")
        print("Type 'exit' to quit, 'help' for commands")
        print(f"Sandbox: {self.config.sandbox_type}")
        print(f"Shell allow list: {', '.join(self.config.shell_allow_list)}")
        print(f"Memory: {'enabled' if self.config.enable_memory else 'disabled'}")
        print(f"Skills: {'enabled' if self.config.enable_skills else 'disabled'}")
        print("-" * 50)

        while True:
            try:
                user_input = input("\n> ")
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye!")
                break

            if user_input.lower() in ("exit", "quit"):
                print("Goodbye!")
                break
            if not user_input.strip():
                continue
            if user_input.lower() == "help":
                self._print_help()
                continue

            result = await self._agent.ainvoke(
                {"messages": [{"role": "user", "content": user_input}]},
                config=config,
            )
            messages = result.get("messages", [])
            if messages:
                print(messages[-1].content)

    @staticmethod
    def _print_help() -> None:
        """Print help message."""
        print("Commands:")
        print("  help  - Show this message")
        print("  exit  - Exit the CLI")
        print("  quit  - Exit the CLI")

    def invoke_sync(self, user_input: str, thread_id: str = "default") -> str:
        """Synchronous single-turn invocation for testing.

        Args:
            user_input: The user message to send.
            thread_id: Session thread identifier.

        Returns:
            The agent's response text.
        """
        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
        result = self._agent.invoke(
            {"messages": [{"role": "user", "content": user_input}]},
            config=config,
        )
        messages = result.get("messages", [])
        return messages[-1].content if messages else ""

    async def invoke(self, user_input: str, thread_id: str = "default") -> str:
        """Asynchronous single-turn invocation.

        Args:
            user_input: The user message to send.
            thread_id: Session thread identifier.

        Returns:
            The agent's response text.
        """
        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
        result = await self._agent.ainvoke(
            {"messages": [{"role": "user", "content": user_input}]},
            config=config,
        )
        messages = result.get("messages", [])
        return messages[-1].content if messages else ""


def create_cli_agent(
    config: CLIAgentConfig | None = None,
) -> CLIAgent:
    """Factory function to create a configured CLI agent.

    Args:
        config: CLI agent configuration. Uses defaults when None.

    Returns:
        A ready-to-use CLIAgent instance.
    """
    return CLIAgent(config=config)


def main() -> None:
    """Entry point for the CLI agent."""
    config = CLIAgentConfig()
    agent = create_cli_agent(config)
    asyncio.run(agent.run_interactive())


if __name__ == "__main__":
    main()
