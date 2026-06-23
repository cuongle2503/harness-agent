"""Slash command handlers and display helpers for the CLI agent.

Provides dispatch_command(), print_welcome(), print_context_bar(), and
all /command implementations. These are pure functions that receive a
CommandContext rather than accessing CLIAgent internals directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from harness_agent.deployment.cli_terminal import (
    BOX_BOT,
    BOX_BOT_R,
    BOX_H,
    BOX_TOP,
    BOX_TOP_R,
    BOX_V,
    Color,
    box_width,
    wcwidth,
)


@dataclass
class CommandContext:
    """Read-only view of agent state for slash commands and display."""

    assistant_id: str
    enable_memory: bool
    sandbox_type: str
    project_root: str
    tools: list[Any]
    llm: Any
    memory: Any
    metrics_server: Any
    harness_config: Any
    harness_builder: Any
    harness_skill_sources: list[str]
    harness_rule_sources: list[str]
    harness_subagent_defs: list[dict[str, Any]]
    event_bus: Any


# ---------------------------------------------------------------------------
# Command dispatch
# ---------------------------------------------------------------------------


async def dispatch_command(
    raw: str,
    history: list,
    conversation_key: str,
    ctx: CommandContext,
) -> str | None:
    """Parse and dispatch a slash command. Returns 'exit' to quit."""
    parts = raw.strip().split(maxsplit=1)
    cmd = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    handlers = {
        "/help": _cmd_help,
        "/clear": _cmd_clear,
        "/context": _cmd_context,
        "/memory": _cmd_memory,
        "/tools": _cmd_tools,
        "/harness": _cmd_harness,
        "/subagents": _cmd_subagents,
        "/exit": _cmd_exit,
        "/quit": _cmd_exit,
    }

    handler = handlers.get(cmd)
    if handler is None:
        print(f"  {Color.warn(f'Unknown command: {cmd}')}")
        print(f"  Type {Color.tool('/help')} to see available commands.")
        return None

    return handler(args, history, conversation_key, ctx)


# ---------------------------------------------------------------------------
# Command implementations
# ---------------------------------------------------------------------------


def _cmd_help(
    args: str, history: list, key: str, ctx: CommandContext
) -> str | None:
    w = box_width()
    print(f"\n  {Color.tool('Slash Commands')}")
    print(f"  {Color.dim('─' * w)}")
    commands = [
        ("/help", "Show this help message"),
        ("/clear", "Reset conversation — start a fresh session"),
        ("/context", "Show current session context and stats"),
        ("/memory", "Show memory store statistics"),
        ("/tools", "List available tools and their descriptions"),
        ("/harness", "Show loaded .harness/ configuration"),
        ("/subagents", "List subagents from .harness/subagents/"),
        ("/exit, /quit", "Exit the CLI"),
    ]
    for cmd, desc in commands:
        print(f"  {Color.tool(cmd):<20} {Color.dim(desc)}")
    print()
    print(
        f"  {Color.dim('Tip: You can still use plain commands like')} "
        f"{Color.tool('help')}{Color.dim(',')} "
        f"{Color.tool('clear')}{Color.dim(',')} "
        f"{Color.tool('exit')}"
    )
    return None


def _cmd_clear(
    args: str, history: list, key: str, ctx: CommandContext
) -> str | None:
    history.clear()
    ctx.memory.delete(key)
    thread_id = ctx.assistant_id + "-session"
    mem_ctx = ctx.memory.get_context("current")
    for item_key in mem_ctx.get("items", []):
        if item_key.startswith(f"turn:{thread_id}:"):
            ctx.memory.delete(item_key)
    print(
        f"\n  {Color.success('✓')} Session reset. "
        f"{Color.dim('Conversation history cleared. Starting fresh.')}"
    )
    return None


def _cmd_context(
    args: str, history: list, key: str, ctx: CommandContext
) -> str | None:
    w = box_width()
    print(f"\n  {Color.tool('Session Context')}")
    print(f"  {Color.dim('─' * w)}")

    print(f"  {Color.dim('Session ID:')}    {ctx.assistant_id}")
    print(
        f"  {Color.dim('Memory:')}       "
        f"{'enabled' if ctx.enable_memory else 'disabled'}"
    )

    model_name = (
        getattr(ctx.llm, "model_name", None)
        or getattr(ctx.llm, "model", None)
        or type(ctx.llm).__name__
    )
    print(f"  {Color.dim('Model:')}        {model_name}")

    user_msgs = sum(1 for m in history if isinstance(m, HumanMessage))
    ai_msgs = sum(1 for m in history if isinstance(m, AIMessage))
    tool_msgs_count = sum(1 for m in history if isinstance(m, ToolMessage))
    print(
        f"  {Color.dim('History:')}      "
        f"{len(history)} messages "
        f"({user_msgs} user, {ai_msgs} assistant, {tool_msgs_count} tool)"
    )

    total_chars = sum(
        len(str(m.content))
        for m in history
        if hasattr(m, "content") and isinstance(m.content, str)
    )
    est_tokens = total_chars // 4
    print(f"  {Color.dim('Est. tokens:')}  ~{est_tokens}")

    mem_count = len(ctx.memory)
    print(f"  {Color.dim('Memory items:')} {mem_count}")

    tool_names = [t.name for t in ctx.tools]
    print(
        f"  {Color.dim('Tools loaded:')} {len(tool_names)} — "
        f"{', '.join(tool_names[:8])}"
    )
    if len(tool_names) > 8:
        print(f"  {' ' * 15}{Color.muted(f'... and {len(tool_names) - 8} more')}")

    print(f"  {Color.dim('Sandbox:')}      {ctx.sandbox_type}")
    print()
    return None


def _cmd_memory(
    args: str, history: list, key: str, ctx: CommandContext
) -> str | None:
    print_memory(ctx.memory)
    return None


def _cmd_tools(
    args: str, history: list, key: str, ctx: CommandContext
) -> str | None:
    w = box_width()
    print(f"\n  {Color.tool('Available Tools')}")
    print(f"  {Color.dim('─' * w)}")
    for tool in ctx.tools:
        name = tool.name
        desc = (tool.description or "No description").split("\n")[0]
        if len(desc) > 100:
            desc = desc[:97] + "..."
        print(f"  {Color.tool(name):<22} {Color.dim(desc)}")
    print()
    return None


def _cmd_exit(
    args: str, history: list, key: str, ctx: CommandContext
) -> str | None:
    print("Goodbye!")
    return "exit"


def _cmd_harness(
    args: str, history: list, key: str, ctx: CommandContext
) -> str | None:
    harness_dir = Path(ctx.project_root) / ".harness"
    if not harness_dir.is_dir():
        print(f"\n  {Color.dim('No .harness/ directory found.')}\n")
        return None

    w = box_width()
    print(f"\n  {Color.tool('Harness Configuration')}")
    print(f"  {Color.dim('─' * w)}")
    print(f"  {Color.dim('Directory:')}   {harness_dir}")

    if ctx.harness_config:
        print(f"  {Color.dim('Model:')}       {ctx.harness_config.model}")
        print(
            f"  {Color.dim('Sandbox:')}     "
            f"{ctx.harness_config.features.sandbox_type}"
        )

    skills_n = len(ctx.harness_skill_sources)
    rules_n = len(ctx.harness_rule_sources)
    subs_n = len(ctx.harness_subagent_defs)
    hooks_n = ctx.event_bus.listener_count

    print(f"  {Color.dim('Skills:')}      {skills_n} loaded")
    print(f"  {Color.dim('Rules:')}       {rules_n} loaded")
    print(f"  {Color.dim('Subagents:')}   {subs_n} loaded")
    print(f"  {Color.dim('Hooks:')}       {hooks_n} registered")
    print()
    return None


def _cmd_subagents(
    args: str, history: list, key: str, ctx: CommandContext
) -> str | None:
    if not ctx.harness_subagent_defs:
        print(f"\n  {Color.dim('No subagents configured.')}")
        print(
            "  "
            + Color.dim(
                "Add .yaml files to .harness/subagents/ to define subagents."
            )
        )
        return None

    w = box_width()
    print(f"\n  {Color.tool('Subagents')}")
    print(f"  {Color.dim('─' * w)}")
    for sub in ctx.harness_subagent_defs:
        name = sub["name"]
        desc = sub.get("description", "")
        tools_n = len(sub.get("tools", []))
        model = sub.get("model", "?")
        print(
            f"  {Color.tool(name):<24} "
            f"{Color.muted(f'{tools_n} tools · {model}')}"
        )
        if desc:
            print(f"  {' ' * 2}{Color.dim(desc[:120])}")
    print()
    return None


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------


def print_welcome(ctx: CommandContext, history: list) -> None:
    """Print a framed welcome header."""
    w = box_width()
    pad = 2

    def _box_line(text: str = "", *, dim: bool = False) -> str:
        cols = wcwidth(text)
        right = w - cols - pad
        right = max(right, 0)
        style = Color.DIM if dim else ""
        return (
            f"  {BOX_V}{' ' * pad}{text}{style}{' ' * right}"
            f"{Color.RESET}{BOX_V}"
        )

    title = Color.paint("🔥  Harness Agent CLI", Color.BOLD)
    content_prefix = f"── {title} "
    content_w = wcwidth(content_prefix)
    h_fill = max(w - content_w, 0)
    print(
        f"\n  {BOX_TOP}{content_prefix}{Color.DIM}{BOX_H * h_fill}"
        f"{BOX_TOP_R}{Color.RESET}"
    )

    sid = ctx.assistant_id
    mem = "enabled" if ctx.enable_memory else "disabled"
    tools_n = len(ctx.tools)
    hist_n = len(history)
    model = (
        getattr(ctx.llm, "model_name", None)
        or getattr(ctx.llm, "model", "?")
    )

    print(_box_line(Color.paint(sid, Color.DIM)))
    print(_box_line(""))
    print(
        _box_line(
            f"{Color.tool('/help')} for commands  ·  "
            f"{Color.tool('/exit')} to quit"
        )
    )
    info = f"Memory: {mem}  ·  {tools_n} tools  ·  model: {model}"
    print(_box_line(Color.muted(info), dim=True))

    harness_dir = Path(ctx.project_root) / ".harness"
    if harness_dir.is_dir():
        skills_n = len(ctx.harness_skill_sources)
        rules_n = len(ctx.harness_rule_sources)
        subs_n = len(ctx.harness_subagent_defs)
        harness_info = (
            f"harness: {skills_n} skills · {rules_n} rules · "
            f"{subs_n} subagents"
        )
        print(_box_line(Color.muted(harness_info), dim=True))

    if ctx.metrics_server is not None:
        dash_url = "http://localhost:2025/ui"
        print(
            _box_line(
                f"Dashboard: {Color.paint(dash_url, Color.CYAN, Color.UNDERLINE)}"
            )
        )
    if history:
        print(
            _box_line(
                Color.muted(f"Restored {hist_n} messages from previous session"),
                dim=True,
            )
        )

    print(
        f"  {Color.dim(BOX_BOT)}{Color.dim(BOX_H * w)}"
        f"{Color.dim(BOX_BOT_R)}{Color.RESET}"
    )


def print_context_bar(ctx: CommandContext, history: list) -> None:
    """Print a compact context bar before the prompt."""
    tool_count = len(ctx.tools)
    mem_count = len(ctx.memory)
    hist_count = len(history)
    model_name = (
        getattr(ctx.llm, "model_name", None)
        or getattr(ctx.llm, "model", "?")
    )
    info = (
        f"{model_name}  ·  {tool_count} tools  ·  "
        f"{hist_count} msgs  ·  {mem_count} mem"
    )
    sep_w = box_width() + 4
    print(Color.muted(info))
    print(Color.dim("─" * sep_w))


def print_memory(memory: Any) -> None:
    """Print memory statistics."""
    item_count = len(memory)
    print(f"Memory items: {item_count}")
    if item_count > 0:
        mem_ctx = memory.get_context("current")
        print(f"Stored keys: {', '.join(mem_ctx['items'][:10])}")
        if len(mem_ctx["items"]) > 10:
            print(f"  ... and {len(mem_ctx['items']) - 10} more")
