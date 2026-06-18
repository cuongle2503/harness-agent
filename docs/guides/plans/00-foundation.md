# Phase 0: Foundation Plan

> **Mục tiêu**: Chuẩn bị môi trường phát triển, chọn model, kiểm kê tools — nền tảng vững chắc trước khi bắt đầu xây dựng agent.

## Prerequisites

- [ ] Đã đọc [AIDLC Lifecycle](../aidlc-lifecycle.md)
- [ ] Đã đọc [Deep Agents README](../../deep-agents/README.md)
- [ ] Đã hiểu tổng quan 9 giai đoạn AIDLC

---

## Step-by-Step Workflow

### Step 0.1: Environment Setup

**Mục tiêu**: Cài đặt Python 3.11+ và tất cả dependencies.

**Cách thực hiện**:
```bash
# Kiểm tra Python version (đã có hook SessionStart tự động)
python3 --version  # Phải >= 3.11

# Cài đặt dependencies với uv
uv sync --extra dev
uv pip install deepagents langchain langgraph langchain-deepseek
uv pip install deepagents-code  # Cho CLI/Server mode

# Dev dependencies
uv pip install pytest pytest-asyncio pytest-cov ruff mypy
```

**Tools hỗ trợ**:
- **Hook `SessionStart`**: Tự động hiển thị Python/uv version khi bắt đầu session
- **Rule**: `.claude/rules/python/coding-style.md` — PEP 8, type hints

**Checklist**:
- [ ] Python 3.11+ installed
- [ ] `uv` package manager available
- [ ] `deepagents` installed
- [ ] `langchain` + `langgraph` installed
- [ ] `langchain-deepseek` installed
- [ ] `deepagents-code` installed (optional, cho CLI/Server)
- [ ] Dev tools: `pytest`, `ruff`, `mypy` installed
- [ ] `uv sync` clean (không lỗi)

---

### Step 0.2: Model Selection

**Mục tiêu**: Chọn model phù hợp cho main agent, subagents, và summarization — tất cả dùng DeepSeek V4 family.

