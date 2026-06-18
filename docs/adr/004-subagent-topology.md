# ADR-004: Subagent Topology — 4 Specialized Subagents

> **Status**: ✅ Accepted
> **Date**: 2026-06-18
> **Phase**: 2 — Architecture & Design
> **Deciders**: harness-architect agent

---

## Context

Coordinator Agent pattern yêu cầu subagents chuyên biệt để xử lý các domain khác nhau. Cần xác định: bao nhiêu subagents? Mỗi subagent có tools gì? Model gì? Và làm sao để main agent chọn đúng subagent?

Dựa trên Requirements (Phase 1), Harness Agent có 4 domain chính: research, coding, code review, và architecture design.

## Decision

**Chọn 4 subagents**: researcher, coder, reviewer, architect — mỗi subagent có single responsibility, tool set riêng, và model phù hợp với task.

### Subagent Interaction Diagram

```
                         User Request
                              │
                              ▼
              ┌───────────────────────────────┐
              │     Main Orchestrator          │
              │     (deepseek-v4-flash)        │
              │                                │
              │  "I need to research X,        │
              │   code Y, and review Z"        │
              └───────┬───────┬───────┬────────┘
                      │       │       │
            ┌─────────┘       │       └─────────┐
            ▼                 ▼                 ▼
   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
   │  researcher  │  │    coder     │  │   reviewer   │
   │ (v4-flash)   │  │  (v4-pro)    │  │ (v4-flash)   │
   │              │  │              │  │              │
   │ web_search   │  │ read_file    │  │ read_file    │
   │ fetch_url    │  │ write_file   │  │ glob         │
   │              │  │ edit_file    │  │ grep         │
   │              │  │ execute_py   │  │ execute_cmd  │
   │              │  │ execute_cmd  │  │              │
   └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
          │                 │                 │
          └─────────────────┼─────────────────┘
                            │
                    ┌───────▼───────┐
                    │  architect    │
                    │  (v4-pro)     │
                    │               │
                    │ read_file     │
                    │ glob          │
                    │ grep          │
                    │ web_search    │
                    └───────────────┘
```

**Note**: Tất cả subagents có thể chạy SONG SONG. Architect thường chạy độc lập khi user yêu cầu thiết kế.

### Subagent Definitions

