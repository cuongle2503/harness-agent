"""Tool inventory for the agent harness.

Phase 0.3 — Tool Inventory Assessment
Catalog of all built-in middleware tools and custom tools needed.
See: AIDLC Lifecycle §0.3, docs/guides/plans/00-foundation.md §0.3

Tool Inventory Overview:
┌──────────────────────┬───────────────────────────┬──────────────┐
│ Category             │ Source                    │ Status       │
├──────────────────────┼───────────────────────────┼──────────────┤
│ File System          │ FilesystemMiddleware      │ ✅ Built-in  │
│ Shell                │ ShellToolMiddleware       │ ✅ Built-in  │
│ Planning             │ TodoListMiddleware        │ ✅ Built-in  │
│ Delegation           │ SubAgentMiddleware        │ ✅ Built-in  │
│ Memory               │ MemoryMiddleware          │ ✅ Built-in  │
│ Summarization        │ SummarizationMiddleware   │ ✅ Built-in  │
│ Context Editing      │ ContextEditingMiddleware  │ ✅ Built-in  │
│ HITL (Approval)      │ HumanInTheLoopMiddleware  │ ✅ Built-in  │
│ Web Search           │ Custom @tool (Tavily)     │ 🔧 Custom    │
│ URL Fetch            │ Custom @tool              │ 🔧 Custom    │
│ Code Execution       │ Custom @tool + Sandbox    │ 🔧 Custom    │
│ Database Query       │ Custom @tool              │ 🔧 Custom    │
└──────────────────────┴───────────────────────────┴──────────────┘

Tool Overlap Analysis:
- FilesystemMiddleware covers: read, write, edit, glob, grep → no duplicate
- ShellToolMiddleware covers: bash execution → unique
- TodoListMiddleware covers: write_todos → unique
- SubAgentMiddleware covers: task → unique
- MemoryMiddleware: uses filesystem via /memories/ → routed by backend, no conflict
- Custom web_search: unique → no overlap with built-in
- Custom fetch_url: unique → no overlap with built-in
- Custom execute_code: unique (sandboxed) → no overlap with ShellToolMiddleware
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ToolSource(Enum):
    """Where a tool comes from."""

    BUILTIN = "builtin"       # Provided by deepagents middleware
    CUSTOM = "custom"         # Custom @tool we build
    MCP = "mcp"               # External MCP server


@dataclass
class ToolSpec:
    """Specification for a single tool in the harness.

    Attributes:
        name: Tool name as exposed to the agent.
        category: High-level grouping (filesystem, shell, networking, etc.).
        source: Where the tool comes from.
        middleware: Which middleware provides it (built-in tools only).
        description: What the tool does — used for agent system prompts.
        enabled: Whether this tool is enabled for the current configuration.
        notes: Implementation notes / status.
    """

    name: str
    category: str
    source: ToolSource
    middleware: str | None = None
    description: str = ""
    enabled: bool = True
    notes: str = ""


@dataclass
class ToolInventory:
    """Complete tool inventory for the agent harness."""

    tools: list[ToolSpec] = field(default_factory=list)

    @classmethod
    def create_default(cls) -> ToolInventory:
        """Create the default tool inventory matching Phase 0.3 plan."""
        return cls(tools=[
            # ── Built-in: Filesystem ──
            ToolSpec(
                name="read_file",
                category="File System",
                source=ToolSource.BUILTIN,
                middleware="FilesystemMiddleware",
                description="Read content from a file at a given path.",
            ),
            ToolSpec(
                name="write_file",
                category="File System",
                source=ToolSource.BUILTIN,
                middleware="FilesystemMiddleware",
                description="Write content to a file, overwriting if it exists.",
            ),
            ToolSpec(
                name="edit_file",
                category="File System",
                source=ToolSource.BUILTIN,
                middleware="FilesystemMiddleware",
                description="Perform exact string replacements in a file.",
            ),
            ToolSpec(
                name="glob",
                category="File System",
                source=ToolSource.BUILTIN,
                middleware="FilesystemMiddleware",
                description="Find files matching a glob pattern.",
            ),
            ToolSpec(
                name="grep",
                category="File System",
                source=ToolSource.BUILTIN,
                middleware="FilesystemMiddleware",
                description="Search file contents with regex patterns.",
            ),

            # ── Built-in: Shell ──
            ToolSpec(
                name="execute_command",
                category="Shell",
                source=ToolSource.BUILTIN,
                middleware="ShellToolMiddleware",
                description="Execute a shell command in a sandboxed environment.",
            ),

            # ── Built-in: Planning ──
            ToolSpec(
                name="write_todos",
                category="Planning",
                source=ToolSource.BUILTIN,
                middleware="TodoListMiddleware",
                description="Create and update a structured task list.",
            ),

            # ── Built-in: Delegation ──
            ToolSpec(
                name="task",
                category="Delegation",
                source=ToolSource.BUILTIN,
                middleware="SubAgentMiddleware",
                description="Delegate a task to a specialized subagent.",
            ),

            # ── Built-in: Memory ──
            ToolSpec(
                name="memory_store",
                category="Memory",
                source=ToolSource.BUILTIN,
                middleware="MemoryMiddleware",
                description="Store data in persistent memory for future recall.",
            ),
            ToolSpec(
                name="memory_retrieve",
                category="Memory",
                source=ToolSource.BUILTIN,
                middleware="MemoryMiddleware",
                description="Retrieve data from persistent memory.",
            ),

            # ── Custom: Web Search ──
            ToolSpec(
                name="web_search",
                category="External API",
                source=ToolSource.CUSTOM,
                description="Search the web using Tavily and return structured results.",
                notes="Uses Tavily API (tavily-python already installed). Requires TAVILY_API_KEY env var.",
            ),

            # ── Custom: URL Fetch ──
            ToolSpec(
                name="fetch_url",
                category="External API",
                source=ToolSource.CUSTOM,
                description="Fetch and parse content from a URL as markdown.",
                notes="Uses httpx + BeautifulSoup for parsing. Input validation required for SSRF prevention.",
            ),

            # ── Custom: Code Execution ──
            ToolSpec(
                name="execute_python",
                category="Code Execution",
                source=ToolSource.CUSTOM,
                description="Execute Python code in a sandboxed environment.",
                notes="Production: Docker sandbox (sandbox_type='docker'). Dev: StateBackend only.",
            ),

            # ── Custom: Database Query ──
            ToolSpec(
                name="query_database",
                category="Data",
                source=ToolSource.CUSTOM,
                description="Run read-only SQL queries against configured databases.",
                notes="Parameterized queries only. Write operations blocked by default.",
            ),
        ])

    def by_category(self) -> dict[str, list[ToolSpec]]:
        """Group tools by category."""
        result: dict[str, list[ToolSpec]] = {}
        for t in self.tools:
            result.setdefault(t.category, []).append(t)
        return result

    def builtins(self) -> list[ToolSpec]:
        """Return only built-in tools."""
        return [t for t in self.tools if t.source == ToolSource.BUILTIN]

    def custom(self) -> list[ToolSpec]:
        """Return only custom tools that need implementation."""
        return [t for t in self.tools if t.source == ToolSource.CUSTOM]

    def enabled(self) -> list[ToolSpec]:
        """Return all enabled tools."""
        return [t for t in self.tools if t.enabled]

    def summary(self) -> str:
        """Human-readable inventory summary."""
        lines = ["Tool Inventory Summary", "=" * 60]
        for category, tools in self.by_category().items():
            lines.append(f"\n{category} ({len(tools)} tools):")
            for t in tools:
                status = "✅" if t.source == ToolSource.BUILTIN else "🔧"
                lines.append(f"  {status} {t.name} — {t.description}")
                if t.notes:
                    lines.append(f"     📝 {t.notes}")
        return "\n".join(lines)
