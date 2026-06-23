# Phase 0 — CRITICAL Fixes

> Priority: **Immediate** — production safety risks

---

## 0.1 Shell Injection in `basic_tools.py`

- **File**: `src/harness_agent/tools/basic_tools.py:287`
- **Issue**: `subprocess.run(command, shell=True)` nhận raw user input mà không filter. Bất kỳ shell metacharacter nào (`; && | $()`) đều thành injection vector.
- **Quy tắc vi phạm**: `.claude/rules/python/security.md` — "Subprocess calls use list args, not shell strings"
- **Fix**:
  - [ ] Thay `shell=True` bằng `shell=False` + `shlex.split(command)`
  - [ ] Wire `ShellInput` validator từ `file_tools.py:164` vào `ExecuteCommandInput`
  - [ ] Hoặc thêm allow-list command validation tương tự `SandboxConfig.is_command_allowed()`
- **Test**: Viết test injection với payload `"ls; cat /etc/passwd"` — phải bị reject

---

## 0.2 Mutable Class-Level Dict in `cli_metrics_server.py`

- **File**: `src/harness_agent/deployment/cli_metrics_server.py:194`
- **Issue**: `harness_info: dict[str, Any] = {}` là class attribute trên `_MetricsHandler`. Mọi concurrent request handler chia sẻ cùng dict object → mutation race condition.
- **Fix**:
  - [ ] Move per-request state vào closure hoặc subclass factory trong `start_metrics_server`
  - [ ] Hoặc freeze dict sau khi set (dùng `types.MappingProxyType`)
- **Test**: Concurrent request test verifying isolation

---

## 0.3 Bare `except: pass` Swallows All Errors in `server.py`

- **File**: `src/harness_agent/deployment/server.py:332`
- **Issue**: `except Exception: pass` trong lifespan fallback nuốt mọi error khi load system prompt. Agent chạy với hardcoded default mà operator không biết.
- **Fix**:
  - [ ] `except Exception as e: logger.warning("Failed to load system prompt: %s", e)`
  - [ ] Cân nhắc raise nếu system prompt là critical (không nên fallback im lặng)
- **Test**: Mock config load failure → verify warning log emitted

---

## Checklist

- [ ] All 3 fixes implemented
- [ ] Tests written for each
- [ ] `ruff check` clean
- [ ] `mypy` clean
- [ ] No regression in existing tests
