# Plan 6: Harness Builder — Kết nối tất cả Loaders

> **Mục tiêu**: `HarnessBuilder` đọc `.harness/`, chạy tất cả loaders, cấu hình `create_deep_agent()` với mọi thứ từ `.harness/`.
> **Package**: `src/harness_agent/loaders/harness_builder.py`
> **Deep Agents doc**: `01-overview-architecture.md` (create_deep_agent entry point), `05-subagents.md` (SubAgentMiddleware)

---

## 1. HarnessBuilder — Entry Point

### 1.1 Trách nhiệm

`HarnessBuilder` là **hàm entry point duy nhất** để tạo agent từ `.harness/`:

```
project_root = Path("my-project/")

builder = HarnessBuilder(project_root)
agent = builder.build()
# → CompiledStateGraph ready for invoke/stream
```

Nó làm 5 việc theo thứ tự:

```
1. ConfigLoader.load()         → HarnessConfig
2. ToolRegistry.setup()        → ToolRegistry (từ config + inventory)
3. SubAgentLoader.load_all()   → list[subagent_definitions]
4. SkillLoader + RuleLoader    → list[memory_sources]
5. HookLoader.load_all()       → EventBus với hooks đã đăng ký
6. create_deep_agent(...)      → CompiledStateGraph
```

### 1.2 Design Principle

- **One call**: `builder.build()` — tất cả những gì cần để có agent chạy được
- **Fail fast**: Validate config trước khi build middleware
- **Graceful defaults**: Thiếu `.harness/` → agent chạy với defaults
- **Immutable**: Builder không thay đổi `.harness/` — chỉ đọc

---

## 2. Implementation

