---
name: agent-harness-construction
description: Design and optimize AI agent action spaces, tool definitions, observation formatting, and multi-agent orchestration for higher completion rates.
origin: harness-agent
---

# Agent Harness Construction

Design and optimize agent action spaces, tool definitions, and observation formatting for higher completion rates in the Harness Agent framework.

## Core Model

Agent output quality is constrained by:
1. **Action space quality** — tools must be well-defined, non-overlapping
2. **Observation quality** — tool responses must be structured and actionable
3. **Recovery quality** — errors must guide the agent toward resolution
4. **Context budget quality** — keep prompts minimal, load on demand

## Action Space Design

1. Use stable, explicit tool names (`search_files`, not `fs_search` or `find`)
2. Keep inputs schema-first and narrow (Pydantic BaseModel)
3. Return deterministic output shapes with status + summary + artifacts
4. Avoid catch-all tools unless isolation is impossible

## Granularity Rules

- **Micro-tools** (<50 LOC): deploy, migrate, permissions, secret rotation
- **Medium tools** (50-200 LOC): file operations, search, code generation
- **Macro-tools** (>200 LOC): only when round-trip overhead is the dominant cost

## Observation Design

Every tool response must include:
```python
@dataclass
class ToolResult:
    status: Literal["success", "warning", "error"]
    summary: str              # One-line result
    next_actions: list[str]   # Actionable follow-ups
    artifacts: list[str]      # File paths / IDs / URLs
    data: Any | None = None   # Optional payload
```

## Error Recovery Contract

For every error path, include:
- **Root cause hint**: "File not found: /path/to/file"
- **Safe retry instruction**: "Check the path and try again with an absolute path"
- **Explicit stop condition**: "If the file still doesn't exist after 3 attempts, ask the user"

## Context Budgeting

1. Keep system prompt minimal and invariant (<2000 tokens)
2. Move large guidance into skills loaded on demand
3. Prefer references to files over inlining long documents
4. Compact at phase boundaries, not arbitrary token thresholds

## Architecture Pattern Guidance

- **ReAct**: Best for exploratory tasks with uncertain paths
- **Function-calling**: Best for structured deterministic flows
- **Hybrid (recommended)**: ReAct planning + typed tool execution via LangGraph

## Benchmarking

Track these metrics for every agent:
- `completion_rate`: % of tasks completed successfully
- `retries_per_task`: avg retries before success/failure
- `pass@1` and `pass@3`: success on first/third attempt
- `cost_per_successful_task`: total token cost / successful tasks

## Anti-Patterns

- Too many tools with overlapping semantics
- Opaque tool output with no recovery hints
- Error-only output without next steps
- Context overloading with irrelevant references
- Single monolithic agent handling too many responsibilities
