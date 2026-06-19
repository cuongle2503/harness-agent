# Project Context

> Project-specific context that evolves as the codebase grows.
> Updated: 2026-06-19

## Current State
- **Version**: 0.1.0 (initial development)
- **Phase**: 8 — Maintenance & Iteration (AIDLC complete)
- **Python**: 3.11+
- **Framework**: LangChain + LangGraph + Deep Agents

## Tech Stack
| Component | Technology |
|-----------|-----------|
| Language | Python 3.11+ |
| Agent Framework | LangChain (Runnable protocol) |
| Orchestration | LangGraph (StateGraph) |
| Memory | HybridMemory (KV + Vector + Buffer) |
| Model | DeepSeek V4 |
| Package Manager | uv |
| Linting | ruff |
| Type Checking | mypy + pyright |
| Testing | pytest + pytest-asyncio |
| CI/CD | GitHub Actions |

## Key Dependencies
- `langchain-core` — Base agent framework
- `langgraph` — State machine orchestration
- `deepagents` — Deep Agent backend support
- `fastapi` + `uvicorn` — API server
- `pydantic` — Data validation

## Architecture Decisions (ADRs)
- **ADR-001**: LangChain Runnable protocol for agent interface
- **ADR-002**: Hybrid memory (KV + vector) over pure vector store
- **ADR-003**: CompositeBackend with store routing for multi-tenant isolation

## File Layout
```
src/harness_agent/
├── agents/          # Agent subtypes (research, code)
├── core/            # Agent core, exceptions, orchestrator
├── deployment/      # CLI, server, multi-tenant
├── evaluation/      # Evaluator, A/B testing
├── memory/          # Hybrid memory + backends
├── middleware/       # Custom middleware
├── monitoring/      # Metrics, alerts, streaming, tracing
├── prompts/         # Prompt templates
├── security/        # HITL, PII, sandbox, permissions
└── tools/           # Tool registry, file/code/search tools
```

## Next Iteration
- Full cosine-similarity vector retrieval
- Additional agent subtypes (reviewer, planner)
- Enhanced MCP tool integration
- Production deployment hardening
