# Phase 2 Extension: `.harness/` Convention Loaders

> **Mục tiêu**: Xây dựng hệ thống loader cho phép mỗi dự án tự định nghĩa skills, rules, subagents, hooks thông qua folder `.harness/`. Harness chỉ là loader + runtime — không hardcode bất kỳ skill/rule/subagent/hook nào.
> **Trạng thái**: 📋 Planning — chờ review
> **Ngày**: 2026-06-23

## Vấn đề cần giải quyết

Phase 2 hiện tại đã thiết kế topology, middleware pipeline, backend strategy, và 4 subagents cố định. Tuy nhiên:

- Skills/rules/subagents/hooks bị **hardcode** trong codebase — không thể thay đổi theo từng dự án
- Mỗi dự án có nhu cầu khác nhau: dự án Python cần skill khác dự án TypeScript, subagent khác nhau, hooks khác nhau
- Người dùng không có cơ chế để tự thêm skill/rule/subagent/hook cho dự án của họ

## Giải pháp: `.harness/` Convention

Mỗi dự án có một folder `.harness/` với cấu trúc chuẩn. Harness **chỉ đọc** — không tự sinh:

```
my-project/
├── .harness/                    # ← Harness đọc folder này khi khởi tạo
│   ├── config.yaml              #   Cấu hình model, backend, middleware order
│   ├── skills/                  #   Skill files (.md) do người dùng viết
│   │   ├── deploy-to-k8s.md
│   │   └── db-migration.md
│   ├── rules/                   #   Rule files (.md) agent phải tuân theo
│   │   ├── api-naming.md
│   │   └── security-policy.md
│   ├── subagents/               #   Sub-agent definitions (.yaml)
│   │   ├── code-reviewer.yaml
│   │   └── api-tester.yaml
│   └── hooks/                   #   Hook scripts (.sh hoặc .py)
│       ├── pre-commit.sh
│       └── pre_tool_call.py
├── src/
├── tests/
└── pyproject.toml
```

## Kiến trúc tổng thể

```
┌──────────────────────────────────────────────────────────────────┐
│                      HarnessBuilder                               │
│                                                                   │
│  project_root = Path("my-project/")                              │
│                                                                   │
│  ┌──────────────────┐  ┌──────────────────────────────────────┐ │
│  │ ConfigLoader      │  │ Đọc .harness/config.yaml             │ │
│  │ → HarnessConfig   │  │ → model, backend, middleware order   │ │
│  └──────────────────┘  └──────────────────────────────────────┘ │
│                                                                   │
│  ┌──────────────────┐  ┌──────────────────────────────────────┐ │
│  │ SkillLoader       │  │ Quét .harness/skills/*.md            │ │
│  │ → list[path]      │  │ → đưa vào MemoryMiddleware.sources   │ │
│  └──────────────────┘  └──────────────────────────────────────┘ │
│                                                                   │
│  ┌──────────────────┐  ┌──────────────────────────────────────┐ │
│  │ RuleLoader        │  │ Quét .harness/rules/*.md             │ │
│  │ → list[path]      │  │ → đưa vào MemoryMiddleware.sources   │ │
│  └──────────────────┘  └──────────────────────────────────────┘ │
│                                                                   │
│  ┌──────────────────┐  ┌──────────────────────────────────────┐ │
│  │ SubAgentLoader    │  │ Parse .harness/subagents/*.yaml      │ │
│  │ → list[dict]      │  │ → resolve tools → register vào       │ │
│  │                   │  │   SubAgentMiddleware                  │ │
│  └──────────────────┘  └──────────────────────────────────────┘ │
│                                                                   │
│  ┌──────────────────┐  ┌──────────────────────────────────────┐ │
│  │ HookLoader        │  │ Quét .harness/hooks/*.{sh,py}        │ │
│  │ + EventBus        │  │ → đăng ký vào event bus              │ │
│  │                   │  │ → fire khi event trigger              │ │
│  └──────────────────┘  └──────────────────────────────────────┘ │
│                                                                   │
│                           ▼                                       │
│                  create_deep_agent(...)                           │
└──────────────────────────────────────────────────────────────────┘
```

