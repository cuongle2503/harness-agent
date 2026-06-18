# Phase 0: Foundation Plan

> **Mục tiêu**: Chuẩn bị môi trường phát triển, chọn model, kiểm kê tools — nền tảng vững chắc trước khi bắt đầu xây dựng agent.
> **Trạng thái**: ✅ Hoàn thành (commit `d06a533`)

## Prerequisites

- [x] Đã đọc [AIDLC Lifecycle](../aidlc-lifecycle.md)
- [x] Đã đọc [Deep Agents README](../../deep-agents/README.md)
- [x] Đã hiểu tổng quan 9 giai đoạn AIDLC

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
- [x] Python 3.11+ installed (3.12.13 in venv)
- [x] `uv` package manager available (0.10.6)
- [x] `deepagents` installed (0.6.10)
- [x] `langchain` + `langgraph` installed (1.3.9 / 1.2.5)
- [x] `langchain-deepseek` installed (1.1.0)
- [x] `deepagents-code` installed (0.1.20)
- [x] Dev tools: `pytest` (9.1.0), `ruff` (0.15.17), `mypy` (2.1.0) installed
- [x] `pyproject.toml` configured with all deps, ruff, mypy, pytest settings
- [x] `uv sync` clean (không lỗi)

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
- [x] Main orchestrator model selected (`deepseek-v4-flash`)
- [x] Subagent model(s) selected (`deepseek-v4-pro` / `deepseek-v4-flash`)
- [x] Summarization model selected (`deepseek-v4-flash`)
- [x] Router/classifier model selected (`deepseek-v4-flash`)
- [x] Model selection rationale documented (commit `c1e131f`: migrate from Claude/Anthropic to DeepSeek V4)
- [x] API keys configured (`DEEPSEEK_API_KEY` env var)

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
- [x] File System tools defined (read, write, edit, glob, grep)
- [x] Shell tools defined (if needed)
- [x] Planning tools defined (write_todos)
- [x] Delegation tools defined (task)
- [x] Memory tools defined (edit_file to /memories/)
- [x] External API tools inventoried (search, fetch, etc.)
- [x] Custom tools scoped and named (`src/harness_agent/tools.py` started)
- [x] Tool overlap analysis completed (no duplicate functionality)

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
- [x] Git repo initialized
- [x] `.gitignore` configured (`.env`, `__pycache__/`, `.pytest_cache/`, `.mypy_cache/`, v.v.)
- [x] Initial commit with conventional format (`4b9f15e chore: initialize agent harness project`)
- [x] Branch strategy defined (`main` + `feat/*` + `fix/*`)
- [x] Recent commits follow conventional format (`d06a533`, `c1e131f`)

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
- [x] `.claude/settings.json` reviewed
- [x] Permissions allow list configured (uv, pytest, ruff, mypy, black, git)
- [x] Permissions deny list configured (rm -rf, push --force, .env files)
- [x] PreToolUse hook configured (bash safety warning)
- [x] PostToolUse hook configured (auto ruff check on Edit/Write)
- [x] Stop hook configured (auto pytest + ruff before session ends)
- [x] SessionStart hook configured (Python/uv environment display)
- [x] `.mcp.json` MCP servers configured (codegraph, context7)

---

### Step 0.6: Documentation Baseline

**Mục tiêu**: Đảm bảo tất cả tài liệu tham khảo đã sẵn sàng.

**Checklist**:
- [x] `CLAUDE.md` reviewed and updated
- [x] `docs/deep-agents/` — 10 reference docs available (README + 9 detail docs)
- [x] `docs/guides/` — AIDLC lifecycle + plans available
- [x] Agent definitions reviewed (5 agents in `.claude/agents/`)
- [x] Skill definitions reviewed (6 skills in `.claude/skills/`)
- [x] Rules reviewed (`.claude/rules/` common + python)

---

## Phase 0 Completion Checklist

Tổng hợp tất cả checklist items:

### Environment
- [x] Python 3.11+ installed (3.12.13 in venv)
- [x] `uv` package manager available (0.10.6)
- [x] All dependencies installed (`deepagents`, `langchain`, `langgraph`, `langchain-deepseek`)
- [x] Dev tools installed (`pytest`, `ruff`, `mypy`)
- [x] `pyproject.toml` configured (ruff, mypy, pytest, coverage, hatchling build)
- [x] `uv sync` clean

### Model
- [x] Main orchestrator model selected (`deepseek-v4-flash`) & rationale documented
- [x] Subagent model(s) selected (`deepseek-v4-pro` heavy, `deepseek-v4-flash` light)
- [x] Summarization model selected (`deepseek-v4-flash`)
- [x] API keys configured in environment variables (`DEEPSEEK_API_KEY`)

### Tools
- [x] Built-in middleware tools inventoried (Filesystem, Shell, TodoList, SubAgent, Memory)
- [x] Custom tools scoped (Web Search, URL Fetch, Code Execution, Database Query)
- [x] No tool overlap

### Git & Config
- [x] Git repo initialized with `.gitignore`
- [x] Initial commit made (`4b9f15e chore: initialize agent harness project`)
- [x] `.claude/settings.json` reviewed
- [x] Permissions, hooks configured (PreToolUse, PostToolUse, Stop, SessionStart)
- [x] MCP servers configured (codegraph, context7)

### Docs
- [x] All reference docs confirmed accessible (10 deep-agents docs + AIDLC lifecycle + plans)
- [x] `CLAUDE.md` current

### Source Code (bắt đầu)
- [x] `src/harness_agent/__init__.py` initialized
- [x] `src/harness_agent/config.py` — config model với DeepSeek defaults
- [x] `src/harness_agent/tools.py` — tool registry skeleton
- [x] `tests/conftest.py` — shared fixtures
- [x] `tests/__init__.py` initialized

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
