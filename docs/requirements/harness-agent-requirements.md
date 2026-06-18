# Agent Requirements: Harness Agent

> **Phase 1: Requirements & Analysis** — AIDLC Lifecycle §1
> **Date**: 2026-06-18
> **Status**: ✅ Complete
> **Based on**: [Phase 1 Plan](../guides/plans/01-requirements.md)

---

## 1. Use Case Classification

### Agent Type: **Coordinator Agent** + **Deep Agent Subagents**

| Thuộc tính | Giá trị |
|------------|---------|
| **Loại Agent** | Coordinator Agent (Main agent + Subagents) |
| **Pattern** | Deep Agent Subagents (SubAgentMiddleware) |
| **Độ phức tạp** | High — multi-domain, multi-step, cần delegation |

### Rationale

**Tại sao Coordinator Agent thay vì Single-task Agent:**
- Harness Agent cần xử lý nhiều domain: code generation, research, code review, shell execution, file manipulation
- Một single agent sẽ bị quá tải với quá nhiều tools và responsibilities
- Cần delegation cho các chuyên gia (researcher, coder, reviewer, architect)

**Tại sao Deep Agent Subagents thay vì Multi-Agent Handoff/Router/Swarm:**
- Các task có thể chạy **độc lập và song song** — không cần handoff tuần tự giữa các agent
- Main agent đóng vai trò **coordinator**: lập kế hoạch → delegate → tổng hợp kết quả
- Subagents là **ephemeral** — không cần duy trì state giữa các lần spawn
- Pattern này tận dụng được tối đa `SubAgentMiddleware` của Deep Agents
- **Context isolation**: subagent có context riêng, không làm nhiễu main agent

**Tại sao không dùng Supervisor-Worker:**
- Supervisor-Worker phù hợp với workflow tuần tự, multi-step với centralized control
- Harness Agent cần parallel execution nhiều hơn là sequential pipeline
- SubAgentMiddleware đã cung cấp cơ chế delegation + parallel đủ mạnh

### Use Cases

1. **Code Generation & Refactoring**: User yêu cầu viết/tối ưu code → agent lập kế hoạch, spawn coder subagent
2. **Research & Synthesis**: User hỏi về công nghệ/library → agent spawn researcher subagent để tìm kiếm
3. **Code Review**: User yêu cầu review code → agent spawn reviewer subagent
4. **Architecture Design**: User cần thiết kế hệ thống → agent spawn architect subagent (dùng model mạnh hơn)
5. **Multi-step Task**: Kết hợp research → code → review trong một workflow
6. **Shell Operations**: Chạy test, lint, build — agent tự thực thi qua ShellToolMiddleware
7. **Memory & Preferences**: Agent nhớ preferences của user qua các session

---

## 2. Capability Mapping

### User Requirement → Deep Agents Capability → Implementation

```
User Requirement                    →  Deep Agents Capability              →  Implementation
────────────────────────────────────────────────────────────────────────────────────────────────────────
"Lập kế hoạch task đa bước"         →  TodoListMiddleware                   →  write_todos tool
"Đọc file trong project"            →  FilesystemMiddleware                 →  read_file tool
"Viết/sửa file"                     →  FilesystemMiddleware                 →  write_file, edit_file tools
"Tìm kiếm file/theo pattern"        →  FilesystemMiddleware                 →  glob, grep tools
"Chạy lệnh shell (test, lint...)"   →  ShellToolMiddleware                  →  execute_command tool
"Delegation cho chuyên gia"         →  SubAgentMiddleware                   →  task tool
"Nhớ preference của user"           →  MemoryMiddleware + StoreBackend      →  edit_file to /memories/
"Xử lý hội thoại dài"               →  SummarizationMiddleware              →  auto-summarize at 85% tokens
"Cần approval trước khi ghi file"   →  HumanInTheLoopMiddleware             →  interrupt_on write/exec
"Chạy code an toàn"                 →  SandboxBackend (Docker)              →  sandbox_type="docker"
"Structured output"                 →  response_format (Pydantic)           →  AnalysisResult model
"Multi-turn conversation"           →  Checkpointer + thread_id             →  InMemorySaver
"Tìm kiếm web"                      →  Custom @tool (Tavily)                →  web_search tool
"Đọc nội dung URL"                  →  Custom @tool (httpx + BS4)           →  fetch_url tool
"Thực thi Python code"              →  Custom @tool + Sandbox               →  execute_python tool
"Truy vấn database"                 →  Custom @tool (parameterized SQL)     →  query_database tool
"Phát hiện PII"                     →  PIIMiddleware                        →  auto-detect & warn
"Fallback khi model lỗi"            →  ModelFallbackMiddleware              →  retry with fallback models
"Retry tool khi fail"               →  ToolRetryMiddleware                  →  exponential backoff
"Quản lý context window"            →  ContextEditingMiddleware             →  trim old tool calls
```

