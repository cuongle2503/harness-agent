# Plan 4: SubAgent Loader — `.harness/subagents/`

> **Mục tiêu**: Parse `.harness/subagents/*.yaml` thành subagent definitions, resolve tool/middleware references, đăng ký vào `SubAgentMiddleware`.
> **Package**: `src/harness_agent/loaders/subagent_loader.py`
> **Deep Agents doc**: `05-subagents.md` (SubAgentMiddleware, task tool, subagent lifecycle)

---

## 1. `.harness/subagents/` Convention

### 1.1 Cấu trúc

```
.harness/subagents/
├── code-reviewer.yaml      # Subagent: review code
├── api-tester.yaml         # Subagent: test API endpoints
├── doc-writer.yaml         # Subagent: viết documentation
└── db-architect.yaml       # Subagent: thiết kế database schema
```

Mỗi file `.yaml` định nghĩa **một subagent**. File name (không có `.yaml`) là tên subagent.

### 1.2 SubAgent YAML Schema

```yaml
# .harness/subagents/<name>.yaml

# ─── Required ────────────────────────────────────────────────
name: code-reviewer                    # Unique name, dùng trong task tool
description: >                         # Mô tả — agent dùng để chọn subagent
  Reviews Python code for bugs,
  security vulnerabilities, and
  style issues.

system_prompt: |                       # System prompt riêng cho subagent
  You are a thorough code reviewer.
  For each review:
  1. Check for bugs and logic errors
  2. Check for security vulnerabilities
  3. Check style/PEP 8 compliance
  4. Suggest improvements with examples

  Always provide file:line references.

# ─── Optional ────────────────────────────────────────────────
tools:                                # Tools subagent được dùng
  - read_file
  - grep
  - glob

model: deepseek-v4-pro                # Model (default: theo config)

middleware:                           # Middleware riêng (thường để trống)
  - ContextEditingMiddleware
  - ToolRetryMiddleware:
      max_retries: 3

# ─── Advanced (optional) ────────────────────────────────────
max_iterations: 50                    # Max tool calling iterations
temperature: 0.0                      # Temperature override
```

### 1.3 Minimal Valid Definition

```yaml
name: simple-reviewer
description: Reviews code for basic issues.
system_prompt: You are a code reviewer. Check for bugs and style.
```

Tất cả field khác đều optional.

---

## 2. Design

### 2.1 Cách tích hợp với Deep Agents

```
┌─────────────────────────────────────────────────────────────┐
│ SubAgentMiddleware                                            │
│                                                              │
│  subagents: [                                                │
│      {                                                        │
│          "name": "code-reviewer",    ← Từ .yaml (LOADED)    │
│          "description": "...",                                │
│          "system_prompt": "...",                              │
│          "tools": [read_file, grep], ← ĐÃ RESOLVE            │
│          "model": "deepseek-v4-pro",                         │
│          "middleware": [ContextEditing(...)], ← ĐÃ RESOLVE   │
│      },                                                       │
│      {                                                        │
│          "name": "api-tester",       ← Từ .yaml (LOADED)    │
│          ...                                                  │
│      },                                                       │
│  ]                                                            │
│                                                              │
│  → Main agent gọi task("code-reviewer", "Review file X")    │
│  → Subagent được spawn với tools + prompt đã cấu hình       │
│  → Subagent chạy độc lập, trả về kết quả                    │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Resolver Pattern

SubAgentLoader cần **resolve** 2 loại reference:

| Reference Type | YAML Value | Resolved To |
|---------------|-----------|-------------|
| **Tool name** | `"read_file"` (string) | `BaseTool` instance từ `ToolRegistry` |
| **Middleware name** | `"ContextEditingMiddleware"` (string) | `AgentMiddleware` instance |
| **Middleware with params** | `{"ToolRetryMiddleware": {"max_retries": 3}}` (dict) | `AgentMiddleware` instance với params |

Loader phụ thuộc vào:
- `ToolRegistry` — để resolve tool names
- `MiddlewareResolver` — để resolve middleware names → instances

### 2.3 Middleware Resolver

Cần một registry nhỏ để map tên middleware → class:

```python
MIDDLEWARE_REGISTRY = {
    "ContextEditingMiddleware": ContextEditingMiddleware,
    "ToolRetryMiddleware": ToolRetryMiddleware,
    "TodoListMiddleware": TodoListMiddleware,
    "SummarizationMiddleware": SummarizationMiddleware,
    "ModelFallbackMiddleware": ModelFallbackMiddleware,
    "ToolCallLimitMiddleware": ToolCallLimitMiddleware,
    "ModelCallLimitMiddleware": ModelCallLimitMiddleware,
    "HumanInTheLoopMiddleware": HumanInTheLoopMiddleware,
    "PIIMiddleware": PIIMiddleware,
    # Các middleware khác có thể đăng ký thêm
}
```

---

## 3. Implementation

```python
# src/harness_agent/loaders/subagent_loader.py

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from harness_agent.core.exceptions import HarnessError
from harness_agent.tools.registry import ToolRegistry


