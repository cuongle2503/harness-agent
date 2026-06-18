# Phase 2: Architecture & Design Plan

> **Mục tiêu**: Thiết kế agent topology, middleware pipeline, backend strategy, và subagent network. Viết Architecture Decision Records (ADRs).

## Prerequisites

- [ ] Phase 1: Requirements hoàn thành
- [ ] Requirements document đã được viết và review
- [ ] Đã đọc [AIDLC Lifecycle §2](../aidlc-lifecycle.md#2-architecture--design)
- [ ] Đã đọc tất cả deep-agents reference docs liên quan

---

## Step-by-Step Workflow

### Step 2.1: Agent Topology Decision

**Mục tiêu**: Chọn topology pattern dựa trên use case từ Phase 1.

**Cách thực hiện**: Dùng decision tree từ [AIDLC Lifecycle §2.1](../aidlc-lifecycle.md#21-agent-topology-decision-tree)

```
Cần 1 agent xử lý tất cả?
├── YES → Single Agent + middleware
│   └── Cần isolation cho task nặng?
│       └── YES → Thêm SubAgentMiddleware
└── NO → Multi-Agent System
    ├── Domain-specific (sales/support)?
    │   └── Handoff Pattern → [Multi-Agent §Pattern 1](../../deep-agents/08-multi-agent.md#pattern-1-handoff-chuyển-giao)
    ├── Multiple knowledge sources?
    │   └── Router Pattern → [Multi-Agent §Pattern 2](../../deep-agents/08-multi-agent.md#pattern-2-router-với-multiple-knowledge-bases)
    ├── Dynamic role switching?
    │   └── Swarm Pattern → [Multi-Agent §Pattern 3](../../deep-agents/08-multi-agent.md#pattern-3-swarm-active-agent-router)
    └── Complex orchestration?
        └── Supervisor-Worker → [Multi-Agent §Pattern 4](../../deep-agents/08-multi-agent.md#pattern-4-supervisor-worker)
```

**Tools hỗ trợ**:
- **Agent `harness-architect`**: CHỦ LỰC — thiết kế topology, đánh giá trade-offs
- **Skill `langchain-patterns`**: Runnable protocol, StateGraph patterns
- **MCP `codegraph`**: `codegraph_explore` để xem topology patterns hiện có

**Output**: Topology Diagram + ADR

**Checklist**:
- [ ] Topology pattern đã được chọn
- [ ] Decision rationale documented
- [ ] Alternatives considered (ít nhất 2)
- [ ] Trade-offs analyzed
- [ ] Topology diagram created (ASCII hoặc Mermaid)
- [ ] ADR written: `docs/adr/001-agent-topology.md`

---

### Step 2.2: Middleware Pipeline Design

**Mục tiêu**: Thiết kế thứ tự middleware pipeline — quyết định kiến trúc quan trọng nhất.

**Cách thực hiện**: Dùng pipeline template từ [AIDLC Lifecycle §2.2](../aidlc-lifecycle.md#22-middleware-pipeline-design)

**Nguyên tắc sắp xếp** (từ [Middleware doc](../../deep-agents/03-middleware.md#thứ-tự-middleware)):
1. **Planning trước** — `TodoListMiddleware` để agent biết cần làm gì
2. **Context trước capabilities** — `MemoryMiddleware` load memory trước khi thực thi
3. **Security trước execution** — `HumanInTheLoopMiddleware`, `PIIMiddleware` kiểm tra trước
4. **Capabilities trước resilience** — Tools trước, retry/fallback sau
5. **Context management cuối** — `SummarizationMiddleware` summarize sau khi mọi thứ đã chạy

**Pipeline Template**:

```python
middleware = [
    # Lớp 1: Planning & Context
    TodoListMiddleware(),           # Planning trước tiên
    MemoryMiddleware(...),          # Load memory vào context

    # Lớp 2: Security
    HumanInTheLoopMiddleware(...),  # Approval check
    PIIMiddleware(),               # PII detection

    # Lớp 3: Capabilities
    FilesystemMiddleware(...),      # File operations

    # Lớp 4: Execution
    ShellToolMiddleware(...),       # Shell commands
    SubAgentMiddleware(...),        # Task delegation

    # Lớp 5: Context Management
    SummarizationMiddleware(...),   # Auto-summarize
    ContextEditingMiddleware(),     # Trim old context

    # Lớp 6: Resilience
    ModelFallbackMiddleware(...),   # Fallback models
    ToolRetryMiddleware(...),       # Retry failed tools
]
```

**Tools hỗ trợ**:
- **Agent `harness-architect`**: Review pipeline order
- **Skill `agent-harness-construction`**: Middleware selection guidance
- **MCP `codegraph`**: `codegraph_impact` để phân tích impact của middleware order

**Middleware Selection Matrix** (từ [AIDLC Lifecycle §B1](../aidlc-lifecycle.md#b1-middleware-selection)):

| Cần capability gì? | Middleware | Required? |
|--------------------|------------|-----------|
| Lập kế hoạch | `TodoListMiddleware` | ☐ |
| Đọc/ghi file | `FilesystemMiddleware` | ☐ |
| Chạy shell | `ShellToolMiddleware` | ☐ |
| Spawn subagent | `SubAgentMiddleware` | ☐ |
| Tóm tắt context | `SummarizationMiddleware` | ☐ |
| Ghi nhớ dài hạn | `MemoryMiddleware` | ☐ |
| Approval trước action | `HumanInTheLoopMiddleware` | ☐ |
| Phát hiện PII | `PIIMiddleware` | ☐ |
| Fallback model | `ModelFallbackMiddleware` | ☐ |
| Retry tool | `ToolRetryMiddleware` | ☐ |
| Giới hạn tool calls | `ToolCallLimitMiddleware` | ☐ |
| Quản lý context | `ContextEditingMiddleware` | ☐ |

**Checklist**:
- [ ] Pipeline order designed theo nguyên tắc 5 lớp
- [ ] Mỗi middleware có lý do cụ thể để included/excluded
- [ ] Middleware selection matrix completed
- [ ] Middleware parameters configured (thresholds, limits, etc.)
- [ ] Custom middleware identified (nếu cần)
- [ ] Pipeline diagram created
- [ ] ADR written: `docs/adr/002-middleware-pipeline.md`

---

### Step 2.3: Backend Strategy

**Mục tiêu**: Thiết kế hybrid backend strategy cho production.

**Cách thực hiện**: Dùng backend strategy từ [AIDLC Lifecycle §2.3](../aidlc-lifecycle.md#23-backend-strategy)

**Backend Routing Design**:

```
File path pattern:        → Backend:              → Purpose:
─────────────────────────────────────────────────────────────
/memories/*               → StoreBackend           Persistent, user-scoped
/policies/*               → StoreBackend           Persistent, org-scoped
/output/*                 → FilesystemBackend      Real disk output
/temp/*                   → StateBackend           Explicit ephemeral
/* (default)              → StateBackend           Ephemeral session
```

**Backend Selection** (từ [Backends doc](../../deep-agents/04-backends.md)):

| Cần gì? | Backend | Dùng trong plan? |
|---------|---------|-----------------|
| Temporary (1 session) | `StateBackend` | ☐ |
| Persistent, cross-session | `StoreBackend` | ☐ |
| Real file system | `FilesystemBackend` | ☐ |
| Hybrid (production) | `CompositeBackend` | ☐ |
| Code execution | Sandbox Backend (Docker) | ☐ |

**Implementation**:

```python
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend

backend = CompositeBackend(
    default=StateBackend(),
    routes={
        "/memories/": StoreBackend(
            namespace=lambda rt: [rt.server_info.user.identity],
        ),
        "/policies/": StoreBackend(
            namespace=lambda rt: [rt.context.org_id],
        ),
        "/output/": FilesystemBackend(root_dir="/data/output"),
    },
)
```

**Tools hỗ trợ**:
- **Agent `harness-architect`**: Review backend strategy
- **MCP `codegraph`**: `codegraph_explore` — backend patterns trong codebase

**Checklist**:
- [ ] Default backend selected (StateBackend)
- [ ] Persistent routes defined (/memories/, /policies/)
- [ ] Namespace factories configured (user-scoped, org-scoped)
- [ ] Sandbox backend configured (if code execution needed)
- [ ] File format selected (v2 recommended)
- [ ] Backend routing diagram created
- [ ] ADR written: `docs/adr/003-backend-strategy.md`

---

### Step 2.4: Subagent Topology

**Mục tiêu**: Thiết kế subagent network — định nghĩa từng subagent.

**Cách thực hiện**: Dùng subagent design từ [AIDLC Lifecycle §2.4](../aidlc-lifecycle.md#24-subagent-topology)

**Subagent Definition Template**:

```python
subagents = [
    {
        "name": "subagent-name",           # Unique, dùng trong task tool
        "description": "What it does...",  # Agent dùng để chọn subagent
        "system_prompt": "You are a...",   # System prompt riêng
        "tools": [tool1, tool2],           # Tools riêng (minimal)
        "model": "deepseek-v4-flash",      # Có thể khác main agent
        "middleware": [],                  # Thường để [] trừ khi cần
    },
]
```

**Subagent Design Principles** (từ [Subagents doc](../../deep-agents/05-subagents.md#best-practices)):
1. **Single Responsibility** — Mỗi subagent làm MỘT việc
2. **Independent** — Không phụ thuộc output của subagent khác
3. **Disposable** — Ephemeral, không lưu state
4. **Minimal tools** — Chỉ cấp tools cần thiết
5. **Clear contract** — Input/output rõ ràng qua task tool description

**Tools hỗ trợ**:
- **Agent `harness-architect`**: Thiết kế subagent network
- **Skill `agent-harness-construction`**: Action space design cho subagents

**Checklist**:
- [ ] Subagents defined với name, description, system_prompt
- [ ] Tools cho mỗi subagent được chọn (minimal set)
- [ ] Model cho mỗi subagent được chọn
- [ ] Middleware cho mỗi subagent configured
- [ ] Subagent design principles verified
- [ ] Subagent interaction diagram created
- [ ] ADR written: `docs/adr/004-subagent-topology.md`

---

### Step 2.5: System Prompt Architecture

**Mục tiêu**: Thiết kế system prompt có cấu trúc cho main agent và subagents.

**Cách thực hiện**: Dùng template từ [AIDLC Lifecycle §C](../aidlc-lifecycle.md#c-system-prompt-template)

```markdown
You are a {role}.

## Core Responsibilities
{responsibilities}

## Available Tools
{tool_descriptions}

## Workflow
1. {step_1}
2. {step_2}
3. {step_3}

## Quality Standards
- {standard_1}
- {standard_2}

## Output Format
{output_format}

## Constraints
- {constraint_1}
- {constraint_2}

## Memory
You have access to persistent memory at /memories/. Save important user
preferences, feedback, and learnings there for future sessions.
```

**Tools hỗ trợ**:
- **Skill `agent-harness-construction`**: Prompt engineering, context budgeting

**Checklist**:
- [ ] Main agent system prompt designed
- [ ] Subagent system prompts designed
- [ ] Prompt structure follows template
- [ ] Context budget respected (<2000 tokens cho invariant parts)
- [ ] Memory guidelines included
- [ ] Tool usage instructions clear

---

### Step 2.6: Write Architecture Decision Records

**Mục tiêu**: Document tất cả architectural decisions.

**Cách thực hiện**: Dùng ADR template từ [AIDLC Lifecycle §2.5](../aidlc-lifecycle.md#25-architecture-decision-record-template)

```markdown
## ADR: [Tên quyết định]

### Context
[Mô tả vấn đề cần giải quyết]

### Decision
[Quyết định đã chọn]

### Alternatives Considered
1. [Alternative 1] — [Pros/Cons]
2. [Alternative 2] — [Pros/Cons]

### Consequences
- Positive: [...]
- Negative: [...]
- Mitigation: [...]
```

**ADRs cần viết**:
- [ ] ADR-001: Agent Topology
- [ ] ADR-002: Middleware Pipeline
- [ ] ADR-003: Backend Strategy
- [ ] ADR-004: Subagent Topology
- [ ] ADR-005: Model Selection (từ Phase 0)
- [ ] ADR-006: System Prompt Architecture

**Tools hỗ trợ**:
- **Agent `harness-architect`**: Review tất cả ADRs
- **Agent `planner`**: Verify ADRs align với requirements

---

## Phase 2 Completion Checklist

### Topology
- [ ] Agent topology pattern selected
- [ ] Topology diagram created
- [ ] ADR-001 written

### Middleware
- [ ] Pipeline order designed (5-layer principle)
- [ ] Middleware selection matrix completed
- [ ] Pipeline diagram created
- [ ] ADR-002 written

### Backend
- [ ] Backend strategy defined (CompositeBackend)
- [ ] Routes and namespaces configured
- [ ] Backend routing diagram created
- [ ] ADR-003 written

### Subagents
- [ ] Subagent definitions complete
- [ ] Subagent interaction diagram created
- [ ] ADR-004 written

### System Prompt
- [ ] Main agent system prompt designed
- [ ] Subagent system prompts designed

### ADRs
- [ ] All 6 ADRs written
- [ ] All ADRs reviewed by `harness-architect`

### Design Review
- [ ] Full architecture review với `harness-architect` agent
- [ ] Security implications reviewed
- [ ] Performance implications reviewed
- [ ] Scalability reviewed (multi-tenant nếu cần)

---

## Next Phase

→ [Phase 3: Implementation](03-implementation.md)

## References

| Tài liệu | Section |
|----------|---------|
| [AIDLC Lifecycle](../aidlc-lifecycle.md) | §2 Architecture & Design |
| [Overview & Architecture](../../deep-agents/01-overview-architecture.md) | Full architecture |
| [Middleware](../../deep-agents/03-middleware.md) | All 14+ middleware |
| [Backends](../../deep-agents/04-backends.md) | All 5 backend types |
| [Subagents](../../deep-agents/05-subagents.md) | Subagent design patterns |
| [Memory](../../deep-agents/06-memory.md) | Memory architecture |
| [Multi-Agent](../../deep-agents/08-multi-agent.md) | 4 multi-agent patterns |
