# Plan 7: Audit — Logic Code vs Kiến Trúc Chuẩn

> **Mục tiêu**: So sánh logic code hiện tại với kiến trúc chuẩn của AI Agent Harness (skills/rules/hooks/subagents), chỉ rõ từng điểm sai và đề xuất hướng sửa.
> **Trạng thái**: 📋 Audit — cần review trước khi implement
> **Ngày**: 2026-06-23

---

## 0. Kiến Trúc Chuẩn (Reference)

Dựa trên Claude Code architecture, research từ web, và các tài liệu deep-agents:

| Component | Cơ chế load | Context cost | Bản chất |
|-----------|-------------|-------------|----------|
| **Rules** | Always-loaded, unscoped hoặc path-scoped, re-injected on compaction | Cao (luôn chiếm context) | Constraints/conventions — "điều gì luôn đúng" |
| **Skills** | Progressive disclosure: chỉ **name + description** load lúc start, **full body** load khi task match | Thấp (body chỉ vào khi cần) | Procedural workflows — "việc này làm thế nào" |
| **Hooks** | 17 lifecycle events, chạy ngoài agent loop, PreToolUse có thể block (exit code 2) | Gần zero | Deterministic automation — "mỗi khi X thì luôn làm Y" |
| **Subagents** | Context-isolated, LLM spawn qua `task` tool, SubAgentMiddleware quản lý, chỉ final message trả về | Riêng biệt (không vào main context) | Context isolation — "giao task phụ cho agent con" |

### Flow chuẩn:

```
Rules ──always──▶ MemoryMiddleware ──▶ System Prompt ──▶ LLM
Skills ─on-demand▶                                    │
                                                       │
User ──input──▶ LLM ◀──tool call/result── Tools       │
                │  │                                    │
                │  └──lifecycle event──▶ Hooks          │
                │       (PreToolUse có thể block)        │
                │                                       │
                ├──task tool──▶ SubAgentMiddleware      │
                │                  └──▶ Subagent (isolated context)
                │◀─────────────── summary ──────────────│
                │                                       │
                └──response──▶ Output ──▶ User          │
```

### Middleware Pipeline (theo `DEFAULT_MIDDLEWARE_ORDER`):

```
Layer 1: TodoListMiddleware, MemoryMiddleware     ← Planning + Context (skills/rules inject ở đây)
Layer 2: HumanInTheLoopMiddleware, PIIMiddleware  ← Security
Layer 3: FilesystemMiddleware                     ← Capabilities
Layer 4: SubAgentMiddleware, ShellToolMiddleware  ← Execution (subagents quản lý ở đây)
Layer 5: SummarizationMiddleware, ContextEditing  ← Context management
Layer 6: ModelFallbackMiddleware, ToolRetry       ← Resilience
```

---

## 1. Skills — ❌ SAI NGHIÊM TRỌNG

### Vấn đề

**Code hiện tại** (`cli.py:_load_harness_if_present` + `_init_agent`):

```python
# Bước 1: Load TOÀN BỘ nội dung từng skill file
for p in skill_loader.get_memory_sources():
    self._harness_skill_texts.append(Path(p).read_text())

# Bước 2: Nhét TOÀN BỘ vào system prompt string
if self._harness_skill_texts:
    system_prompt += "\n\n## Skills\n\n"
    for content in self._harness_skill_texts:
        system_prompt += content + "\n"
```

**Điều này dẫn đến**:

- ❌ **Không có progressive disclosure** — skill "Cách deploy K8s 500 dòng" bị load full vào context ngay cả khi user chỉ hỏi "1+1=?"
- ❌ **Context cost của skills = context cost của rules** — phí phạm context window
- ❌ Skills giống hệt rules về mặt cơ chế — chỉ khác tên folder
- ❌ Không có cơ chế **description-only load** rồi **body load on invoke**

### Cách đúng

