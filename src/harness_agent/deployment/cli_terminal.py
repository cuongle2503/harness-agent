"""Terminal UI primitives for the CLI agent.

Provides ANSI color styling, Unicode box-drawing, spinners, input prompts,
and stream-chunk extraction. Zero dependency on agent state.
"""

from __future__ import annotations

import asyncio
import re
import shutil
import sys
import unicodedata
from typing import Any

# ---------------------------------------------------------------------------
# ANSI color palette
# ---------------------------------------------------------------------------

ANSI_RE = re.compile(r"\033\[[0-9;]*m")


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
    ORANGE = "\033[38;5;208m"
    DARK_ORANGE = "\033[38;5;202m"
    GOLD = "\033[38;5;220m"
    DARK_RED = "\033[38;5;160m"
    BRIGHT_RED = "\033[38;5;196m"

    @staticmethod
    def paint(text: str, *styles: str) -> str:
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
        chars = list(text)
        out = ""
        n = len(chars)
        for i, ch in enumerate(chars):
            t = i / max(n - 1, 1)
            if t < 0.33:
                out += Color.paint(ch, Color.BOLD, Color.BRIGHT_RED)
            elif t < 0.66:
                out += Color.paint(ch, Color.BOLD, Color.ORANGE)
            else:
                out += Color.paint(ch, Color.BOLD, Color.GOLD)
        return out

    @staticmethod
    def fire_prompt() -> str:
        return flicker_flame() + "  "


# ---------------------------------------------------------------------------
# Flame flicker animation
# ---------------------------------------------------------------------------

_FLAME_FRAMES = [
    Color.RED + Color.BOLD,
    Color.BRIGHT_RED + Color.BOLD,
    Color.DARK_RED + Color.BOLD,
    Color.ORANGE + Color.BOLD,
    Color.YELLOW + Color.BOLD,
    Color.GOLD + Color.BOLD,
    Color.ORANGE + Color.BOLD,
    Color.BRIGHT_RED + Color.BOLD,
]
_FLAME_TICK = 0


def flicker_flame() -> str:
    """Cycle fire emoji through flame colors for a flickering effect."""
    global _FLAME_TICK
    color = _FLAME_FRAMES[_FLAME_TICK % len(_FLAME_FRAMES)]
    _FLAME_TICK += 1
    return f"{color}🔥{Color.RESET}"


# ---------------------------------------------------------------------------
# Unicode box-drawing constants
# ---------------------------------------------------------------------------

BOX_TOP = "╭"
BOX_TOP_R = "╮"
BOX_BOT = "╰"
BOX_BOT_R = "╯"
BOX_H = "─"
BOX_V = "│"
BOX_MID = "├"
BOX_MID_R = "┤"


# ---------------------------------------------------------------------------
# ANSI / width utilities
# ---------------------------------------------------------------------------


def visible_len(text: str) -> int:
    """Return visible character count, stripping ANSI escape sequences."""
    return len(ANSI_RE.sub("", text))


def wcwidth(text: str) -> int:
    """Return terminal column count, handling wide chars (CJK, emoji)."""
    clean = ANSI_RE.sub("", text)
    width = 0
    for ch in clean:
        w = unicodedata.east_asian_width(ch)
        width += 2 if w in ("W", "F") else 1
    return width


def truncate_visible(text: str, max_visible: int) -> str:
    """Truncate to max_visible chars, preserving ANSI codes."""
    if "\033" not in text:
        return text[:max_visible] if len(text) > max_visible else text

    result_parts: list[str] = []
    visible = 0
    i = 0
    chars = list(text)
    while i < len(chars):
        if chars[i] == "\033" and i + 1 < len(chars) and chars[i + 1] == "[":
            seq = "\033["
            i += 2
            while i < len(chars) and chars[i] != "m":
                seq += chars[i]
                i += 1
            if i < len(chars):
                seq += chars[i]
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
    if "\033" in result and not result.endswith("\033[0m"):
        result += "\033[0m"
    return result


# ---------------------------------------------------------------------------
# Box layout helpers
# ---------------------------------------------------------------------------


