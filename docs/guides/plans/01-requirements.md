# Phase 1: Requirements & Analysis Plan

> **Mục tiêu**: Xác định rõ use case, map requirements → capabilities, và viết requirements document cho agent.

## Prerequisites

- [ ] Phase 0: Foundation hoàn thành
- [ ] Môi trường dev sẵn sàng, model đã chọn
- [ ] Đã đọc [AIDLC Lifecycle §1](../aidlc-lifecycle.md#1-requirements--analysis)

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
- [ ] Use case đã được phân loại rõ ràng
- [ ] Agent type đã được chọn
- [ ] Pattern đã được xác định
- [ ] Rationale documented
- [ ] Đã tham khảo `harness-architect` agent (nếu cần)

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
- [ ] Tất cả user requirements đã được liệt kê
- [ ] Mỗi requirement đã được map đến capability cụ thể
- [ ] Implementation approach đã xác định cho mỗi capability
- [ ] Không có requirement nào bị bỏ sót
- [ ] Đã kiểm tra codebase hiện có (tránh trùng lặp)

---

### Step 1.3: Subagent Identification

**Mục tiêu**: Xác định các subagent cần thiết (nếu dùng Coordinator/Multi-Agent pattern).

**Cách thực hiện**: Với mỗi domain/task phức tạp, định nghĩa một subagent:

| Subagent | Responsibility | Tools Needed | Model |
|----------|---------------|-------------|-------|
| `researcher` | Web research, data synthesis | `search`, `fetch_url` | `claude-sonnet-4-6` |
| `coder` | Code generation, execution | `read_file`, `execute_python` | `claude-sonnet-4-6` |
| `reviewer` | Code review, quality check | `read_file`, `grep` | `claude-sonnet-4-6` |
| `architect` | System design decisions | `read_file`, `search` | `claude-opus-4-8` |

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
- [ ] Subagents đã được xác định (nếu cần)
- [ ] Mỗi subagent có responsibility rõ ràng
- [ ] Tools cho mỗi subagent đã được liệt kê
- [ ] Model cho mỗi subagent đã được chọn
- [ ] Subagent design principles được tuân thủ

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
- [ ] User preferences storage defined
- [ ] Project context (AGENTS.md) structure planned
- [ ] Session state persistence strategy defined
- [ ] Org-level policies defined (if multi-tenant)
- [ ] Ephemeral vs persistent storage boundaries clear

---

### Step 1.5: Security Requirements

**Mục tiêu**: Xác định security requirements ngay từ đầu.

**Cách thực hiện**: Dựa trên [AIDLC Lifecycle §5](../aidlc-lifecycle.md#5-security-hardening):

**Checklist**:
- [ ] Sandbox requirement defined (none / Docker / VM)
- [ ] HITL approval requirements listed (những tool nào cần approval)
- [ ] PII detection cần thiết?
- [ ] Shell allow list scope defined
- [ ] File system permission boundaries defined
- [ ] Multi-tenant isolation requirements (nếu có)

---

### Step 1.6: Non-Functional Requirements

**Mục tiêu**: Xác định các yêu cầu phi chức năng.

**Checklist**:
- [ ] Latency target defined (ms)
- [ ] Max context window defined (tokens)
- [ ] Streaming requirement (Yes/No)
- [ ] Multi-tenant requirement (Yes/No)
- [ ] Availability target (%)
- [ ] Rate limiting strategy

---

### Step 1.7: Write Requirements Document

**Mục tiêu**: Tổng hợp tất cả findings vào một Requirements Document.

**Cách thực hiện**: Dùng template từ [AIDLC Lifecycle §1.3](../aidlc-lifecycle.md#13-requirements-document-template)

**Tools hỗ trợ**:
- **Agent `planner`**: Review requirements document
- **Skill `plan`**: Create implementation plan từ requirements

**Output**: `docs/requirements/[agent-name]-requirements.md`

**Checklist**:
- [ ] Mục tiêu agent rõ ràng
- [ ] Use cases documented
- [ ] Tools required listed
- [ ] Subagents defined (nếu có)
- [ ] Memory requirements documented
- [ ] Security requirements documented
- [ ] Non-functional requirements documented
- [ ] Requirements document reviewed bởi `planner` agent

---

## Phase 1 Completion Checklist

### Use Case & Classification
- [ ] Use case classified (Single-task / Coordinator / Multi-Agent / Autonomous)
- [ ] Agent type selected with rationale
- [ ] Architecture pattern selected

### Capability Mapping
- [ ] All user requirements mapped to Deep Agents capabilities
- [ ] Implementation approach clear for each
- [ ] No gaps identified

### Subagents
- [ ] Subagents identified and defined (if applicable)
- [ ] Each has clear responsibility, tools, model

### Memory
- [ ] Memory types defined (preferences, context, session, policies)
- [ ] Storage backends mapped

### Security
- [ ] Sandbox, HITL, PII requirements defined
- [ ] Permission boundaries clear

### Non-Functional
- [ ] Latency, context, streaming, multi-tenant targets set

### Documentation
- [ ] Requirements document written
- [ ] Reviewed and approved

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
