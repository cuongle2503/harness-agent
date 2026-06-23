"""CLI agent deployment mode (Step 6.2).

Provides an interactive command-line agent for development and internal use.
Supports shell commands, MCP server integration, and memory persistence.
"""

from __future__ import annotations

import asyncio
import json
import os
import re as _re
import shutil
import sys
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig

from harness_agent.config import AgentModelSelection
from harness_agent.core.agent import DEFAULT_MAX_TOOL_ITERATIONS, HarnessAgent
from harness_agent.deployment.cli_metrics_server import (
    record_activity,
    record_session,
    record_tool_history,
)
from harness_agent.loaders.config_loader import ConfigLoader, HarnessConfig
from harness_agent.loaders.harness_builder import HarnessBuilder
from harness_agent.loaders.hook_loader import (
    EventBus,
    HookEvent,
    HookResult,
)
from harness_agent.loaders.skill_loader import SkillLoader
from harness_agent.memory.hybrid_memory import HybridMemory
from harness_agent.monitoring.metrics import AgentMetrics
from harness_agent.prompts import load_prompt
from harness_agent.security.sandbox import SandboxConfig
from harness_agent.tools.registry import ToolRegistry

# ---------------------------------------------------------------------------
# Metrics bridge — host mode (direct) vs client mode (HTTP POST)
# ---------------------------------------------------------------------------


class _MetricsBridge:
    """Routes metric recordings to either direct function calls (host mode)
    or HTTP POST to the aggregator (client mode)."""

    def __init__(
        self, session_id: str, *, http_port: int | None = None
    ) -> None:
        self.sid = session_id
        self._port = http_port
        self._url = f"http://127.0.0.1:{http_port}" if http_port else ""
        self._push_ok = True  # becomes False on first failure

    @property
    def is_host(self) -> bool:
        return self._port is None

    def tool_history(self, **kw: Any) -> None:
        if self._port:
            self._post("/push/tool-history", kw)
        else:
            record_tool_history(session_id=self.sid, **kw)

    def activity(self, event_type: str, **kw: Any) -> None:
        if self._port:
            self._post("/push/activity", {"event_type": event_type, **kw})
        else:
            record_activity(event_type, session_id=self.sid, **kw)

    def session(self, thread_id: str, **kw: Any) -> None:
        if self._port:
            self._post("/push/session", {"thread_id": thread_id, **kw})
        else:
            record_session(thread_id, session_id=self.sid, **kw)

    def push_metrics(self, metrics_dict: dict[str, Any]) -> None:
        """Push current metrics snapshot (client mode only)."""
        if not self._port:
            return
        self._post("/push/metrics", {"metrics": metrics_dict})

    def _post(self, path: str, data: dict[str, Any]) -> None:
        """Fire-and-forget HTTP POST to aggregator (no proxy)."""
        import urllib.request as _ur
        body = json.dumps({**data, "session_id": self.sid}).encode("utf-8")
        try:
            req = _ur.Request(
                self._url + path,
                data=body,
                headers={"Content-Type": "application/json"},
            )
            _no_proxy = _ur.ProxyHandler({})
            _ur.build_opener(_no_proxy).open(req, timeout=2)
        except Exception:
            if self._push_ok:
                self._push_ok = False
                print("\n  ⚠ Metrics push failed (proxy may block localhost "
                      "connections)")

# ---------------------------------------------------------------------------
# Terminal colors (ANSI)
# ---------------------------------------------------------------------------


class Color:
    """ANSI escape codes for terminal output."""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    ITALIC = "\033[3m"
    UNDERLINE = "\033[4m"
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    GRAY = "\033[90m"
    # 256-color flame palette
    ORANGE = "\033[38;5;208m"
    DARK_ORANGE = "\033[38;5;202m"
    GOLD = "\033[38;5;220m"
    DARK_RED = "\033[38;5;160m"
    BRIGHT_RED = "\033[38;5;196m"

    @staticmethod
    def paint(text: str, *styles: str) -> str:
        """Apply multiple ANSI styles to text."""
        prefix = "".join(styles)
        return f"{prefix}{text}{Color.RESET}" if styles else text

    @staticmethod
    def tool(msg: str) -> str:
        return Color.paint(msg, Color.BOLD, Color.CYAN)

    @staticmethod
    def arg(msg: str) -> str:
        return Color.paint(msg, Color.DIM)

    @staticmethod
    def result(msg: str) -> str:
        return Color.paint(msg, Color.DIM, Color.GREEN)

    @staticmethod
    def dim(msg: str) -> str:
        return Color.paint(msg, Color.DIM)

    @staticmethod
    def muted(msg: str) -> str:
        return Color.paint(msg, Color.GRAY)

    @staticmethod
    def warn(msg: str) -> str:
        return Color.paint(msg, Color.BOLD, Color.YELLOW)

    @staticmethod
    def error(msg: str) -> str:
        return Color.paint(msg, Color.BOLD, Color.RED)

    @staticmethod
    def success(msg: str) -> str:
        return Color.paint(msg, Color.BOLD, Color.GREEN)

    @staticmethod
    def flame(text: str) -> str:
        """Gradient flame effect using orange/yellow tones."""
        chars = list(text)
        result = ""
        n = len(chars)
        for i, ch in enumerate(chars):
            t = i / max(n - 1, 1)
            if t < 0.33:
                result += Color.paint(ch, Color.BOLD, Color.BRIGHT_RED)
            elif t < 0.66:
                result += Color.paint(ch, Color.BOLD, Color.ORANGE)
            else:
                result += Color.paint(ch, Color.BOLD, Color.GOLD)
        return result

    @staticmethod
    def fire_prompt() -> str:
        """Return a flame-styled CLI prompt with flicker animation."""
        return _flicker_flame() + "  "


# ---------------------------------------------------------------------------
# Flame flicker animation
# ---------------------------------------------------------------------------

_FLAME_FRAMES = [
    Color.RED + Color.BOLD,          # red
    Color.BRIGHT_RED + Color.BOLD,   # bright red
    Color.DARK_RED + Color.BOLD,     # dark red
    Color.ORANGE + Color.BOLD,       # orange
    Color.YELLOW + Color.BOLD,       # yellow
    Color.GOLD + Color.BOLD,         # gold
    Color.ORANGE + Color.BOLD,       # orange
    Color.BRIGHT_RED + Color.BOLD,   # bright red
]
_FLAME_TICK = 0


def _flicker_flame() -> str:
    """Cycle 🔥 through flame colors for a flickering fire effect."""
    global _FLAME_TICK
    color = _FLAME_FRAMES[_FLAME_TICK % len(_FLAME_FRAMES)]
    _FLAME_TICK += 1
    return f"{color}🔥{Color.RESET}"


DEFAULT_MAX_TOOL_ITERATIONS = 50


# ---------------------------------------------------------------------------
# Chat input prompt
# ---------------------------------------------------------------------------


def _draw_chat_input() -> str:
    """Draw a fully framed chat input box and return the user's input.

    The full box (top, empty middle, bottom) is pre-drawn so it looks
    complete before the user types.  Cursor save/restore (DECSC/DECRC)
    handles terminal line-wrapping for long text — after input the
    middle line is repainted cleanly with truncation and the bottom
    border is redrawn at the correct position.

    Looks like::

          ╭── 🔥 ─────────────────────────────────────╮
          │  user types here                          │
          ╰───────────────────────────────────────────╯
    """
    w = _box_width()
    flame = Color.flame("🔥")

    # ── Top border ──
    # Content between corners (╭...╮) must be exactly w columns.
    # Separate the corner from the content so h_fill is measured correctly.
    content_prefix = f"── {flame} "
    content_w = _wcwidth(content_prefix)
    h_fill = max(w - content_w, 0)
    print(f"\n  {_BOX_TOP}{content_prefix}{_BOX_H * h_fill}{_BOX_TOP_R}")

    # ── Pre-draw empty middle + bottom (box looks complete immediately) ──
    print(f"  {_BOX_V}{' ' * w}{_BOX_V}")
    print(f"  {_BOX_BOT}{_BOX_H * w}{_BOX_BOT_R}")

    # ── Move cursor into the box and save position ──
    sys.stdout.write("\033[2A")          # up 2 lines → middle line
    sys.stdout.write(f"\r  {_BOX_V}  ")  # left border + padding
    sys.stdout.write("\0337")            # DECSC: save cursor (right after "│  ")
    sys.stdout.flush()

    # ── Read input (may wrap across many lines) ──
    result = input()  # no prompt arg — already positioned

    # ── Restore cursor & redraw from saved position ──
    # \0338 jumps back to "│  " regardless of how many lines input() wrapped.
    # \033[J erases from cursor to end of screen (wipes wrapped lines *and*
    # the pre-drawn bottom border), then we redraw cleanly.
    sys.stdout.write("\0338")  # DECRC: back to middle line, right after "│  "
    sys.stdout.write("\033[J")  # erase cursor → end of screen

    inner_w = w - 2
    # Use _wcwidth for column-based alignment, _visible_len for truncation
    cols_used = _wcwidth(result)
    if cols_used <= inner_w:
        display = result
        pad = inner_w - cols_used
    else:
        display = _truncate_visible(result, inner_w - 3) + "..."
        pad = inner_w - _wcwidth(display)
    if pad < 0:
        pad = 0

    sys.stdout.write(f"{display}{' ' * pad}{_BOX_V}\n")
    sys.stdout.write(f"  {_BOX_BOT}{_BOX_H * w}{_BOX_BOT_R}\n")
    sys.stdout.flush()

    return result