### Capability Gap Analysis

| Capability | Status | Ghi chú |
|------------|--------|---------|
| File System (r/w/e/glob/grep) | ✅ Built-in | `FilesystemMiddleware` |
| Shell Execution | ✅ Built-in | `ShellToolMiddleware` |
| Task Planning | ✅ Built-in | `TodoListMiddleware` |
| Subagent Delegation | ✅ Built-in | `SubAgentMiddleware` |
| Memory (persistent) | ✅ Built-in | `MemoryMiddleware` + `StoreBackend` |
| Summarization | ✅ Built-in | `SummarizationMiddleware` |
| HITL Approval | ✅ Built-in | `HumanInTheLoopMiddleware` |
| PII Detection | ✅ Built-in | `PIIMiddleware` |
| Context Editing | ✅ Built-in | `ContextEditingMiddleware` |
| Model Fallback | ✅ Built-in | `ModelFallbackMiddleware` |
| Tool Retry | ✅ Built-in | `ToolRetryMiddleware` |
| Web Search | 🔧 Custom Needed | `@tool` using Tavily API |
| URL Fetch | 🔧 Custom Needed | `@tool` using httpx + BeautifulSoup |
| Code Execution | 🔧 Custom Needed | `@tool` + Sandbox backend |
| Database Query | 🔧 Custom Needed | `@tool` with parameterized SQL |

**No gaps** — tất cả requirements đều có capability tương ứng.

---

## 3. Subagent Identification

### Subagent Topology

```
Main Orchestrator (deepseek-v4-flash)
  │
  ├── task("researcher", "...")     → Researcher Subagent (deepseek-v4-flash)
  │     Tools: web_search, fetch_url
  │
  ├── task("coder", "...")          → Coder Subagent (deepseek-v4-pro)
  │     Tools: read_file, write_file, execute_python, execute_command
  │
  ├── task("reviewer", "...")       → Reviewer Subagent (deepseek-v4-flash)
  │     Tools: read_file, glob, grep, execute_command
  │
  └── task("architect", "...")      → Architect Subagent (deepseek-v4-pro)
        Tools: read_file, glob, grep, web_search
```

### Subagent Definitions

| Subagent | Responsibility | Tools | Model | Middleware | Rationale |
|----------|---------------|-------|-------|------------|-----------|
| **researcher** | Web research, data gathering, technology evaluation, documentation lookup | `web_search`, `fetch_url` | `deepseek-v4-flash` | `[]` | Task nặng về searching/synthesis, không cần file access |
| **coder** | Code generation, refactoring, debugging, test writing | `read_file`, `write_file`, `edit_file`, `execute_python`, `execute_command` | `deepseek-v4-pro` | `[]` | Cần reasoning mạnh nhất cho code generation; cần cả file + execution |
| **reviewer** | Code review, quality check, security scan, lint analysis | `read_file`, `glob`, `grep`, `execute_command` | `deepseek-v4-flash` | `[]` | Review cần đọc nhiều file + chạy lint tool; không cần write |
| **architect** | System design, architecture decisions, technology selection | `read_file`, `glob`, `grep`, `web_search` | `deepseek-v4-pro` | `[]` | Architecture cần deep reasoning; cần research + codebase context |

### Design Principles Compliance

- [x] **Single Responsibility**: Mỗi subagent làm MỘT việc (research, code, review, architecture)
- [x] **Independent**: Các subagent không phụ thuộc output của nhau — có thể chạy song song
- [x] **Disposable**: Ephemeral — không lưu state giữa các lần spawn
- [x] **Minimal tools**: Chỉ cấp tools cần thiết cho task đó (researcher không cần write_file)
- [x] **Clear contract**: Input/output rõ ràng qua `task` tool description

### Subagent System Prompts

**Researcher:**
```
You are a thorough researcher. For each research task:
1. Search for relevant information using web_search
2. Cross-reference multiple sources with fetch_url
3. Synthesize findings into a structured summary
4. Include citations for all claims
5. Note any conflicting information between sources
```

**Coder:**
```
You are a skilled software engineer. For each coding task:
1. Read and understand the existing codebase first
2. Follow project conventions (imports, naming, patterns)
3. Write clean, well-documented Python code with type hints
4. Test your code by executing it when possible
5. Return the complete solution with explanation
```