```python
# src/harness_agent/loaders/harness_builder.py

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from deepagents import create_deep_agent
from deepagents.backends import (
    CompositeBackend,
    FilesystemBackend,
    StateBackend,
    StoreBackend,
)
from deepagents.middleware.filesystem import FilesystemMiddleware
from deepagents.middleware.memory import MemoryMiddleware
from deepagents.middleware.subagents import SubAgentMiddleware
from deepagents.middleware.summarization import (
    SummarizationMiddleware,
)
from langchain.agents.middleware import (
    ContextEditingMiddleware,
    HumanInTheLoopMiddleware,
    ModelFallbackMiddleware,
    PIIMiddleware,
    ShellToolMiddleware,
    TodoListMiddleware,
    ToolRetryMiddleware,
)
from langchain_core.language_models import BaseChatModel
from langgraph.graph.state import CompiledStateGraph

from harness_agent.config import AgentModelSelection
from harness_agent.loaders.config_loader import (
    ConfigLoader,
    HarnessConfig,
)
from harness_agent.loaders.hook_loader import EventBus, HookLoader
from harness_agent.loaders.rule_loader import RuleLoader
from harness_agent.loaders.skill_loader import SkillLoader
from harness_agent.loaders.subagent_loader import (
    MiddlewareResolver,
    SubAgentLoader,
)
from harness_agent.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

# Default middleware order (5-layer principle from 03-middleware.md)
DEFAULT_MIDDLEWARE_ORDER = [
    "TodoListMiddleware",          # Layer 1: Planning
    "MemoryMiddleware",            # Layer 1: Context
    "HumanInTheLoopMiddleware",    # Layer 2: Security
    "PIIMiddleware",               # Layer 2: Security
    "FilesystemMiddleware",        # Layer 3: Capabilities
    "SubAgentMiddleware",          # Layer 4: Execution
    "ShellToolMiddleware",         # Layer 4: Execution
    "SummarizationMiddleware",     # Layer 5: Context Management
    "ContextEditingMiddleware",    # Layer 5: Context Management
    "ModelFallbackMiddleware",     # Layer 6: Resilience
    "ToolRetryMiddleware",         # Layer 6: Resilience
]


class HarnessBuilder:
    """Builder đọc .harness/ → cấu hình → create_deep_agent().

    Đây là ENTRY POINT DUY NHẤT để tạo agent. Mọi thứ agent cần
    đều được load từ .harness/ folder trong project.

    Usage:
        builder = HarnessBuilder(Path("my-project/"))
        agent = builder.build()
        result = agent.invoke({"messages": [{"role": "user", "content": "..."}]})
    """

    def __init__(
        self,
        project_root: Path,
        *,
        tool_registry: ToolRegistry | None = None,
        model_selection: AgentModelSelection | None = None,
    ) -> None:
        self.project_root = project_root.resolve()
        self.harness_dir = self.project_root / ".harness"
        self.tool_registry = tool_registry or ToolRegistry()
        self.model_selection = model_selection or AgentModelSelection()

        # Khởi tạo sub-components
        self.event_bus = EventBus()
        self.config_loader = ConfigLoader(self.harness_dir)
        self.skill_loader = SkillLoader(self.harness_dir)
        self.rule_loader = RuleLoader(self.harness_dir)
        self.subagent_loader = SubAgentLoader(
            self.harness_dir, self.tool_registry
        )
        self.hook_loader = HookLoader(self.harness_dir, self.event_bus)

        # Kết quả build (set sau khi build())
        self.config: HarnessConfig | None = None
        self.agent: CompiledStateGraph | None = None

    def build(self) -> CompiledStateGraph:
        """Build agent từ .harness/ configuration.

        Returns:
            CompiledStateGraph ready for invoke/stream.

        Raises:
            HarnessBuildError: Nếu config không hợp lệ.
        """
        logger.info("Building harness from: %s", self.harness_dir)

        # Step 1: Load & validate config
        self.config = self._load_and_validate_config()

        # Step 2: Load hooks (phải load trước để các bước sau có hooks)
        self.hook_loader.load_all()
        self.event_bus.fire(
            "session_start",
            {"project_root": str(self.project_root)},
        )

        # Step 3: Setup backend
        backend = self._build_backend()

        # Step 4: Load subagents từ .harness/subagents/
        subagent_defs = self.subagent_loader.load_all()

        # Step 5: Load skills + rules → memory sources
        memory_sources = self._collect_memory_sources()

        # Step 6: Resolve models
        main_model = self._resolve_model(self.config.model)
        summarization_model = self._resolve_model(
            self.config.summarization_model
        )

        # Step 7: Build middleware pipeline
        middleware = self._build_middleware_pipeline(
            backend=backend,
            subagent_defs=subagent_defs,
            memory_sources=memory_sources,
            summarization_model=summarization_model,
        )

        # Step 8: Build system prompt
        system_prompt = self._build_system_prompt()

        # Step 9: Create agent
        self.agent = create_deep_agent(
            model=main_model,
            middleware=middleware,
            backend=backend,
            system_prompt=system_prompt,
        )

        logger.info("Harness built successfully")
        return self.agent

    def _load_and_validate_config(self) -> HarnessConfig:
        """Load config và validate. Raise nếu có lỗi."""
        config = self.config_loader.load()
        errors = config.validate()
        if errors:
            raise HarnessBuildError(
                f"Invalid .harness/config.yaml:\n" +
                "\n".join(f"  - {e}" for e in errors)
            )
        return config

    def _build_backend(self) -> CompositeBackend:
        """Build CompositeBackend từ config."""
        cfg = self.config.backend
        routes: dict[str, Any] = {}

        for route in cfg.routes:
            if route.backend == "store":
                routes[route.path] = StoreBackend(file_format="v2")
            elif route.backend == "filesystem":
                routes[route.path] = FilesystemBackend(
                    root_dir=cfg.output_dir, virtual_mode=True
                )
            elif route.backend == "state":
                routes[route.path] = StateBackend()

        default_backend = {
            "state": StateBackend(),
            "store": StoreBackend(file_format="v2"),
            "filesystem": FilesystemBackend(
                root_dir=cfg.output_dir, virtual_mode=True
            ),
        }.get(cfg.default, StateBackend())

        return CompositeBackend(default=default_backend, routes=routes)

    def _collect_memory_sources(self) -> list[str]:
        """Collect tất cả memory sources từ skills + rules."""
        sources: list[str] = []
        sources.extend(self.skill_loader.get_memory_sources())
        sources.extend(self.rule_loader.get_memory_sources())
        return sources

    def _resolve_model(self, model_name: str) -> BaseChatModel:
        """Resolve model name → BaseChatModel instance."""
        from langchain_deepseek import ChatDeepSeek
        return ChatDeepSeek(model=model_name, temperature=0.0)

    def _build_middleware_pipeline(
        self,
        backend: CompositeBackend,
        subagent_defs: list[dict],
        memory_sources: list[str],
        summarization_model: BaseChatModel,
    ) -> list[Any]:
        """Build middleware pipeline từ config hoặc default.

        Map tên middleware → instance. Nếu config có
        middleware_order, dùng theo thứ tự đó.
        Nếu không, dùng DEFAULT_MIDDLEWARE_ORDER.
        """
        order = self.config.middleware_order or DEFAULT_MIDDLEWARE_ORDER

        # Middleware name → factory function
        factories: dict[str, Any] = {
            "TodoListMiddleware": lambda: TodoListMiddleware(),
            "MemoryMiddleware": lambda: MemoryMiddleware(
                backend=backend,
                sources=memory_sources if memory_sources else None,
            ),
            "HumanInTheLoopMiddleware": lambda: HumanInTheLoopMiddleware(
                interrupt_on=self.config.security.interrupt_on or None,
            ),
            "PIIMiddleware": lambda: PIIMiddleware(),
            "FilesystemMiddleware": lambda: FilesystemMiddleware(
                backend=backend
            ),
            "SubAgentMiddleware": lambda: SubAgentMiddleware(
                backend=backend,
                subagents=subagent_defs if subagent_defs else [],
            ),
            "ShellToolMiddleware": lambda: ShellToolMiddleware(),
            "SummarizationMiddleware": lambda: SummarizationMiddleware(
                model=summarization_model,
                backend=backend,
                trigger=("fraction", 0.85),
                keep=("fraction", 0.10),
            ),
            "ContextEditingMiddleware": lambda: ContextEditingMiddleware(),
            "ModelFallbackMiddleware": lambda: ModelFallbackMiddleware(
                fallback_models=["deepseek-v4-flash"],
                max_retries=2,
            ),
            "ToolRetryMiddleware": lambda: ToolRetryMiddleware(),
            "ToolCallLimitMiddleware": lambda: None,  # Placeholder
            "ModelCallLimitMiddleware": lambda: None,  # Placeholder
            "LLMToolSelectorMiddleware": lambda: None, # Placeholder
            "LLMToolEmulator": lambda: None,           # Placeholder
            "FilesystemFileSearchMiddleware": lambda: None, # Placeholder
        }

        pipeline = []
        for mw_name in order:
            factory = factories.get(mw_name)
            if factory is None:
                logger.warning(
                    "Middleware '%s' not yet implemented, skipping", mw_name
                )
                continue
            instance = factory()
            if instance is not None:
                pipeline.append(instance)

        return pipeline

    def _build_system_prompt(self) -> str:
        """Build system prompt từ config override hoặc default."""
        # Load từ file nếu configured
        custom_prompt = self.config_loader.load_system_prompt(
            self.config, self.project_root
        )
        if custom_prompt:
            return custom_prompt

        # Default system prompt
        return self._default_system_prompt()

    def _default_system_prompt(self) -> str:
        """Default system prompt khi không có custom."""
        return """You are a helpful AI assistant.

## Core Responsibilities
- Understand user requests and execute them accurately
- Use available tools to accomplish tasks
- Delegate complex tasks to subagents when appropriate

## Workflow
1. Analyze the user's request
2. Plan the approach using write_todos if needed
3. Execute using tools or delegate to subagents
4. Synthesize results and respond clearly

## Quality Standards
- Be thorough and accurate
- Cite sources when providing factual information
- Ask clarifying questions when requirements are unclear

## Memory
You have access to persistent memory. Save important preferences
and learnings for future sessions.
"""


class HarnessBuildError(Exception):
    """Raised when harness cannot be built from .harness/ config."""
```

