# Agent Learnings

> Patterns and insights discovered by the agent over time through
> interactions with the codebase and user feedback.

## Architecture Patterns

### HarnessAgent is Runnable-based
- All agents implement LangChain's Runnable protocol
- `invoke()` and `ainvoke()` are the primary entry points
- Tools are bound to the LLM at initialization time

### Memory Architecture
- Hybrid: key-value + vector store + conversation buffer
- CompositeBackend routes: `/memories/*` → StoreBackend, `/output/*` → FilesystemBackend, `/*` → StateBackend
- Vector retrieval is simplified (most-recent-k); full cosine similarity deferred

### Monitoring Stack
- Metrics collected via AgentMetrics dataclass
- Alerting with configurable thresholds and severity levels
- Streaming via LangChain's streaming callback system
- Debug mode toggle at runtime

### Security Layers
- HITL approval middleware for sensitive operations
- PII sanitization middleware for data privacy
- Sandbox for safe code execution
- Subprocess safety with list-arg enforcement

## Common Pitfalls

### Mutating messages in place
- Always create new message lists rather than mutating input
- The agent's `invoke()` copies messages before prepending SystemMessage

### Tool registration order
- Duplicate registration silently overwrites (by design)
- Always check `registry.get()` before registering to avoid surprises

### Memory cleanup
- Delete during iteration: use `list(keys)` copy to avoid RuntimeError
- Clear then store: safe; clear() fully resets both kv and vector stores

## Optimization Insights

### Token usage
- System prompt should be <2000 tokens for invariant parts
- Summarization triggers when context exceeds threshold
- Use FakeListChatModel for unit tests to avoid API costs

### Test performance
- Use `@pytest.mark.parametrize` for edge cases
- Shared fixtures in `conftest.py` reduce setup duplication
- Mock external APIs with `autospec=True` adapters