**Reviewer:**
```
You are a thorough code reviewer. For each review:
1. Read all changed files completely
2. Check for: bugs, security issues, style violations, performance problems
3. Run lint and type check tools when available
4. Categorize findings: CRITICAL, HIGH, MEDIUM, LOW
5. Provide specific, actionable feedback with code examples
```

**Architect:**
```
You are a senior software architect. For each architecture task:
1. Understand the requirements and constraints thoroughly
2. Research best practices and alternative approaches
3. Evaluate trade-offs: complexity vs flexibility, performance vs maintainability
4. Design clear component boundaries and interfaces
5. Document decisions with rationale (ADR format)
```

---

## 4. Memory Requirements

### Memory Architecture

```
Memory System
├── User Preferences → /memories/preferences.md (StoreBackend, user-scoped)
├── Project Context  → AGENTS.md + CLAUDE.md (MemoryMiddleware, file-based)
├── Session State    → Checkpointer + thread_id (InMemorySaver / SqliteSaver)
├── Feedback Log     → /memories/feedback.md (StoreBackend, user-scoped)
└── Temporary Data   → StateBackend (ephemeral, per-session)
```

### Memory Type Details

| Memory Type | Storage | Scope | Persistence | Ví dụ |
|------------|---------|-------|-------------|-------|
| **User Preferences** | `StoreBackend` → `/memories/preferences.md` | User-specific | Cross-session | Language, coding style, preferred tools |
| **User Feedback** | `StoreBackend` → `/memories/feedback.md` | User-specific | Cross-session | What went wrong, corrections, improvements |
| **Project Context** | `MemoryMiddleware` → `AGENTS.md`, `CLAUDE.md` | Project-specific | File-based | Conventions, architecture, deploy info |
| **Session State** | `Checkpointer` + `thread_id` | Session | Configurable | Conversation history, agent state |
| **Temporary** | `StateBackend` (default) | Ephemeral | Session only | Intermediate results, tool outputs |
| **Org Policies** | `StoreBackend` → `/policies/` | Org-level | Cross-session | Compliance rules, coding standards (future) |

### Backend Configuration

```python
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend

backend = CompositeBackend(
    default=StateBackend(),                    # Ephemeral cho mọi thứ khác
    routes={
        "/memories/": StoreBackend(
            namespace=lambda rt: [rt.server_info.user.identity],
        ),
    },
)
```

### Memory Lifecycle

1. **Agent khởi tạo** → `MemoryMiddleware` load `AGENTS.md` + `CLAUDE.md` + `/memories/*`
2. **Inject vào system prompt** → nội dung memory được bọc trong `<agent_memory>` tags
3. **Tương tác với user** → agent học preferences, feedback
4. **Ghi memory** → agent gọi `edit_file` vào `/memories/` để persist
5. **Lần invoke sau** → memory đã cập nhật được tự động load

### Memory Best Practices

- [x] Phân biệt memory types rõ ràng
- [x] Namespace isolation cho user-specific data
- [x] **KHÔNG lưu secrets** (API keys, passwords, tokens) trong memory
- [x] Memory có thể outdated — luôn verify với user request
- [x] Update promptly khi user feedback
- [x] Capture WHY, không chỉ WHAT

---

## 5. Security Requirements

### Sandbox Configuration

| Môi trường | Sandbox Type | Lý do |
|------------|-------------|-------|
| **Development** | `sandbox_type="none"` | Trusted local code, focus on speed |
| **Production** | `sandbox_type="docker"` | Isolation cho untrusted code execution |

### Human-in-the-Loop (HITL)

Các tool cần approval trước khi thực thi:

| Tool | Dev | Production | Lý do |
|------|-----|------------|-------|
| `write_file` | ❌ Auto | ✅ Approval | Tránh ghi đè file quan trọng |
| `edit_file` | ❌ Auto | ✅ Approval | Same as write |
| `execute_command` | ❌ Auto | ✅ Approval | Shell injection risk |
| `task` (subagent) | ❌ Auto | ✅ Approval | Kiểm soát resource usage |
| `execute_python` | ❌ Auto | ✅ Approval | Code execution risk |
| `web_search` | ❌ Auto | ❌ Auto | Read-only, low risk |
| `read_file` | ❌ Auto | ❌ Auto | Read-only |

### Shell Allow List

```python
# Development (permissive)
shell_allow_list = None  # Allow all

# Production (restrictive)
shell_allow_list = [
    "ls", "cat", "head", "tail",
    "grep", "find", "wc", "sort", "uniq",
    "python", "pytest", "ruff", "mypy",
    "git", "pip", "uv",
]
```

