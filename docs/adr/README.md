# Architecture Decision Records (ADRs)

> Harness Agent — Architecture decisions documented in ADR format.

## ADR Index

| ADR | Title | Status | Date | Phase |
|-----|-------|--------|------|-------|
| [001](001-agent-topology.md) | Agent Topology — Coordinator + Deep Agent Subagents | ✅ Accepted | 2026-06-18 | 2 |
| [002](002-middleware-pipeline.md) | Middleware Pipeline — 6-Layer Architecture | ✅ Accepted | 2026-06-18 | 2 |
| [003](003-backend-strategy.md) | Backend Strategy — CompositeBackend with Hybrid Routing | ✅ Accepted | 2026-06-18 | 2 |
| [004](004-subagent-topology.md) | Subagent Topology — 4 Specialized Subagents | ✅ Accepted | 2026-06-18 | 2 |
| [005](005-model-selection.md) | Model Selection — DeepSeek V4 Family Strategy | ✅ Accepted | 2026-06-18 | 2 |
| [006](006-system-prompt-architecture.md) | System Prompt Architecture — Structured Template with Memory | ✅ Accepted | 2026-06-18 | 2 |

## Deferred ADRs (Future Phases)

| ADR | Title | Target Phase | Rationale |
|-----|-------|-------------|-----------|
| 007 | Sandbox & Execution Isolation | Phase 5 (Security) | Docker sandbox config, execution boundaries, network policy, resource limits |
| 008 | Session State & Checkpointing | Phase 6 (Deployment) | Checkpointer backend selection (InMemory/SQLite/Postgres), thread lifecycle, multi-tenant scoping |
| 009 | Error Handling Contract | Phase 3 (Implementation) | Error propagation subagent→main, retry/stop conditions, observation quality metadata |
| 010 | Custom Tools Architecture | Phase 3 (Implementation) | Tool registration, Pydantic validation framework, security review checklist, middleware integration |

## ADR Lifecycle

```
Proposed → Accepted → Superseded
```

- **Proposed**: ADR đang được review
- **Accepted**: ADR đã được approved, là source of truth
- **Superseded**: ADR bị thay thế bởi ADR mới hơn (include link to new ADR)

## Format

Each ADR follows the template from [AIDLC Lifecycle §2.5](../guides/aidlc-lifecycle.md#25-architecture-decision-record-template):

```markdown
## ADR: [Tên quyết định]

### Context
### Decision
### Alternatives Considered
### Consequences
```

## References

- [AIDLC Lifecycle](../guides/aidlc-lifecycle.md) — Full development lifecycle
- [Phase 2 Plan](../guides/plans/02-architecture.md) — Architecture phase checklist
