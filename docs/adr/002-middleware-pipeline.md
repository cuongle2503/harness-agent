# ADR-002: Middleware Pipeline — 6-Layer Architecture

> **Status**: ✅ Accepted
> **Date**: 2026-06-18
> **Phase**: 2 — Architecture & Design
> **Deciders**: harness-architect agent

---

## Context

Middleware pipeline là quyết định kiến trúc quan trọng nhất trong Deep Agents. Thứ tự middleware quyết định thứ tự thực thi và ảnh hưởng đến mọi khía cạnh của agent: planning, security, capabilities, context management, và resilience.

Cần thiết kế pipeline order tối ưu cho Harness Agent — một Coordinator Agent với 4 subagents, cần planning, file operations, shell execution, memory, HITL, summarization, và resilience.

## Decision

**Chọn 6-layer middleware pipeline** — mỗi layer có vai trò rõ ràng, xếp theo nguyên tắc: Planning → Security → Capabilities → Execution → Context Management → Resilience.

```python
middleware = [
    # ═══════════════════════════════════════════════════════════
    # LỚP 1: PLANNING & CONTEXT
    # Mục đích: Agent biết cần làm gì và có đầy đủ context
    # ═══════════════════════════════════════════════════════════
    TodoListMiddleware(),            # write_todos tool — lập kế hoạch
    MemoryMiddleware(                # Load memory vào system prompt
        backend=backend,
        sources=[
            "~/.deepagents/AGENTS.md",
            "./.deepagents/AGENTS.md",
            "/memories/preferences.md",
            "/memories/feedback.md",
        ],
    ),

    # ═══════════════════════════════════════════════════════════
    # LỚP 2: SECURITY
    # Mục đích: Chặn hành vi nguy hiểm TRƯỚC khi thực thi
    # ═══════════════════════════════════════════════════════════
    HumanInTheLoopMiddleware(        # Approval cho tool nguy hiểm
        interrupt_on={
            "write_file": True,
            "edit_file": True,
            "execute_command": True,
            "task": True,            # Spawn subagent cũng cần approval
        },
    ),
    PIIMiddleware(),                 # Phát hiện PII trong input/output

    # ═══════════════════════════════════════════════════════════
    # LỚP 3: CAPABILITIES
    # Mục đích: Cung cấp foundational tools
    # ═══════════════════════════════════════════════════════════
    FilesystemMiddleware(            # File tools: read, write, edit, glob, grep
        backend=backend,
    ),

    # ═══════════════════════════════════════════════════════════
    # LỚP 4: EXECUTION
    # Mục đích: Công cụ thực thi và delegation
    # ═══════════════════════════════════════════════════════════
    ShellToolMiddleware(           # Persistent shell session
        # Development: allow all (no restrictions)
        # Production: restrict to allow list
        shell_allow_list=[
            "ls", "cat", "head", "tail",
            "grep", "find", "wc", "sort", "uniq",
            "python", "pytest", "ruff", "mypy",
            "git", "pip", "uv",
        ],
    ),
    SubAgentMiddleware(              # task tool — spawn subagents
        backend=backend,
        subagents=[researcher, coder, reviewer, architect],
    ),

    # ═══════════════════════════════════════════════════════════
    # LỚP 5: CONTEXT MANAGEMENT
    # Mục đích: Quản lý context window, tránh overflow
    # ═══════════════════════════════════════════════════════════
    SummarizationMiddleware(         # Auto-summarize at 85% tokens
        model=summarization_model,
        backend=backend,
        trigger=("fraction", 0.85),
        keep=("fraction", 0.10),
    ),
    ContextEditingMiddleware(),      # Trim old tool calls/results

    # ═══════════════════════════════════════════════════════════
    # LỚP 6: RESILIENCE
    # Mục đích: Phục hồi khi có lỗi
    # ═══════════════════════════════════════════════════════════
    ModelFallbackMiddleware(         # Fallback model khi primary fail
        fallback_models=["deepseek-v4-flash"],
        max_retries=3,
    ),
    ToolRetryMiddleware(             # Retry tool calls với backoff
        max_retries=3,
    ),
]
```