# ---------------------------------------------------------------------------
# ANSI utility
# ---------------------------------------------------------------------------

_ANSI_RE = _re.compile(r"\033\[[0-9;]*m")


def _visible_len(text: str) -> int:
    """Return the visible character count, stripping ANSI escape sequences."""
    return len(_ANSI_RE.sub("", text))


def _wcwidth(text: str) -> int:
    """Return terminal column count, stripping ANSI codes and accounting for
    wide characters (CJK ideographs, emoji, etc. that occupy 2 columns).

    Use this for alignment math; use ``_visible_len`` for truncation logic
    where character count matters.
    """
    clean = _ANSI_RE.sub("", text)
    width = 0
    for ch in clean:
        w = unicodedata.east_asian_width(ch)
        width += 2 if w in ("W", "F") else 1
    return width



# ---------------------------------------------------------------------------
# Unicode box-drawing helpers
# ---------------------------------------------------------------------------

# Box characters for Claude-style tool display
_BOX_TOP = "╭"
_BOX_TOP_R = "╮"
_BOX_BOT = "╰"
_BOX_BOT_R = "╯"
_BOX_H = "─"
_BOX_V = "│"
_BOX_MID = "├"
_BOX_MID_R = "┤"


def _box_width() -> int:
    """Get box content width based on terminal size (capped at 72)."""
    tw = shutil.get_terminal_size().columns
    return min(tw - 4, 72)


def _box_content(text: str, width: int, *, pad: int = 2) -> str:
    """Format content inside a box with vertical borders and padding.

    Returns a string with vertical borders, left-padded content, and
    right-padded to fill the full box width. ANSI escape codes in text
    are accounted for so the right border aligns correctly.
    """
    indent = " " * pad
    max_text = width - pad  # preserve right margin inside border
    if _visible_len(text) > max_text:
        # Truncate by visible characters, preserving any ANSI prefix
        text = _truncate_visible(text, max_text - 3) + "..."
    # Use _wcwidth for column-level alignment (handles emoji, CJK)
    right_pad = width - _wcwidth(text) - pad
    if right_pad < 0:
        right_pad = 0
    return f"{_BOX_V}{indent}{text}{' ' * right_pad}{_BOX_V}"


def _truncate_visible(text: str, max_visible: int) -> str:
    """Truncate text to max_visible visible characters, preserving ANSI codes.

    The result always ends with an ANSI reset to avoid color leaks.
    """
    # Fast path: no ANSI codes
    if "\033" not in text:
        if len(text) <= max_visible:
            return text
        return text[:max_visible]

    # Build result char by char, tracking visible count and open ANSI codes
    result_parts: list[str] = []
    visible = 0
    i = 0
    chars = list(text)
    while i < len(chars):
        if chars[i] == "\033" and i + 1 < len(chars) and chars[i + 1] == "[":
            # Collect the full ANSI escape sequence
            seq = "\033["
            i += 2
            while i < len(chars) and chars[i] != "m":
                seq += chars[i]
                i += 1
            if i < len(chars):
                seq += chars[i]  # the 'm'
                i += 1
            result_parts.append(seq)
        else:
            if visible < max_visible:
                result_parts.append(chars[i])
                visible += 1
            else:
                break
            i += 1

    result = "".join(result_parts)
    # Always close any open ANSI codes
    if "\033" in result and not result.endswith("\033[0m"):
        result += "\033[0m"
    return result


def _fmt_tool_args(args: dict[str, Any], width: int) -> list[str]:
    """Format tool arguments for box display, truncating long values."""
    lines: list[str] = []
    for k, v in args.items():
        s = str(v)
        if len(s) > 120:
            s = s[:117] + "..."
        key_part = f"{Color.paint(k, Color.DIM)}: "
        line = key_part + s
        # Use _wcwidth for column alignment; _visible_len for truncation
        if _visible_len(line) > width - 4:
            max_val = width - 4 - _visible_len(key_part) - 3
            if max_val < 10:
                max_val = 10
            s = s[:max_val] + "..."
            line = key_part + s
        lines.append(line)
    return lines


def _draw_tool_box_top(tool_name: str, tool_args: dict[str, Any]) -> int:
    """Draw the top half of a tool-call box (name + args). Returns box width.

    The tool name is embedded in the top border: ╭── ✦ tool_name ──────
    """
    w = _box_width()

    # Top border with tool name embedded (left-aligned after corner)
    title = f"✦ {tool_name} "
    title_w = _wcwidth(title)
    remaining = w - title_w
    if remaining < 2:
        remaining = 2
    top = f"  {_BOX_TOP} {title}{_BOX_H * (remaining - 1)}"
    print(Color.paint(top, Color.BOLD, Color.CYAN))

    # Arguments
    arg_lines = _fmt_tool_args(tool_args, w)
    for line in arg_lines:
        print(f"  {_box_content(line, w)}")

    # Middle separator — the spinner will overwrite this line
    mid = f"  {_BOX_MID}{_BOX_H * w}{_BOX_MID_R}"
    print(Color.dim(mid))

    sys.stdout.flush()
    return w


def _draw_tool_box_bottom(
    w: int,
    result: str,
    *,
    elapsed_ms: float = 0,
    error: bool = False,
) -> None:
    """Draw the bottom half of a tool-call box (status + result + bottom border)."""
    # Status line with timing
    status_icon = Color.error("✗") if error else Color.success("✓")
    timing = ""
    if elapsed_ms > 0:
        if elapsed_ms < 1000:
            timing = f" ({elapsed_ms:.0f}ms)"
        else:
            timing = f" ({elapsed_ms / 1000:.1f}s)"
    status_line = f"{status_icon} done{timing}"
    print(f"  {_box_content(status_line, w)}")

    # Result content (truncated)
    result_lines = result.strip().split("\n")
    if not result_lines or result_lines == [""]:
        result_lines = [Color.dim("(no output)")]
    shown = result_lines[:5]
    for line in shown:
        print(f"  {_box_content(Color.dim(line), w)}")
    if len(result_lines) > 5:
        remaining_count = len(result_lines) - 5
        print(
            f"  {_box_content(Color.muted(f'... ({remaining_count} more lines)'), w)}"
        )

    # Bottom border
    bot = f"  {_BOX_BOT}{_BOX_H * w}{_BOX_BOT_R}"
    print(Color.dim(bot))
    sys.stdout.flush()


# ---------------------------------------------------------------------------
# Streaming indicator helpers
# ---------------------------------------------------------------------------

_INDICATOR_MESSAGES = {
    "thinking": "Thinking...",
    "planning": "Choosing tools...",
    "running": "Running",
}


_DEBUG_CHUNK_COUNT = 0


def _debug_chunk(chunk: Any, extracted: str) -> None:
    """Log first 5 chunks to help diagnose streaming issues."""
    global _DEBUG_CHUNK_COUNT
    if _DEBUG_CHUNK_COUNT >= 5:
        return
    _DEBUG_CHUNK_COUNT += 1
    try:
        with open("/tmp/harness-debug.log", "a") as f:
            f.write(f"--- Chunk {_DEBUG_CHUNK_COUNT} ---\n")
            f.write(f"  type: {type(chunk).__name__}\n")
            f.write(f"  content type: {type(getattr(chunk, 'content', None)).__name__}\n")
            f.write(f"  content repr: {repr(getattr(chunk, 'content', None))[:500]}\n")
            f.write(f"  has tool_call_chunks: {hasattr(chunk, 'tool_call_chunks')}\n")
            if hasattr(chunk, "tool_call_chunks") and chunk.tool_call_chunks:
                f.write(f"  tool_call_chunks: {repr(chunk.tool_call_chunks)[:300]}\n")
            f.write(f"  extracted text: {repr(extracted)}\n")
            f.write(f"  all attrs: {[a for a in dir(chunk) if not a.startswith('_')]}\n")
            f.write("\n")
    except Exception:
        pass