class SubAgentLoader:
    """Parse .harness/subagents/*.yaml thành subagent definitions.

    Mỗi file .yaml định nghĩa 1 subagent với:
    - name, description, system_prompt (required)
    - tools, model, middleware (optional)

    Tools được resolve qua ToolRegistry.
    Middleware được resolve qua MiddlewareResolver.

    Usage:
        registry = ToolRegistry()
        registry.register(read_file_tool)
        registry.register(grep_tool)

        loader = SubAgentLoader(Path("my-project/.harness"), registry)
        subagents = loader.load_all()
        # subagents = [
        #     {"name": "code-reviewer", "description": "...", ...},
        #     {"name": "api-tester", "description": "...", ...},
        # ]
    """

    # Middleware name → class mapping
    MIDDLEWARE_CLASSES: dict[str, type] = {}  # Populated at runtime

    def __init__(
        self,
        harness_dir: Path,
        tool_registry: ToolRegistry,
    ) -> None:
        self.subagents_dir = harness_dir / "subagents"
        self.tool_registry = tool_registry
        self._middleware_resolver = MiddlewareResolver()

    @property
    def exists(self) -> bool:
        """Kiểm tra subagents/ folder có tồn tại không."""
        return self.subagents_dir.is_dir()

    def load_all(self) -> list[dict[str, Any]]:
        """Load tất cả subagent definitions từ .harness/subagents/.

        Returns:
            List[dict] các subagent definitions sẵn sàng cho SubAgentMiddleware.

        Raises:
            SubAgentLoadError: Nếu file YAML không hợp lệ hoặc thiếu required fields.
        """
        if not self.exists:
            return []

        definitions = []
        for file in sorted(self.subagents_dir.glob("*.yaml")):
            definition = self._load_one(file)
            definitions.append(definition)

        return definitions

    def _load_one(self, file: Path) -> dict[str, Any]:
        """Load và validate 1 subagent definition file.

        Raises:
            SubAgentLoadError: Nếu parse error hoặc thiếu required fields.
        """
        # 1. Parse YAML
        try:
            with open(file, "r") as f:
                raw = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            raise SubAgentLoadError(
                f"Failed to parse {file.name}: {e}"
            ) from e

        # 2. Validate required fields
        missing = []
        for field in ["name", "description", "system_prompt"]:
            if field not in raw or not raw[field]:
                missing.append(field)
        if missing:
            raise SubAgentLoadError(
                f"Missing required fields in {file.name}: {missing}"
            )

        # 3. Resolve tools
        tools = self._resolve_tools(raw.get("tools", []), file.name)

        # 4. Resolve middleware
        middleware = self._middleware_resolver.resolve(
            raw.get("middleware", []), file.name
        )

        # 5. Build definition
        return {
            "name": raw["name"],
            "description": raw["description"],
            "system_prompt": raw["system_prompt"],
            "tools": tools,
            "model": raw.get("model", "deepseek-v4-flash"),
            "middleware": middleware,
        }

    def _resolve_tools(
        self, tool_names: list[str], source_file: str
    ) -> list[Any]:
        """Resolve tool names → tool objects qua ToolRegistry.

        Args:
            tool_names: List tên tool từ YAML.
            source_file: Tên file .yaml (để báo lỗi).

        Returns:
            List[BaseTool] instances.

        Raises:
            SubAgentLoadError: Nếu tool không tìm thấy trong registry.
        """
        tools = []
        for name in tool_names:
            try:
                tool = self.tool_registry.get(name)
                tools.append(tool)
            except Exception:
                available = [
                    t["name"] for t in self.tool_registry.list_tools()
                ]
                raise SubAgentLoadError(
                    f"Tool '{name}' in {source_file} not found in registry. "
                    f"Available tools: {available}"
                )
        return tools

    def list_subagents(self) -> list[SubAgentInfo]:
        """Liệt kê thông tin các subagents đã đăng ký (không resolve tools)."""
        if not self.exists:
            return []
        result = []
        for file in sorted(self.subagents_dir.glob("*.yaml")):
            raw = yaml.safe_load(file.read_text()) or {}
            result.append(SubAgentInfo(
                name=raw.get("name", file.stem),
                source_file=file.name,
                description=raw.get("description", ""),
                tool_count=len(raw.get("tools", [])),
            ))
        return result


