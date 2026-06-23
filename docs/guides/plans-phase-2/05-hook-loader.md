# Plan 5: Hook Loader — `.harness/hooks/` + EventBus

> **Mục tiêu**: Xây dựng EventBus + HookLoader để đọc `.harness/hooks/*.{sh,py}`, đăng ký vào event system, và fire khi event trigger.
> **Package**: `src/harness_agent/loaders/hook_loader.py`
> **Deep Agents doc**: Không có built-in — đây là custom component mới hoàn toàn.

---

## 1. `.harness/hooks/` Convention

### 1.1 Cấu trúc

```
.harness/hooks/
├── session_start.sh         # Chạy khi session bắt đầu
├── session_end.sh           # Chạy khi session kết thúc
├── pre_tool_call.py         # Chạy trước mỗi tool call
├── post_tool_call.sh        # Chạy sau mỗi tool call
├── pre_llm_call.py          # Chạy trước mỗi LLM call
├── post_llm_call.sh         # Chạy sau mỗi LLM call
└── on_error.py              # Chạy khi có lỗi
```

**Naming convention**: `{event_name}.{sh|py}` — file name (không có extension) map vào `HookEvent` enum.

### 1.2 Hook Event Types

```python
class HookEvent(str, Enum):
    SESSION_START = "session_start"       # Khi agent.invoke() được gọi lần đầu
    SESSION_END = "session_end"           # Khi agent.invoke() hoàn thành
    PRE_TOOL_CALL = "pre_tool_call"       # Trước khi tool được thực thi
    POST_TOOL_CALL = "post_tool_call"     # Sau khi tool hoàn thành
    PRE_LLM_CALL = "pre_llm_call"         # Trước khi LLM được gọi
    POST_LLM_CALL = "post_llm_call"       # Sau khi LLM trả về response
    ON_ERROR = "on_error"                 # Khi có exception
```

### 1.3 Hook Script Format

#### Shell Hook (`.sh`)

```bash
#!/bin/bash
# .harness/hooks/pre_tool_call.sh
#
# Nhận context qua environment variable HOOK_CONTEXT (JSON).
# Exit code 0 = cho phép continue, exit code khác 0 = block.

CONTEXT=$(echo "$HOOK_CONTEXT" | python3 -c "import sys,json; print(json.load(sys.stdin))")
TOOL_NAME=$(echo "$CONTEXT" | python3 -c "import sys,json; print(json.load(sys.stdin)['tool_name'])")

echo "[pre_tool_call] About to call: $TOOL_NAME"

# Ví dụ: block nếu tool là rm
if [ "$TOOL_NAME" = "rm" ]; then
    echo "❌ Blocked: rm is not allowed"
    exit 1
fi

exit 0
```

#### Python Hook (`.py`)

```python
# .harness/hooks/pre_tool_call.py

def handle(context: dict) -> dict:
    """Hàm bắt buộc — nhận context, trả về result.

    Args:
        context: {
            "event": "pre_tool_call",
            "tool_name": "write_file",
            "tool_args": {"file_path": "...", "content": "..."},
            "session_id": "...",
            "timestamp": "2026-06-23T10:00:00Z",
        }

    Returns:
        {
            "allowed": True,           # False để block
            "modified_args": {...},    # Optional: sửa tool args
            "message": "...",          # Optional: log message
        }
    """
    if context.get("tool_name") == "write_file":
        file_path = context.get("tool_args", {}).get("file_path", "")
        if file_path.endswith(".env"):
            return {"allowed": False, "message": "Blocked: .env file write"}
    return {"allowed": True}
```

---

## 2. Design — EventBus

### 2.1 Kiến trúc

```
┌──────────────────────────────────────────────────────────────┐
│                         EventBus                              │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ _listeners: dict[HookEvent, list[callable]]              │ │
│  │                                                          │ │
│  │  "pre_tool_call" → [hook1, hook2, hook3]                │ │
│  │  "post_tool_call" → [hook4]                              │ │
│  │  "on_error" → [hook5, hook6]                             │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                               │
│  fire(event, context):                                        │
│      1. Lấy tất cả listeners cho event                       │
│      2. Chạy tuần tự (theo thứ tự đăng ký)                   │
│      3. Nếu listener trả về {"allowed": False} → dừng        │
│      4. Trả về aggregated results                            │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 Tích hợp vào Agent Pipeline

```
invoke()
  │
  ├── EventBus.fire(SESSION_START, {...})
  │
  ├── for each tool call:
  │     ├── EventBus.fire(PRE_TOOL_CALL, {tool_name, args})
  │     │     └── if blocked → skip tool, return error
  │     ├── execute tool
  │     └── EventBus.fire(POST_TOOL_CALL, {tool_name, result})
  │
  ├── EventBus.fire(SESSION_END, {...})
  │
  └── on exception:
        └── EventBus.fire(ON_ERROR, {error, traceback})