def _extract_chunk_text(chunk: Any) -> str:
    """Extract text content from a stream chunk.

    Handles various LangChain content formats:
    - String content (most common)
    - List of content blocks: ``[{"type": "text", "text": "Hello"}]``
    - AIMessageChunk with ``text`` or ``content_blocks`` attribute
    """
    raw = getattr(chunk, "content", None)
    if not raw:
        raw = getattr(chunk, "text", None)
    if not raw:
        raw = getattr(chunk, "content_blocks", None)
    if raw is None or raw == "":
        return ""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        parts: list[str] = []
        for block in raw:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(str(block.get("text", "")))
                elif "text" in block:
                    parts.append(str(block["text"]))
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return str(raw)


def _show_indicator(kind: str) -> None:
    """Show a status indicator on the current line (overwritten on next call).

    Uses carriage-return to stay on the same line so streamed text
    above is not disturbed. The line is fully cleared before writing.
    """
    msg = _INDICATOR_MESSAGES.get(kind, kind)
    line = f"  {Color.paint('⏳', Color.DIM)} {Color.paint(msg, Color.DIM, Color.ITALIC)}"
    # Clear the line first, then write indicator
    sys.stdout.write(f"\r\033[K{line}")
    sys.stdout.flush()


def _clear_indicator(kind: str | None) -> None:
    """Clear the current indicator line and move cursor back to start."""
    if kind is not None:
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()


async def _run_tool_with_spinner(
    tool: Any, tool_args: dict[str, Any], box_w: int
) -> tuple[str, bool]:
    """Execute a tool in a thread while showing a spinner on the separator line.

    The spinner overwrites the middle separator line (one line above the
    cursor after _draw_tool_box_top). When done, the separator is redrawn
    and the cursor returns below it.

    Returns (result_message, is_error).
    """
    result_container: dict[str, Any] = {"msg": "", "error": False, "done": False}
    spinner_running = True

    async def spin() -> None:
        """Animate a spinner on the separator line while the tool runs."""
        frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        i = 0
        while spinner_running:
            frame = frames[i % len(frames)]
            # Build spinner line: │ ⠋ Running...                │
            prefix = f"  {_BOX_V}  {Color.paint(frame, Color.CYAN)} "
            suffix = f"{_BOX_V}"
            prefix_visible = _wcwidth(prefix)
            suffix_visible = _wcwidth(suffix)
            label = Color.paint("Running...", Color.DIM)
            label_visible = _wcwidth(label)
            # Match the separator width: indent(2) + border(1) + content(box_w) + border(1)
            total_w = box_w + 4
            right_pad = total_w - prefix_visible - label_visible - suffix_visible
            if right_pad < 1:
                right_pad = 1
            line = f"{prefix}{label}{' ' * right_pad}{suffix}"
            # Move up one line (to separator), clear it, write spinner
            sys.stdout.write(f"\r\033[F\033[2K{line}")
            sys.stdout.flush()
            await asyncio.sleep(0.08)
            i += 1

    async def execute() -> None:
        """Run the actual tool in a thread."""
        try:
            result = await asyncio.to_thread(tool.invoke, tool_args)
            result_container["msg"] = str(result)
            result_container["error"] = False
        except Exception as e:
            result_container["msg"] = f"Tool error: {e}"
            result_container["error"] = True
        result_container["done"] = True

    # Run spinner and tool concurrently
    spinner_task = asyncio.create_task(spin())
    exec_task = asyncio.create_task(execute())

    # Wait for execution to complete
    await exec_task

    # Stop spinner and wait for it to finish its last frame
    spinner_running = False
    await spinner_task

    # Clear the spinner line and redraw the separator
    sys.stdout.write("\r\033[F\033[2K")
    mid = f"  {_BOX_MID}{_BOX_H * box_w}{_BOX_MID_R}"
    sys.stdout.write(f"{mid}\n")
    sys.stdout.flush()

    return result_container["msg"], result_container["error"]


# ===========================================================================
# CLI Agent classes
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
    session_name: str = ""  # Human-readable label for UI session selector
    system_prompt: str = ""  # Empty = load default from prompts/main_agent.md
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