### Pipeline Flow Diagram

```
REQUEST ═══════════════════════════════════════════════▶ RESPONSE
  │                                                       ▲
  ▼                                                       │
┌─────────────────────────────────────────────────────────┴──┐
│ Layer 1: Planning & Context                                 │
│ ┌─────────────────┐  ┌──────────────────┐                  │
│ │ TodoListMiddleware│─▶│ MemoryMiddleware │                  │
│ │ (write_todos)    │  │ (AGENTS.md, prefs)│                 │
│ └─────────────────┘  └──────────────────┘                  │
├────────────────────────────────────────────────────────────┤
│ Layer 2: Security                                           │
│ ┌──────────────────────┐  ┌──────────────┐                 │
│ │ HumanInTheLoop        │─▶│ PIIMiddleware │                 │
│ │ (approval check)      │  │ (PII detect)  │                 │
│ └──────────────────────┘  └──────────────┘                 │
├────────────────────────────────────────────────────────────┤
│ Layer 3: Capabilities                                       │
│ ┌──────────────────────────┐                                │
│ │ FilesystemMiddleware      │                               │
│ │ (read,write,edit,glob,grep)│                              │
│ └──────────────────────────┘                                │
├────────────────────────────────────────────────────────────┤
│ Layer 4: Execution                                          │
│ ┌──────────────────┐  ┌─────────────────────┐              │
│ │ ShellToolMiddleware│─▶│ SubAgentMiddleware   │              │
│ │ (execute_command) │  │ (task spawner)       │              │
│ └──────────────────┘  └─────────────────────┘              │
├────────────────────────────────────────────────────────────┤
│ Layer 5: Context Management                                 │
│ ┌───────────────────────┐  ┌────────────────────────┐      │
│ │ SummarizationMiddleware │─▶│ ContextEditingMiddleware │      │
│ │ (auto-compact at 85%)  │  │ (trim old context)      │      │
│ └───────────────────────┘  └────────────────────────┘      │
├────────────────────────────────────────────────────────────┤
│ Layer 6: Resilience                                         │
│ ┌─────────────────────┐  ┌──────────────────┐              │
│ │ ModelFallbackMiddleware│─▶│ ToolRetryMiddleware│              │
│ │ (fallback models)    │  │ (exponential backoff)│           │
│ └─────────────────────┘  └──────────────────┘              │
└────────────────────────────────────────────────────────────┘
```

### Middleware Selection Matrix

| Middleware | Included | Rationale |
|-----------|----------|-----------|
| `TodoListMiddleware` | ✅ Required | Multi-step task cần planning |
| `MemoryMiddleware` | ✅ Required | User preferences, feedback, project context |
| `HumanInTheLoopMiddleware` | ✅ Required | Approval cho write/exec/subagent |
| `PIIMiddleware` | ✅ Required | Phát hiện PII trong production |
| `FilesystemMiddleware` | ✅ Required | Core capability — đọc/ghi file |
| `ShellToolMiddleware` | ✅ Required | Chạy test, lint, git commands |
| `SubAgentMiddleware` | ✅ Required | Core pattern — delegation |
| `SummarizationMiddleware` | ✅ Required | 1M context, cần auto-compact |
| `ContextEditingMiddleware` | ✅ Required | Trim old tool calls |
| `ModelFallbackMiddleware` | ✅ Required | Resilience khi model fail |
| `ToolRetryMiddleware` | ✅ Required | Retry tool calls với backoff |
| `ToolCallLimitMiddleware` | ⬜ Future | Thêm trong Phase 5 (production hardening) |
| `ModelCallLimitMiddleware` | ⬜ Future | Thêm trong Phase 5 |
| `LLMToolSelectorMiddleware` | ⬜ Not needed | SubAgentMiddleware đã routing tốt hơn |
| `LLMToolEmulator` | ⬜ Testing only | Chỉ dùng trong test suite |
| `FilesystemFileSearchMiddleware` | ⬜ Redundant | FilesystemMiddleware đã có glob/grep |

