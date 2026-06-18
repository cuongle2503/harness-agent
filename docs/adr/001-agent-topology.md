# ADR-001: Agent Topology — Coordinator + Deep Agent Subagents

> **Status**: ✅ Accepted
> **Date**: 2026-06-18
> **Phase**: 2 — Architecture & Design
> **Deciders**: harness-architect agent

---

## Context

Harness Agent cần xử lý đa dạng task trên nhiều domain: code generation, research, code review, shell execution, file manipulation, và architecture design. Câu hỏi kiến trúc cốt lõi: **một agent duy nhất với nhiều tools, hay nhiều agent chuyên biệt phối hợp?**

Các yếu tố cần cân nhắc:
- Mỗi domain cần reasoning strategy và tool set khác nhau
- Một số task có thể chạy song song (research + code generation)
- Context isolation quan trọng — không muốn context của coder bị nhiễu bởi research context
- Muốn tận dụng model khác nhau cho các task khác nhau (pro cho code, flash cho research)

## Decision

**Chọn Coordinator Agent + Deep Agent Subagents pattern** (SubAgentMiddleware).

```
┌─────────────────────────────────────────────────────────────┐
│                  Main Orchestrator Agent                     │
│                   (deepseek-v4-flash)                        │
│                                                              │
│  Responsibilities:                                           │
│  • Lập kế hoạch task (TodoListMiddleware)                    │
│  • Phân tích yêu cầu → chọn subagent phù hợp                │
│  • Tổng hợp kết quả từ subagents                            │
│  • Tương tác trực tiếp với user                             │
│                                                              │
│  Tools: write_todos, read_file, write_file, edit_file,      │
│         glob, grep, execute_command, task                    │
└──────────┬──────────┬──────────┬──────────┬─────────────────┘
           │          │          │          │
           ▼          ▼          ▼          ▼
    ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
    │Researcher│ │  Coder   │ │ Reviewer │ │Architect │
    │(v4-flash)│ │(v4-pro)  │ │(v4-flash)│ │(v4-pro)  │
    │          │ │          │ │          │ │          │
    │web_search│ │read_file │ │read_file │ │read_file │
    │fetch_url │ │write_file│ │glob      │ │glob      │
    │          │ │edit_file │ │grep      │ │grep      │
    │          │ │exec_py   │ │exec_cmd  │ │web_search│
    │          │ │exec_cmd  │ │          │ │          │
    └──────────┘ └──────────┘ └──────────┘ └──────────┘
         ▲            ▲            ▲            ▲
         │            │            │            │
         └────────────┴────────────┴────────────┘
              Ephemeral — spawn on demand, die after result
```

### Luồng xử lý điển hình

```
User Request
    │
    ▼
Main Orchestrator phân tích yêu cầu
    │
    ├── Plan: write_todos()
    │
    ├── Spawn subagents (có thể song song):
    │   ├── task("researcher", "Research X...")
    │   ├── task("coder", "Implement Y...")
    │   └── task("reviewer", "Review Z...")
    │
    ├── Collect results từ các subagents
    │
    ├── Synthesize & present
    │
    └── Response to user
```

## Alternatives Considered

### 1. Single Agent + All Tools (Rejected)

**Mô tả**: Một agent duy nhất với toàn bộ tools (web_search, execute_python, read_file, write_file, execute_command...).

**Pros**:
- Đơn giản — một agent, không cần orchestration
- Không có overhead subagent spawn
- Dễ debug

**Cons**:
- Context bị nhiễu — quá nhiều tools trong system prompt (~15+ tools)
- Không có context isolation — research context lẫn với code context
- Không tận dụng được model khác nhau cho từng task
- Không thể chạy song song các task độc lập
- Token cost cao hơn vì context lớn

**Lý do reject**: Harness Agent có quá nhiều domain không đồng nhất. Một agent đơn lẻ sẽ bị quá tải tool selection và context.

### 2. Multi-Agent Handoff Pattern (Rejected)

**Mô tả**: Các agent chuyên biệt (sales/support style), chuyển giao conversation giữa các agent.

**Pros**:
- Mỗi agent có expertise rõ ràng
- Context isolation tốt
- Phù hợp với domain-specific routing

**Cons**:
- Không hỗ trợ parallel execution — chỉ một agent active tại một thời điểm
- Handoff overhead — cần serialize/deserialize state
- Không phù hợp với task cần multiple perspectives đồng thời
- User có thể bị "ping pong" giữa các agent

**Lý do reject**: Harness Agent cần chạy song song (research + code + review đồng thời), không phải tuần tự handoff.

### 3. Supervisor-Worker Pattern (Rejected)

**Mô tả**: Supervisor agent quyết định worker nào chạy ở mỗi bước, workers báo cáo lại cho supervisor.

**Pros**:
- Centralized control
- Phù hợp với multi-step sequential workflows
- Supervisor có thể điều chỉnh hướng đi

**Cons**:
- Supervisor là bottleneck — tất cả decisions qua supervisor
- Không hỗ trợ parallel execution tự nhiên
- Phức tạp hơn SubAgentMiddleware
- Over-engineering cho use case của Harness Agent

**Lý do reject**: Harness Agent cần parallel execution nhiều hơn sequential pipeline. SubAgentMiddleware đã cung cấp cơ chế delegation + parallel đủ mạnh và đơn giản hơn.

## Consequences

### Positive
- ✅ **Context isolation**: Mỗi subagent có context riêng, không bị nhiễu
- ✅ **Model optimization**: Dùng v4-pro cho task nặng (code, architecture), v4-flash cho task nhẹ (research, review)
- ✅ **Parallel execution**: Các subagents chạy song song, giảm latency
- ✅ **Minimal tools per agent**: Mỗi subagent chỉ có tools cần thiết → tool selection chính xác hơn
- ✅ **Ephemeral & disposable**: Subagents không lưu state → không leak memory giữa các task
- ✅ **Scalable**: Dễ dàng thêm subagent mới mà không ảnh hưởng agent khác

### Negative
- ⚠️ **Spawn overhead**: Mỗi subagent cần khởi tạo context mới (~200-500ms)
- ⚠️ **No inter-agent communication**: Subagents không thể nói chuyện trực tiếp với nhau
- ⚠️ **Orchestrator complexity**: Main agent cần biết khi nào dùng subagent nào
- ⚠️ **Token cost**: Mỗi subagent có system prompt riêng → tổng token có thể cao hơn

### Mitigation
- **Spawn overhead**: Chỉ spawn subagent cho task thực sự phức tạp (>3 tool calls). Task đơn giản thì main agent tự xử lý.
- **No inter-agent**: Nếu cần multi-step dependency, main agent sẽ orchestrate tuần tự: spawn A → collect result → spawn B với result của A.
- **Orchestrator complexity**: System prompt của main agent có hướng dẫn rõ ràng khi nào dùng subagent nào.
- **Token cost**: Dùng v4-flash ($0.14/1M input) cho subagent nhẹ. Chỉ dùng v4-pro ($0.435/1M input) cho code và architecture.

---

## References

- [AIDLC Lifecycle §2.1](../guides/aidlc-lifecycle.md#21-agent-topology-decision-tree)
- [Deep Agents Overview §4](../deep-agents/01-overview-architecture.md#4-subagents--ủy-quyền-task)
- [Subagents & Task Delegation](../deep-agents/05-subagents.md)
- [Multi-Agent Patterns — Pattern Comparison](../deep-agents/08-multi-agent.md#pattern-comparison)
- [Harness Agent Requirements §1](../requirements/harness-agent-requirements.md#1-use-case-classification)