---

## 3. Usage — từ 3 góc nhìn

### 3.1 Project có `.harness/` đầy đủ

```python
from pathlib import Path
from harness_agent.loaders import HarnessBuilder

builder = HarnessBuilder(Path("my-api-project/"))
agent = builder.build()

# Agent đã có:
# - Skills từ .harness/skills/
# - Rules từ .harness/rules/
# - Subagents từ .harness/subagents/
# - Hooks từ .harness/hooks/
# - Config từ .harness/config.yaml

result = agent.invoke({
    "messages": [{"role": "user", "content": "Review code in src/"}]
})
```

### 3.2 Project không có `.harness/`

```python
builder = HarnessBuilder(Path("plain-project/"))
agent = builder.build()
# → Agent chạy với defaults: không skills, không rules,
#   không subagents, middleware default 5-layer
```

### 3.3 Custom ToolRegistry + ModelSelection

```python
from harness_agent.tools.registry import ToolRegistry
from harness_agent.tools.search_tools import create_search_tool

# Setup custom tools
registry = ToolRegistry()
registry.register(create_search_tool())
registry.register(create_code_executor())

# Setup custom models
models = AgentModelSelection()
models.orchestrator.model_id = "deepseek-v4-pro"  # Override

builder = HarnessBuilder(
    Path("my-project/"),
    tool_registry=registry,
    model_selection=models,
)
agent = builder.build()
```