class MiddlewareResolver:
    """Resolve middleware names → instances."""

    def __init__(self) -> None:
        self._registry: dict[str, type] = {}

    def register(self, name: str, middleware_class: type) -> None:
        """Đăng ký một middleware class."""
        self._registry[name] = middleware_class

    def resolve(
        self, raw_middleware: list[Any], source_file: str
    ) -> list[Any]:
        """Resolve list middleware specs → list instances.

        Hỗ trợ 2 format:
        1. String: "ContextEditingMiddleware" → ContextEditingMiddleware()
        2. Dict với params: {"ToolRetryMiddleware": {"max_retries": 3}}
           → ToolRetryMiddleware(max_retries=3)
        """
        instances = []
        for item in raw_middleware:
            if isinstance(item, str):
                cls = self._registry.get(item)
                if cls is None:
                    raise SubAgentLoadError(
                        f"Unknown middleware '{item}' in {source_file}. "
                        f"Known: {list(self._registry.keys())}"
                    )
                instances.append(cls())
            elif isinstance(item, dict):
                for name, params in item.items():
                    cls = self._registry.get(name)
                    if cls is None:
                        raise SubAgentLoadError(
                            f"Unknown middleware '{name}' in {source_file}."
                        )
                    instances.append(cls(**params))
            else:
                raise SubAgentLoadError(
                    f"Invalid middleware spec in {source_file}: {item}"
                )
        return instances


class SubAgentInfo:
    """Thông tin cơ bản về một subagent (không resolve tools)."""
    name: str
    source_file: str
    description: str
    tool_count: int

    def __init__(
        self, name: str, source_file: str,
        description: str, tool_count: int,
    ) -> None:
        self.name = name
        self.source_file = source_file
        self.description = description
        self.tool_count = tool_count


class SubAgentLoadError(HarnessError):
    """Raised when a subagent definition file cannot be loaded."""
```

---

## 4. Validation Rules

| Rule | Check |
|------|-------|
| `name` must be unique | Không được trùng với subagent khác |
| `name` must be valid identifier | Chỉ chứa `[a-z0-9-]` |
| `description` non-empty | Ít nhất 10 ký tự |
| `system_prompt` non-empty | Ít nhất 20 ký tự |
| `tools` must exist in registry | Mọi tool name phải resolve được |
| `model` must be valid | Phải có trong ModelRegistry |
| `middleware` must be known | Mọi middleware name phải resolve được |

Validation chạy trong `_load_one()` — raise `SubAgentLoadError` với message rõ ràng.

---

## 5. Error Handling Strategy

| Scenario | Behavior |
|----------|----------|
| `.harness/subagents/` không tồn tại | Trả về `[]` |
| File `.yaml` parse error | `SubAgentLoadError` với file name + line |
| Thiếu `name`, `description`, hoặc `system_prompt` | `SubAgentLoadError` liệt kê fields thiếu |
| Tool name không có trong `ToolRegistry` | `SubAgentLoadError` + list available tools |
| Middleware name không có trong `MiddlewareResolver` | `SubAgentLoadError` + list known middleware |
| `name` trùng với subagent khác | `SubAgentLoadError` (duplicate) |
| File không phải `.yaml` | Bỏ qua (chỉ glob `*.yaml`) |
| Symlink tới file `.yaml` | Không follow |

---

## 6. Testing Plan

### 6.1 Unit Tests (`tests/unit/loaders/test_subagent_loader.py`)

| Test Case | Mô tả |
|-----------|-------|
| `test_no_subagents_dir` | Không có subagents/ → load_all() trả về [] |
| `test_empty_subagents_dir` | subagents/ rỗng → [] |
| `test_load_minimal_subagent` | Chỉ có required fields → parse đúng |
| `test_load_full_subagent` | Đủ tất cả fields → parse đúng |
| `test_load_multiple_subagents` | 3 files → 3 definitions |
| `test_missing_required_fields` | Thiếu description → SubAgentLoadError |
| `test_unknown_tool` | Tool không có trong registry → SubAgentLoadError |
| `test_tool_resolved_correctly` | Tool name → đúng BaseTool instance |
| `test_unknown_middleware` | Middleware không có trong resolver → SubAgentLoadError |
| `test_middleware_with_params` | Dict format → instance với params |
| `test_middleware_simple_string` | String format → instance không params |
| `test_invalid_yaml_syntax` | YAML syntax error → SubAgentLoadError |
| `test_duplicate_subagent_names` | 2 files cùng name → SubAgentLoadError |
| `test_list_subagents_returns_info` | list_subagents() → list[SubAgentInfo] |

### 6.2 Fixtures

```python
@pytest.fixture
def tool_registry():
    registry = ToolRegistry()
    # Register mock tools
    registry.register(MockTool(name="read_file", description="Read a file"))
    registry.register(MockTool(name="grep", description="Search files"))
    registry.register(MockTool(name="glob", description="Find files"))
    return registry