class CLIAgent:
    """Interactive CLI agent for development and internal use.

    Example:
        config = CLIAgentConfig()
        agent = CLIAgent(config)
        await agent.run_interactive()
    """

    def __init__(self, config: CLIAgentConfig | None = None) -> None:
        self.config = config or CLIAgentConfig()

        # ── Harness state (populated by _load_harness_if_present) ──
        self._harness_config: HarnessConfig | None = None
        self._harness_skill_sources: list[str] = []
        self._harness_rule_sources: list[str] = []
        self._harness_subagent_defs: list[dict[str, Any]] = []
        self._harness_builder: Any = None  # HarnessBuilder | None
        self._event_bus = EventBus()
        self._load_harness_if_present()

        # ── Initialize components (may use harness overrides) ──
        self._llm = self._init_llm()
        self._sandbox = self._init_sandbox()
        self._agent = self._init_agent()
        self._graph: Any = None  # CompiledStateGraph from HarnessBuilder
        self._memory = HybridMemory()
        self._metrics = AgentMetrics()
        self._start_time = time.monotonic()
        self._session_id = ""
        self._bridge: _MetricsBridge | None = None
        self._metrics_server = self._connect_metrics_aggregator()
        self._init_debug_mode()

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

    # ── Harness loading ─────────────────────────────────────────────────

    def _load_harness_if_present(self) -> None:
        """Detect and load ``.harness/`` configuration.

        Uses ``HarnessBuilder`` for proper progressive disclosure
        (MemoryMiddleware) and subagent management (SubAgentMiddleware).

        If ``.harness/`` does not exist at ``project_root``, this is a
        no-op — the agent works as before with built-in defaults.
        """
        project_root = Path(self.config.project_root)
        harness_dir = project_root / ".harness"
        if not harness_dir.is_dir():
            return

        from harness_agent.tools.basic_tools import BASIC_TOOLS

        # Build tool registry for subagent validation
        tool_registry = ToolRegistry()
        for t in BASIC_TOOLS:
            tool_registry.register(t)

        # Use HarnessBuilder as single entry point for all harness loading
        builder = HarnessBuilder(
            project_root,
            tool_registry=tool_registry,
            model_selection=self.config.model_selection,
        )
        self._harness_builder = builder

        # 1. Load & validate config.yaml
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

        # 2. Use builder's EventBus — hooks were registered into it by
        #    load_config(). Replace the CLI's empty EventBus so _fire_hook
        #    actually triggers the registered hooks.
        self._event_bus = builder.event_bus

        # 3. Collect skill/rule memory sources (file paths, NOT content)
        # MemoryMiddleware in create_deep_agent handles progressive
        # disclosure — skills are name+description only until invoked.
        self._harness_skill_sources = builder.skill_loader.get_memory_sources()
        self._harness_rule_sources = builder.rule_loader.get_memory_sources()

        # 4. Hooks are already registered by load_config() above —
        #    we're now using builder.event_bus (see step 2).

        # 5. Load subagent definitions
        try:
            self._harness_subagent_defs = builder.get_subagent_defs()
        except Exception as e:
            print(
                f"  {Color.warn(f'⚠ Subagent loading failed: {e}')}"
            )

    # ── LLM / Agent initialization ──────────────────────────────────────

    def _init_llm(self) -> BaseChatModel:
        """Initialize the language model from config.

        If ``.harness/config.yaml`` specifies a model, it overrides the
        default orchestrator model from ``AgentModelSelection``.
        """
        from typing import cast

        model_config = self.config.model_selection.orchestrator

        # .harness/config.yaml model override
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
        """Initialize the LangChain agent with tools and system prompt.

        When ``.harness/`` is present and ``deepagents`` is available,
        attempts to use ``HarnessBuilder.build()`` to create a full
        ``CompiledStateGraph`` with MemoryMiddleware (progressive
        disclosure for skills/rules) and SubAgentMiddleware (task tool).

        Falls back to ``HarnessAgent`` when ``deepagents`` is not
        installed or ``.harness/`` is absent.

        System prompt priority:
        1. ``CLIAgentConfig.system_prompt`` (CLI flag)
        2. ``.harness/config.yaml`` inline ``system_prompt`` or
           ``system_prompt_file``
        3. ``HarnessBuilder.get_system_prompt()`` (when .harness/ present)
        4. Built-in ``load_prompt("main_agent")``
        """
        # ── Try HarnessBuilder.build() for full middleware support ──
        if self._harness_builder is not None:
            try:
                self._graph = self._harness_builder.build()
                # Return a lightweight HarnessAgent wrapper for backward
                # compatibility — _stream_turn detects self._graph and
                # uses astream_events() instead of manual LLM loop.
                from harness_agent.tools.basic_tools import BASIC_TOOLS
                return HarnessAgent(
                    llm=self._llm,
                    tools=BASIC_TOOLS,
                    system_prompt=self._harness_builder.get_system_prompt(),
                    max_tool_iterations=self.config.max_tool_iterations,
                )
            except Exception as e:
                print(
                    f"\n  {Color.warn(f'⚠ HarnessBuilder.build() failed: {e}')}"
                )
                fallback_msg = (
                    "Falling back to HarnessAgent "
                    "(no MemoryMiddleware/SubAgentMiddleware)."
                )
                print(f"  {Color.dim(fallback_msg)}")
                self._graph = None  # Ensure graph is None for fallback

        # ── Resolve base system prompt ──
        system_prompt = self.config.system_prompt

        if not system_prompt and self._harness_builder is not None:
            system_prompt = self._harness_builder.get_system_prompt()

        if not system_prompt and self._harness_config:
            project_root = Path(self.config.project_root)
            loader = ConfigLoader(project_root / ".harness")
            system_prompt = loader.load_system_prompt(
                self._harness_config, project_root
            )

        if not system_prompt:
            if self._harness_config is not None:
                system_prompt = self._build_harness_system_prompt()
            else:
                system_prompt = load_prompt("main_agent")

        from harness_agent.tools.basic_tools import BASIC_TOOLS

        return HarnessAgent(
            llm=self._llm,
            tools=BASIC_TOOLS,
            system_prompt=system_prompt,
            max_tool_iterations=self.config.max_tool_iterations,
        )

    def _build_harness_system_prompt(self) -> str:
        """Build a complete system prompt from .harness/ configuration.

        Only describes capabilities that actually exist — no hardcoded
        subagents or tools that aren't configured.
        """
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

        # Skills section — progressive disclosure (name+desc always visible)
        if self._harness_skill_sources:
            # Use SkillLoader to extract name + description metadata
            project_root = Path(self.config.project_root)
            skill_loader = SkillLoader(project_root / ".harness")
            skill_list = skill_loader.list_skills()
            if skill_list:
                parts.append("")
                parts.append("## Available Skills")
                parts.append(
                    "These skills are **always available**. When a task "
                    "matches a skill's description below, follow its "
                    "instructions precisely. Skills provide step-by-step "
                    "workflows for specific tasks."
                )
                parts.append("")
                for sk in skill_list:
                    name = sk.name or sk.path
                    desc = sk.description or "No description available"
                    parts.append(f"- **{name}**: {desc}")

        # Subagents section — only list what's actually configured
        if self._harness_subagent_defs:
            parts.append("")
            parts.append("## Available Subagents")
            parts.append(
                "These subagents are **pre-configured** in "
                "``.harness/subagents/``. You can delegate tasks "
                "to them when appropriate. "
                "You do NOT have permission to create, modify, or "
                "delete ``.harness/subagents/*.yaml`` files."
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
                ""
                "**No subagents are configured.** "
                "Handle all tasks directly with your available tools. "
                "Do NOT create ``.harness/subagents/*.yaml`` files "
                "yourself; subagents must be pre-configured by the user."
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
            "## Quality Standards",
            "- Always plan before executing complex tasks",
            "- Follow project conventions (PEP 8, type hints, conventional commits)",
            "- Provide specific, actionable responses with code examples",
            "- Ask clarifying questions when requirements are unclear",
            "",
            "## Constraints",
            "- Never expose API keys, passwords, or secrets",
            "- Never hardcode secrets in source code",
            "- Never execute dangerous shell commands without user approval",
            "- Do not describe capabilities you don't actually have",
        ])

        return "\n".join(parts)

    # ── Hook helpers ────────────────────────────────────────────────────

    def _fire_hook(
        self, event: HookEvent, context: dict[str, Any]
    ) -> HookResult:
        """Fire a hook event and return the aggregated result.

        If no hooks are registered for this event (typical when
        ``.harness/`` is absent), returns a default ``allowed=True``
        result with near-zero overhead.

        Also emits a ``hook_fired`` activity event so the Live
        Workflow UI can visualize hook interception in real time.
        """
        result = self._event_bus.fire(event, context)

        # Emit activity event for the Live Workflow UI
        if self._bridge:
            self._bridge.activity(
                "hook_fired",
                event=event.value,
                name=", ".join(result.messages) if result.messages else event.value,
                allowed=result.allowed,
            )

        return result

    def _connect_metrics_aggregator(self) -> Any:
        """Connect to the metrics aggregator (host or client mode).

        HOST MODE (first CLI): starts the aggregator server on the configured
        port and records metrics via direct function calls.

        CLIENT MODE (subsequent CLIs): the port is already bound → registers
        with the existing aggregator via HTTP POST and pushes metrics via HTTP.
        """
        import urllib.request as _ur

        from harness_agent.deployment.cli_metrics_server import (
            start_metrics_server,
        )

        port = self.config.monitoring_port
        env_port = os.environ.get("HARNESS_MONITORING_PORT")
        if env_port:
            try:
                port = int(env_port)
            except ValueError:
                pass

        name = self.config.session_name or os.environ.get(
            "HARNESS_SESSION_NAME", ""
        )
        # Ensure unique session_id: use name if set, otherwise agent_id + short PID suffix
        if name:
            session_id = name
        else:
            session_id = f"{self.config.assistant_id}-{os.getpid()}"

        # No proxy for localhost — urllib may route through http_proxy otherwise
        _no_proxy = _ur.ProxyHandler({})
        _opener = _ur.build_opener(_no_proxy)

        # Check if an aggregator is already running on this port
        # Retry — the server daemon thread may not be ready yet
        aggregator_alive = False
        for attempt in range(5):
            try:
                _opener.open(f"http://127.0.0.1:{port}/health", timeout=1)
                aggregator_alive = True
                break
            except Exception:
                if attempt < 4:
                    time.sleep(0.5)

        # --- Try client mode first (POST /register) ---
        if aggregator_alive:
            result = self._try_client_mode(port, session_id, name)
            if result is not None:
                return result

        # --- HOST MODE: start aggregator ---
        try:
            server, actual_port = start_metrics_server(
                metrics=self._metrics,
                start_time=self._start_time,
                memory=self._memory,
                port=port,
                agent_id=self.config.assistant_id,
                sandbox_type=self.config.sandbox_type,
                session_name=name,
                session_id=session_id,
            )
            self._session_id = session_id
            self._bridge = _MetricsBridge(session_id)  # host mode
            url = f"http://127.0.0.1:{actual_port}/ui"
            print(f"\n  {Color.success('📊 Dashboard:')} "
                  f"{Color.paint(url, Color.CYAN)}")
            msg2 = f'aggregator started, session: "{session_id}"'
            print(f"  {Color.dim(msg2)}")
            return server
        except OSError:
            # Port in use — aggregator exists but health check missed it
            print(f"\n  {Color.dim(f'Port {port} in use, trying client mode...')}")
            result = self._try_client_mode(port, session_id, name)
            if result is not None:
                return result
            print(f"\n  {Color.warn('⚠ Dashboard server: port in use')}")
            print(f"  {Color.dim('Metrics and UI unavailable this session.')}")
            return None

    def _try_client_mode(self, port: int, session_id: str, name: str) -> Any:
        """Try to register as a client with an existing aggregator."""
        import urllib.request as _ur
        url = f"http://127.0.0.1:{port}"
        _no_proxy = _ur.ProxyHandler({})
        _opener = _ur.build_opener(_no_proxy)
        try:
            body = json.dumps({
                "session_id": session_id,
                "name": name,
                "agent_id": self.config.assistant_id,
                "pid": os.getpid(),
            }).encode("utf-8")
            req = _ur.Request(
                f"{url}/register",
                data=body,
                headers={"Content-Type": "application/json"},
            )
            resp = json.loads(_opener.open(req, timeout=3).read())
            actual_sid = resp.get("session_id", session_id)
            self._session_id = actual_sid
            self._bridge = _MetricsBridge(actual_sid, http_port=port)
            if actual_sid != session_id:
                note = f'session_id "{session_id}" taken, using "{actual_sid}"'
                print(f"\n  {Color.dim(note)}")
            print(f"\n  {Color.success('📊 Dashboard:')} "
                  f"{Color.paint(f'http://127.0.0.1:{port}/ui', Color.CYAN)}")
            msg = f'connected to existing aggregator as "{actual_sid}"'
            print(f"  {Color.dim(msg)}")
            import atexit as _ae
            _ae.register(self._unregister_from_aggregator)
            return True  # success (client mode, no server)
        except Exception as e:
            msg = f'⚠ Cannot reach aggregator at http://127.0.0.1:{port}: {e}'
            print(f"\n  {Color.warn(msg)}")
            return None  # signal failure to caller

    def _unregister_from_aggregator(self) -> None:
        """Notify aggregator that this session is gone (client mode)."""
        import urllib.request as _ur
        port = self.config.monitoring_port
        try:
            body = json.dumps(
                {"session_id": self._session_id}
            ).encode("utf-8")
            req = _ur.Request(
                f"http://127.0.0.1:{port}/unregister",
                data=body,
                headers={"Content-Type": "application/json"},
            )
            _ur.urlopen(req, timeout=2)
        except Exception:
            pass

    async def _stream_turn(
        self, messages: list, config: RunnableConfig
    ) -> tuple[str | None, list]:
        """Stream a single agent turn with Claude-style tool display.

        Delegates to ``_stream_turn_graph`` when ``self._graph``
        (CompiledStateGraph from HarnessBuilder) is available — this
        provides proper MemoryMiddleware (progressive disclosure for
        skills/rules) and SubAgentMiddleware (task tool for subagents).

        Falls back to manual LLM-loop streaming when using the basic
        ``HarnessAgent``.

        Returns (final_text_response, updated_messages).
        """
        # Delegate to graph-based streaming when HarnessBuilder built the agent
        if self._graph is not None:
            return await self._stream_turn_graph(messages, config)

        return await self._stream_turn_agent(messages, config)

    async def _stream_turn_graph(
        self, messages: list, config: RunnableConfig
    ) -> tuple[str | None, list]:
        """Stream a turn using CompiledStateGraph.astream_events().

        This path is used when ``HarnessBuilder.build()`` succeeded —
        the agent has full MemoryMiddleware (progressive disclosure for
        skills/rules) and SubAgentMiddleware (task tool for subagents).

        Uses LangGraph's event-based streaming to get token-level text
        AND tool-call visibility, then renders them with the same
        Claude-style tool display boxes as the manual loop.
        """
        thread_id = config.get("configurable", {}).get("thread_id", "default")

        # Emit llm_start + rule_applied for the Live Workflow UI
        if self._bridge:
            self._bridge.activity(
                "llm_start",
                model=getattr(self._llm, "model_name", "?"),
                thread=thread_id,
            )
            # Rules are always loaded into system prompt every turn
            if self._harness_rule_sources:
                self._bridge.activity("rule_applied", name="rules")

        # Fire pre_llm_call hooks
        self._fire_hook(
            HookEvent.PRE_LLM_CALL,
            {
                "session_id": thread_id,
                "model": getattr(self._llm, "model_name", "?"),
                "messages_count": len(messages),
                "timestamp": time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                ),
            },
        )

        stream_start = time.perf_counter()
        final_text = ""
        tool_count = 0
        last_messages: list = list(messages)

        try:
            # Build input for CompiledStateGraph
            graph_input: dict[str, Any] = {"messages": messages}

            async for event in self._graph.astream_events(
                graph_input, config, version="v2"
            ):
                kind = event.get("event", "")

                if kind == "on_chat_model_stream":
                    # Stream text tokens
                    chunk = event.get("data", {}).get("chunk")
                    if chunk is not None:
                        content = _extract_chunk_text(chunk)
                        if content:
                            sys.stdout.write(content)
                            sys.stdout.flush()
                            final_text += content

                elif kind == "on_tool_start":
                    tool_count += 1
                    tool_name = event.get("name", "unknown")
                    tool_input = event.get("data", {}).get("input", {})

                    # Emit subagent_start when task tool spawns a subagent
                    if tool_name == "task" and self._bridge:
                        subagent_name = (
                            tool_input.get("subagent_type", "")
                            if isinstance(tool_input, dict)
                            else str(tool_input)[:60]
                        )
                        self._bridge.activity(
                            "subagent_start",
                            name=subagent_name or "subagent",
                            input=str(tool_input)[:200],
                        )

                    # Fire pre_tool_call hooks
                    pre_result = self._fire_hook(
                        HookEvent.PRE_TOOL_CALL,
                        {
                            "session_id": thread_id,
                            "tool_name": tool_name,
                            "tool_args": tool_input,
                            "timestamp": time.strftime(
                                "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                            ),
                        },
                    )
                    if not pre_result.allowed:
                        blocked_msg = (
                            f"Tool '{tool_name}' blocked by hook: "
                            + "; ".join(pre_result.messages)
                        )
                        print(f"\n  {Color.warn('🚫 ' + blocked_msg)}")
                        continue

                    # Draw tool box top
                    print()  # fresh line before tool box
                    box_w = _draw_tool_box_top(tool_name, tool_input)

                    # Store for on_tool_end
                    self._graph_tool_state = {
                        "name": tool_name,
                        "input": tool_input,
                        "box_w": box_w,
                        "start": time.perf_counter(),
                    }

                elif kind == "on_tool_end":
                    tool_state = getattr(self, "_graph_tool_state", None)
                    if tool_state is not None:
                        tool_name = tool_state["name"]
                        tool_input = tool_state["input"]
                        box_w = tool_state["box_w"]
                        t0 = tool_state["start"]
                        elapsed_ms = (time.perf_counter() - t0) * 1000

                        # Emit subagent_end when task tool completes
                        if tool_name == "task" and self._bridge:
                            self._bridge.activity(
                                "subagent_end",
                                name=(
                                    tool_input.get("subagent_type", "")
                                    if isinstance(tool_input, dict)
                                    else "subagent"
                                ),
                                latency_ms=round(elapsed_ms, 2),
                            )

                        output = event.get("data", {}).get("output")
                        result_str = str(output) if output else "(no output)"
                        error = "error" in str(kind).lower()

                        # Fire post_tool_call hooks
                        self._fire_hook(
                            HookEvent.POST_TOOL_CALL,
                            {
                                "session_id": thread_id,
                                "tool_name": tool_name,
                                "tool_args": tool_input,
                                "tool_result": result_str,
                                "duration_ms": int(elapsed_ms),
                                "success": not error,
                            },
                        )

                        # Record tool metrics
                        self._metrics.record_tool_call(
                            tool_name, elapsed_ms, success=not error
                        )

                        # Draw tool box bottom
                        _draw_tool_box_bottom(
                            box_w,
                            result=result_str,
                            elapsed_ms=elapsed_ms,
                            error=error,
                        )

                        # Record to activity feed
                        if self._bridge:
                            self._bridge.tool_history(
                                name=tool_name,
                                input_str=json.dumps(tool_input)
                                if isinstance(tool_input, dict)
                                else str(tool_input),
                                output_str=result_str[:500],
                                latency_ms=elapsed_ms,
                                success=not error,
                            )
                            self._bridge.activity(
                                "tool_end",
                                name=tool_name,
                                latency_ms=round(elapsed_ms, 2),
                            )

                        self._graph_tool_state = None

                elif kind == "on_chain_end":
                    # Capture final messages from the chain output
                    output = event.get("data", {}).get("output", {})
                    if isinstance(output, dict):
                        last_messages = output.get("messages", last_messages)

        except Exception as e:
            # Fire ON_ERROR hook
            import traceback as _traceback
            self._fire_hook(
                HookEvent.ON_ERROR,
                {
                    "session_id": thread_id,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "traceback": _traceback.format_exc(),
                    "context": {
                        "messages_count": len(messages),
                        "tool_count": tool_count,
                    },
                },
            )
            raise

        # Fire post_llm_call hooks
        stream_elapsed_ms = int((time.perf_counter() - stream_start) * 1000)
        self._fire_hook(
            HookEvent.POST_LLM_CALL,
            {
                "session_id": thread_id,
                "model": getattr(self._llm, "model_name", "?"),
                "tokens_used": 0,  # Graph doesn't expose token counts directly
                "duration_ms": stream_elapsed_ms,
                "success": True,
            },
        )

        if final_text:
            print()  # trailing newline after streamed text

        return (final_text if final_text else None, last_messages)

    async def _stream_turn_agent(
        self, messages: list, config: RunnableConfig
    ) -> tuple[str | None, list]:
        """Manual LLM-loop streaming for basic HarnessAgent (no .harness/)."""
        full_msgs = list(messages)
        if self._agent.system_prompt and (
            not full_msgs or not isinstance(full_msgs[0], SystemMessage)
        ):
            full_msgs.insert(0, SystemMessage(content=self._agent.system_prompt))

        llm_with_tools = self._agent.llm

        iteration = 0
        while iteration < self.config.max_tool_iterations:
            iteration += 1

            # Stream tokens from LLM with status indicators
            global _DEBUG_CHUNK_COUNT
            _DEBUG_CHUNK_COUNT = 0  # reset per turn
            accumulated: AIMessageChunk | None = None
            tool_calls_in_progress: dict[int, dict[str, Any]] = {}
            indicator_shown: str | None = None  # "thinking" | "planning" | None
            text_streamed: bool = False  # track if any text was output this iteration

            # ── Emit llm_start + rule_applied for Live Workflow UI ──
            thread_id = config.get("configurable", {}).get("thread_id", "default")
            if self._bridge:
                self._bridge.activity(
                    "llm_start",
                    model=getattr(llm_with_tools, "model_name", "?"),
                    thread=thread_id,
                )
                # Rules are always loaded into system prompt every turn
                if self._harness_rule_sources:
                    self._bridge.activity("rule_applied", name="rules")

            # Fire pre_llm_call hooks
            self._fire_hook(
                HookEvent.PRE_LLM_CALL,
                {
                    "session_id": thread_id,
                    "model": getattr(llm_with_tools, "model_name", "?"),
                    "messages_count": len(full_msgs),
                    "timestamp": time.strftime(
                        "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                    ),
                },
            )
            stream_start = time.perf_counter()

            async for chunk in llm_with_tools.astream(full_msgs, config):
                # Merge chunks
                accumulated = (
                    chunk
                    if accumulated is None
                    else accumulated + chunk  # type: ignore[operator]
                )

                # Extract text from chunk (handles both str and list content)
                content = _extract_chunk_text(chunk)
                has_tool_calls = (
                    hasattr(chunk, "tool_call_chunks")
                    and chunk.tool_call_chunks
                )

                # DEBUG: log first few chunks to /tmp/harness-debug.log
                _debug_chunk(chunk, content)

                # Stream text content as it arrives
                if content:
                    _clear_indicator(indicator_shown)
                    indicator_shown = None
                    sys.stdout.write(content)
                    sys.stdout.flush()
                    text_streamed = True

                # Track tool calls being built from stream
                if has_tool_calls:
                    for tc_chunk in chunk.tool_call_chunks:
                        idx = (
                            tc_chunk.get("index", 0)
                            if isinstance(tc_chunk, dict)
                            else getattr(tc_chunk, "index", 0)
                        )
                        name = (
                            tc_chunk.get("name")
                            if isinstance(tc_chunk, dict)
                            else getattr(tc_chunk, "name", None)
                        )
                        args = (
                            tc_chunk.get("args")
                            if isinstance(tc_chunk, dict)
                            else getattr(tc_chunk, "args", None)
                        )
                        id_ = (
                            tc_chunk.get("id")
                            if isinstance(tc_chunk, dict)
                            else getattr(tc_chunk, "id", None)
                        )
                        if idx not in tool_calls_in_progress:
                            tool_calls_in_progress[idx] = {
                                "name": "",
                                "args": "",
                                "id": "",
                            }
                        if name:
                            tool_calls_in_progress[idx]["name"] += name
                        if args:
                            tool_calls_in_progress[idx]["args"] += args
                        if id_ and not tool_calls_in_progress[idx]["id"]:
                            tool_calls_in_progress[idx]["id"] = id_

                    # Show tool-planning indicator.
                    # If text was already streamed on this line, move to a
                    # fresh line first so the text is preserved on screen.
                    if indicator_shown != "planning":
                        _clear_indicator(indicator_shown)
                        if text_streamed:
                            print()  # preserve streamed text, start fresh line
                            text_streamed = False
                        _show_indicator("planning")
                        indicator_shown = "planning"

                elif indicator_shown is None and not content:
                    # No text, no tool calls yet → LLM is thinking
                    _show_indicator("thinking")
                    indicator_shown = "thinking"

            # Clear any leftover indicator
            if indicator_shown:
                _clear_indicator(indicator_shown)
                indicator_shown = None

            if accumulated is None:
                return ("", full_msgs)

            # Extract usage metadata from the accumulated chunk for metrics
            usage_meta: dict[str, Any] = getattr(accumulated, "usage_metadata", None) or {}
            input_tokens = usage_meta.get("input_tokens", 0)
            output_tokens = usage_meta.get("output_tokens", 0)

            # Fire post_llm_call hooks
            stream_elapsed_ms = int(
                (time.perf_counter() - stream_start) * 1000
            )
            self._fire_hook(
                HookEvent.POST_LLM_CALL,
                {
                    "session_id": thread_id,
                    "model": getattr(llm_with_tools, "model_name", "?"),
                    "tokens_used": int(
                        input_tokens + output_tokens
                    ),
                    "duration_ms": stream_elapsed_ms,
                    "success": accumulated is not None,
                },
            )
            total_tokens = usage_meta.get("total_tokens", 0)
            if not total_tokens:
                total_tokens = input_tokens + output_tokens

            # Record model call metrics for the monitoring dashboard
            self._metrics.record_model_call(
                latency_ms=0.0,  # per-iteration latency tracked via turn-level
                success=True,
                tokens=int(total_tokens),
                input_tokens=int(input_tokens),
                output_tokens=int(output_tokens),
            )

            # Update session metrics with token/API call counts
            if total_tokens or input_tokens or output_tokens:
                tid = config.get("configurable", {}).get("thread_id", "default")
                if self._bridge:
                    self._bridge.session(
                        tid,
                        input_tokens=int(input_tokens),
                        output_tokens=int(output_tokens),
                        api_calls=1,
                    )

            content = _extract_chunk_text(accumulated)

            # Resolve tool calls
            resolved_tool_calls = None
            if tool_calls_in_progress:
                resolved_tool_calls = [
                    {
                        "name": tc["name"],
                        "args": json.loads(tc["args"]) if tc["args"] else {},
                        "id": tc["id"] or f"call_{idx}",
                    }
                    for idx, tc in tool_calls_in_progress.items()
                ]
            elif hasattr(accumulated, "tool_calls") and accumulated.tool_calls:
                resolved_tool_calls = accumulated.tool_calls  # type: ignore[assignment]

            ai_msg: AIMessage
            if resolved_tool_calls:
                ai_msg = AIMessage(content=str(content), tool_calls=resolved_tool_calls)
            else:
                ai_msg = AIMessage(content=str(content))

            full_msgs.append(ai_msg)

            # No tool calls = final response
            if not ai_msg.tool_calls:
                if ai_msg.content:
                    print()  # trailing newline after streamed text
                return (str(ai_msg.content), full_msgs)

            # Start tool boxes on a fresh line
            print()

            # Execute tools one at a time with Claude-style box display
            tool_msgs: list[Any] = []
            for tc in ai_msg.tool_calls:
                tool_name = tc.get("name", "unknown")
                tool_args = tc.get("args", {})
                tool_id = tc.get("id", "")

                # Fire pre_tool_call hooks — may block execution
                pre_result = self._fire_hook(
                    HookEvent.PRE_TOOL_CALL,
                    {
                        "session_id": thread_id,
                        "tool_name": tool_name,
                        "tool_args": tool_args,
                        "timestamp": time.strftime(
                            "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                        ),
                    },
                )
                if not pre_result.allowed:
                    blocked_msg = (
                        f"Tool '{tool_name}' blocked by hook: "
                        + "; ".join(pre_result.messages)
                    )
                    print(
                        f"\n  {Color.warn('🚫 ' + blocked_msg)}"
                    )
                    tool_msgs.append(
                        ToolMessage(
                            content=blocked_msg,
                            tool_call_id=tool_id,
                        )
                    )
                    continue

                # Draw the top half of the tool box immediately
                box_w = _draw_tool_box_top(tool_name, tool_args)

                # Execute the tool with a concurrent spinner
                tool = self._agent._tool_map.get(tool_name)
                error = False
                t0 = time.perf_counter()

                if tool is None:
                    msg = f"Unknown tool: {tool_name}"
                    error = True
                else:
                    # Run tool in thread while spinner animates concurrently
                    msg, error = await _run_tool_with_spinner(
                        tool, tool_args, box_w
                    )

                elapsed_ms = (time.perf_counter() - t0) * 1000

                # Fire post_tool_call hooks
                self._fire_hook(
                    HookEvent.POST_TOOL_CALL,
                    {
                        "session_id": thread_id,
                        "tool_name": tool_name,
                        "tool_args": tool_args,
                        "tool_result": (
                            msg if isinstance(msg, str) else str(msg)
                        ),
                        "duration_ms": int(elapsed_ms),
                        "success": not error,
                    },
                )

                # Record tool call metrics for the monitoring dashboard
                self._metrics.record_tool_call(
                    tool_name, elapsed_ms, success=not error
                )

                # Record activity: tool call started
                if self._bridge:
                    self._bridge.activity(
                        "tool_start",
                        name=tool_name,
                        input=json.dumps(tool_args)[:200] if isinstance(tool_args, dict) else str(tool_args)[:200],
                    )

                # Record to shared CLI metrics server history (for dashboard UI)
                if self._bridge:
                    self._bridge.tool_history(
                        name=tool_name,
                        input_str=json.dumps(tool_args) if isinstance(tool_args, dict) else str(tool_args),
                        output_str=msg[:500],
                        latency_ms=elapsed_ms,
                        success=not error,
                    )

                # Record activity: tool call completed
                if self._bridge:
                    self._bridge.activity(
                        "tool_end",
                        name=tool_name,
                        latency_ms=round(elapsed_ms, 2),
                    )

                # Draw the bottom half with result and timing
                _draw_tool_box_bottom(
                    box_w, result=msg, elapsed_ms=elapsed_ms, error=error
                )

                tool_msg: Any = ToolMessage(content=msg, tool_call_id=tool_id)
                tool_msgs.append(tool_msg)

            full_msgs.extend(tool_msgs)

        print(f"\n  {Color.error('⚠ Max tool iterations reached')}")
        # Try to get any text from the last AI message
        last_text = ""
        for msg in reversed(full_msgs):
            if isinstance(msg, AIMessage) and msg.content:
                last_text = str(msg.content)
                break
        return (last_text, full_msgs)

    async def run_interactive(self) -> None:
        """Run the interactive CLI loop with streaming and tool visibility."""
        thread_id = f"{self.config.assistant_id}-session"
        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}

        # Load past conversation from memory
        conversation_key = f"conversation:{thread_id}"
        saved = self._memory.get(conversation_key)
        history: list = saved if saved else []

        self._print_welcome(history)
        self._print_context_bar(history)

        # Fire session_start hooks
        self._fire_hook(
            HookEvent.SESSION_START,
            {
                "session_id": thread_id,
                "project_root": str(
                    Path(self.config.project_root).resolve()
                ),
                "config": {
                    "model": getattr(self._llm, "model_name", "?"),
                },
                "timestamp": time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                ),
            },
        )

        # Emit initial harness state for Live Workflow UI
        if self._bridge:
            # Rules are "always-on" — loaded into system prompt every turn
            if self._harness_rule_sources:
                self._bridge.activity(
                    "rule_applied",
                    name=f"{len(self._harness_rule_sources)} rules active",
                )
            # Skills are available on-demand (progressive disclosure)
            if self._harness_skill_sources:
                self._bridge.activity(
                    "skill_used",
                    name=f"{len(self._harness_skill_sources)} skills available",
                )

        success = True
        try:
            while True:
                try:
                    user_input = _draw_chat_input()
                except (EOFError, KeyboardInterrupt):
                    print("\nGoodbye!")
                    break

                if not user_input.strip():
                    continue

                # Dispatch slash commands
                if user_input.startswith("/"):
                    handled = await self._dispatch_command(
                        user_input, history, conversation_key
                    )
                    if handled == "exit":
                        break
                    # Refresh history after commands that may modify it
                    saved = self._memory.get(conversation_key)
                    history = saved if saved else []
                    continue

                # Plain-text commands (backward compatibility)
                if user_input.lower() in ("exit", "quit"):
                    print("Goodbye!")
                    break
                if user_input.lower() == "help":
                    self._print_help()
                    continue
                if user_input.lower() == "clear":
                    history = []
                    self._memory.delete(conversation_key)
                    print("Conversation cleared.")
                    continue
                if user_input.lower() == "memory":
                    self._print_memory()
                    continue

                # Build messages: history + new user message
                messages = [
                    *history,
                    HumanMessage(content=user_input),
                ]

                # Record user message to dashboard activity feed
                if self._bridge:
                    self._bridge.activity(
                        "user_msg", content=user_input[:200], thread=thread_id
                    )

                self._metrics.record_task_start()
                turn_start = time.perf_counter()

                text_response, updated_msgs = await self._stream_turn(
                    messages, config
                )

                turn_elapsed_ms = (time.perf_counter() - turn_start) * 1000
                self._metrics.record_task_complete(turn_elapsed_ms)

                # Record to shared CLI metrics server for dashboard UI
                if self._bridge:
                    self._bridge.activity(
                        "turn_end",
                        latency_ms=round(turn_elapsed_ms, 1),
                        thread=thread_id,
                    )
                    self._bridge.session(thread_id, turns=1)

                if text_response is None and updated_msgs:
                    # Try to extract text from last AI message
                    for msg in reversed(updated_msgs):
                        if isinstance(msg, AIMessage):
                            text_response = (
                                str(msg.content) if msg.content else ""
                            )
                            break

                # Update history with the exchange
                history.append(HumanMessage(content=user_input))
                if text_response is not None:
                    history.append(AIMessage(content=text_response))

                # Persist to memory
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

                # Push full metrics snapshot (client mode syncs to aggregator)
                if self._bridge:
                    self._bridge.push_metrics(self._metrics.to_dict())

        finally:
            # Fire session_end hooks on every exit path
            self._fire_hook(
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
    # Slash command system
    # ------------------------------------------------------------------

    async def _dispatch_command(
        self, raw: str, history: list, conversation_key: str
    ) -> str | None:
        """Parse and dispatch a slash command. Returns "exit" to quit."""
        parts = raw.strip().split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        handlers = {
            "/help": self._cmd_help,
            "/clear": self._cmd_clear,
            "/context": self._cmd_context,
            "/memory": self._cmd_memory,
            "/tools": self._cmd_tools,
            "/harness": self._cmd_harness,
            "/subagents": self._cmd_subagents,
            "/exit": self._cmd_exit,
            "/quit": self._cmd_exit,
        }

        handler = handlers.get(cmd)
        if handler is None:
            print(f"  {Color.warn(f'Unknown command: {cmd}')}")
            print(f"  Type {Color.tool('/help')} to see available commands.")
            return None

        return handler(args, history, conversation_key)

    def _cmd_help(self, args: str, history: list, key: str) -> str | None:
        """Show all available slash commands."""
        w = _box_width()
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
        print(f"  {Color.dim('Tip: You can still use plain commands like')} "
              f"{Color.tool('help')}{Color.dim(',')} "
              f"{Color.tool('clear')}{Color.dim(',')} "
              f"{Color.tool('exit')}")
        return None

    def _cmd_clear(self, args: str, history: list, key: str) -> str | None:
        """Reset the conversation session."""
        history.clear()
        self._memory.delete(key)
        # Also clean up turn keys via context
        thread_id = self.config.assistant_id + "-session"
        ctx = self._memory.get_context("current")
        for item_key in ctx.get("items", []):
            if item_key.startswith(f"turn:{thread_id}:"):
                self._memory.delete(item_key)
        print(f"\n  {Color.success('✓')} Session reset. "
              f"{Color.dim('Conversation history cleared. Starting fresh.')}")
        return None

    def _cmd_context(self, args: str, history: list, key: str) -> str | None:
        """Show current session context."""
        w = _box_width()
        print(f"\n  {Color.tool('Session Context')}")
        print(f"  {Color.dim('─' * w)}")

        # Session info
        print(f"  {Color.dim('Session ID:')}    {self.config.assistant_id}")
        print(f"  {Color.dim('Memory:')}       "
              f"{'enabled' if self.config.enable_memory else 'disabled'}")

        # Model info
        model_name = getattr(self._llm, 'model_name', None) or \
                     getattr(self._llm, 'model', None) or \
                     type(self._llm).__name__
        print(f"  {Color.dim('Model:')}        {model_name}")

        # History stats
        user_msgs = sum(1 for m in history if isinstance(m, HumanMessage))
        ai_msgs = sum(1 for m in history if isinstance(m, AIMessage))
        tool_msgs_count = sum(1 for m in history if isinstance(m, ToolMessage))
        print(f"  {Color.dim('History:')}      "
              f"{len(history)} messages "
              f"({user_msgs} user, {ai_msgs} assistant, {tool_msgs_count} tool)")

        # Token estimate (rough: ~4 chars per token)
        total_chars = sum(
            len(str(m.content)) for m in history
            if hasattr(m, 'content') and isinstance(m.content, str)
        )
        est_tokens = total_chars // 4
        print(f"  {Color.dim('Est. tokens:')}  ~{est_tokens}")

        # Memory stats
        mem_count = len(self._memory)
        print(f"  {Color.dim('Memory items:')} {mem_count}")

        # Tools
        tool_names = [t.name for t in self._agent._tools]
        print(f"  {Color.dim('Tools loaded:')} {len(tool_names)} — "
              f"{', '.join(tool_names[:8])}")
        if len(tool_names) > 8:
            print(f"  {' ' * 15}{Color.muted(f'... and {len(tool_names) - 8} more')}")

        # Sandbox
        print(f"  {Color.dim('Sandbox:')}      {self.config.sandbox_type}")
        print()
        return None

    def _cmd_memory(self, args: str, history: list, key: str) -> str | None:
        """Show memory store details."""
        self._print_memory()
        return None

    def _cmd_tools(
        self, args: str, history: list, key: str
    ) -> str | None:
        """List all available tools with their descriptions."""
        w = _box_width()
        print(f"\n  {Color.tool('Available Tools')}")
        print(f"  {Color.dim('─' * w)}")

        for tool in self._agent._tools:
            name = tool.name
            desc = (tool.description or "No description").split("\n")[0]
            # Truncate long descriptions
            if len(desc) > 100:
                desc = desc[:97] + "..."
            print(f"  {Color.tool(name):<22} {Color.dim(desc)}")
        print()
        return None

    def _cmd_exit(self, args: str, history: list, key: str) -> str | None:
        """Exit the CLI."""
        print("Goodbye!")
        return "exit"

    def _cmd_harness(
        self, args: str, history: list, key: str
    ) -> str | None:
        """Show loaded .harness/ configuration status."""
        harness_dir = Path(self.config.project_root) / ".harness"
        if not harness_dir.is_dir():
            msg = "No .harness/ directory found."
            print(f"\n  {Color.dim(msg)}\n")
            return None

        w = _box_width()
        print(f"\n  {Color.tool('Harness Configuration')}")
        print(f"  {Color.dim('─' * w)}")
        print(f"  {Color.dim('Directory:')}   {harness_dir}")

        if self._harness_config:
            print(
                f"  {Color.dim('Model:')}       "
                f"{self._harness_config.model}"
            )
            print(
                f"  {Color.dim('Sandbox:')}     "
                f"{self._harness_config.features.sandbox_type}"
            )

        skills_n = len(self._harness_skill_sources)
        rules_n = len(self._harness_rule_sources)
        subs_n = len(self._harness_subagent_defs)
        hooks_n = self._event_bus.listener_count

        print(f"  {Color.dim('Skills:')}      {skills_n} loaded")
        print(f"  {Color.dim('Rules:')}       {rules_n} loaded")
        print(f"  {Color.dim('Subagents:')}   {subs_n} loaded")
        print(f"  {Color.dim('Hooks:')}       {hooks_n} registered")
        print()
        return None

    def _cmd_subagents(
        self, args: str, history: list, key: str
    ) -> str | None:
        """List subagents discovered from .harness/subagents/."""
        if not self._harness_subagent_defs:
            print(f"\n  {Color.dim('No subagents configured.')}")
            print(
                "  "
                + Color.dim(
                    "Add .yaml files to .harness/subagents/ "
                    "to define subagents."
                )
            )
            return None

        w = _box_width()
        print(f"\n  {Color.tool('Subagents')}")
        print(f"  {Color.dim('─' * w)}")
        for sub in self._harness_subagent_defs:
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

    # ------------------------------------------------------------------
    # Display helpers
    # ------------------------------------------------------------------

    def _print_welcome(self, history: list) -> None:
        """Print a framed welcome header."""
        w = _box_width()
        pad = 2

        def _box_line(text: str = "", *, dim: bool = False) -> str:
            """Render one line inside the header box."""
            cols = _wcwidth(text)
            right = w - cols - pad
            right = max(right, 0)
            style = Color.DIM if dim else ""
            return f"  {_BOX_V}{' ' * pad}{text}{style}{' ' * right}{Color.RESET}{_BOX_V}"

        # Top border
        title = Color.paint("🔥  Harness Agent CLI", Color.BOLD)
        # Content between corners (╭...╮) must equal w columns
        content_prefix = f"── {title} "
        content_w = _wcwidth(content_prefix)
        h_fill = max(w - content_w, 0)
        print(f"\n  {_BOX_TOP}{content_prefix}{Color.DIM}{_BOX_H * h_fill}{_BOX_TOP_R}{Color.RESET}")

        # Content lines
        sid = self.config.assistant_id
        mem = "enabled" if self.config.enable_memory else "disabled"
        tools_n = len(self._agent._tools)
        hist_n = len(history)
        model = (
            getattr(self._llm, "model_name", None)
            or getattr(self._llm, "model", "?")
        )

        print(_box_line(Color.paint(sid, Color.DIM)))
        print(_box_line(""))
        print(_box_line(
            f"{Color.tool('/help')} for commands  ·  "
            f"{Color.tool('/exit')} to quit"
        ))
        info = f"Memory: {mem}  ·  {tools_n} tools  ·  model: {model}"
        print(_box_line(Color.muted(info), dim=True))

        # Show harness info if loaded
        harness_dir = Path(self.config.project_root) / ".harness"
        if harness_dir.is_dir():
            skills_n = len(self._harness_skill_sources)
            rules_n = len(self._harness_rule_sources)
            subs_n = len(self._harness_subagent_defs)
            harness_info = (
                f"harness: {skills_n} skills · {rules_n} rules · "
                f"{subs_n} subagents"
            )
            print(_box_line(Color.muted(harness_info), dim=True))

        if self._metrics_server is not None:
            dash_url = f"http://localhost:{self.config.monitoring_port}/ui"
            print(_box_line(
                f"Dashboard: {Color.paint(dash_url, Color.CYAN, Color.UNDERLINE)}"
            ))
        if history:
            print(_box_line(
                Color.muted(f"Restored {hist_n} messages from previous session"),
                dim=True,
            ))

        # Bottom border
        print(f"  {Color.dim(_BOX_BOT)}{Color.dim(_BOX_H * w)}{Color.dim(_BOX_BOT_R)}{Color.RESET}")

    def _print_context_bar(self, history: list) -> None:
        """Print a compact context bar before the prompt."""
        tool_count = len(self._agent._tools)
        mem_count = len(self._memory)
        hist_count = len(history)
        model_name = (
            getattr(self._llm, 'model_name', None)
            or getattr(self._llm, 'model', '?')
        )
        info = (
            f"{model_name}  ·  {tool_count} tools  ·  "
            f"{hist_count} msgs  ·  {mem_count} mem"
        )
        # Adaptive separator width — match the box width
        sep_w = _box_width() + 4  # +4 accounts for "  " indent + left/right borders
        print(Color.muted(info))
        print(Color.dim("─" * sep_w))

    @staticmethod
    def _print_help() -> None:
        """Print help message."""
        w = _box_width()
        print(f"\n  {Color.tool('Slash Commands')}")
        print(f"  {Color.dim('─' * w)}")
        print(f"  {Color.tool('/help'):<20} Show this message")
        print(f"  {Color.tool('/clear'):<20} Reset session — start fresh")
        print(f"  {Color.tool('/context'):<20} Show session context & stats")
        print(f"  {Color.tool('/memory'):<20} Show memory store stats")
        print(f"  {Color.tool('/exit'):<20} Exit the CLI")
        print(f"\n  {Color.dim('Plain commands (no /) also work:')} "
              f"help, clear, memory, exit")

    def _print_memory(self) -> None:
        """Print memory statistics."""
        item_count = len(self._memory)
        print(f"Memory items: {item_count}")
        if item_count > 0:
            ctx = self._memory.get_context("current")
            print(f"Stored keys: {', '.join(ctx['items'][:10])}")
            if len(ctx["items"]) > 10:
                print(f"  ... and {len(ctx['items']) - 10} more")

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
    """Entry point for the CLI agent.

    Automatically loads environment variables from .env file if present.
    """
    # Load .env from current directory or project root
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