---

## 4. Error Handling

| Scenario | Behavior |
|----------|----------|
| `.harness/` không tồn tại | Config defaults, tất cả loaders trả về empty |
| `config.yaml` invalid | `HarnessBuildError` — dừng build |
| Subagent YAML invalid | `SubAgentLoadError` — dừng build |
| Tool không tìm thấy trong registry | `SubAgentLoadError` — dừng build |
| Hook script lỗi | Log warning, không dừng build |
| Middleware không implemented | Log warning, skip middleware đó |

---

## 5. `loaders/__init__.py` — Public API

```python
# src/harness_agent/loaders/__init__.py
"""Loaders for .harness/ convention — skills, rules, subagents, hooks, config."""

from harness_agent.loaders.config_loader import (
    BackendConfig,
    BackendRouteConfig,
    ConfigLoader,
    ConfigParseError,
    FeaturesConfig,
    HarnessConfig,
    MiddlewareParamConfig,
    SecurityConfig,
)
from harness_agent.loaders.harness_builder import (
    HarnessBuildError,
    HarnessBuilder,
)
from harness_agent.loaders.hook_loader import (
    EventBus,
    HookEvent,
    HookLoader,
    HookResult,
)
from harness_agent.loaders.rule_loader import RuleInfo, RuleLoader
from harness_agent.loaders.skill_loader import SkillInfo, SkillLoader
from harness_agent.loaders.subagent_loader import (
    MiddlewareResolver,
    SubAgentInfo,
    SubAgentLoadError,
    SubAgentLoader,
)

__all__ = [
    # Config
    "BackendConfig",
    "BackendRouteConfig",
    "ConfigLoader",
    "ConfigParseError",
    "FeaturesConfig",
    "HarnessConfig",
    "MiddlewareParamConfig",
    "SecurityConfig",
    # Builder
    "HarnessBuildError",
    "HarnessBuilder",
    # Hook
    "EventBus",
    "HookEvent",
    "HookLoader",
    "HookResult",
    # Rule
    "RuleInfo",
    "RuleLoader",
    # Skill
    "SkillInfo",
    "SkillLoader",
    # SubAgent
    "MiddlewareResolver",
    "SubAgentInfo",
    "SubAgentLoadError",
    "SubAgentLoader",
]
```

---

## 6. Testing Plan

### 6.1 Integration Tests (`tests/integration/test_harness_builder.py`)

| Test Case | Mô tả |
|-----------|-------|
| `test_build_with_empty_harness_dir` | `.harness/` rỗng → agent với defaults |
| `test_build_with_no_harness_dir` | Không có `.harness/` → agent với defaults |
| `test_build_with_config_only` | Chỉ có `config.yaml` → parse + defaults cho còn lại |
| `test_build_with_skills` | Có skills → inject vào memory sources |
| `test_build_with_rules` | Có rules → inject vào memory sources |
| `test_build_with_subagents` | Có subagents → register vào middleware |
| `test_build_with_hooks` | Có hooks → đăng ký vào event bus |
| `test_build_full_harness` | Đủ tất cả → agent với mọi thứ |
| `test_build_invalid_config_fails` | config.yaml sai → HarnessBuildError |
| `test_build_missing_tool_fails` | Subagent dùng tool không tồn tại → SubAgentLoadError |
| `test_build_custom_tool_registry` | ToolRegistry custom → tools resolved đúng |
| `test_build_custom_middleware_order` | middleware_order trong config → đúng thứ tự |
| `test_build_agent_can_invoke` | Agent build xong → invoke được |

### 6.2 Fixtures

```python
@pytest.fixture
def full_harness_project(tmp_path):
    """Tạo project với .harness/ đầy đủ."""
    project = tmp_path / "test-project"
    project.mkdir()

    harness_dir = project / ".harness"
    harness_dir.mkdir()

    # config.yaml
    (harness_dir / "config.yaml").write_text("model: deepseek-v4-flash\n")

    # skills/
    skills_dir = harness_dir / "skills"
    skills_dir.mkdir()
    (skills_dir / "test-skill.md").write_text("# Test Skill\n\n...")

    # rules/
    rules_dir = harness_dir / "rules"
    rules_dir.mkdir()
    (rules_dir / "test-rule.md").write_text("# Test Rule\n\n...")

    # subagents/
    subs_dir = harness_dir / "subagents"
    subs_dir.mkdir()
    (subs_dir / "test-agent.yaml").write_text("""\
name: test-agent
description: A test subagent.
system_prompt: You are a test agent.
""")

    # hooks/
    hooks_dir = harness_dir / "hooks"
    hooks_dir.mkdir()
    (hooks_dir / "session_start.sh").write_text("""\
#!/bin/bash
echo "Session started"
exit 0
""")
    (hooks_dir / "session_start.sh").chmod(0o755)

    return project
```