```python
subagents = [
    {
        "name": "researcher",
        "description": (
            "Web research specialist. Use for: technology evaluation, "
            "documentation lookup, data gathering, competitive analysis. "
            "Returns structured research summaries with citations."
        ),
        "system_prompt": (
            "You are a thorough researcher. For each research task:\n"
            "1. Plan your research approach\n"
            "2. Search for relevant information using web_search\n"
            "3. Cross-reference multiple sources with fetch_url\n"
            "4. Synthesize findings into a structured summary\n"
            "5. Include citations for all claims\n"
            "6. Note any conflicting information between sources\n"
            "7. Return only verified, factual information"
        ),
        "tools": [web_search, fetch_url],
        "model": "deepseek-v4-flash",
        "middleware": [ToolRetryMiddleware(max_retries=2)],
    },
    {
        "name": "coder",
        "description": (
            "Software engineer specialist. Use for: code generation, "
            "refactoring, debugging, test writing, script creation. "
            "Returns complete, working code with explanation."
        ),
        "system_prompt": (
            "You are a skilled software engineer. For each coding task:\n"
            "1. Read and understand the existing codebase first\n"
            "2. Follow project conventions (imports, naming, patterns, type hints)\n"
            "3. Write clean, well-documented Python code\n"
            "4. Test your code by executing it when possible\n"
            "5. Handle edge cases and errors\n"
            "6. Return the complete solution with explanation\n"
            "7. If you need to modify existing files, use edit_file"
        ),
        "tools": [
            read_file, write_file, edit_file,
            execute_python, execute_command,
        ],
        "model": "deepseek-v4-pro",
        "middleware": [
            ContextEditingMiddleware(),     # Trim context for long code sessions
            ToolRetryMiddleware(max_retries=3),
        ],
    },
    {
        "name": "reviewer",
        "description": (
            "Code review specialist. Use for: code quality review, "
            "security audit, style check, performance analysis. "
            "Returns categorized findings with actionable feedback."
        ),
        "system_prompt": (
            "You are a thorough code reviewer. For each review:\n"
            "1. Read all changed files completely\n"
            "2. Check for: bugs, security issues, style violations, "
            "performance problems\n"
            "3. Run lint and type check tools when available\n"
            "4. Verify logic correctness and edge case handling\n"
            "5. Categorize findings: CRITICAL, HIGH, MEDIUM, LOW\n"
            "6. Provide specific, actionable feedback with code examples\n"
            "7. Suggest improvements, not just problems"
        ),
        "tools": [read_file, glob, grep, execute_command],
        "model": "deepseek-v4-flash",
        "middleware": [
            ContextEditingMiddleware(),     # Trim context for large review sessions
            ToolRetryMiddleware(max_retries=2),
        ],
    },
    {
        "name": "architect",
        "description": (
            "System architecture specialist. Use for: system design, "
            "technology selection, architecture decisions, trade-off analysis. "
            "Returns design documents with rationale (ADR format)."
        ),
        "system_prompt": (
            "You are a senior software architect. For each architecture task:\n"
            "1. Understand the requirements and constraints thoroughly\n"
            "2. Research best practices and alternative approaches\n"
            "3. Evaluate trade-offs: complexity vs flexibility, "
            "performance vs maintainability, cost vs capability\n"
            "4. Design clear component boundaries and interfaces\n"
            "5. Document decisions with rationale (ADR format)\n"
            "6. Consider: scalability, security, observability, cost\n"
            "7. Provide multiple options with pros/cons when appropriate"
        ),
        "tools": [read_file, glob, grep, web_search],
        "model": "deepseek-v4-pro",
        "middleware": [
            ContextEditingMiddleware(),     # Trim context for design sessions
            ToolRetryMiddleware(max_retries=2),
        ],
    },
]
```

### Decision Matrix: Which Subagent When?

Main agent chọn subagent dựa trên task characteristics:

| Task Type | Subagent | Trigger Keywords | Model |
|-----------|----------|-----------------|-------|
| Web research, docs lookup, tech evaluation | `researcher` | research, search, find, what is, compare | v4-flash |
| Code writing, refactoring, bug fixing | `coder` | write, create, implement, fix, refactor, build | v4-pro |
| Code review, quality check, security audit | `reviewer` | review, check, audit, inspect, analyze | v4-flash |
| System design, architecture, tech choices | `architect` | design, architect, plan system, choose tech | v4-pro |
| Simple question / tool call (<3 steps) | (none — main agent handles directly) | — | v4-flash |

## Alternatives Considered

### 1. 3 Subagents (merge reviewer + architect) (Rejected)

**Mô tả**: Gộp reviewer và architect thành "senior-engineer" subagent.

**Pros**: Ít subagents hơn, đơn giản hơn

**Cons**:
- Vi phạm Single Responsibility — review và architecture là 2 skill khác nhau
- Architect cần v4-pro cho deep reasoning; reviewer chỉ cần v4-flash — gộp lại buộc phải dùng model mạnh hơn (đắt hơn)
- Review focus vào code quality; architecture focus vào system design — context khác nhau

**Lý do reject**: Giữ 4 subagents riêng biệt cho phép dùng model phù hợp và giữ responsibility rõ ràng.

### 2. 6+ Subagents (quá granular) (Rejected)

**Mô tả**: Thêm subagents như: tester, documenter, devops, data-analyst.

**Pros**: Cực kỳ chuyên biệt

**Cons**:
- Quá nhiều subagents → main agent khó chọn
- Nhiều subagent có tool set gần giống nhau
- Over-engineering cho Phase 2

**Lý do reject**: 4 subagents cover tất cả use cases hiện tại. Có thể thêm sau nếu cần.

### 3. Dynamic subagents (spawn với custom tools mỗi lần) (Rejected)

**Mô tả**: Không định nghĩa subagents cố định — main agent tự chọn tools cho mỗi lần spawn.

