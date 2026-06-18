# ADR-009: Error Handling Contract

## Context

The agent harness needs a consistent error handling strategy across all components: agent core, tool registry, memory, agent factories, and subagent orchestration. Without a clear contract, error propagation between subagents and the main agent becomes unpredictable, and debugging distributed agent failures is difficult.

## Decision

### Exception Hierarchy

We define a single base exception `HarnessError` with four concrete subtypes:

```
Exception
└── HarnessError                    # Base for all harness errors
    ├── ToolNotFoundError           # Configuration error — never retried
    ├── ToolExecutionError          # Runtime tool failure — retryable
    ├── AgentExecutionError         # LLM/agent failure — retryable
    └── SubagentTimeoutError        # Subagent timeout — retryable once
```

All exceptions carry structured context accessible via attributes:

```python
class ToolNotFoundError(HarnessError):
    tool_name: str

class ToolExecutionError(HarnessError):
    tool_name: str
    original_error: Exception

class AgentExecutionError(HarnessError):
    agent_id: str
    original_error: Exception

class SubagentTimeoutError(HarnessError):
    agent_id: str
    timeout_seconds: float | None
```

### Propagation Rules

1. **ToolNotFoundError**: Raised synchronously by `ToolRegistry.get()`. Never retried — this is a configuration error. The caller must fix the tool name or register the tool. Returns severity `[FATAL]`.

2. **ToolExecutionError**: Raised when a tool's `invoke()` method throws. The `ToolRegistry.invoke_tool()` method catches the original exception and wraps it. The caller (agent or middleware) may retry. Returns severity `[ERROR]`.

3. **AgentExecutionError**: Raised when the LLM call or agent graph execution fails. Wraps the original error from LangChain/LangGraph. The caller may retry with backoff. Returns severity `[ERROR]`.

4. **SubagentTimeoutError**: Raised when a subagent exceeds its timeout. The main agent may retry once with a longer timeout or report the failure to the user. Returns severity `[WARN]`.

### Error Messages

Every error message follows this format for machine-parseability:

```
[SEVERITY][code] Human-readable description
```

Examples:
- `[FATAL][TOOL_NOT_FOUND] Tool 'web_search' not found in registry`
- `[ERROR][TOOL_EXEC_FAILED] Tool 'execute_python' execution failed: timeout after 30s`
- `[ERROR][AGENT_EXEC_FAILED] Agent 'researcher' execution failed: API rate limit exceeded`
- `[WARN][SUBAGENT_TIMEOUT] Subagent 'researcher' timed out after 60.0s`

### Retry Strategy

| Error Type | Max Retries | Backoff | Retry By |
|------------|-------------|---------|----------|
| ToolNotFoundError | 0 | N/A | N/A |
| ToolExecutionError | 3 | Exponential (1s, 2s, 4s) | ToolRetryMiddleware |
| AgentExecutionError | 3 | Exponential (2s, 4s, 8s) | Caller |
| SubagentTimeoutError | 1 | Linear (timeout × 2) | Main agent |

## Alternatives Considered

1. **Flat exceptions (no hierarchy)**: Simpler but loses the ability to catch all harness errors with one `except HarnessError`. Rejected — hierarchy adds clarity with zero cost.

2. **Each component defines its own exceptions**: More flexibility but leads to inconsistent error handling. Rejected — unified hierarchy ensures consistent behavior.

3. **Return error objects instead of raising**: Go-style error handling. Rejected — not Pythonic; LangChain/LangGraph use exceptions throughout.

## Consequences

- **Positive**: Consistent error handling across all components. Machine-parseable error messages enable monitoring and alerting. Clear retry semantics prevent infinite loops.
- **Negative**: Requires all code paths to use these exceptions instead of generic `Exception` or `RuntimeError`. Migration burden if we switch to a different error model later.
- **Mitigation**: The hierarchy is small (5 classes) and the base class is `HarnessError` — easy to grep for and clear in intent.

## References

- [Phase 3 Implementation Plan](../guides/plans/03-implementation.md#step-35-error-handling)
- [AIDLC Lifecycle §3 Pattern 3](../guides/aidlc-lifecycle.md#pattern-3-error-handling)
- [ADR-002: Middleware Pipeline](./002-middleware-pipeline.md) — ToolRetryMiddleware configuration