---

## 7. File Structure Summary

```
src/harness_agent/loaders/
├── __init__.py              # Public API exports
├── config_loader.py         # ConfigLoader + HarnessConfig + dataclasses
├── skill_loader.py          # SkillLoader + SkillInfo
├── rule_loader.py           # RuleLoader + RuleInfo
├── subagent_loader.py       # SubAgentLoader + MiddlewareResolver + SubAgentInfo
├── hook_loader.py           # EventBus + HookLoader + HookEvent + HookResult
└── harness_builder.py       # HarnessBuilder + HarnessBuildError
```

---

## 8. Checklist

### Design
- [ ] `HarnessBuilder.build()` là single entry point
- [ ] Build order: config → hooks → backend → subagents → memory sources → models → middleware → system prompt → agent
- [ ] `DEFAULT_MIDDLEWARE_ORDER` defined (11 middleware, 5 layers)
- [ ] Middleware name → factory mapping
- [ ] Error handling strategy cho từng failure mode

### Implementation
- [ ] `HarnessBuilder.__init__` nhận `project_root`, optional `tool_registry`, `model_selection`
- [ ] `HarnessBuilder.build()` — 9 bước tuần tự
- [ ] `_build_backend()` — map BackendRouteConfig → CompositeBackend
- [ ] `_build_middleware_pipeline()` — map tên middleware → instance
- [ ] `_collect_memory_sources()` — merge skills + rules
- [ ] `_build_system_prompt()` — custom hoặc default
- [ ] `HarnessBuildError` exception
- [ ] `loaders/__init__.py` với đầy đủ exports
- [ ] Type hints đầy đủ
- [ ] File harness_builder.py < 300 lines

### Testing
- [ ] 13 integration tests
- [ ] Fixtures cho full `.harness/` project
- [ ] Test từng thành phần độc lập
- [ ] Test error paths
- [ ] Test agent invoke được sau khi build
- [ ] Coverage ≥ 80%

### Integration
- [ ] `HarnessBuilder` exported trong `src/harness_agent/__init__.py`
- [ ] Tất cả loaders exported trong `src/harness_agent/__init__.py`
- [ ] `MemoryMiddleware` sources bao gồm skills + rules
- [ ] `SubAgentMiddleware` subagents từ `.harness/subagents/`
- [ ] `EventBus` hooks được fire tại các điểm trong agent pipeline
- [ ] `ConfigLoader` validate trước khi build

### Documentation
- [ ] Ví dụ `.harness/config.yaml` mẫu
- [ ] Ví dụ `.harness/subagents/*.yaml` mẫu
- [ ] Ví dụ `.harness/skills/*.md` mẫu
- [ ] Ví dụ `.harness/rules/*.md` mẫu
- [ ] Ví dụ `.harness/hooks/*.{sh,py}` mẫu

---

## References

| Tài liệu | Section |
|----------|---------|
| [Overview & Architecture](../../deep-agents/01-overview-architecture.md) | create_deep_agent entry point + middleware pipeline |
| [Subagents docs](../../deep-agents/05-subagents.md) | SubAgentMiddleware + subagent definitions |
| [Memory docs](../../deep-agents/06-memory.md) | MemoryMiddleware + sources + agent_memory tags |
| [Middleware docs](../../deep-agents/03-middleware.md) | Pipeline order + 14+ middleware |
| [Backends docs](../../deep-agents/04-backends.md) | CompositeBackend + routing |
| [AIDLC Lifecycle](../aidlc-lifecycle.md) | §2 Architecture & Design |
| [ADR-002: Middleware Pipeline](../../adr/002-middleware-pipeline.md) | Default middleware order |
| [ADR-003: Backend Strategy](../../adr/003-backend-strategy.md) | Backend routing |
| [ADR-004: Subagent Topology](../../adr/004-subagent-topology.md) | Subagent design principles |