def box_width() -> int:
    """Get box content width based on terminal size (capped at 72)."""
    tw = shutil.get_terminal_size().columns
    return min(tw - 4, 72)


def box_content(text: str, width: int, *, pad: int = 2) -> str:
    """Format content inside a box with vertical borders."""
    indent = " " * pad
    max_text = width - pad
    if visible_len(text) > max_text:
        text = truncate_visible(text, max_text - 3) + "..."
    right_pad = width - wcwidth(text) - pad
    if right_pad < 0:
        right_pad = 0
    return f"{BOX_V}{indent}{text}{' ' * right_pad}{BOX_V}"


def fmt_tool_args(args: dict[str, Any], width: int) -> list[str]:
    """Format tool arguments for box display, truncating long values."""
    lines: list[str] = []
    for k, v in args.items():
        s = str(v)
        if len(s) > 120:
            s = s[:117] + "..."
        key_part = f"{Color.paint(k, Color.DIM)}: "
        line = key_part + s
        if visible_len(line) > width - 4:
            max_val = width - 4 - visible_len(key_part) - 3
            if max_val < 10:
                max_val = 10
            s = s[:max_val] + "..."
            line = key_part + s
        lines.append(line)
    return lines


# ---------------------------------------------------------------------------
# Chat input prompt
# ---------------------------------------------------------------------------


def draw_chat_input() -> str:
    """Draw a framed chat input box and return the user's input."""
    w = box_width()
    flame = Color.flame("🔥")

    content_prefix = f"── {flame} "
    content_w = wcwidth(content_prefix)
    h_fill = max(w - content_w, 0)
    print(f"\n  {BOX_TOP}{content_prefix}{BOX_H * h_fill}{BOX_TOP_R}")

    print(f"  {BOX_V}{' ' * w}{BOX_V}")
    print(f"  {BOX_BOT}{BOX_H * w}{BOX_BOT_R}")

    sys.stdout.write("\033[2A")
    sys.stdout.write(f"\r  {BOX_V}  ")
    sys.stdout.write("\0337")
    sys.stdout.flush()

    result = input()

    sys.stdout.write("\0338")
    sys.stdout.write("\033[J")

    inner_w = w - 2
    cols_used = wcwidth(result)
    if cols_used <= inner_w:
        display = result
        pad = inner_w - cols_used
    else:
        display = truncate_visible(result, inner_w - 3) + "..."
        pad = inner_w - wcwidth(display)
    if pad < 0:
        pad = 0

    sys.stdout.write(f"{display}{' ' * pad}{BOX_V}\n")
    sys.stdout.write(f"  {BOX_BOT}{BOX_H * w}{BOX_BOT_R}\n")
    sys.stdout.flush()

    return result


# ---------------------------------------------------------------------------
# Tool-call box display
# ---------------------------------------------------------------------------


def draw_tool_box_top(tool_name: str, tool_args: dict[str, Any]) -> int:
    """Draw top half of a tool-call box. Returns box width."""
    w = box_width()

    title = f"✦ {tool_name} "
    title_w = wcwidth(title)
    remaining = w - title_w
    if remaining < 2:
        remaining = 2
    top = f"  {BOX_TOP} {title}{BOX_H * (remaining - 1)}"
    print(Color.paint(top, Color.BOLD, Color.CYAN))

    arg_lines = fmt_tool_args(tool_args, w)
    for line in arg_lines:
        print(f"  {box_content(line, w)}")

    mid = f"  {BOX_MID}{BOX_H * w}{BOX_MID_R}"
    print(Color.dim(mid))

    sys.stdout.flush()
    return w


def draw_tool_box_bottom(
    w: int,
    result: str,
    *,
    elapsed_ms: float = 0,
    error: bool = False,
) -> None:
    """Draw bottom half of a tool-call box (status + result)."""
    status_icon = Color.error("✗") if error else Color.success("✓")
    timing = ""
    if elapsed_ms > 0:
        if elapsed_ms < 1000:
            timing = f" ({elapsed_ms:.0f}ms)"
        else:
            timing = f" ({elapsed_ms / 1000:.1f}s)"
    status_line = f"{status_icon} done{timing}"
    print(f"  {box_content(status_line, w)}")

    result_lines = result.strip().split("\n")
    if not result_lines or result_lines == [""]:
        result_lines = [Color.dim("(no output)")]
    shown = result_lines[:5]
    for line in shown:
        print(f"  {box_content(Color.dim(line), w)}")
    if len(result_lines) > 5:
        remaining_count = len(result_lines) - 5
        print(
            f"  {box_content(Color.muted(f'... ({remaining_count} more lines)'), w)}"
        )

    bot = f"  {BOX_BOT}{BOX_H * w}{BOX_BOT_R}"
    print(Color.dim(bot))
    sys.stdout.flush()