### Filesystem Permission Boundaries

```
/workspace/**  → read, write         # Project code
/data/**       → read                # Reference data
/output/**     → write               # Generated artifacts
/memories/**   → read, write         # Agent memory
/system/**     → deny                # System files
.env           → deny                # Secrets
```

### PII Detection

- [x] `PIIMiddleware` enabled trong production
- [x] Memory **KHÔNG** lưu API keys, passwords, tokens
- [x] Error messages không leak sensitive data (paths, keys, internals)

### Additional Security Measures

- [x] **Path traversal prevention**: `pathlib.Path.resolve()` + validate
- [x] **Unsafe deserialization**: Không `pickle.load()` untrusted data
- [x] **Subprocess**: List args, không shell string
- [x] **SQL injection**: Parameterized queries only
- [x] **Input validation**: Pydantic schema cho tất cả tool inputs
- [x] **Secrets management**: `os.environ` only, không hardcode
- [x] **SSRF prevention**: URL validation trong `fetch_url` tool

---

## 6. Non-Functional Requirements

### Performance

| Metric | Target | Notes |
|--------|--------|-------|
| **Latency (orchestrator response)** | < 2000ms | Tool selection + routing decision |
| **Latency (subagent completion)** | < 30000ms | Complex task; có thể song song hóa |
| **Latency (tool execution)** | < 5000ms | Shell commands, file operations |
| **Max context window** | 1M tokens | DeepSeek V4 context limit |
| **Summarization trigger** | 85% context (850K tokens) | `("fraction", 0.85)` |
| **Keep recent context** | 10% context (100K tokens) | `("fraction", 0.10)` |
| **Max output tokens** | 384K tokens | DeepSeek V4 output limit |

### Concurrency & Throughput

| Metric | Target | Notes |
|--------|--------|-------|
| **Max concurrent subagents** | 4-8 | Giới hạn bởi model concurrency (2500 QPS v4-flash) |
| **Max tool calls per turn** | 50 | `ToolCallLimitMiddleware` |
| **Max model calls per task** | 100 | `ModelCallLimitMiddleware` |
| **Rate limiting strategy** | Token bucket, per-user | TBD in Phase 6 |

### Reliability

| Metric | Target |
|--------|--------|
| **Availability** | 99.5% (development), 99.9% (production) |
| **Error rate** | < 5% tool calls |
| **Model fallback** | Auto-retry 3 lần với `ModelFallbackMiddleware` |
| **Tool retry** | Exponential backoff, max 3 retries |

### Streaming

| Feature | Status | Notes |
|---------|--------|-------|
| **Token streaming** | ✅ Yes | `stream_mode=["messages"]` — real-time token output |
| **Node updates** | ✅ Yes | `stream_mode=["updates"]` — state transitions |
| **Task events** | ✅ Yes | `stream_mode=["tasks"]` — subagent lifecycle |
| **Custom events** | ✅ Yes | `stream_mode=["custom"]` — progress events |

### Multi-Tenant

| Feature | Phase 1 | Future |
|---------|---------|--------|
| **Multi-tenant** | ❌ No | Phase 6 — `TenantAgentManager` |
| **User isolation** | N/A | Separate `StoreBackend` namespace per user |
| **Resource limits** | N/A | Per-tenant rate limiting, sandbox limits |

---

## 7. Tool Inventory (Detailed)

### Built-in Tools (from Middleware)

| Middleware | Tools Provided | Status |
|-----------|---------------|--------|
| `FilesystemMiddleware` | `read_file`, `write_file`, `edit_file`, `glob`, `grep` | ✅ Ready |
| `ShellToolMiddleware` | `execute_command` | ✅ Ready |
| `TodoListMiddleware` | `write_todos` | ✅ Ready |
| `SubAgentMiddleware` | `task` | ✅ Ready |
| `MemoryMiddleware` | `edit_file` (to `/memories/`) | ✅ Ready |
| `SummarizationMiddleware` | auto-summarize (not a tool) | ✅ Ready |
| `HumanInTheLoopMiddleware` | interrupt_on (not a tool) | ✅ Ready |
| `PIIMiddleware` | auto-detect (not a tool) | ✅ Ready |

### Custom Tools (Need Implementation)

| Tool | Category | Priority | Dependencies |
|------|----------|----------|-------------|
| `web_search` | External API | 🔧 Phase 3 | Tavily API (`TAVILY_API_KEY`) |
| `fetch_url` | External API | 🔧 Phase 3 | httpx, BeautifulSoup |
| `execute_python` | Code Execution | 🔧 Phase 3 | Sandbox backend |
| `query_database` | Data | 🔧 Phase 3+ | SQLAlchemy / psycopg2 |