**Pros**: Cực kỳ linh hoạt

**Cons**:
- Phức tạp implementation
- Main agent có thể chọn sai tools
- Không có system prompt chuyên biệt → subagent chất lượng thấp hơn
- Deep Agents không hỗ trợ pattern này trực tiếp

**Lý do reject**: Subagents được định nghĩa trước với tool set cố định đảm bảo chất lượng. Pattern này đã được chứng minh hiệu quả.

## Design Principles Compliance

| Principle | Compliance |
|-----------|-----------|
| **Single Responsibility** | ✅ Mỗi subagent làm MỘT việc: research, code, review, architecture |
| **Independent** | ✅ Các subagents không phụ thuộc output của nhau — chạy song song được |
| **Disposable** | ✅ Ephemeral — không lưu state giữa các lần spawn |
| **Minimal tools** | ✅ Researcher chỉ có 2 tools; Reviewer không có write; Architect không có execute |
| **Clear contract** | ✅ Mỗi subagent có description rõ ràng + system prompt chi tiết |

### Subagent Middleware Strategy

Subagents KHÔNG để `middleware: []` hoàn toàn trống. Mỗi subagent có một bộ middleware tối thiểu:

| Middleware | Researcher | Coder | Reviewer | Architect | Rationale |
|-----------|:---:|:---:|:---:|:---:|-----------|
| `ContextEditingMiddleware` | ❌ | ✅ | ✅ | ✅ | Subagents xử lý nhiều file → trim old context |
| `ToolRetryMiddleware` | ✅ | ✅ | ✅ | ✅ | Resilience cho tool calls (max 2-3 retries) |

**Subagents KHÔNG có HITL Middleware** — Design intent: HITL check được thực hiện ở main agent khi gọi `task` tool. Subagent đã được user approve thông qua main agent. Đây là điểm kiểm soát tập trung.

**Subagents KHÔNG có SummarizationMiddleware** — Subagents là short-lived; nếu context quá dài, `ContextEditingMiddleware` trim old tool calls. Summarization chỉ cần ở main agent level cho cross-turn conversation.

**Subagents KHÔNG có MemoryMiddleware** — Subagents không cần biết user preferences/project context. Chúng nhận đầy đủ instructions từ main agent. Memory chỉ load ở main agent.

**Subagents KHÔNG có ModelFallbackMiddleware** — `ToolRetryMiddleware` đã đủ resilience. Model fallback được xử lý ở main agent level.

## Consequences

### Positive
- ✅ **Clear responsibility boundaries**: Mỗi subagent có domain rõ ràng
- ✅ **Model optimization**: v4-pro cho code/architecture, v4-flash cho research/review → cost-efficient
- ✅ **Parallel execution**: Researcher + Coder + Reviewer có thể chạy đồng thời
- ✅ **Context isolation**: Code context không nhiễu research context
- ✅ **Easy to extend**: Thêm subagent mới chỉ cần thêm definition

### Negative
- ⚠️ **Spawn overhead cho task nhỏ**: Nếu user hỏi câu đơn giản, spawn subagent là lãng phí
- ⚠️ **Main agent routing complexity**: Cần system prompt tốt để chọn đúng subagent
- ⚠️ **Không có inter-agent collaboration**: Researcher không thể trực tiếp yêu cầu Coder

### Mitigation
- **Spawn overhead**: Main agent system prompt hướng dẫn: chỉ spawn khi task >3 bước hoặc cần chuyên môn
- **Routing complexity**: Subagent descriptions chi tiết + examples trong main agent system prompt
- **No collaboration**: Main agent orchestrate: researcher result → feed vào coder → feed vào reviewer

---

## References

- [AIDLC Lifecycle §2.4](../guides/aidlc-lifecycle.md#24-subagent-topology)
- [Deep Agents Subagents](../deep-agents/05-subagents.md)
- [Subagent Best Practices](../deep-agents/05-subagents.md#best-practices)
- [Harness Agent Requirements §3](../requirements/harness-agent-requirements.md#3-subagent-identification)
