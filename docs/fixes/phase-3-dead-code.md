# Phase 3 — Dead Code & Misleading Stubs

> Priority: **Next sprint** — cleanup giảm confusion cho maintainers

---

## 3.1 `AgentOrchestrator` — Empty Class Exported as Public API

- **File**: `src/harness_agent/core/orchestrator.py`
- **Issue**: Class chỉ có `__init__`, không method nào. Exported trong `core/__init__.py` và top-level `__init__.py`.
- **Fix**:
  - [x] Xóa khỏi `__all__` cho đến khi implement
  - [x] Hoặc raise `NotImplementedError` trên mọi call attempt
  - [x] Xóa unused `from typing import Any` nếu không cần

---

## 3.2 `AgentMessage` — Unused Model

- **File**: `src/harness_agent/deployment/server.py:50`
- **Issue**: Pydantic model defined nhưng không dùng ở bất kỳ route nào.
- **Fix**:
  - [x] Xóa, hoặc dùng làm element type trong `AgentRequest.messages`

---

## 3.3 `_collect_memory_sources` — Dead Private Method

- **File**: `src/harness_agent/loaders/harness_builder.py:321`
- **Issue**: Không được gọi ở đâu. Docstring nói "prefer `get_memory_sources()`".
- **Fix**:
  - [x] Xóa method

---

## 3.4 `_print_help` — Duplicate of `_cmd_help`

- **File**: `src/harness_agent/deployment/cli.py:2275`
- **Issue**: Legacy branch gọi `_print_help` thay vì `_cmd_help`. Hai output khác nhau → inconsistent help text.
- **Fix**:
  - [x] Legacy branch gọi `_cmd_help` trực tiếp
  - [x] Xóa `_print_help`

---

## 3.5 `ToolRegistry.from_inventory` — Stub Ignores Parameter

- **File**: `src/harness_agent/tools/registry.py:93`
- **Issue**: `inventory: Any` được nhận rồi bỏ qua. Body chỉ `return cls()`.
- **Fix**:
  - [x] Implement đúng hoặc raise `NotImplementedError`
  - [x] Type param: `inventory: ToolInventory`

---

## 3.6 Stub Tools Returning Fake Results

- **Files**:
  - `src/harness_agent/tools/search_tools.py:62` — `web_search` trả `{"results": []}`
  - `src/harness_agent/tools/code_tools.py:95` — `execute_python` trả string giống success
  - `src/harness_agent/tools/file_tools.py:226` — `fetch_url` trả `"placeholder"`
- **Issue**: Agent nhận kết quả rỗng/giả mà không biết tool chưa implement.
- **Fix**:
  - [x] Return `{"status": "not_implemented", "message": "..."}`
  - [x] Hoặc raise `NotImplementedError` rõ ràng

---

## 3.7 `_llm_judge` Unreachable Guard

- **File**: `src/harness_agent/evaluation/ab_testing.py:203-204`
- **Issue**: `if self.judge is None: return "tie"` — unreachable vì caller đã check `is not None`.
- **Fix**:
  - [x] Xóa dead guard

---

## 3.8 `evaluate()` / `aevaluate()` Code Duplication

- **File**: `src/harness_agent/evaluation/evaluator.py:102-172`
- **Issue**: 95% logic giống nhau, chỉ khác `invoke` vs `ainvoke`.
- **Fix**:
  - [x] Extract shared aggregation logic vào private helper
  - [x] Cả hai methods gọi helper với results tương ứng

---

## 3.9 `ShellInput` Validator — Defined But Never Wired

- **File**: `src/harness_agent/tools/file_tools.py:164-193`
- **Issue**: Validator tồn tại nhưng docstring nói "NOT currently wired to any @tool".
- **Fix**:
  - [x] Wire vào `ExecuteCommandInput` trong `basic_tools.py` (kết hợp Phase 0.1)
  - [x] Hoặc xóa nếu không dùng

---

## 3.10 `middleware/custom_middleware.py` — Pure Re-export Shim

- **File**: `src/harness_agent/middleware/custom_middleware.py`
- **Issue**: Chỉ import và re-export `StructuredLoggingMiddleware` → 2 layer indirection vô nghĩa.
- **Fix**:
  - [x] Alias trực tiếp trong `middleware/__init__.py`
  - [x] Xóa `custom_middleware.py`

---

## Checklist

- [x] All dead code removed or properly stubbed
- [x] No exported symbols that don't work
- [x] `ruff check` clean (F811, F401)
- [x] Existing tests still pass
