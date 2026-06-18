# Phase 1: Requirements & Analysis Plan

> **Mục tiêu**: Xác định rõ use case, map requirements → capabilities, và viết requirements document cho agent.
> **Trạng thái**: ✅ Hoàn thành (2026-06-18)
> **Output**: [harness-agent-requirements.md](../../requirements/harness-agent-requirements.md)

## Prerequisites

- [x] Phase 0: Foundation hoàn thành
- [x] Môi trường dev sẵn sàng, model đã chọn
- [x] Đã đọc [AIDLC Lifecycle §1](../aidlc-lifecycle.md#1-requirements--analysis)

---

## Step-by-Step Workflow

### Step 1.1: Use Case Classification

**Mục tiêu**: Xác định loại agent cần xây dựng → quyết định architecture pattern.

**Cách thực hiện**: Dùng classification framework từ [AIDLC Lifecycle §1.1](../aidlc-lifecycle.md#11-use-case-classification)

| Agent Type | Pattern | Khi nào dùng |
|------------|---------|-------------|
| **Single-task Agent** | 1 agent + tools | Task đơn giản, 1 domain |
| **Coordinator Agent** | Main agent + subagents | Cần delegation, multi-step |
| **Multi-Agent System** | Handoff / Router / Swarm | Nhiều domain, dynamic routing |
| **Autonomous Agent** | Deep Agent + Sandbox + Memory | Tự động hoàn toàn, dài hạn |

**Tools hỗ trợ**:
- **Agent `harness-architect`**: Tư vấn chọn pattern dựa trên use case
- **Skill `deep-research`**: Research similar agent implementations
- **MCP `codegraph`**: `codegraph_explore` để tìm patterns trong codebase hiện có

**Output**: Use Case Classification Document

```markdown
## Agent Classification: [Tên dự án]

### Loại Agent
[Single-task / Coordinator / Multi-Agent / Autonomous]

### Lý do
- [Lý do 1]
- [Lý do 2]

### Pattern sẽ dùng
[ReAct / Function-calling / Hybrid / Handoff / Router / Swarm / Supervisor-Worker]
```

**Checklist**:
- [x] Use case đã được phân loại rõ ràng
- [x] Agent type đã được chọn
- [x] Pattern đã được xác định
- [x] Rationale documented
- [x] Đã tham khảo `harness-architect` agent (nếu cần)

---

### Step 1.2: Capability Mapping

**Mục tiêu**: Map từng user requirement → Deep Agents capability cụ thể.

**Cách thực hiện**: Dùng bảng mapping từ [AIDLC Lifecycle §1.2](../aidlc-lifecycle.md#12-capability-mapping)

```
User Requirement          →  Deep Agents Capability          →  Implementation
─────────────────────────────────────────────────────────────────────────────────
"Lên kế hoạch task"       →  TodoListMiddleware               →  write_todos tool
"Đọc/ghi file"            →  FilesystemMiddleware             →  read_file, write_file...
"Chạy command"            →  ShellToolMiddleware              →  execute_command
"Delegation cho expert"   →  SubAgentMiddleware               →  task tool
"Nhớ preference"          →  MemoryMiddleware + StoreBackend  →  /memories/*
"Xử lý context dài"       →  SummarizationMiddleware          →  auto-summarize
"Cần approval"            →  HumanInTheLoopMiddleware         →  interrupt_on
"Code trong sandbox"      →  SandboxBackend (Docker)          →  sandbox_type="docker"
"Structured output"       →  response_format (Pydantic)       →  AnalysisResult
"Multi-turn conversation" →  Checkpointer + thread_id         →  InMemorySaver
```

**Tools hỗ trợ**:
- **MCP `codegraph`**: `codegraph_search` để kiểm tra capability đã có trong codebase chưa
- **Skill `langchain-patterns`**: Runnable protocol, tool definition patterns
- **Skill `agent-harness-construction`**: Action space design

**Output**: Capability Mapping Table

**Checklist**:
- [x] Tất cả user requirements đã được liệt kê
- [x] Mỗi requirement đã được map đến capability cụ thể
- [x] Implementation approach đã xác định cho mỗi capability
- [x] Không có requirement nào bị bỏ sót
- [x] Đã kiểm tra codebase hiện có (tránh trùng lặp)

---

### Step 1.3: Subagent Identification

**Mục tiêu**: Xác định các subagent cần thiết (nếu dùng Coordinator/Multi-Agent pattern).

**Cách thực hiện**: Với mỗi domain/task phức tạp, định nghĩa một subagent:

| Subagent | Responsibility | Tools Needed | Model |
|----------|---------------|-------------|-------|
| `researcher` | Web research, data synthesis | `search`, `fetch_url` | `deepseek-v4-flash` |
| `coder` | Code generation, execution | `read_file`, `execute_python` | `deepseek-v4-flash` |
| `reviewer` | Code review, quality check | `read_file`, `grep` | `deepseek-v4-flash` |
| `architect` | System design decisions | `read_file`, `search` | `deepseek-v4-pro` |

**Tools hỗ trợ**:
- **Agent `harness-architect`**: Thiết kế subagent topology
- **Skill `agent-harness-construction`**: Subagent design principles

**Design Principles** (từ [Subagents doc](../../deep-agents/05-subagents.md)):
1. **Single Responsibility** — mỗi subagent làm MỘT việc
2. **Independent** — không phụ thuộc output của subagent khác
3. **Disposable** — ephemeral, không lưu state
4. **Minimal tools** — chỉ cấp tools cần thiết
5. **Clear contract** — input/output rõ ràng

**Checklist**:
- [x] Subagents đã được xác định (nếu cần)
- [x] Mỗi subagent có responsibility rõ ràng
- [x] Tools cho mỗi subagent đã được liệt kê
- [x] Model cho mỗi subagent đã được chọn
- [x] Subagent design principles được tuân thủ

---

### Step 1.4: Memory Requirements

**Mục tiêu**: Xác định loại memory cần thiết.

**Cách thực hiện**: Dựa trên [Memory doc](../../deep-agents/06-memory.md):

| Memory Type | Storage | Scope | Ví dụ |
|------------|---------|-------|-------|
| **User Preferences** | `StoreBackend` → `/memories/` | User-specific | Language preference, coding style |
| **Project Context** | `AGENTS.md` | Project-specific | Conventions, architecture, deploy info |
| **Session State** | `Checkpointer` + `thread_id` | Session | Conversation history |
| **Org Policies** | `StoreBackend` → `/policies/` | Org-level | Compliance rules, coding standards |
| **Temporary** | `StateBackend` (default) | Ephemeral | Intermediate results |

**Tools hỗ trợ**:
- **MCP `codegraph`**: `codegraph_explore` — tìm memory patterns hiện có

**Checklist**:
- [x] User preferences storage defined
- [x] Project context (AGENTS.md) structure planned
- [x] Session state persistence strategy defined
- [x] Org-level policies defined (if multi-tenant)
- [x] Ephemeral vs persistent storage boundaries clear

---

### Step 1.5: Security Requirements

**Mục tiêu**: Xác định security requirements ngay từ đầu.

**Cách thực hiện**: Dựa trên [AIDLC Lifecycle §5](../aidlc-lifecycle.md#5-security-hardening):

**Checklist**:
- [x] Sandbox requirement defined (none / Docker / VM)
- [x] HITL approval requirements listed (những tool nào cần approval)
- [x] PII detection cần thiết?
- [x] Shell allow list scope defined
- [x] File system permission boundaries defined
- [x] Multi-tenant isolation requirements (nếu có)

---

### Step 1.6: Non-Functional Requirements

**Mục tiêu**: Xác định các yêu cầu phi chức năng.

**Checklist**:
- [x] Latency target defined (ms)
- [x] Max context window defined (tokens)
- [x] Streaming requirement (Yes/No)
- [x] Multi-tenant requirement (Yes/No)
- [x] Availability target (%)
- [x] Rate limiting strategy

---

### Step 1.7: Write Requirements Document

**Mục tiêu**: Tổng hợp tất cả findings vào một Requirements Document.

**Cách thực hiện**: Dùng template từ [AIDLC Lifecycle §1.3](../aidlc-lifecycle.md#13-requirements-document-template)

**Tools hỗ trợ**:
- **Agent `planner`**: Review requirements document
- **Skill `plan`**: Create implementation plan từ requirements

**Output**: `docs/requirements/harness-agent-requirements.md` ✅

**Checklist**:
- [x] Mục tiêu agent rõ ràng
- [x] Use cases documented
- [x] Tools required listed
- [x] Subagents defined (nếu có)
- [x] Memory requirements documented
- [x] Security requirements documented
- [x] Non-functional requirements documented
- [x] Requirements document reviewed bởi `planner` agent

---

## Phase 1 Completion Checklist

### Use Case & Classification
- [x] Use case classified (Coordinator Agent + Deep Agent Subagents)
- [x] Agent type selected with rationale
- [x] Architecture pattern selected

### Capability Mapping
- [x] All user requirements mapped to Deep Agents capabilities
- [x] Implementation approach clear for each
- [x] No gaps identified

### Subagents
- [x] Subagents identified and defined (researcher, coder, reviewer, architect)
- [x] Each has clear responsibility, tools, model

### Memory
- [x] Memory types defined (preferences, context, session, policies)
- [x] Storage backends mapped

### Security
- [x] Sandbox, HITL, PII requirements defined
- [x] Permission boundaries clear

### Non-Functional
- [x] Latency, context, streaming, multi-tenant targets set

### Documentation
- [x] Requirements document written (harness-agent-requirements.md)
- [x] Reviewed and approved

---

## Next Phase

→ [Phase 2: Architecture & Design](02-architecture.md)

## References

| Tài liệu | Section |
|----------|---------|
| [AIDLC Lifecycle](../aidlc-lifecycle.md) | §1 Requirements & Analysis |
| [Overview & Architecture](../../deep-agents/01-overview-architecture.md) | Agent components |
| [Middleware](../../deep-agents/03-middleware.md) | Capability → Middleware mapping |
| [Subagents](../../deep-agents/05-subagents.md) | Subagent design |
| [Memory](../../deep-agents/06-memory.md) | Memory architecture |
| [Multi-Agent](../../deep-agents/08-multi-agent.md) | Pattern selection |
