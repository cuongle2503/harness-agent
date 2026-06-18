# 1. Tổng quan & Kiến trúc Deep Agents

## Deep Agents là gì?

Deep Agents là một thư viện Python (`deepagents`) được xây dựng trên LangGraph, cung cấp agent có khả năng "sâu" (deep) — tức là có thể tự lập kế hoạch, quản lý file system, spawn sub-agent, ghi nhớ dài hạn, và tự tóm tắt context.

Khác với `create_agent` cơ bản của LangChain, `create_deep_agent` tích hợp sẵn một pipeline middleware toàn diện.

## Kiến trúc tổng thể

```
┌──────────────────────────────────────────────────────────────┐
│                    create_deep_agent()                        │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │                    Middleware Pipeline                    │ │
│  │                                                          │ │
│  │  Request ──▶ [TodoList] ──▶ [Memory] ──▶ [HITL] ──▶     │ │
│  │              [Filesystem] ──▶ [SubAgents] ──▶            │ │
│  │              [Summarization] ──▶ [PII] ──▶ ... ──▶ LLM  │ │
│  │                                                          │ │
│  │  ◀── LLM Response ── [Tool Calls] ── [Middleware] ──     │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │                     Backend Layer                        │ │
│  │                                                          │ │
│  │  StateBackend ◀─▶ StoreBackend ◀─▶ FilesystemBackend    │ │
│  │         │              │                 │                │ │
│  │         └──────────────┼─────────────────┘                │ │
│  │                        ▼                                  │ │
│  │               CompositeBackend                            │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │                    LangGraph Layer                        │ │
│  │                                                          │ │
│  │  StateGraph ──▶ Nodes ──▶ Edges ──▶ Conditional Routes   │ │
│  │       │                                                  │ │
│  │       ├── Checkpointer (short-term state)                │ │
│  │       └── BaseStore (long-term memory)                   │ │
│  └─────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

## Các thành phần chính

### 1. `create_deep_agent()` — Hàm entry point

Hàm duy nhất để khởi tạo deep agent, trả về `CompiledStateGraph`. Nhận tất cả cấu hình: model, tools, middleware, backends, memory, permissions...

### 2. Middleware — Pipeline xử lý

Middleware là các lớp can thiệp vào vòng đời request/response của agent. Mỗi middleware có thể:
- Thêm tools vào agent
- Sửa system prompt
- Can thiệp trước/sau khi LLM được gọi
- Xử lý tool calls

Có **14+ middleware** có sẵn (xem [Middleware](03-middleware.md)).

### 3. Backends — Lớp lưu trữ

Backend quyết định cách agent lưu trữ file và state:
- **StateBackend** — lưu trong state của graph (ephemeral)
- **StoreBackend** — lưu vào LangGraph Store (persistent, cross-thread)
- **FilesystemBackend** — lưu vào ổ đĩa thật
- **CompositeBackend** — kết hợp nhiều backend theo path prefix

### 4. Subagents — Ủy quyền task

Agent chính có thể spawn sub-agent thông qua `task` tool (từ `SubAgentMiddleware`). Sub-agent là ephemeral, chạy độc lập và trả về kết quả duy nhất.

### 5. Memory — Bộ nhớ dài hạn

Memory được quản lý qua:
- **MemoryMiddleware** — đọc file AGENTS.md, inject vào system prompt
- **StoreBackend** — lưu key-value persistent với namespace
- **CompositeBackend** — route các path như `/memories/` vào StoreBackend

### 6. Streaming

Deep Agents hỗ trợ streaming qua `stream()` và `astream()` với nhiều `stream_mode`:
- `values` — state sau mỗi bước
- `updates` — updates từ mỗi node
- `messages` — LLM tokens token-by-token
- `custom` — custom events từ bên trong nodes

Đặc biệt, `deepagents` hỗ trợ **subagent streaming** — có thể stream riêng biệt từng sub-agent song song với main agent.

## Vòng đời request

```
1. User gửi message
2. MemoryMiddleware inject AGENTS.md vào system prompt
3. FilesystemMiddleware cung cấp các file tools (read, write, edit, glob, grep)
4. TodoListMiddleware thêm write_todos tool
5. SubAgentMiddleware thêm task tool
6. LLM xử lý request, quyết định gọi tools
7. Tool calls được thực thi (có thể qua HITL nếu configured)
8. Summarization kiểm tra token limit, tự động summarize nếu cần
9. LLM tổng hợp kết quả
10. Response được trả về (kèm stream nếu dùng stream)
```

## Khả năng đặc biệt của Deep Agents

| Khả năng | Cơ chế |
|----------|--------|
| **Lập kế hoạch** | TodoListMiddleware — `write_todos` tool |
| **Quản lý file** | FilesystemMiddleware — `read_file`, `write_file`, `edit_file`, `glob`, `grep` |
| **Shell execution** | ShellToolMiddleware — persistent shell session |
| **Code execution** | Sandbox backends (Docker, etc.) |
| **Ủy quyền** | SubAgentMiddleware — `task` tool spawn sub-agent |
| **Ghi nhớ** | MemoryMiddleware + StoreBackend — persistent cross-session |
| **Tóm tắt** | SummarizationMiddleware — auto-compact context |
| **An toàn** | HITL Middleware, PII Middleware, Filesystem Permissions |
| **Streaming** | Multi-mode stream + subagent stream handles |
| **Fallback** | ModelFallbackMiddleware — tự động chuyển model dự phòng |
