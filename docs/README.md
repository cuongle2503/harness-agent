# Harness Agent — Documentation

## What's Implemented

A Python agent framework built on LangChain with optional `deepagents` integration.

### Core
- **HarnessAgent** — LangChain `Runnable` with tool-calling loop (sync + async)
- **HarnessBuilder** — Loads `.harness/` config, builds agent (graph path or enhanced fallback)
- **CLIAgent** — Interactive REPL with streaming, slash commands, conversation persistence

### Modules
- **Loaders** — ConfigLoader, SkillLoader, RuleLoader, SubAgentLoader, HookLoader
- **Tools** — ToolRegistry + built-in tools (file, code, search, skill, task)
- **Memory** — HybridMemory (in-memory KV store)
- **Security** — HITL, permissions, PII, sandbox, subprocess safety
- **Monitoring** — Stream events, metrics, alerts, tracing
- **Deployment** — CLI, HTTP server, multi-tenant

## Docs

| File | Purpose |
|------|---------|
| [deep-agents-reference.md](deep-agents-reference.md) | API reference for the external `deepagents` library |
| [architecture-decisions.md](architecture-decisions.md) | Key design decisions with rationale (ADRs) |

## Running

```bash
uv run harness-agent          # Interactive CLI
uv run harness-agent --serve  # HTTP server
```