```

### 2.3 Fire Result

Mỗi lần `fire()` trả về `HookResult`:

```python
@dataclass
class HookResult:
    allowed: bool = True           # False nếu hook block
    messages: list[str] = []       # Log messages từ hooks
    modified_context: dict = {}    # Context bị sửa bởi hooks (merged)
    errors: list[str] = []         # Errors từ hooks (non-blocking)
```

---

## 3. Implementation

### 3.1 EventBus

```python
# src/harness_agent/loaders/hook_loader.py

from __future__ import annotations

import json
import os
import subprocess
import importlib.util
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


class HookEvent(str, Enum):
    """Các event trong vòng đời agent mà hook có thể listen."""
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    PRE_TOOL_CALL = "pre_tool_call"
    POST_TOOL_CALL = "post_tool_call"
    PRE_LLM_CALL = "pre_llm_call"
    POST_LLM_CALL = "post_llm_call"
    ON_ERROR = "on_error"


@dataclass
class HookResult:
    """Kết quả sau khi fire hooks cho một event."""
    allowed: bool = True
    messages: list[str] = field(default_factory=list)
    modified_context: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


class EventBus:
    """Event bus cho harness hooks.

    Đăng ký listeners cho từng HookEvent. Khi fire(), chạy
    tất cả listeners tuần tự theo thứ tự đăng ký.

    Usage:
        bus = EventBus()
        bus.on(HookEvent.PRE_TOOL_CALL, my_hook_function)
        result = bus.fire(HookEvent.PRE_TOOL_CALL, {"tool_name": "write_file"})
        if not result.allowed:
            print(f"Blocked: {result.messages}")
    """

    def __init__(self) -> None:
        self._listeners: dict[HookEvent, list[Callable]] = defaultdict(list)

    def on(self, event: HookEvent, listener: Callable) -> None:
        """Đăng ký một listener cho event.

        Args:
            event: HookEvent để listen.
            listener: Callable nhận (context: dict) → trả về dict hoặc HookResult.
        """
        self._listeners[event].append(listener)
        logger.debug("Registered hook for %s: %s", event.value, listener)

    def fire(self, event: HookEvent, context: dict) -> HookResult:
        """Kích hoạt tất cả listeners đã đăng ký cho event.

        Chạy tuần tự. Nếu một listener trả về allowed=False,
        các listener sau KHÔNG được chạy.

        Args:
            event: Event được fire.
            context: Context dict truyền cho listeners.

        Returns:
            HookResult tổng hợp từ tất cả listeners.
        """
        result = HookResult()
        for listener in self._listeners.get(event, []):
            try:
                listener_result = listener(context)
                parsed = self._parse_listener_result(listener_result)

                if not parsed.allowed:
                    result.allowed = False
                    result.messages.extend(parsed.messages)
                    result.errors.extend(parsed.errors)
                    break  # Dừng chuỗi — không chạy listener sau

                result.messages.extend(parsed.messages)
                result.modified_context.update(parsed.modified_context)
                result.errors.extend(parsed.errors)

            except Exception as e:
                logger.error("Hook error for %s: %s", event.value, e)
                result.errors.append(str(e))
                # Không block — lỗi hook không nên dừng agent

        return result

    def _parse_listener_result(self, raw: Any) -> HookResult:
        """Parse kết quả từ listener thành HookResult."""
        if isinstance(raw, HookResult):
            return raw
        if isinstance(raw, dict):
            return HookResult(
                allowed=raw.get("allowed", True),
                messages=raw.get("messages", []),
                modified_context=raw.get("modified_context", {}),
                errors=raw.get("errors", []),
            )
        # Nếu listener không trả về gì → coi là allowed
        return HookResult()

    @property
    def listener_count(self) -> int:
        """Tổng số listeners đã đăng ký."""
        return sum(len(v) for v in self._listeners.values())

    def clear(self) -> None:
        """Xóa tất cả listeners."""
        self._listeners.clear()