1. **Lúc init**: Chỉ load `name` + `description` (từ frontmatter hoặc vài dòng đầu) vào context
2. **Khi invoke**: Khi task match description → load full body
3. **Dùng MemoryMiddleware**: `create_deep_agent(memory=sources)` — MemoryMiddleware có cơ chế progressive disclosure built-in, không cần tự implement

### Hướng sửa

- CLI và Server phải gọi `HarnessBuilder.build()` thay vì tự build agent thủ công
- `HarnessBuilder` đã pass skills dưới dạng file paths vào `memory=` parameter của `create_deep_agent` → MemoryMiddleware sẽ xử lý progressive disclosure
- Bỏ `self._harness_skill_texts` — không còn đọc nội dung thủ công nữa

---

## 2. Rules — ⚠️ ĐÚNG HƯỚNG, SAI CƠ CHẾ

### Vấn đề

**Code hiện tại**:

```python
# Append rules vào system prompt string thủ công
if self._harness_rule_texts:
    system_prompt += "\n\n## Rules\n\n"
    for content in self._harness_rule_texts:
        system_prompt += content + "\n"
```

**Điều này dẫn đến**:

- ⚠️ Rules là "always present" → đúng hướng
- ❌ **Không dùng MemoryMiddleware** — HarnessBuilder đã có sẵn `memory=sources` parameter
- ❌ **Không path-scoping** — tất cả rules load dù không liên quan đến file đang thao tác. Ví dụ rule `src/api/**` vẫn load khi đang sửa docs
- ❌ **Không re-inject on compaction** — khi context bị compact, rules không được tự động load lại (vì chỉ là string trong system prompt)
- ❌ Rules và skills đều được append giống hệt nhau vào system prompt string → mất hết sự khác biệt về cơ chế

### Cách đúng

1. Rules được pass vào `create_deep_agent(memory=sources)` dưới dạng file paths
2. MemoryMiddleware tự đọc file, re-inject on compaction
3. Path-scoped rules (frontmatter `paths:`) chỉ load khi chạm file liên quan
4. Unscoped rules luôn load

### Hướng sửa

- Bỏ `self._harness_rule_texts` — không đọc nội dung thủ công
- Pass rule paths vào `memory=` parameter của `create_deep_agent`
- MemoryMiddleware sẽ tự quản lý load/re-inject/path-scoping

---

## 3. Hooks — ⚠️ THIẾU EVENT TYPES

### Vấn đề

**Code hiện tại** (`_stream_turn`):

| HookEvent | Đã fire? | Vị trí |
|-----------|----------|--------|
| `PRE_LLM_CALL` | ✅ | Trước `llm.astream()` |
| `POST_LLM_CALL` | ✅ | Sau `llm.astream()` |
| `PRE_TOOL_CALL` | ✅ | Trước mỗi tool execution |
| `POST_TOOL_CALL` | ✅ | Sau mỗi tool execution |
| `SESSION_START` | ❌ | Không fire |
| `SESSION_END` | ❌ | Không fire |
| `ON_ERROR` | ❌ | Không fire |

**Ngoài ra**:

- ⚠️ PreToolUse **có block capability** (`allowed=False` → skip tool) → đúng
- ❌ Thiếu `SubagentStart`/`SubagentStop` events (vì subagents chưa hoạt động)
- ⚠️ Chỉ CLI mới fire hooks — **server mode không fire hooks**

### Hướng sửa

- Fire `SESSION_START` trong `__init__` hoặc `run_interactive`
- Fire `SESSION_END` khi user `/exit` hoặc session kết thúc
- Fire `ON_ERROR` trong `except` blocks
- Khi subagents hoạt động → thêm `SubagentStart`/`SubagentStop` events
- Server mode cũng phải fire hooks

---

## 4. Subagents — ❌ DEAD CODE

### Vấn đề

**Code hiện tại**:

```python
# Load subagent definitions (cli.py dòng 807-813)
subagent_loader = SubAgentLoader(harness_dir, subagent_registry)
self._harness_subagent_defs = subagent_loader.load_all()

# Nhưng trong system prompt lại nói: (cli.py dòng 927-931)
"**IMPORTANT:** You cannot spawn or invoke subagents "
"directly — there is no ``task`` tool. "
"Subagents listed here are for reference only. "
"You do NOT have permission to create, modify, or "
"delete ``.harness/subagents/*.yaml`` files."
```

**Điều này dẫn đến**:

- ❌ Subagent definitions được load nhưng **không có `task` tool** → LLM không thể spawn
- ❌ CLI dùng `HarnessAgent(llm=..., tools=BASIC_TOOLS, ...)` thay vì `create_deep_agent(subagents=...)` → không có SubAgentMiddleware
- ❌ Subagents chỉ được liệt kê text trong system prompt → vô dụng
- ❌ **Server mode** cũng không có subagents

### So sánh: HarnessBuilder vs CLI

| | HarnessBuilder | CLI |
|---|---|---|
| Agent factory | `create_deep_agent(subagents=subagent_defs, ...)` | `HarnessAgent(...)` |
| SubAgentMiddleware | ✅ Có (auto-create từ `subagents=`) | ❌ Không có |
| `task` tool | ✅ Có | ❌ Không có |
| Context isolation | ✅ Qua SubAgentMiddleware | ❌ Không |
| Kết quả | LLM spawn được subagent | Subagent chỉ là text trong prompt |

### Cách đúng

1. Dùng `create_deep_agent(subagents=subagent_defs)` — SubAgentMiddleware tự động được tạo
2. SubAgentMiddleware cung cấp `task` tool cho LLM
3. Subagent chạy trong context riêng, chỉ final message trả về main conversation

### Hướng sửa

- CLI gọi `HarnessBuilder.build()` thay vì `HarnessAgent(...)` thủ công
- `HarnessBuilder` đã pass `subagents=subagent_defs` vào `create_deep_agent` → SubAgentMiddleware tự quản lý
- Bỏ hardcode "you cannot spawn subagents" trong system prompt

---

## 5. Server Mode — ❌ BỎ QUA TOÀN BỘ HARNESS

### Vấn đề

```python
# server.py: create_server_app()
agent = HarnessAgent(
    llm=llm,
    tools=BASIC_TOOLS,
    system_prompt="You are a production coding assistant...",  # Hardcoded!
    max_tool_iterations=cfg.max_tool_iterations,
)
```

**Điều này dẫn đến**:

- ❌ Không skills, rules, hooks, subagents
- ❌ System prompt cứng — không đọc từ `.harness/config.yaml`
- ❌ Không MemoryMiddleware → không load skills/rules
- ❌ Không SubAgentMiddleware → không có subagents
- ❌ Không EventBus → không fire hooks

### Hướng sửa

- `create_server_app` dùng `HarnessBuilder.build()` với `harness_dir` từ config
- Hoặc ít nhất pass `harness_dir` để load skills/rules/hooks/subagents

---

## 6. Gốc Rễ Vấn Đề

```
                        ┌─────────────────────┐
                        │   HarnessBuilder     │  ← ĐÚNG: dùng create_deep_agent()
                        │   .build()           │     memory=..., subagents=...
                        │                      │     MemoryMiddleware + SubAgentMiddleware
                        └──────────┬──────────┘
                                   │
                    ┌──────────────┼──────────────┐
                    │              │              │
                    ▼              ▼              ▼
              ❌ Không ai       ❌ CLI           ❌ Server
                 gọi cả      _init_agent()   create_server_app()
                             HarnessAgent()  HarnessAgent()
                             + manual str    + hardcoded str
```

**Vấn đề cốt lõi**: `HarnessBuilder` đã được implement đúng, nhưng **CLI và Server đều bỏ qua nó**, tự build agent thủ công với `HarnessAgent` + string concatenation. Tất cả logic progressive disclosure, MemoryMiddleware, SubAgentMiddleware bị bỏ qua.

---

## 7. Kế Hoạch Sửa (Đề Xuất)