## Danh sách Plan Files

| # | Plan File | Thành phần | Package |
|---|-----------|-----------|---------|
| 1 | [01-config-loader.md](01-config-loader.md) | ConfigLoader + HarnessConfig | `src/harness_agent/loaders/config_loader.py` |
| 2 | [02-skill-loader.md](02-skill-loader.md) | SkillLoader | `src/harness_agent/loaders/skill_loader.py` |
| 3 | [03-rule-loader.md](03-rule-loader.md) | RuleLoader | `src/harness_agent/loaders/rule_loader.py` |
| 4 | [04-subagent-loader.md](04-subagent-loader.md) | SubAgentLoader | `src/harness_agent/loaders/subagent_loader.py` |
| 5 | [05-hook-loader.md](05-hook-loader.md) | HookLoader + EventBus | `src/harness_agent/loaders/hook_loader.py` |
| 6 | [06-harness-builder.md](06-harness-builder.md) | HarnessBuilder + Integration | `src/harness_agent/loaders/__init__.py` |

## Deep Agents Docs Integration

Mỗi loader được thiết kế dựa trên một phần cụ thể của deep-agents framework:

| Loader | Deep Agents Doc | Cơ chế tích hợp |
|--------|---------------|-----------------|
| SkillLoader | `06-memory.md` | `MemoryMiddleware.sources` — inject vào system prompt |
| RuleLoader | `06-memory.md` | `MemoryMiddleware.sources` — inject vào system prompt |
| SubAgentLoader | `05-subagents.md` | `SubAgentMiddleware(subagents=[...])` — register subagent definitions |
| HookLoader | Custom (không có built-in) | EventBus riêng — fire trước/sau tool calls, LLM calls, session events |
| ConfigLoader | `03-middleware.md`, `04-backends.md` | Cấu hình middleware order + backend routes |

## Quy tắc chung cho tất cả loader

1. **Fail gracefully**: Nếu `.harness/` không tồn tại, loader trả về default/empty — không crash
2. **Validate early**: Parse error ở file YAML phải raise rõ ràng với path + line
3. **Không mutate**: Loader chỉ đọc, không bao giờ ghi vào `.harness/`
4. **Resolver pattern**: Loader resolve references (tool names → tool objects, middleware names → instances)
5. **Type hints mandatory**: Mọi public method phải có type hints đầy đủ
6. **Unit test trước**: Mỗi loader phải có test với fixture `.harness/` giả lập

## Implementation Order (khuyến nghị)

```
1. ConfigLoader   ← Foundation (các loader khác cần config)
2. SubAgentLoader ← Phức tạp nhất (resolve tools, middleware)
3. HookLoader     ← Cần EventBus (component mới)
4. SkillLoader    ← Đơn giản (chỉ quét file .md)
5. RuleLoader     ← Đơn giản (giống SkillLoader)
6. HarnessBuilder ← Kết nối tất cả
```

## References

| Tài liệu | Section |
|----------|---------|
| [Phase 2: Architecture & Design](../plans/02-architecture.md) | Current Phase 2 plan |
| [Deep Agents Subagents](../../deep-agents/05-subagents.md) | SubAgentMiddleware + task tool |
| [Deep Agents Memory](../../deep-agents/06-memory.md) | MemoryMiddleware + sources |
| [Deep Agents Middleware](../../deep-agents/03-middleware.md) | 14+ middleware có sẵn |
| [Deep Agents Backends](../../deep-agents/04-backends.md) | Backend routing |
| [AIDLC Lifecycle](../aidlc-lifecycle.md) | §2 Architecture & Design |
| [ADR-004: Subagent Topology](../../adr/004-subagent-topology.md) | Current subagent definitions |
| [ADR-006: System Prompt Architecture](../../adr/006-system-prompt-architecture.md) | System prompt structure |