```

### 3.2 HookLoader

```python
class HookLoader:
    """Đọc hooks từ .harness/hooks/ và đăng ký vào EventBus.

    Hỗ trợ 2 loại hook:
    - Shell scripts (.sh): nhận context qua HOOK_CONTEXT env var
    - Python modules (.py): phải có def handle(context) -> dict

    Usage:
        bus = EventBus()
        loader = HookLoader(Path("my-project/.harness"), bus)
        loader.load_all()
        # Hooks đã được đăng ký vào bus
    """

    # Map tên sự kiện → HookEvent
    EVENT_MAP: dict[str, HookEvent] = {
        "session_start": HookEvent.SESSION_START,
        "session_end": HookEvent.SESSION_END,
        "pre_tool_call": HookEvent.PRE_TOOL_CALL,
        "post_tool_call": HookEvent.POST_TOOL_CALL,
        "pre_llm_call": HookEvent.PRE_LLM_CALL,
        "post_llm_call": HookEvent.POST_LLM_CALL,
        "on_error": HookEvent.ON_ERROR,
    }

    def __init__(self, harness_dir: Path, event_bus: EventBus) -> None:
        self.hooks_dir = harness_dir / "hooks"
        self.event_bus = event_bus

    @property
    def exists(self) -> bool:
        return self.hooks_dir.is_dir()

    def load_all(self) -> list[str]:
        """Quét .harness/hooks/, đăng ký tất cả hooks vào EventBus.

        Returns:
            List[str] tên các hook đã load thành công.
        """
        if not self.exists:
            return []

        loaded = []
        for file in sorted(self.hooks_dir.iterdir()):
            if file.is_dir():
                continue

            event = self._file_to_event(file.stem)
            if event is None:
                logger.warning(
                    "Unknown hook event: %s (expected one of: %s)",
                    file.stem, list(self.EVENT_MAP.keys()),
                )
                continue

            executor = self._create_executor(file)
            if executor is not None:
                self.event_bus.on(event, executor)
                loaded.append(file.name)

        return loaded

    def _file_to_event(self, stem: str) -> HookEvent | None:
        return self.EVENT_MAP.get(stem)

    def _create_executor(self, file: Path) -> Callable | None:
        """Tạo executor function từ file .sh hoặc .py."""
        if file.suffix == ".sh":
            return self._create_shell_executor(file)
        elif file.suffix == ".py":
            return self._create_python_executor(file)
        else:
            logger.warning("Unsupported hook type: %s", file.suffix)
            return None

    def _create_shell_executor(self, file: Path) -> Callable:
        def executor(context: dict) -> dict:
            env = {**os.environ, "HOOK_CONTEXT": json.dumps(context)}
            try:
                result = subprocess.run(
                    ["bash", str(file)],
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                return {
                    "allowed": result.returncode == 0,
                    "messages": [
                        line
                        for line in (result.stdout + result.stderr).splitlines()
                        if line.strip()
                    ],
                }
            except subprocess.TimeoutExpired:
                return {
                    "allowed": True,  # Timeout không block
                    "messages": [f"Hook {file.name} timed out (30s)"],
                }
        return executor

    def _create_python_executor(self, file: Path) -> Callable | None:
        try:
            spec = importlib.util.spec_from_file_location(
                f"harness_hook_{file.stem}", file
            )
            if spec is None or spec.loader is None:
                logger.error("Cannot load hook: %s", file)
                return None
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            if not hasattr(module, "handle"):
                logger.error(
                    "Python hook %s missing handle(context) function", file
                )
                return None

            return module.handle
        except Exception as e:
            logger.error("Failed to load hook %s: %s", file, e)
            return None
```

---

## 4. Context Schema (truyền cho hooks)

Mỗi event có context schema riêng:

```python
# Context schema by event type
CONTEXT_SCHEMAS = {
    HookEvent.SESSION_START: {
        "session_id": str,
        "project_root": str,
        "config": dict,         # HarnessConfig serialized
        "timestamp": str,       # ISO 8601
    },
    HookEvent.SESSION_END: {
        "session_id": str,
        "total_tokens": int,
        "tool_calls_count": int,
        "duration_ms": int,
        "success": bool,
    },
    HookEvent.PRE_TOOL_CALL: {
        "session_id": str,
        "tool_name": str,
        "tool_args": dict,
        "timestamp": str,
    },
    HookEvent.POST_TOOL_CALL: {
        "session_id": str,
        "tool_name": str,
        "tool_args": dict,
        "tool_result": str,
        "duration_ms": int,
        "success": bool,
    },
    HookEvent.ON_ERROR: {
        "session_id": str,
        "error_type": str,
        "error_message": str,
        "traceback": str,
        "context": dict,        # Context khi lỗi xảy ra
    },
}
```

---

## 5. Error Handling

| Scenario | Behavior |
|----------|----------|
| `.harness/hooks/` không tồn tại | `load_all()` trả về `[]` |
| File không phải `.sh` hoặc `.py` | Log warning, bỏ qua |
| File name không map vào `HookEvent` | Log warning, bỏ qua |
| Shell script timeout (30s) | Trả về `allowed=True`, ghi log message |
| Shell script crash (exit code ≠ 0) | Trả về `allowed=False`, ghi stderr vào messages |
| Python hook không có `handle()` | Log error, bỏ qua |
| Python hook import error | Log error, bỏ qua |
| Listener throw exception | Bắt exception, thêm vào `result.errors`, không block |

**Nguyên tắc quan trọng**: Hook error **không bao giờ dừng agent** — chỉ block nếu hook explicitly trả về `allowed=False`.

---

## 6. Testing Plan

### 6.1 Unit Tests — EventBus (`tests/unit/loaders/test_event_bus.py`)

| Test Case | Mô tả |
|-----------|-------|
| `test_register_listener` | `on()` → listener được đăng ký |
| `test_fire_calls_listener` | `fire()` → listener được gọi với context |
| `test_fire_multiple_listeners` | 3 listeners → tất cả được gọi tuần tự |
| `test_block_stops_chain` | Listener 1 trả về `allowed=False` → listener 2 không được gọi |
| `test_listener_error_non_blocking` | Listener throw → thêm vào `result.errors`, vẫn continue |
| `test_parse_dict_result` | Listener trả về dict → parse thành HookResult |
| `test_parse_hookresult` | Listener trả về HookResult → giữ nguyên |
| `test_listener_count` | 5 listeners → `listener_count == 5` |
| `test_clear_removes_all` | `clear()` → `listener_count == 0` |
| `test_fire_no_listeners` | Fire event không có listener → HookResult defaults |
| `test_modified_context_merged` | 2 listeners sửa context → merged |

### 6.2 Unit Tests — HookLoader (`tests/unit/loaders/test_hook_loader.py`)

| Test Case | Mô tả |
|-----------|-------|
| `test_no_hooks_dir` | Không có hooks/ → load_all() trả về [] |
| `test_load_shell_hook` | File .sh → đăng ký vào bus |
| `test_load_python_hook` | File .py có handle() → đăng ký vào bus |
| `test_python_hook_missing_handle` | File .py không có handle() → bỏ qua |
| `test_unsupported_extension` | File .txt → bỏ qua |
| `test_unknown_event_name` | File name không map → bỏ qua |
| `test_shell_hook_execution` | Shell hook chạy → kết quả đúng |
| `test_shell_hook_timeout` | Shell hook chạy > 30s → timeout, allowed=True |

---

## 7. Checklist

### Design
- [ ] `HookEvent` enum với 7 events
- [ ] `EventBus` class với `on()`, `fire()`, `clear()`
- [ ] `HookResult` dataclass
- [ ] Context schema cho mỗi event type
- [ ] Shell hook contract (`HOOK_CONTEXT` env var, exit code)
- [ ] Python hook contract (`def handle(context) -> dict`)
- [ ] "Hook error never stops agent" principle

### Implementation
- [ ] `EventBus` class — `src/harness_agent/loaders/hook_loader.py`
- [ ] `HookLoader` class — quét + đăng ký hooks
- [ ] `_create_shell_executor()` — subprocess với timeout
- [ ] `_create_python_executor()` — importlib
- [ ] `HookEvent` enum
- [ ] `HookResult` dataclass
- [ ] Type hints đầy đủ
- [ ] File < 350 lines

### Testing
- [ ] 11 EventBus unit tests
- [ ] 8 HookLoader unit tests
- [ ] Mock shell scripts trong tmp_path
- [ ] Mock Python hooks với `handle()` function
- [ ] Test timeout behavior
- [ ] Coverage ≥ 85%

### Integration
- [ ] `EventBus` được tạo trong `HarnessBuilder`
- [ ] `EventBus.fire()` được gọi tại các điểm trong agent pipeline
- [ ] `HookLoader` imported trong `src/harness_agent/loaders/__init__.py`

---

## References

| Tài liệu | Section |
|----------|---------|
| [Middleware docs](../../deep-agents/03-middleware.md) | Custom middleware pattern (base class để tạo hook-like behavior) |
| [HumanInTheLoopMiddleware](../../deep-agents/03-middleware.md#humanintheloopmiddleware) | Pattern tương tự — interrupt execution |
| [ADR-002: Middleware Pipeline](../../adr/002-middleware-pipeline.md) | Pipeline order — hooks phải chạy ở đâu |