### Phase A: Sửa CLI dùng HarnessBuilder

| # | Task | File | Impact |
|---|------|------|--------|
| A1 | `CLIAgent._init_agent()` gọi `HarnessBuilder.build()` thay vì `HarnessAgent(...)` | `cli.py` | 🔴 Core change |
| A2 | Bỏ `_harness_skill_texts`, `_harness_rule_texts` — không đọc nội dung thủ công | `cli.py` | 🟡 Cleanup |
| A3 | Bỏ hardcode "you cannot spawn subagents" trong `_build_harness_system_prompt` | `cli.py` | 🟡 Cleanup |
| A4 | Fire `SESSION_START`, `SESSION_END`, `ON_ERROR` hooks | `cli.py` | 🟢 New events |
| A5 | System prompt từ `HarnessBuilder._build_system_prompt()` hoặc config | `cli.py` | 🟡 Refactor |

### Phase B: Sửa Server dùng HarnessBuilder

| # | Task | File | Impact |
|---|------|------|--------|
| B1 | `create_server_app()` dùng `HarnessBuilder.build()` thay vì `HarnessAgent(...)` | `server.py` | 🔴 Core change |
| B2 | Pass `harness_dir` vào `ServerConfig` để builder biết project root | `server.py` | 🟡 Config |
| B3 | Server lifespan fire `SESSION_START`/`SESSION_END` hooks | `server.py` | 🟢 New events |

### Phase C: MemoryMiddleware Integration

| # | Task | File | Impact |
|---|------|------|--------|
| C1 | Verify `create_deep_agent(memory=sources)` có progressive disclosure cho skills | Research | 🔍 Verify |
| C2 | Nếu MemoryMiddleware chưa hỗ trợ path-scoping → thêm frontmatter `paths:` cho rules | `rule_loader.py` | 🟡 Enhancement |

### Phase D: Event Types Bổ Sung

| # | Task | File | Impact |
|---|------|------|--------|
| D1 | Thêm `SubagentStart`/`SubagentStop` vào `HookEvent` enum | `hook_loader.py` | 🟢 Extension |
| D2 | Fire `SubagentStart`/`SubagentStop` khi SubAgentMiddleware spawn/complete | `cli.py` | 🟢 New events |
| D3 | Activity UI handle `subagent_start`/`subagent_end` events | `activity.html` | 🟢 Already done |

---

## 8. Risk Assessment

| Risk | Mức độ | Mitigation |
|------|--------|-----------|
| `create_deep_agent` API thay đổi | Medium | Pin version deepagents |
| MemoryMiddleware không hỗ trợ progressive disclosure | Medium | Có thể tự implement nếu cần |
| Thay đổi CLI flow làm break user đang dùng | High | Giữ backward compat — nếu không có `.harness/` thì dùng defaults như cũ |
| Server mode refactor ảnh hưởng production | Medium | Test kỹ với `TestClient` + integration test |

---

## 9. References

| Tài liệu | Nội dung |
|----------|----------|
| [Claude Code Blog: Steering Claude Code](https://claude.com/blog/steering-claude-code-skills-hooks-rules-subagents-and-more) | Kiến trúc skills/rules/hooks/subagents chuẩn |
| [Tencent Cloud: Skills, Commands, Rules, Hooks](https://cloud.tencent.cn/developer/article/2684744) | Phân biệt 4 cơ chế extension |
| [Harness Builder Plan](06-harness-builder.md) | Thiết kế HarnessBuilder hiện tại |
| [Deep Agents Subagents](../../deep-agents/05-subagents.md) | SubAgentMiddleware + task tool |
| [Deep Agents Memory](../../deep-agents/06-memory.md) | MemoryMiddleware + sources |
| `src/harness_agent/loaders/harness_builder.py` | HarnessBuilder implementation |
| `src/harness_agent/deployment/cli.py` | CLI implementation (cần sửa) |
| `src/harness_agent/deployment/server.py` | Server implementation (cần sửa) |