---

## 8. Middleware Pipeline Design

Pipeline thứ tự cho Harness Agent:

```python
middleware = [
    # Lớp 1: Planning & Context
    TodoListMiddleware(),            # Planning — agent biết cần làm gì
    MemoryMiddleware(                # Load memory vào context
        backend=backend,
        sources=[
            "~/.deepagents/AGENTS.md",
            "./.deepagents/AGENTS.md",
            "/memories/preferences.md",
            "/memories/feedback.md",
        ],
    ),

    # Lớp 2: Security
    HumanInTheLoopMiddleware(        # Approval check
        interrupt_on={
            "write_file": True,
            "edit_file": True,
            "execute_command": True,
            "task": True,
        },
    ),
    PIIMiddleware(),                 # PII detection

    # Lớp 3: Capabilities
    FilesystemMiddleware(backend=backend),  # File operations

    # Lớp 4: Execution
    ShellToolMiddleware(),           # Shell commands
    SubAgentMiddleware(              # Task delegation
        backend=backend,
        subagents=[researcher, coder, reviewer, architect],
    ),

    # Lớp 5: Context Management
    SummarizationMiddleware(         # Auto-summarize at 85%
        model="deepseek-v4-flash",
        backend=backend,
        trigger=("fraction", 0.85),
        keep=("fraction", 0.10),
    ),
    ContextEditingMiddleware(),      # Trim old context

    # Lớp 6: Resilience
    ModelFallbackMiddleware(         # Fallback models
        fallback_models=["deepseek-v4-flash"],
        max_retries=3,
    ),
    ToolRetryMiddleware(             # Retry failed tools
        max_retries=3,
    ),
]
```

---

## 9. Model Selection Summary

| Role | Model | Rationale |
|------|-------|-----------|
| **Main Orchestrator** | `deepseek-v4-flash` | Fast tool calling, low cost ($0.14/1M input), 2500 QPS |
| **Subagent: Coder** | `deepseek-v4-pro` | Strongest reasoning (1.6T params) for code generation |
| **Subagent: Architect** | `deepseek-v4-pro` | Deep reasoning for system design decisions |
| **Subagent: Researcher** | `deepseek-v4-flash` | Searching/synthesis, cost efficient |
| **Subagent: Reviewer** | `deepseek-v4-flash` | Pattern matching, cost efficient, fast |
| **Summarization** | `deepseek-v4-flash` | 1M context, $0.28/1M output, cheap |
| **Router/Classifier** | `deepseek-v4-flash` | Structured output, fast, cheap |

---

## 10. Dependencies & Prerequisites

### Phase 0 Foundation (Complete ✅)

- [x] Python 3.11+ installed (3.12.13)
- [x] All dependencies installed (`deepagents`, `langchain`, `langgraph`, `langchain-deepseek`)
- [x] Dev tools installed (`pytest`, `ruff`, `mypy`)
- [x] `pyproject.toml` configured
- [x] Git repo initialized with conventional commits
- [x] `.claude/settings.json` configured (hooks, permissions)
- [x] MCP servers configured (codegraph, context7)
- [x] Source code initialized: `config.py`, `tools.py`, `tests/conftest.py`

### Phase 1 Deliverables

- [x] Use case classification document (this file §1)
- [x] Capability mapping table (this file §2)
- [x] Subagent definitions (this file §3)
- [x] Memory requirements (this file §4)
- [x] Security requirements (this file §5)
- [x] Non-functional requirements (this file §6)
- [x] Tool inventory detailed (this file §7)
- [x] Middleware pipeline design (this file §8)
- [x] Model selection summary (this file §9)

---

## Next Phase

→ [Phase 2: Architecture & Design](../guides/plans/02-architecture.md)

## References

| Tài liệu | Section |
|----------|---------|
| [AIDLC Lifecycle](../guides/aidlc-lifecycle.md) | §1 Requirements & Analysis |
| [Overview & Architecture](../deep-agents/01-overview-architecture.md) | Agent components |
| [Middleware](../deep-agents/03-middleware.md) | Capability → Middleware mapping |
| [Subagents](../deep-agents/05-subagents.md) | Subagent design & best practices |
| [Memory](../deep-agents/06-memory.md) | Memory architecture & backends |
| [Multi-Agent](../deep-agents/08-multi-agent.md) | Pattern selection & comparison |
| [CLI/Server](../deep-agents/09-deepagents-code.md) | Deployment modes |
