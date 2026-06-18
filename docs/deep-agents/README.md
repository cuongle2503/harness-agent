# LangChain Deep Agents — Tài liệu tổng hợp

Deep Agents là kiến trúc agent tiên tiến nhất của LangChain, được xây dựng trên LangGraph, cung cấp khả năng planning, filesystem, subagent orchestration, memory, và streaming.

## Mục lục

| # | Tài liệu | Mô tả |
|---|----------|-------|
| 1 | [Tổng quan & Kiến trúc](01-overview-architecture.md) | Deep Agent là gì, kiến trúc tổng thể, các thành phần chính |
| 2 | [API: `create_deep_agent`](02-api-reference.md) | Tham số, kiểu trả về, cách sử dụng hàm chính |
| 3 | [Hệ thống Middleware](03-middleware.md) | 14+ middleware có sẵn: Summarization, HITL, TodoList, PII, Filesystem... |
| 4 | [Hệ thống Backends](04-backends.md) | StateBackend, StoreBackend, FilesystemBackend, CompositeBackend, Sandbox |
| 5 | [Subagents & Task Delegation](05-subagents.md) | Cách spawn subagent, task tool, async subagent, handoff pattern |
| 6 | [Hệ thống Memory](06-memory.md) | MemoryMiddleware, AGENTS.md, long-term memory, StoreBackend, namespace |
| 7 | [Streaming & Events](07-streaming.md) | stream, astream, stream_mode, subagent streaming, custom events |
| 8 | [Multi-Agent Patterns](08-multi-agent.md) | Handoff, Router, Swarm, collaboration patterns với LangGraph |
| 9 | [Deep Agents Code (CLI/Server)](09-deepagents-code.md) | `create_cli_agent`, `server_session`, sandbox, MCP integration |

## Deep Agents là gì?

**Deep Agents** là một extension của LangChain cung cấp agent có khả năng:

- **Planning** — lập kế hoạch và theo dõi tiến độ với TodoListMiddleware
- **File System** — đọc/ghi file qua FilesystemMiddleware với nhiều backend
- **Subagents** — spawn các sub-agent để xử lý task độc lập, song song
- **Memory** — lưu trữ dài hạn qua StoreBackend, hỗ trợ AGENTS.md
- **Summarization** — tự động tóm tắt context khi vượt ngưỡng token
- **Streaming** — stream real-time messages, subagent progress, tool calls

## Cài đặt

```bash
pip install deepagents langchain langgraph
```

## Kiến trúc tổng thể

```
┌─────────────────────────────────────────────────────┐
│                  create_deep_agent()                 │
├─────────────────────────────────────────────────────┤
│  Model (LLM)                                         │
│  ├── Tools (custom + built-in)                       │
│  ├── Middleware Pipeline                             │
│  │   ├── TodoListMiddleware (planning)               │
│  │   ├── FilesystemMiddleware (file ops)             │
│  │   ├── SubAgentMiddleware (task delegation)        │
│  │   ├── SummarizationMiddleware (context mgmt)      │
│  │   ├── MemoryMiddleware (long-term memory)         │
│  │   ├── HumanInTheLoopMiddleware (approval)         │
│  │   └── ... (custom middleware)                     │
│  ├── Backend (State | Store | Filesystem | Composite)│
│  ├── Checkpointer (state persistence)                │
│  └── Store (long-term memory)                        │
└─────────────────────────────────────────────────────┘
                        │
                        ▼
            CompiledStateGraph (LangGraph)
                        │
                        ▼
              invoke / stream / astream
```

## Ví dụ nhanh

```python
from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from deepagents.middleware.summarization import (
    SummarizationMiddleware,
    SummarizationToolMiddleware,
)
from langchain_deepseek import ChatDeepSeek

model = ChatDeepSeek(model="deepseek-v4-flash")

backend = FilesystemBackend(root_dir="/data")

summ = SummarizationMiddleware(
    model="deepseek-v4-flash",
    backend=backend,
    trigger=("fraction", 0.85),
    keep=("fraction", 0.10),
)

agent = create_deep_agent(
    model=model,
    tools=[],  # custom tools here
    system_prompt="You are a helpful assistant.",
    middleware=[summ, SummarizationToolMiddleware(summ)],
    backend=backend,
)

result = agent.invoke(
    {"messages": [{"role": "user", "content": "Analyze the data..."}]},
    config={"configurable": {"thread_id": "session-1"}},
)
```

## So sánh: LangChain Agent vs Deep Agent

| Tính năng | `create_agent` | `create_deep_agent` |
|-----------|----------------|---------------------|
| Tool calling | ✅ | ✅ |
| Filesystem | ❌ | ✅ (FilesystemMiddleware) |
| Planning/Todo | ❌ (manual) | ✅ (TodoListMiddleware) |
| Subagents | ❌ | ✅ (SubAgentMiddleware) |
| Memory | ❌ (manual) | ✅ (MemoryMiddleware) |
| Summarization | ❌ | ✅ (SummarizationMiddleware) |
| Streaming | ✅ | ✅ (enhanced: subagent streams) |
| HITL | ❌ | ✅ (HumanInTheLoopMiddleware) |

## Nguồn tham khảo

- [LangChain Reference Docs](https://reference.langchain.com/python/deepagents)
- [LangChain OSS Docs](https://docs.langchain.com/oss/python/langchain)
- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
