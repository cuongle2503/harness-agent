# Skills & Subagents — Logic Bugs & Fix Plan

**Date**: 2026-06-23  
**Scope**: `src/harness_agent/loaders/`, `src/harness_agent/deployment/cli.py`, `src/harness_agent/deployment/cli_streaming.py`, `src/harness_agent/loaders/harness_builder.py`

---

## Summary

Skills and subagents are loaded but **not functionally wired** to the agent's runtime behavior. The system collects metadata (counts, names, descriptions) for display purposes, but the actual execution path either silently discards them or passes them to `create_deep_agent` which is unlikely to be installed.

---

## Bug 1: Skills Are Never Injected Into Agent Context (Fallback Path)

**Location**: `cli.py:215-225` (`_init_agent`)

**Problem**: When `.harness/` is present and `HarnessBuilder.build()` succeeds, a `CompiledStateGraph` is stored in `self._graph`. But a **separate** `HarnessAgent` is also created with only `BASIC_TOOLS` and the system prompt — it has **no knowledge of skills**.

When `.harness/` is present but `deepagents` is NOT installed (which is the common case — it's an optional dependency), `HarnessBuilder.build()` raises `HarnessBuildError`. The exception is **not caught** in `_init_agent()`, so the entire `CLIAgent.__init__()` crashes.

**Expected behavior**: If `deepagents` is unavailable, fall back gracefully to the manual agent path but still inject skill content into the system prompt.

**Root cause**: The code assumes `deepagents` is always available when `.harness/` exists. There's no fallback that injects skill/rule markdown into the `HarnessAgent`'s system prompt directly.

**Fix**:
```python
def _init_agent(self) -> HarnessAgent:
    if self._harness_builder is not None:
        try:
            self._graph = self._harness_builder.build(model=self._llm)
        except Exception as e:
            # deepagents not installed or build failed — fall back
            logger.warning("HarnessBuilder.build() failed: %s", e)
            self._graph = None

    # Fallback: build system prompt with skills/rules/subagents info
    system_prompt = self._build_harness_system_prompt() if self._harness_builder else ""
    if not system_prompt:
        system_prompt = self.config.system_prompt or load_prompt("main_agent")

    # Inject rule content directly into system prompt (simulates MemoryMiddleware)
    rule_content = self._load_rule_content()
    if rule_content:
        system_prompt += "\n\n" + rule_content

    from harness_agent.tools.basic_tools import BASIC_TOOLS
    return HarnessAgent(
        llm=self._llm,
        tools=BASIC_TOOLS,
        system_prompt=system_prompt,
        max_tool_iterations=self.config.max_tool_iterations,
    )
```

---

## Bug 2: Subagents Are Loaded But Never Executable (Fallback Path)

**Location**: `cli.py:289-294` (`_build_harness_info`), `cli_streaming.py:306-523` (`stream_turn_agent`)

**Problem**: Subagent definitions are loaded from `.harness/subagents/*.yaml` and stored in `self._harness_subagent_defs`. They appear in:
- The welcome banner (counts)
- The `/subagents` slash command (names + descriptions)
- The system prompt (`_build_harness_system_prompt`)

But in the **fallback agent path** (`stream_turn_agent`), there is **no `task` tool** registered. The LLM is told subagents exist and instructed to use the `task` tool, but:
1. `HarnessAgent` only has `BASIC_TOOLS` (read_file, write_file, edit_file, glob, grep, execute_command)
2. No `task` tool is registered in the tool map
3. If the LLM generates a `task` tool call, it gets "Unknown tool: task"

**Expected behavior**: Either register a `task` tool that spawns subagents in the fallback path, or **don't advertise subagents** in the system prompt when they can't be executed.

**Fix (option A — implement a task tool for fallback)**:
```python
# In cli.py or a new file: tools/task_tool.py
from langchain_core.tools import tool
from pydantic import BaseModel, Field

class TaskInput(BaseModel):
    subagent_type: str = Field(..., description="Name of the subagent to delegate to")
    task: str = Field(..., description="Task description for the subagent")

@tool(args_schema=TaskInput)
def delegate_task(subagent_type: str, task: str) -> str:
    """Delegate a task to a subagent. The subagent runs independently and returns a result."""
    # Look up subagent def, create a temporary HarnessAgent with
    # the subagent's system_prompt and tools, invoke it, return result.
    ...
```

**Fix (option B — don't advertise what can't run)**:
Remove subagent references from `_build_harness_system_prompt()` when `self._graph is None`.

---

## Bug 3: Skill Sources Return Directory Paths, But Fallback Cannot Use Them

**Location**: `skill_loader.py:163-173` (`get_memory_sources`), `harness_builder.py:233-242`

**Problem**: `SkillLoader.get_memory_sources()` returns **directory paths** (for `SkillsMiddleware` to scan). But `SkillsMiddleware` only exists inside `deepagents`. In the fallback path, these directory paths are never read — no code opens `SKILL.md` files from those directories.

The `_build_harness_system_prompt()` method in `cli.py` does NOT include skill instructions — it only includes subagent descriptions and rule names. Skills are completely invisible to the agent in fallback mode.

**Expected behavior**: In fallback mode, read `SKILL.md` files and inject their content (or at minimum name + description) into the system prompt so the agent knows what skills are available and their instructions.

**Fix**:
```python
def _load_skill_content(self) -> str:
    """Load skill names + descriptions for system prompt injection."""
    if not self._harness_builder:
        return ""
    skills = self._harness_builder.skill_loader.list_skills()
    if not skills:
        return ""
    parts = ["## Available Skills"]
    for sk in skills:
        parts.append(f"- **{sk.name}**: {sk.description}")
    return "\n".join(parts)
```

---

## Bug 4: `stream_turn_graph` — Tool Hook Blocking Doesn't Prevent Execution

**Location**: `cli_streaming.py:234-241`

**Problem**: When `PRE_TOOL_CALL` hook returns `allowed=False`, the code prints a warning and calls `continue`. But `continue` in the `async for event in graph.astream_events(...)` loop only skips **processing that event** — it does NOT prevent the tool from executing. The tool already ran inside LangGraph's internal execution; the `on_tool_start` event is merely a notification that execution began.

In contrast, in the `stream_turn_agent` path (line 474-481), tool blocking works correctly because the code manually controls tool execution.

**Expected behavior**: To actually block tools in the graph path, you must use `interrupt_on` configuration in `create_deep_agent`, or the `HumanInTheLoopMiddleware`. Event-stream-level blocking is a no-op.

**Impact**: Hooks configured in `.harness/hooks/pre_tool_call.sh` that return exit code 1 (block) will:
- ✅ Work in fallback agent mode (`stream_turn_agent`)
- ❌ NOT work in graph mode (`stream_turn_graph`) — tool executes anyway

**Fix**:
Pass `interrupt_on` to `create_deep_agent` based on hook configuration:
```python
# In harness_builder.py, build():
interrupt_config = None
if self.hook_loader.exists:
    hooks = self.hook_loader.list_hooks()
    has_pre_tool_hook = any(h.event == "pre_tool_call" for h in hooks)
    if has_pre_tool_hook:
        # Let HumanInTheLoopMiddleware handle blocking
        interrupt_config = {"tools": True}

self.agent = create_deep_agent(
    ...,
    interrupt_on=interrupt_config,
)
```

---

## Bug 5: `_build_middleware_pipeline` Passes `memory_sources` to Function But Never Uses Them

**Location**: `harness_builder.py:254-258`, `354-434`

**Problem**: `_build_middleware_pipeline` receives `memory_sources` as a parameter but annotates it `# noqa: ARG002` (unused argument). The middleware pipeline assembly completely ignores the memory sources.

This is technically correct because `create_deep_agent` auto-creates `MemoryMiddleware` from the `memory=` parameter. But the combined `rule_sources + skill_sources` passed on line 257 is wrong — skill sources should go to `skills=`, not `memory=`.

**Actual bug on line 257**:
```python
middleware = self._build_middleware_pipeline(
    ...
    memory_sources=rule_sources + skill_sources,  # BUG: skills != memory
    ...
)
```

This conflation doesn't cause runtime errors (the param is unused), but it documents confusion about the architecture. The real issue is that skill_sources and rule_sources are correctly separated on lines 276-277:
```python
memory=rule_sources if rule_sources else None,
skills=skill_sources if skill_sources else None,
```

**Fix**: Remove the misleading `memory_sources` parameter from `_build_middleware_pipeline`, or pass only `rule_sources`.

---

## Bug 6: Subagent Tool Resolution Fails Silently During Build

**Location**: `subagent_loader.py:275-303` (`_resolve_tools`)

**Problem**: When a subagent YAML references tool names (e.g., `tools: [read_file, grep]`), these are resolved against `ToolRegistry`. But the registry used is the one passed at `CLIAgent._load_harness_if_present()` time — populated only with `BASIC_TOOLS`.

If a subagent references a tool not in `BASIC_TOOLS` (e.g., a custom MCP tool, or `execute_command` which IS in BASIC_TOOLS but could be misspelled), `_resolve_tools` raises `SubAgentLoadError`. This exception is caught at `cli.py:192-194`:
```python
try:
    self._harness_subagent_defs = builder.get_subagent_defs()
except Exception as e:
    print(f"  {Color.warn(f'⚠ Subagent loading failed: {e}')}")
```

**Impact**: A single misconfigured subagent YAML silently disables ALL subagents (because `load_all()` is atomic — one failure aborts the entire load).

**Fix**: Load subagents individually with per-file error handling:
```python
def load_all_graceful(self) -> tuple[list[dict], list[str]]:
    """Load subagents, collecting errors per-file instead of failing all."""
    definitions = []
    errors = []
    for file in sorted(self.subagents_dir.glob("*.yaml")):
        try:
            definitions.append(self._load_one(file))
        except SubAgentLoadError as e:
            errors.append(str(e))
    return definitions, errors
```

---

## Bug 7: Graph Path — `on_chain_end` Overwrites `last_messages` Incorrectly

**Location**: `cli_streaming.py:283-286`

**Problem**:
```python
elif kind == "on_chain_end":
    output = event.get("data", {}).get("output", {})
    if isinstance(output, dict):
        last_messages = output.get("messages", last_messages)
```

`astream_events` fires `on_chain_end` for EVERY node in the graph (tool nodes, model nodes, router nodes). Each intermediate node's output may have a `messages` key with partial state. The code overwrites `last_messages` with whatever the last `on_chain_end` emits — which might be from an intermediate node, not the final output.

**Impact**: The returned `last_messages` may be incomplete or from a mid-graph state rather than the final agent response.

**Fix**: Only capture messages from the ROOT chain's `on_chain_end`:
```python
elif kind == "on_chain_end":
    # Only capture the top-level graph output
    run_id = event.get("run_id", "")
    parent_ids = event.get("parent_ids", [])
    if not parent_ids:  # Root-level chain
        output = event.get("data", {}).get("output", {})
        if isinstance(output, dict):
            last_messages = output.get("messages", last_messages)
```

---

## Bug 8: `HarnessAgent` Does Not Bind Tools to LLM for Subagent Awareness

**Location**: `core/agent.py:40`

**Problem**: `HarnessAgent` binds only `BASIC_TOOLS` to the LLM via `llm.bind_tools()`. Even if a `task` tool were created for the fallback path, it would need to be included in the tools list at construction time. Currently there's no mechanism to add the task tool dynamically.

This is not a bug per se, but an architectural gap: the fallback path has no extensibility point for adding the `task` tool without modifying `BASIC_TOOLS`.

**Fix**: Accept additional tools in `_init_agent()`:
```python
tools = list(BASIC_TOOLS)
if self._harness_subagent_defs and self._graph is None:
    task_tool = self._create_task_tool()
    tools.append(task_tool)
```

---

## Bug 9: Skill Loader — `list_skills()` Calls `_extract_skill_metadata` Before `_extract_yaml_frontmatter`

**Location**: `skill_loader.py:196-200`

**Problem**:
```python
name, description = _extract_skill_metadata(content)     # heading-based
fm_name, fm_desc = _extract_yaml_frontmatter(content)    # YAML frontmatter
name = fm_name or name
description = fm_desc or description
```

The order is correct (YAML takes priority), but `_extract_skill_metadata` has a bug: when YAML frontmatter exists (starts with `---`), the regex `^#\s+(.+)` with `re.MULTILINE` will match a heading INSIDE the frontmatter if the description contains a `#` character, or more commonly, it will match the first heading AFTER the frontmatter close. This works correctly.

**However**, `_extract_skill_metadata` reads `---` as a potential horizontal rule stop token (line 74):
```python
if re.match(r"^(#+|[-*]\s|```|--|\|)", stripped):
    break
