# ADR-010: Custom Tools Architecture

## Context

The harness needs custom tools for web search (`web_search`), URL fetching (`fetch_url`), Python code execution (`execute_python`), and database queries (`query_database`). These complement built-in middleware tools (FilesystemMiddleware, ShellToolMiddleware). We need a consistent pattern for defining, validating, registering, and integrating custom tools.

## Decision

### Tool Registry Pattern

We use a central `ToolRegistry` that wraps a `dict[str, BaseTool]`:

```python
class ToolRegistry:
    def register(self, tool: BaseTool) -> None: ...
    def get(self, name: str) -> BaseTool: ...          # raises ToolNotFoundError
    def list_tools(self) -> list[dict[str, Any]]: ...   # returns JSON-serializable schemas
    def invoke_tool(self, name: str, **kwargs) -> Any: ...
```

Key design choices:
- **`get()` raises `ToolNotFoundError`**, not `KeyError` — consistent with ADR-009 error handling contract.
- **`invoke_tool()` wraps tool exceptions** in `ToolExecutionError` for consistent error propagation.
- **Duplicate registration overwrites** silently — tools are stateless functions; the latest registration wins.
- **Built-in middleware tools are NOT in the registry** — they are managed by their respective middleware.

### Tool Definition Contract

Every custom tool MUST:
1. Use the `@tool` decorator from `langchain_core.tools`
2. Have a Pydantic `args_schema` for input validation
3. Have a docstring (used as the tool description by LangChain)
4. Have type annotations on the function signature
5. Return a string (or JSON-serializable type) — not raw objects

Example:
```python
from langchain_core.tools import tool
from pydantic import BaseModel, Field

class WebSearchInput(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    max_results: int = Field(default=5, ge=1, le=20)

@tool(args_schema=WebSearchInput)
def web_search(query: str, max_results: int = 5) -> str:
    """Search the web and return structured results with citations."""
    ...
```

### Security Review per Category

| Category | Tools | Validation Rules |
|----------|-------|-----------------|
| **External API** | `web_search`, `fetch_url` | SSRF prevention (validate URLs against allowlist), response size limits (1MB), timeout (30s), no internal IPs |
| **Code Execution** | `execute_python` | Sandbox mandatory (Docker in production, StateBackend in dev), timeout (30s), output cap (100KB), no network access |
| **Data** | `query_database` | Parameterized queries only, read-only enforced at tool level, query timeout (10s), result row limit (1000) |

### Custom Tool Inventory

| Tool | Source | Status | Dependencies |
|------|--------|--------|-------------|
| `web_search` | Custom `@tool` | 🔧 To implement | `tavily-python` (installed), `TAVILY_API_KEY` |
| `fetch_url` | Custom `@tool` | 🔧 To implement | `httpx` (installed), `beautifulsoup4` (installed) |
| `execute_python` | Custom `@tool` + Sandbox | 🔧 To implement | Docker sandbox (Phase 5) or StateBackend (Phase 3) |
| `query_database` | Custom `@tool` | 📋 Phase 6+ | SQLAlchemy, database connector |

### Middleware Integration

Custom tools are passed to `create_deep_agent()` via the `tools=` parameter:

```python
agent = create_deep_agent(
    model=model,
    tools=[web_search, fetch_url, execute_python],
    middleware=[FilesystemMiddleware(), SubAgentMiddleware(...)],
)
```

Custom tools do NOT require their own middleware. They integrate with:
- `FilesystemMiddleware` — custom tools read/write files through the same backend
- `SubAgentMiddleware` — subagents inherit tools from the parent or have their own subset
- `ToolRetryMiddleware` — retries failed tool calls per ADR-009 retry strategy

## Alternatives Considered

1. **Plugin-based tool system with dynamic loading**: More flexible for third-party tools but adds complexity. Rejected for Phase 3 — plugin system deferred to Phase 6+.
2. **Tools as standalone classes (no decorator)**: More control over lifecycle but more boilerplate. Rejected — `@tool` decorator is the LangChain standard and integrates with `create_deep_agent()`.
3. **All tools in one file**: Simpler structure but violates the "files < 800 lines" rule as tool count grows. Rejected — category-based file organization scales better.

## Consequences

- **Positive**: Consistent tool definition pattern. Clear security checklist per category. Integration with existing middleware pipeline. Registry provides single point of discovery and invocation.
- **Negative**: Registry is in-memory only (no persistence). If the process restarts, all tools must be re-registered. Tool registration is synchronous and must happen before agent creation.
- **Mitigation**: Tool registration is lightweight (no I/O). The registry can be extended with persistence (StoreBackend) in a future phase if needed.

## References

- [Phase 0 Tool Inventory](../guides/plans/00-foundation.md#step-03-tool-inventory-assessment)
- [ADR-002: Middleware Pipeline](./002-middleware-pipeline.md)
- [ADR-009: Error Handling Contract](./009-error-handling-contract.md)
- [LangChain Tools Documentation](https://python.langchain.com/docs/concepts/tools/)
