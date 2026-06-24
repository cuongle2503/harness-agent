# Deep Agents — API Reference

> Reference for the external `deepagents` library built on LangGraph.

## create_deep_agent()

```python
from deepagents import create_deep_agent

agent = create_deep_agent(
    model="deepseek-v4-flash",
    tools=[...],
    system_prompt="...",
    middleware=[...],
    subagents=[...],
    memory=["/memories/preferences.md"],
    backend=backend,
    checkpointer=InMemorySaver(),
    store=store,
)
# Returns: CompiledStateGraph — use invoke(), ainvoke(), stream(), astream()
```

Key parameters:

| Parameter | Type | Purpose |
|-----------|------|---------|
| `model` | `str \| BaseChatModel` | LLM with tool calling support |
| `tools` | `Sequence[BaseTool]` | Custom tools available to agent |
| `middleware` | `Sequence[AgentMiddleware]` | Pipeline that defines capabilities |
| `subagents` | `Sequence[dict]` | Sub-agent definitions for task delegation |
| `memory` | `list[str]` | File paths injected into system prompt |
| `backend` | `BackendProtocol` | Storage layer for files |
| `checkpointer` | `Checkpointer` | State persistence (short-term) |
| `store` | `BaseStore` | Long-term memory (cross-thread) |

## Middleware

Order matters. Recommended: Planning → Security → Capabilities → Execution → Context → Resilience.

| Middleware | Source | Purpose |
|-----------|--------|---------|
| `TodoListMiddleware` | `langchain` | `write_todos` tool for planning |
| `MemoryMiddleware` | `deepagents` | Load AGENTS.md into system prompt |
| `HumanInTheLoopMiddleware` | `langchain` | Approval before dangerous tools |
| `PIIMiddleware` | `langchain` | Detect PII |
| `FilesystemMiddleware` | `deepagents` | `read_file`, `write_file`, `edit_file`, `glob`, `grep` |
| `ShellToolMiddleware` | `langchain` | `execute_command` (persistent shell) |
| `SubAgentMiddleware` | `deepagents` | `task` tool to spawn subagents |
| `SummarizationMiddleware` | `deepagents` | Auto-compact at token threshold |
| `ContextEditingMiddleware` | `langchain` | Trim old tool calls |
| `ModelFallbackMiddleware` | `langchain` | Fallback model on failure |
| `ToolRetryMiddleware` | `langchain` | Retry with exponential backoff |

## Backends

| Backend | Persistent | Use Case |
|---------|-----------|----------|
| `StateBackend` | ❌ | Dev/testing, ephemeral workspace |
| `StoreBackend` | ✅ | Memory, preferences (user/org scoped) |
| `FilesystemBackend` | ✅ | Real disk (needs sandbox/HITL) |
| `CompositeBackend` | Hybrid | Production — routes by path prefix |

```python
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend

backend = CompositeBackend(
    default=StateBackend(),
    routes={
        "/memories/": StoreBackend(namespace=lambda rt: [rt.user_id]),
        "/policies/": StoreBackend(namespace=lambda rt: [rt.org_id]),
    },
)
```

## Subagents

Defined as dicts, spawned via `task` tool from `SubAgentMiddleware`:

```python
{
    "name": "researcher",
    "description": "Web research and structured summaries",
    "system_prompt": "You are a researcher...",
    "tools": [web_search, fetch_url],
    "model": "deepseek-v4-flash",
    "middleware": [],
}
```

Lifecycle: Spawn → Run autonomously → Return single result → Main agent synthesizes.

When to use: complex multi-step tasks, parallel independent work, focused reasoning.
When NOT to use: trivial lookups (<3 tool calls), need intermediate steps.

## Streaming

```python
# Token-by-token
async for token, meta in agent.astream(input, stream_mode="messages"): ...

# State after each step
async for step in agent.astream(input, stream_mode="values"): ...

# Multiple modes
async for mode, data in agent.astream(input, stream_mode=["messages", "updates"]): ...
```

Use `subgraphs=True` to stream subagent progress.

## Memory

- `MemoryMiddleware` loads files (AGENTS.md, memory paths) → injects into system prompt
- Agent updates memory via `edit_file` on `/memories/` paths
- `StoreBackend` persists memory cross-session with namespace isolation

## Multi-Agent Patterns

| Pattern | Use Case |
|---------|----------|
| **Subagents** (task tool) | Independent parallel tasks with context isolation |
| **Handoff** | Domain-specific agents, sequential transfer |
| **Router** | Multi-source queries, fan-out + synthesize |
| **Swarm** | Dynamic role switching in conversation |
| **Supervisor-Worker** | Complex multi-step sequential workflows |