**Cách thực hiện**: Dùng decision matrix từ [AIDLC Lifecycle §0.2](../aidlc-lifecycle.md#02-model-selection-decision-matrix)

| Vai trò | Model khuyến nghị | Lý do |
|---------|-------------------|-------|
| **Main orchestrator** | `deepseek-v4-flash` | Tool calling nhanh, rẻ ($0.14/1M input), 2500 QPS |
| **Subagents (heavy)** | `deepseek-v4-pro` | Reasoning mạnh nhất (1.6T params), code generation |
| **Subagents (light)** | `deepseek-v4-flash` | Cost efficiency cho task đơn giản |
| **Summarization** | `deepseek-v4-flash` | 1M context, $0.28/1M output |
| **Router/Classifier** | `deepseek-v4-flash` | Structured output nhanh, rẻ |

**Tools hỗ trợ**:
- **MCP `context7`**: `resolve-library-id` → `query-docs` để tra cứu model capabilities mới nhất
- **DeepSeek API Docs**: https://api-docs.deepseek.com/quick_start/pricing

**Checklist**:
- [ ] Main orchestrator model selected
- [ ] Subagent model(s) selected
- [ ] Summarization model selected
- [ ] Router/classifier model selected (if needed)
- [ ] Model selection rationale documented
- [ ] API keys configured (`DEEPSEEK_API_KEY` env var)

---

### Step 0.3: Tool Inventory Assessment

**Mục tiêu**: Liệt kê tất cả tools cần thiết trước khi code.

**Cách thực hiện**: Dùng tool inventory template từ [AIDLC Lifecycle §0.3](../aidlc-lifecycle.md#03-tool-inventory-assessment)

| Tool Category | Built-in Source | Custom Needed? |
|---------------|----------------|----------------|
| File System | `FilesystemMiddleware` | No |
| Shell | `ShellToolMiddleware` | No |
| Planning | `TodoListMiddleware` | No |
| Delegation | `SubAgentMiddleware` | No |
| Memory | `MemoryMiddleware` | No |
| Web Search | — | Yes (`@tool`) |
| URL Fetch | — | Yes (`@tool`) |
| Code Execution | — | Yes (`@tool` + Sandbox) |
| Database Query | — | Yes (`@tool`) |

**Tools hỗ trợ**:
- **MCP `codegraph`**: `codegraph_search` để tìm existing tool implementations trong codebase
- **Skill `agent-harness-construction`**: Action space design principles

**Checklist**:
- [ ] File System tools defined (read, write, edit, glob, grep)
- [ ] Shell tools defined (if needed)
- [ ] Planning tools defined (write_todos)
- [ ] Delegation tools defined (task)
- [ ] Memory tools defined (edit_file to /memories/)
- [ ] External API tools inventoried (search, fetch, etc.)
- [ ] Custom tools scoped and named
- [ ] Tool overlap analysis completed (no duplicate functionality)

---

### Step 0.4: Git Repository Setup

**Mục tiêu**: Khởi tạo git repo với conventional commits.

**Cách thực hiện**:
```bash
git init  # Nếu chưa có
git add .
git commit -m "chore: initialize agent harness project"
```

**Tools hỗ trợ**:
- **Rule**: `.claude/rules/common/git-workflow.md` — Commit format, branching strategy

**Checklist**:
- [ ] Git repo initialized
- [ ] `.gitignore` configured (`.env`, `__pycache__/`, `.pytest_cache/`, etc.)
- [ ] Initial commit with conventional format
- [ ] Branch strategy defined (`main` + `feat/*` + `fix/*`)

---

### Step 0.5: Project Configuration

**Mục tiêu**: Cấu hình Claude Code harness cho dự án.

**Cách thực hiện**: Review và cập nhật `.claude/settings.json`:
```bash
# Xem cấu hình hiện tại
cat .claude/settings.json
```

**Tools hỗ trợ**:
- **Skill `update-config`**: Cấu hình settings.json, hooks, permissions
- **Skill `fewer-permission-prompts`**: Tối ưu allowlist để giảm permission prompts

**Checklist**:
- [ ] `.claude/settings.json` reviewed
- [ ] Permissions allow list configured (pytest, ruff, mypy, git)
- [ ] Permissions deny list configured (rm -rf, push --force, .env files)
- [ ] PreToolUse hook configured (bash safety)
- [ ] PostToolUse hook configured (auto ruff check)
- [ ] Stop hook configured (auto pytest + ruff)
- [ ] SessionStart hook configured (environment display)
- [ ] `.mcp.json` MCP servers configured (codegraph, context7)

---

### Step 0.6: Documentation Baseline

**Mục tiêu**: Đảm bảo tất cả tài liệu tham khảo đã sẵn sàng.

**Checklist**:
- [ ] `CLAUDE.md` reviewed and updated
- [ ] `docs/deep-agents/` — 9 reference docs available
- [ ] `docs/guides/` — AIDLC lifecycle + plans available
- [ ] Agent definitions reviewed (`.claude/agents/`)
- [ ] Skill definitions reviewed (`.claude/skills/`)
- [ ] Rules reviewed (`.claude/rules/`)

---

## Phase 0 Completion Checklist

Tổng hợp tất cả checklist items:

### Environment
- [ ] Python 3.11+ installed
- [ ] `uv` package manager available
- [ ] All dependencies installed (`deepagents`, `langchain`, `langgraph`, `langchain-deepseek`)
- [ ] Dev tools installed (`pytest`, `ruff`, `mypy`)
- [ ] `uv sync` clean

### Model
- [ ] Main orchestrator model selected & rationale documented
- [ ] Subagent model(s) selected
- [ ] Summarization model selected
- [ ] API keys configured in environment variables

### Tools
- [ ] Built-in middleware tools inventoried
- [ ] Custom tools scoped
- [ ] No tool overlap

### Git & Config
- [ ] Git repo initialized with `.gitignore`
- [ ] Initial commit made
- [ ] `.claude/settings.json` reviewed
- [ ] Permissions, hooks configured
- [ ] MCP servers configured

### Docs
- [ ] All reference docs confirmed accessible
- [ ] `CLAUDE.md` current

---

## Next Phase

→ [Phase 1: Requirements & Analysis](01-requirements.md)

## References

| Tài liệu | Section |
|----------|---------|
| [AIDLC Lifecycle](../aidlc-lifecycle.md) | §0 Foundation |
| [Deep Agents README](../../deep-agents/README.md) | Installation, Architecture |
| [API Reference](../../deep-agents/02-api-reference.md) | `create_deep_agent()` |
| [CLI/Server](../../deep-agents/09-deepagents-code.md) | `create_cli_agent`, MCP |
| [Rules: Python Coding Style](../../../.claude/rules/python/coding-style.md) | PEP 8, type hints |
| [Rules: Git Workflow](../../../.claude/rules/common/git-workflow.md) | Commit format |