@pytest.fixture
def temp_harness_dir(tmp_path):
    harness_dir = tmp_path / ".harness"
    harness_dir.mkdir()
    return harness_dir

@pytest.fixture
def subagents_dir_with_files(temp_harness_dir):
    sub_dir = temp_harness_dir / "subagents"
    sub_dir.mkdir()
    (sub_dir / "code-reviewer.yaml").write_text("""\
name: code-reviewer
description: Reviews code for bugs, security, and style issues.
system_prompt: You are a thorough code reviewer.
tools:
  - read_file
  - grep
model: deepseek-v4-pro
middleware:
  - ContextEditingMiddleware
  - ToolRetryMiddleware:
      max_retries: 3
""")
    (sub_dir / "api-tester.yaml").write_text("""\
name: api-tester
description: Tests API endpoints.
system_prompt: You test APIs thoroughly.
tools:
  - read_file
model: deepseek-v4-flash
""")
    return temp_harness_dir
```

---

## 7. Checklist

### Design
- [x] YAML schema spec hoàn chỉnh (required + optional fields)
- [x] Resolver pattern rõ ràng (tools + middleware)
- [x] `MiddlewareResolver` class với registry
- [x] Validation rules table
- [x] Error handling strategy table

### Implementation
- [x] `SubAgentLoader.__init__` nhận `harness_dir` + `tool_registry`
- [x] `SubAgentLoader.exists` property
- [x] `SubAgentLoader.load_all()` → `list[dict]`
- [x] `SubAgentLoader._load_one()` với validation
- [x] `SubAgentLoader._resolve_tools()` — resolve qua ToolRegistry
- [x] `SubAgentLoader.list_subagents()` → `list[SubAgentInfo]`
- [x] `MiddlewareResolver` class với `register()` + `resolve()`
- [x] `SubAgentInfo` dataclass
- [x] `SubAgentLoadError` exception
- [x] Type hints đầy đủ
- [x] File < 300 lines

### Testing
- [x] 28 unit tests (vượt kế hoạch 14), tổ chức thành 6 test classes:
  - `TestSubAgentLoaderExists` (2 tests)
  - `TestSubAgentLoaderLoadAll` (11 tests): no dir, empty dir, minimal, full, multiple, missing fields, unknown tool, tool resolved, unknown middleware, invalid yaml, duplicate names, non-dict yaml
  - `TestMiddlewareResolver` (4 tests): simple string, with params, unknown middleware, invalid spec
  - `TestSubAgentLoaderListSubagents` (3 tests): returns info, no dir, empty dir
  - `TestSubAgentInfo` (5 tests): fields, repr, equality, inequality, not equal to other type
  - `TestMiddlewareResolverRegister` (2 tests): register multiple, params not dict
- [x] Mock ToolRegistry với các tool giả (BaseTool subclasses)
- [x] Mock MiddlewareResolver
- [x] Test tất cả error paths
- [x] Test resolve tools thành công
- [x] Test resolve middleware với cả 2 format
- [x] Coverage ≥ 90% (đạt 93% — subagent_loader.py: 112/120 statements)

### Integration
- [x] Đăng ký `MiddlewareResolver` với tất cả known middleware classes
- [x] `SubAgentLoader` imported trong `src/harness_agent/loaders/__init__.py`
- [x] `SubAgentInfo`, `SubAgentLoadError` exported

---

## References

| Tài liệu | Section |
|----------|---------|
| [Subagents docs](../../deep-agents/05-subagents.md) | SubAgentMiddleware, task tool, best practices |
| [Subagent Definition Structure](../../deep-agents/05-subagents.md#cấu-trúc-subagent-definition) | Required fields |
| [Subagent Design Principles](../../deep-agents/05-subagents.md#best-practices) | Single responsibility, minimal tools |
| [ADR-004: Subagent Topology](../../adr/004-subagent-topology.md) | Current subagent definitions |