## Alternatives Considered

### 1. Flat middleware order (không phân layer) (Rejected)

**Mô tả**: Đặt tất cả middleware theo thứ tự import, không phân layer rõ ràng.

**Pros**: Đơn giản

**Cons**:
- Không rõ ràng về dependency giữa các middleware
- Dễ mắc lỗi thứ tự (vd: Summarization trước SubAgent → context bị summarize trước khi subagent chạy)
- Khó maintain khi thêm middleware mới

**Lý do reject**: Với 11 middleware, cần tổ chức rõ ràng để tránh sai thứ tự.

### 2. Security-first order (Rejected)

**Mô tả**: Đặt Security layer lên đầu tiên trước Planning.

**Pros**:
- Security check ngay từ đầu
- Chặn được input độc hại trước khi xử lý

**Cons**:
- Agent chưa có plan để biết cần làm gì → security check không có context
- Memory chưa được load → không biết user permissions
- PII check trên memory chưa load là vô ích

**Lý do reject**: Planning & Context phải có trước Security. Agent cần biết mình đang làm gì và có context gì trước khi security checks.

### 3. Resilience-first order (Rejected)

**Mô tả**: Đặt ModelFallback và ToolRetry ở đầu pipeline.

**Pros**: Mọi thứ đều có retry ngay từ đầu

**Cons**:
- Retry trên tool call khi chưa có HITL approval → retry không kiểm soát
- ModelFallback trước khi Summarization → context overflow gây fallback không cần thiết
- Vi phạm nguyên tắc "capabilities trước resilience"

**Lý do reject**: Resilience là lớp bảo vệ cuối cùng, phải ở cuối pipeline.

## Consequences

### Positive
- ✅ **Rõ ràng về dependency**: Mỗi layer phụ thuộc vào layer trước đó, không phụ thuộc ngược
- ✅ **An toàn**: Security check trước khi capabilities và execution chạy
- ✅ **Hiệu quả**: Context được quản lý tự động (summarize + trim)
- ✅ **Mạnh mẽ**: Resilience layer đảm bảo agent không fail hoàn toàn
- ✅ **Dễ maintain**: Thêm middleware mới chỉ cần xác định layer phù hợp
- ✅ **Theo best practices**: Tuân thủ nguyên tắc từ Deep Agents docs

### Negative
- ⚠️ **11 middleware** — pipeline dài, mỗi request qua 11 lớp
- ⚠️ **HITL overhead**: Production cần approval cho 4 tool types → có thể chậm
- ⚠️ **Memory load time**: Load AGENTS.md + memory files trước mỗi request

### Mitigation
- **Pipeline length**: Deep Agents optimized cho middleware pipeline — overhead không đáng kể
- **HITL overhead**: Development mode auto-approve, chỉ bật HITL trong production
- **Memory load time**: Cache memory content trong store, chỉ reload khi file thay đổi

---

## Custom Middleware (Future)

Các middleware tùy chỉnh có thể cần trong tương lai:

| Middleware | Purpose | Priority |
|-----------|---------|----------|
| `StructuredLoggingMiddleware` | JSON logging cho mọi tool call | Phase 7 |
| `MetricsMiddleware` | Ghi nhận latency, token usage | Phase 7 |
| `RateLimitMiddleware` | Rate limiting per user/tenant | Phase 6 |
| `CacheMiddleware` | Cache LLM responses cho FAQ | Phase 8 |

---

## References

- [AIDLC Lifecycle §2.2](../guides/aidlc-lifecycle.md#22-middleware-pipeline-design)
- [Deep Agents Middleware](../deep-agents/03-middleware.md)
- [Middleware Thứ tự](../deep-agents/03-middleware.md#thứ-tự-middleware)
- [Harness Agent Requirements §8](../requirements/harness-agent-requirements.md#8-middleware-pipeline-design)