```

The pattern `--` matches `---` (the closing frontmatter delimiter), causing description extraction to break early — before finding any actual description text. If the first heading appears after `---\n---\n`, the `in_desc` flag is set but immediately broken by the closing `---`.

**Impact**: Skills with YAML frontmatter fall back to `fm_desc` from `_extract_yaml_frontmatter`, which works. Skills WITHOUT frontmatter but with `--` horizontal rules lose their description. Low severity — YAML frontmatter is the recommended format.

**Fix**: Make the stop pattern more specific:
```python
if re.match(r"^(#{1,6}\s|[-*]\s|```|---+$|\|)", stripped):
    break
```

---

## Bug 10: `create_deep_agent` Call — `memory` vs `skills` Semantic Mismatch

**Location**: `harness_builder.py:269-277`

**Problem**: According to the deep-agents reference (doc 05-subagents and 09-deepagents-code):
- `memory=` expects file paths that are **always loaded** into the system prompt via `MemoryMiddleware`
- `skills=` expects **directory paths** that `SkillsMiddleware` scans for progressive disclosure

The code correctly separates them:
```python
memory=rule_sources if rule_sources else None,    # file paths
skills=skill_sources if skill_sources else None,  # directory paths
```

BUT `rule_sources` on line 239 are converted via `_rel()` to project-relative paths:
```python
_rel = lambda p: str(Path(p).resolve().relative_to(self.project_root))
rule_sources = [_rel(p) for p in rule_sources]
```

The `MemoryMiddleware` uses the `backend` to read files. If `backend.default` is `StateBackend` (ephemeral, no disk access), then relative paths like `.harness/rules/python/coding-style.md` **cannot be read** — `StateBackend.read()` only reads from in-memory state.

**Expected behavior**: `MemoryMiddleware` should be able to read rule files from disk.

**Fix**: Ensure the `CompositeBackend` routes `.harness/` paths to `FilesystemBackend`:
```python
# In _build_backend():
routes[".harness/"] = FilesystemBackend(
    root_dir=str(self.project_root), virtual_mode=False
)
```

Or use absolute paths and let `FilesystemBackend` handle them (it supports absolute paths when `virtual_mode=False`).

---

## Priority Matrix

| Bug | Severity | Impact | Effort |
|-----|----------|--------|--------|
| 1 | **CRITICAL** | Agent crashes if `deepagents` not installed but `.harness/` exists | Medium |
| 2 | **HIGH** | Subagents advertised but never callable in fallback mode | High |
| 3 | **HIGH** | Skills invisible to agent in fallback mode | Medium |
| 4 | **HIGH** | Tool blocking hooks silently fail in graph mode | Medium |
| 7 | **MEDIUM** | Intermediate node messages corrupt final response | Low |
| 6 | **MEDIUM** | One bad subagent YAML disables all subagents | Low |
| 10 | **MEDIUM** | Rules may not load if backend doesn't support disk reads | Medium |
| 5 | **LOW** | Misleading parameter name, no runtime effect | Trivial |
| 8 | **LOW** | Architectural gap, not a crash bug | Medium |
| 9 | **LOW** | Edge case in description extraction | Trivial |

---

## Recommended Fix Order

1. **Bug 1** — Add try/except around `HarnessBuilder.build()` in `_init_agent()` for graceful fallback
2. **Bug 3** — Inject skill names + descriptions into fallback system prompt
3. **Bug 2** — Either implement a `task` tool for fallback OR suppress subagent prompt when `self._graph is None`
4. **Bug 4** — Use `interrupt_on` in `create_deep_agent` for proper hook-based blocking
5. **Bug 7** — Filter `on_chain_end` events to root-level only
6. **Bug 6** — Make subagent loading per-file with error collection
7. **Bug 10** — Route `.harness/` to `FilesystemBackend` in `CompositeBackend`
8. **Bug 5** — Clean up unused parameter
9. **Bug 8** — Add extensibility for dynamic tool injection
10. **Bug 9** — Fix regex stop pattern

---

## Architecture Observation

The core issue is a **dual-path architecture** without parity:

```
.harness/ present + deepagents installed → Graph path (full features)
.harness/ present + deepagents missing  → CRASH (Bug 1)
.harness/ absent                        → Agent path (basic, no skills/subagents)
```

The fix should establish a **three-tier graceful degradation**:

```
Tier 1: Graph path     — full deepagents features (skills, subagents, middleware)
Tier 2: Enhanced agent — .harness/ config loads skills into prompt, task tool for subagents
Tier 3: Basic agent    — no .harness/, plain HarnessAgent with BASIC_TOOLS
```

This requires:
1. Try/except around `build()` (Bug 1)
2. A `_build_enhanced_agent()` method for Tier 2 that:
   - Reads skill SKILL.md content and injects into system prompt
   - Creates a `task` tool backed by spawning temporary `HarnessAgent` instances per subagent def
   - Applies rule content directly into system prompt
   - Registers all tools (BASIC_TOOLS + task tool) with the LLM
