# Phase 2 — Async/Sync Mismatch & Type Safety

> Priority: **This week** — correctness and maintainability

---

## 2.1 `ainvoke` Blocks Event Loop

- **File**: `src/harness_agent/core/agent.py:121`
- **Issue**: `ainvoke` dùng `await self.llm.ainvoke()` nhưng gọi sync `_execute_tools()` → block event loop trên mọi tool I/O.
- **Fix**:
  - [ ] Tạo `async _aexecute_tools()` gọi `await tool.ainvoke(tool_args, config)`
  - [ ] `ainvoke` dùng `_aexecute_tools` thay vì `_execute_tools`
- **Test**: Async test verify event loop không bị block

---

## 2.2 Broad Exception Catch in `_execute_tools`

- **File**: `src/harness_agent/core/agent.py:65`
- **Issue**: `except Exception as e` nuốt mọi error, convert thành string message không log.
- **Fix**:
  - [ ] Catch specific: `(ToolException, ValueError, RuntimeError)`
  - [ ] `logger.warning("Tool %s failed: %s", tool_name, e)` trước khi convert
  - [ ] Re-raise non-recoverable exceptions
- **Test**: Mock tool raise → verify warning logged

---

## 2.3 `run_id: str` Should Be `UUID` in Server Callbacks

- **File**: `src/harness_agent/deployment/server.py:146,153`
- **Issue**: `on_llm_start` và `on_tool_start` declare `run_id: str` nhưng LangChain truyền `UUID`. Tool latency metrics bị drop vì key mismatch.
- **Fix**:
  - [ ] `from uuid import UUID`
  - [ ] Sửa signature: `run_id: UUID`
- **Test**: Verify tool latency tracked correctly sau fix

---

## 2.4 Exception Chaining Missing (`from e`)

- **Files**:
  - `src/harness_agent/loaders/subagent_loader.py:295` — `raise SubAgentLoadError(...)`
  - `src/harness_agent/tools/basic_tools.py:38` — `raise ValueError(...)`
- **Fix**:
  - [ ] Thêm `from e` / `from exc` cho tất cả re-raise
- **Quy tắc**: ruff B904

---

## 2.5 `DEFAULT_MAX_TOOL_ITERATIONS` Redefined

- **File**: `src/harness_agent/deployment/cli.py:227`
- **Issue**: Module-level constant shadow import từ `harness_agent.core.agent`. ruff F811.
- **Fix**:
  - [ ] Xóa line 227, dùng import từ line 32

---

## 2.6 Missing Type Arguments (Bare `list`, `dict`)

- **Files**:
  - `deployment/cli.py:1213,1234,1470` — `messages: list` → `list[BaseMessage]`
  - `loaders/config_loader.py:304,342,350,364,374` — `raw: dict` → `dict[str, Any]`
  - `tools/basic_tools.py:315` — `BASIC_TOOLS: list` → `list[BaseTool]`
  - `evaluation/ab_testing.py:97` — `agent_a: Any` → `Runnable`
  - `evaluation/evaluator.py:90` — `agent: Any` → `Runnable`
  - `config.py:168` — return `Any` → `BaseChatModel`
- **Fix**:
  - [ ] Thêm type arguments cho tất cả bare collections
  - [ ] Thay `Any` bằng proper protocol types

---

## 2.7 `assert` Used as Runtime Guard

- **File**: `src/harness_agent/loaders/harness_builder.py:297,374,449`
- **Issue**: `assert self.config is not None` bị strip khi chạy `python -O`.
- **Fix**:
  - [ ] Thay bằng `if self.config is None: raise HarnessBuildError(...)`

---

## 2.8 Undeclared Instance Attribute

- **File**: `src/harness_agent/deployment/cli.py:1343`
- **Issue**: `self._graph_tool_state = {...}` set mid-method, không khai báo trong `__init__`.
- **Fix**:
  - [ ] Khai báo `self._graph_tool_state: dict[str, Any] | None = None` trong `__init__`

---

## 2.9 `_read_body` Returns Unvalidated JSON

- **File**: `src/harness_agent/deployment/cli_metrics_server.py:225`
- **Issue**: `json.loads()` trả `Any`. Nếu body là JSON array `[]` → crash khi caller gọi `.get()`.
- **Fix**:
  - [ ] `data = json.loads(raw); return data if isinstance(data, dict) else {}`

---

## 2.10 Hook Loader Returns Unvalidated Callable

- **File**: `src/harness_agent/loaders/hook_loader.py:446`
- **Issue**: `module.handle` là `Any`, không kiểm tra `callable()` trước khi return.
- **Fix**:
  - [ ] `if not callable(handle): logger.error(...); return None`
  - [ ] `return cast(Callable[..., Any], handle)`

---

## Checklist

- [ ] All 10 fixes implemented
- [ ] `mypy --strict` passes trên affected files
- [ ] `ruff check` clean
- [ ] Existing tests still pass
