# AIDLC Phase Plans — Kế hoạch triển khai chi tiết

Mỗi file trong thư mục này là một **kế hoạch thực thi chi tiết** cho một giai đoạn của AIDLC (AI Development Life Cycle). Các kế hoạch được thiết kế để tận dụng tối đa tất cả capabilities của Harness Agent framework.

## Cách sử dụng

1. **Tuần tự**: Thực hiện từ Phase 0 → Phase 8 theo thứ tự
2. **Checklist-driven**: Mỗi phase có checklist — tick từng mục khi hoàn thành
3. **Tool-aware**: Mỗi bước chỉ rõ nên dùng skill/agent/MCP/rule nào
4. **Git commit**: Commit sau mỗi phase hoàn thành với conventional commit format

## Danh sách Phase Plans

| # | Plan File | Giai đoạn | Mục tiêu chính |
|---|-----------|-----------|----------------|
| 0 | [00-foundation.md](00-foundation.md) | Foundation | Môi trường, model selection, tool inventory |
| 1 | [01-requirements.md](01-requirements.md) | Requirements & Analysis | Use case, capability mapping, requirements doc |
| 2 | [02-architecture.md](02-architecture.md) | Architecture & Design | Agent topology, middleware pipeline, backend strategy |
| 3 | [03-implementation.md](03-implementation.md) | Implementation | TDD: RED → GREEN → REFACTOR |
| 4 | [04-testing.md](04-testing.md) | Testing & QA | Unit, integration, adversarial, evaluation |
| 5 | [05-security.md](05-security.md) | Security Hardening | PII, sandbox, HITL, secrets, permissions |
| 6 | [06-deployment.md](06-deployment.md) | Deployment | CLI, Server, Docker, multi-tenant |
| 7 | [07-monitoring.md](07-monitoring.md) | Monitoring & Observability | Streaming, logging, metrics, alerting |
| 8 | [08-maintenance.md](08-maintenance.md) | Maintenance & Iteration | Memory updates, feedback loops, continuous improvement |

## Capabilities Map — Công cụ có sẵn cho mỗi phase

### Skills (gọi qua `/skill-name` hoặc `Skill` tool)

| Skill | Dùng cho Phase |
|-------|---------------|
| `agent-harness-construction` | 2, 3 — Thiết kế action space, tool definition |
| `langchain-patterns` | 2, 3, 6 — Runnable, StateGraph, MCP, memory |
| `python-patterns` | 3, 8 — PEP 8, type hints, Pythonic idioms |
| `python-testing` | 4 — pytest strategies, fixtures, coverage |
| `tdd-workflow` | 3, 4 — RED → GREEN → REFACTOR |
| `deep-research` | 1 — Multi-source research |
| `plan` | ALL — Implementation planning |
| `code-review` | 3, 8 — Code quality review |
| `python-review` | 3, 8 — Python-specific review |
| `security-scan` | 5 — Security vulnerability scan |
| `test` | 3, 4 — TDD test writing |
| `verify` | 4, 6 — Verify changes work |
| `update-config` | 0, 6 — Configure settings.json, hooks |
| `simplify` | 3, 8 — Code simplification |

### Subagents (gọi qua `Agent` tool)

| Agent | Dùng cho Phase |
|-------|---------------|
| `harness-architect` | 2 — Thiết kế agent topology, middleware pipeline |
| `planner` | ALL — Lập kế hoạch triển khai |
| `python-reviewer` | 3, 4, 8 — Review Python code |
| `code-reviewer` | 3, 4, 8 — Review code tổng quát |
| `security-reviewer` | 5 — Security audit |
| `Explore` | 1, 2, 4 — Search/explore codebase |

### MCP Tools

| MCP Server | Tool | Dùng cho Phase |
|-----------|------|---------------|
| `codegraph` | `codegraph_explore` | 1, 2, 3 — Hiểu codebase, trace flow |
| `codegraph` | `codegraph_search` | 1, 2, 3 — Tìm symbols |
| `codegraph` | `codegraph_callers` / `codegraph_callees` | 2, 3 — Impact analysis |
| `codegraph` | `codegraph_impact` | 2, 8 — Refactor impact |
| `context7` | `resolve-library-id` + `query-docs` | 0, 3, 6 — Tra cứu library docs |

### Rules (tự động áp dụng)

| Rule File | Áp dụng cho |
|-----------|------------|
| `.claude/rules/common/development-workflow.md` | Tất cả phase |
| `.claude/rules/common/git-workflow.md` | Commit, branching |
| `.claude/rules/common/security.md` | Phase 5 |
| `.claude/rules/python/coding-style.md` | Phase 3, 8 |
| `.claude/rules/python/patterns.md` | Phase 2, 3 |
| `.claude/rules/python/security.md` | Phase 5 |
| `.claude/rules/python/testing.md` | Phase 3, 4 |

### Hooks (tự động kích hoạt)

| Hook | Trigger | Mô tả |
|------|---------|-------|
| `PreToolUse` | Bash calls | Cảnh báo an toàn trước mỗi bash command |
| `PostToolUse` | Edit/Write/MultiEdit | Tự động chạy ruff check sau khi sửa file |
| `Stop` | Session stop | Tự động chạy pytest + ruff |
| `SessionStart` | Session start | Hiển thị Python/uv version |

## Tài liệu tham khảo

| Tài liệu | Nội dung |
|----------|----------|
| [AIDLC Lifecycle](../aidlc-lifecycle.md) | Quy trình tổng thể 9 giai đoạn |
| [Deep Agents README](../../deep-agents/README.md) | Tổng quan framework |
| [Overview & Architecture](../../deep-agents/01-overview-architecture.md) | Kiến trúc Deep Agents |
| [API Reference](../../deep-agents/02-api-reference.md) | `create_deep_agent()` |
| [Middleware](../../deep-agents/03-middleware.md) | 14+ middleware |
| [Backends](../../deep-agents/04-backends.md) | Hệ thống lưu trữ |
| [Subagents](../../deep-agents/05-subagents.md) | Task delegation |
| [Memory](../../deep-agents/06-memory.md) | Memory system |
| [Streaming](../../deep-agents/07-streaming.md) | Streaming & events |
| [Multi-Agent](../../deep-agents/08-multi-agent.md) | Multi-agent patterns |
| [CLI/Server](../../deep-agents/09-deepagents-code.md) | Deployment modes |