# ---------------------------------------------------------------------------
# Streaming indicators
# ---------------------------------------------------------------------------

_INDICATOR_MESSAGES = {
    "thinking": "Thinking...",
    "planning": "Choosing tools...",
    "running": "Running",
}


def show_indicator(kind: str) -> None:
    """Show a status indicator on the current line."""
    msg = _INDICATOR_MESSAGES.get(kind, kind)
    line = f"  {Color.paint('⏳', Color.DIM)} {Color.paint(msg, Color.DIM, Color.ITALIC)}"
    sys.stdout.write(f"\r\033[K{line}")
    sys.stdout.flush()


def clear_indicator(kind: str | None) -> None:
    """Clear the current indicator line."""
    if kind is not None:
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()


# ---------------------------------------------------------------------------
# Tool execution with spinner
# ---------------------------------------------------------------------------


async def run_tool_with_spinner(
    tool: Any, tool_args: dict[str, Any], box_w: int
) -> tuple[str, bool]:
    """Execute a tool while showing a spinner on the separator line.

    Returns (result_message, is_error).
    """
    result_container: dict[str, Any] = {"msg": "", "error": False, "done": False}
    spinner_running = True

    async def spin() -> None:
        frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        i = 0
        while spinner_running:
            frame = frames[i % len(frames)]
            prefix = f"  {BOX_V}  {Color.paint(frame, Color.CYAN)} "
            suffix = f"{BOX_V}"
            prefix_visible = wcwidth(prefix)
            suffix_visible = wcwidth(suffix)
            label = Color.paint("Running...", Color.DIM)
            label_visible = wcwidth(label)
            total_w = box_w + 4
            right_pad = total_w - prefix_visible - label_visible - suffix_visible
            if right_pad < 1:
                right_pad = 1
            line = f"{prefix}{label}{' ' * right_pad}{suffix}"
            sys.stdout.write(f"\r\033[F\033[2K{line}")
            sys.stdout.flush()
            await asyncio.sleep(0.08)
            i += 1

    async def execute() -> None:
        try:
            result = await asyncio.to_thread(tool.invoke, tool_args)
            result_container["msg"] = str(result)
            result_container["error"] = False
        except Exception as e:
            result_container["msg"] = f"Tool error: {e}"
            result_container["error"] = True
        result_container["done"] = True

    spinner_task = asyncio.create_task(spin())
    exec_task = asyncio.create_task(execute())

    await exec_task

    spinner_running = False
    await spinner_task

    sys.stdout.write("\r\033[F\033[2K")
    mid = f"  {BOX_MID}{BOX_H * box_w}{BOX_MID_R}"
    sys.stdout.write(f"{mid}\n")
    sys.stdout.flush()

    return result_container["msg"], result_container["error"]


# ---------------------------------------------------------------------------
# Stream chunk extraction
# ---------------------------------------------------------------------------

_DEBUG_CHUNK_COUNT = 0


def debug_chunk(chunk: Any, extracted: str) -> None:
    """Log first 5 chunks to help diagnose streaming issues (debug mode only)."""
    from harness_agent.monitoring.debug import is_debug_enabled

    if not is_debug_enabled():
        return

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


def reset_debug_chunk_count() -> None:
    """Reset the debug chunk counter (called per turn)."""
    global _DEBUG_CHUNK_COUNT
    _DEBUG_CHUNK_COUNT = 0


def extract_chunk_text(chunk: Any) -> str:
    """Extract text content from a stream chunk.

    Handles string content, list of content blocks, and various
    LangChain chunk formats.
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
