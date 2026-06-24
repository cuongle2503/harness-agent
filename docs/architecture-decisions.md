# Architecture Decisions

> Key decisions made for Harness Agent, with rationale.

## ADR-001: Coordinator + Subagent Topology

**Decision**: Main orchestrator (v4-flash) delegates to 4 ephemeral subagents via `SubAgentMiddleware`.

**Why**: Context isolation, parallel execution, model optimization per task. Single-agent-with-all-tools rejected (context pollution, no parallelism). Handoff rejected (no parallel). Supervisor-worker rejected (bottleneck, overkill).

**Subagents**:

| Subagent | Model | Tools | Trigger |
|----------|-------|-------|---------|
| researcher | v4-flash | web_search, fetch_url | research, compare, evaluate |
| coder | v4-pro | read/write/edit_file, execute | implement, fix, refactor |
| reviewer | v4-flash | read_file, glob, grep, exec | review, audit, check |
| architect | v4-pro | read_file, glob, grep, web_search | design, architecture |

Simple tasks (<3 tool calls) handled directly by main agent.

## ADR-002: 6-Layer Middleware Pipeline

**Decision**: Planning → Security → Capabilities → Execution → Context Management → Resilience.

**Why**: Each layer depends on the previous. Security needs context (loaded in L1). Capabilities needed before execution. Resilience is last defense. 11 middleware total.

## ADR-003: CompositeBackend with Hybrid Routing

**Decision**: Route storage by path prefix.

| Path | Backend | Persistence |
|------|---------|------------|
| `/memories/*` | StoreBackend (user-scoped) | ✅ Cross-session |
| `/policies/*` | StoreBackend (org-scoped) | ✅ Cross-session |
| `/output/*` | FilesystemBackend | ✅ Real disk |
| `/*` (default) | StateBackend | ❌ Ephemeral |

**Why**: Different data has different persistence needs. StateBackend-only breaks memory. FilesystemBackend-only is a security risk. StoreBackend-only wastes storage on temp files.

## ADR-005: DeepSeek V4 Model Selection

**Decision**: v4-flash (80% of tasks) + v4-pro (code, architecture).

| Criteria | v4-pro | v4-flash |
|----------|--------|----------|
| Input cost | $0.435/1M | $0.14/1M |
| Output cost | $0.87/1M | $0.28/1M |
| Context | 1M | 1M |
| QPS | 500 | 2,500 |

**Why**: 1M context for long agent conversations. Tool calling ⭐⭐⭐⭐⭐ on both. 3x cheaper for most tasks. v4-pro only where deep reasoning matters.

## ADR-006: System Prompt Architecture

**Decision**: Structured template ~1,900 tokens covering: responsibilities, tools, workflow, subagent selection guide, quality standards, constraints, memory guidelines.

**Why**: Under 2K token budget. Gives agent clear delegation rules. Dynamic prompts rejected (unpredictable). Minimal prompts rejected (agent doesn't know when to delegate).

## ADR-009: Error Handling

**Decision**: `HarnessError` base with 4 subtypes:

| Exception | Retryable | Severity |
|-----------|-----------|----------|
| `ToolNotFoundError` | No | FATAL |
| `ToolExecutionError` | 3x exponential | ERROR |
| `AgentExecutionError` | 3x exponential | ERROR |
| `SubagentTimeoutError` | 1x (2× timeout) | WARN |

## ADR-010: Custom Tools

**Decision**: Central `ToolRegistry` + `@tool` decorator with Pydantic `args_schema`. Security rules per category (SSRF prevention for web, sandbox for code execution, parameterized queries for DB).
