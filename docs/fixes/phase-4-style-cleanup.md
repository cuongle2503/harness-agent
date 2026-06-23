# Phase 4 — Style & Minor Refactors

> Priority: **Backlog** — không ảnh hưởng correctness, cải thiện maintainability

---

## 4.1 `import time` Inside Method Bodies

- **Files**:
  - `src/harness_agent/deployment/cli_metrics_server.py:62,94,115,132`
  - `src/harness_agent/deployment/server.py:157,172,203,502`
  - `src/harness_agent/monitoring/alerts.py:174`
- **Fix**:
  - [x] Hoist `import time` lên module level
  - [x] Xóa các alias `_t`, `_t0`, `_ttt` — dùng `time` trực tiếp

---

## 4.2 `import os` / `import fnmatch` Inside Function

- **File**: `src/harness_agent/security/permissions.py:148-149,155`
- **Fix**:
  - [x] Move lên top of module

---

## 4.3 Import Sorting (ruff I001)

- **Files**:
  - `src/harness_agent/loaders/__init__.py:3`
  - `src/harness_agent/loaders/config_loader.py:10`
  - `src/harness_agent/loaders/hook_loader.py:17,25`
- **Fix**:
  - [x] `ruff check --fix src/harness_agent/loaders/`

---

## 4.4 `try/except ValueError: pass` → `contextlib.suppress`

- **Files**:
  - `src/harness_agent/deployment/cli.py:1089`
  - `src/harness_agent/deployment/cli_metrics_server.py:354,365`
- **Fix**:
  - [x] `with contextlib.suppress(ValueError):`

---

## 4.5 `_FIELD_MAP` Constant Inside Function

- **File**: `src/harness_agent/deployment/cli_metrics_server.py:513`
- **Fix**:
  - [x] Move ra module level

---

## 4.6 Ternary Simplification

- **File**: `src/harness_agent/deployment/cli.py:1098`
- **Issue**: `if name: session_id = name else: session_id = ...`
- **Fix**:
  - [x] `session_id = name or f"{self.config.assistant_id}-{os.getpid()}"`

---

## 4.7 `noqa` Comments Không Cần Thiết

- **File**: `src/harness_agent/__init__.py:12,20,27,43,53`
- **Fix**:
  - [x] Xóa `noqa: E402, F401` — `__all__` đã handle

---

## 4.8 `open()` Without `encoding=`

- **File**: `src/harness_agent/loaders/config_loader.py:255`
- **Fix**:
  - [x] `open(self.config_path, encoding="utf-8")`

---

## 4.9 `_classify_event` Unnecessary Inline Type Annotations

- **File**: `src/harness_agent/monitoring/streaming.py:67-68`
- **Fix**:
  - [x] Xóa standalone `token: Any` và `metadata: dict[str, Any]` annotations

---

## 4.10 `list.pop(0)` cho Rolling Window

- **File**: `src/harness_agent/monitoring/metrics.py:322-325`
- **Issue**: O(n) trên mỗi append. Không critical ở window=100 nhưng sai data structure.
- **Fix**:
  - [x] Dùng `collections.deque(maxlen=100)`

---

## 4.11 `pass_at_3` Magic Number

- **File**: `src/harness_agent/evaluation/evaluator.py:134,170`
- **Issue**: `pass_at_3 = completion_rate + 0.1` — không có cơ sở methodology.
- **Fix**:
  - [x] Implement actual pass@3 (chạy 3 lần) hoặc xóa field

---

## 4.12 Module Docstring in Vietnamese

- **File**: `src/harness_agent/loaders/harness_builder.py:1`
- **Fix**:
  - [x] Translate sang English cho consistency

---

## 4.13 `_WORKSPACE` Captured at Import Time

- **File**: `src/harness_agent/tools/basic_tools.py:29`
- **Issue**: `Path.cwd()` tại import time. Nếu process đổi directory → security boundary sai.
- **Fix**:
  - [x] Dùng `os.environ.get("HARNESS_WORKSPACE_ROOT", ...)` như `file_tools.py`

---

## 4.14 Unused Parameters in Metrics Methods

- **File**: `src/harness_agent/monitoring/metrics.py:205-244`
- **Issue**: `subagent_name`, `tokens_before/after`, `tool_name` được nhận rồi discard.
- **Fix**:
  - [x] Log tại DEBUG level hoặc store per-tool breakdown
  - [x] Hoặc xóa params nếu không cần

---

## 4.15 `PermissionBoundary.workspace_root` Hardcoded Path

- **File**: `src/harness_agent/security/permissions.py:47`
- **Issue**: Default `Path.home() / "my-projects"` — machine-specific.
- **Fix**:
  - [x] Default to `Path.cwd()` hoặc `os.environ.get("HARNESS_WORKSPACE")`

---

## 4.16 `validate()` / `validate_secrets()` Overlap

- **File**: `src/harness_agent/config.py:141,154`
- **Fix**:
  - [x] `validate_secrets()` gọi `validate()` internally

---

## 4.17 `type: ignore` Without Explanation

- **Files**:
  - `src/harness_agent/agents/code_agent.py:27,64,65,67`
  - `src/harness_agent/agents/research_agent.py:26,64,65`
- **Fix**:
  - [x] Thêm reason: `# type: ignore[return-value]  # CompiledStateGraph is generic`

---

## 4.18 `virtual_mode` Conflict with Recent Fix

- **File**: `src/harness_agent/memory/backends.py:42`
- **Issue**: Commit `e69f749` set `virtual_mode=False` nhưng code hiện tại là `True`.
- **Fix**:
  - [x] Verify intent theo ADR-003
  - [x] Set đúng giá trị và document why

---

## Checklist

- [x] `ruff check --fix` applied
- [x] `mypy` clean
- [x] All tests pass
- [x] Code đọc dễ hơn, ít noise hơn
