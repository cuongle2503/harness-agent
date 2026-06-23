# Phase 1 — Security Boundary Fixes

> Priority: **This week** — correctness bugs in security-critical code

---

## 1.1 Path Traversal Bypass via `startswith()`

- **File**: `src/harness_agent/security/permissions.py:127`
- **Issue**: `str(resolved).startswith(str(workspace))` cho phép `/home/user/project-evil/secret` bypass check khi workspace là `/home/user/project`. String prefix matching không phải path-level comparison.
- **Fix**:
  - [x] Thay bằng `resolved.is_relative_to(workspace)` (Python 3.9+, project yêu cầu 3.11+)
- **Test**: `is_path_safe("/workspace-evil/file")` phải trả `False`

---

## 1.2 Path Traversal Bypass in `_path_matches()` Pattern

- **File**: `src/harness_agent/security/permissions.py:144`
- **Issue**: `file_path.startswith(prefix)` cho pattern `/**` cũng bị cùng lỗi.
- **Fix**:
  - [x] `file_path.startswith(prefix + "/") or file_path == prefix`
  - [x] Hoặc dùng `PurePath(file_path).is_relative_to(prefix)`
- **Test**: Pattern `/workspace/**` không match `/workspace-other/file`

---

## 1.3 PII Scanner Accumulation Bug

- **File**: `src/harness_agent/security/pii.py:39`
- **Issue**: `_detected` accumulate qua mọi lần `scan()` mà không clear. `has_pii()` trả `True` mãi mãi sau lần detect đầu tiên.
- **Fix**:
  - [x] Clear `_detected` ở đầu mỗi `scan()` call
  - [x] Drive redaction decision từ local match count, không phải instance-level `_detected`
- **Test**: `scan("clean text")` sau `scan("email@test.com")` → `has_pii()` trả `False`

---

## 1.4 `value_preview` Unconditional Ellipsis

- **File**: `src/harness_agent/security/pii.py:55`
- **Issue**: `str(match)[:50] + "..."` luôn thêm `...` kể cả khi match < 50 chars.
- **Fix**:
  - [x] `str(match)[:50] + ("..." if len(str(match)) > 50 else "")`

---

## 1.5 HITL Exception Chain Lost

- **File**: `src/harness_agent/security/hitl.py:104-110`
- **Issue**: `raise HITLApprovalDeniedError(tool_name)` không có `from exc` → mất traceback gốc.
- **Fix**:
  - [x] `raise HITLApprovalDeniedError(tool_name) from exc`

---

## 1.6 `safe_run()` Bypasses Allow-List

- **File**: `src/harness_agent/security/subprocess_safety.py:57`
- **Issue**: `safe_run()` không gọi `SandboxConfig.is_command_allowed()`. Caller có thể invoke bất kỳ binary nào.
- **Fix**:
  - [x] Nhận optional `SandboxConfig` param và enforce allow-list bên trong `safe_run()`
  - [x] Hoặc document rõ caller responsibility

---

## Checklist

- [x] All 6 fixes implemented
- [x] Security tests added
- [x] Path traversal test suite
- [x] `ruff check` clean
- [x] `mypy` clean
