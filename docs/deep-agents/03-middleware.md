# 3. Hệ thống Middleware

Middleware là cơ chế mở rộng chính của Deep Agents. Mỗi middleware can thiệp vào vòng đời của agent: trước/sau khi LLM gọi, thêm tools, sửa system prompt, xử lý tool calls...

## Danh sách Middleware

### Deep Agents Middleware

| Middleware | Package | Mô tả |
|-----------|---------|-------|
| **FilesystemMiddleware** | `deepagents.middleware.filesystem` | Cung cấp file tools: `read_file`, `write_file`, `edit_file`, `glob`, `grep` |
| **SubAgentMiddleware** | `deepagents.middleware.subagents` | Thêm `task` tool để spawn sub-agent |
| **SummarizationMiddleware** | `deepagents.middleware.summarization` | Tự động tóm tắt conversation khi vượt ngưỡng token |
| **MemoryMiddleware** | `deepagents.middleware.memory` | Load AGENTS.md và memory files, inject vào system prompt |

### LangChain Middleware

| Middleware | Package | Mô tả |
|-----------|---------|-------|
| **TodoListMiddleware** | `langchain.agents.middleware` | Thêm `write_todos` tool cho task planning |
| **HumanInTheLoopMiddleware** | `langchain.middleware` | Dừng execution để chờ human approval |
| **ModelCallLimitMiddleware** | `langchain.middleware` | Giới hạn số lần gọi model |
| **ToolCallLimitMiddleware** | `langchain.middleware` | Giới hạn số lần gọi tool |
| **ModelFallbackMiddleware** | `langchain.middleware` | Tự động chuyển model dự phòng khi primary fail |
| **PIIMiddleware** | `langchain.middleware` | Phát hiện và xử lý PII |
| **LLMToolSelectorMiddleware** | `langchain.middleware` | Dùng LLM để chọn tools trước khi gọi main model |
| **ToolRetryMiddleware** | `langchain.middleware` | Tự động retry tool calls với exponential backoff |
| **LLMToolEmulator** | `langchain.middleware` | Emulate tool execution bằng LLM (testing) |
| **ContextEditingMiddleware** | `langchain.middleware` | Quản lý context: trim/clear tool calls cũ |
| **ShellToolMiddleware** | `langchain.middleware` | Persistent shell session cho command execution |
| **FilesystemFileSearchMiddleware** | `langchain.middleware` | Glob và Grep search tools cho filesystem |
| **AgentMiddleware** | `langchain.middleware` | Base class để tạo custom middleware |

---

## Chi tiết từng middleware

### FilesystemMiddleware

Middleware quan trọng nhất — cung cấp file system tools cho agent.

```python
from deepagents.middleware.filesystem import FilesystemMiddleware
from deepagents.backends import StateBackend, StoreBackend, CompositeBackend

# Ephemeral storage (mất khi session kết thúc)
agent = create_agent(middleware=[FilesystemMiddleware()])

# Hybrid: ephemeral + persistent /memories/
backend = CompositeBackend(
    default=StateBackend(),
    routes={"/memories/": StoreBackend()},
)
agent = create_agent(middleware=[FilesystemMiddleware(backend=backend)])

# Với sandbox Docker (có execution)
from my_sandbox import DockerSandboxBackend
sandbox = DockerSandboxBackend(container_id="my-container")
agent = create_agent(middleware=[FilesystemMiddleware(backend=sandbox)])
```

**Tools được thêm**: `read_file`, `write_file`, `edit_file`, `glob`, `grep`

---

### SubAgentMiddleware

Cho phép main agent spawn ephemeral sub-agent để xử lý task phức tạp, độc lập.

```python
from deepagents.middleware.subagents import SubAgentMiddleware
from deepagents.backends import StateBackend

backend = StateBackend()

agent = create_agent(
    "deepseek-v4-flash",
    middleware=[
        SubAgentMiddleware(
            backend=backend,
            subagents=[
                {
                    "name": "researcher",
                    "description": "Searches and returns a structured summary.",
                    "system_prompt": "Use the search tool to research.",
                    "tools": [search_tool],
                    "model": "deepseek-v4-flash",
                    "middleware": [],  # subagent cũng có thể có middleware riêng
                },
                {
                    "name": "code-reviewer",
                    "description": "Reviews code for bugs and style issues.",
                    "system_prompt": "You are a thorough code reviewer.",
                    "tools": [read_file, grep_tool],
                    "model": "deepseek-v4-flash",
                },
            ],
        ),
    ],
)
```

**SubAgent lifecycle**:
1. **Spawn** — Main agent gọi `task` tool với role, instructions, expected output
2. **Run** — Subagent hoàn thành task autonomously
3. **Return** — Subagent trả về single structured result
4. **Reconcile** — Main agent tích hợp kết quả

**Khi nào dùng task tool**:
- ✅ Task phức tạp, multi-step, có thể làm độc lập
- ✅ Task independent, có thể chạy song song
- ✅ Task cần focused reasoning hoặc heavy token/context
- ✅ Sandboxing cải thiện reliability (code execution, structured searches)

**Khi nào KHÔNG dùng**:
- ❌ Cần xem intermediate steps sau khi subagent hoàn thành
- ❌ Task quá đơn giản (vài tool calls hoặc lookup)
- ❌ Delegation không giảm token usage/complexity

---

### SummarizationMiddleware

Tự động tóm tắt conversation khi vượt quá ngưỡng token.

```python
from deepagents.middleware.summarization import (
    SummarizationMiddleware,
    SummarizationToolMiddleware,
)
from deepagents.backends import FilesystemBackend

backend = FilesystemBackend(root_dir="/data")

summ = SummarizationMiddleware(
    model="deepseek-v4-flash",       # Model dùng để summarize
    backend=backend,             # Nơi lưu bản tóm tắt
    trigger=("fraction", 0.85),  # Trigger khi dùng 85% context window
    keep=("fraction", 0.10),     # Giữ 10% context gần nhất
)

# Tool middleware: cho phép agent tự gọi summarize
tool_mw = SummarizationToolMiddleware(summ)

agent = create_deep_agent(middleware=[summ, tool_mw])
```

**Cấu hình trigger**:
- `("fraction", 0.85)` — trigger ở 85% token limit
- `("tokens", 100000)` — trigger khi vượt 100K tokens

**Cấu hình keep**:
- `("fraction", 0.10)` — giữ 10% context gần nhất
- `("tokens", 10000)` — giữ 10K tokens gần nhất

---

### TodoListMiddleware

Thêm `write_todos` tool để agent có thể lập kế hoạch và theo dõi tiến độ.

```python
from langchain.agents.middleware import TodoListMiddleware
from langchain.agents import create_agent

agent = create_agent(
    "deepseek-v4-flash",
    middleware=[
        TodoListMiddleware(
            system_prompt="Use the write_todos tool to plan and track your tasks.",
            tool_description="Write and update a structured task list.",
        ),
    ],
)

result = agent.invoke({"messages": [HumanMessage("Help me refactor my codebase")]})

# Xem danh sách todo
print(result["todos"])
# [
#   {"id": "1", "content": "Analyze current codebase", "status": "completed"},
#   {"id": "2", "content": "Identify refactoring targets", "status": "in_progress"},
#   {"id": "3", "content": "Apply refactoring", "status": "pending"},
# ]
```

---

### HumanInTheLoopMiddleware

Dừng execution để chờ human approval trước khi thực hiện tool calls.

```python
from langchain.middleware import HumanInTheLoopMiddleware

agent = create_agent(
    "deepseek-v4-flash",
    middleware=[
        HumanInTheLoopMiddleware(
            interrupt_on=["write_file", "execute_command"],  # Các tool cần approval
        ),
    ],
)
```

---

### ModelFallbackMiddleware

Tự động chuyển sang model dự phòng khi primary fail.

```python
from langchain.middleware import ModelFallbackMiddleware

agent = create_agent(
    "deepseek-v4-flash",
    middleware=[
        ModelFallbackMiddleware(
            fallback_models=["deepseek-v4-flash"],
            max_retries=3,
        ),
    ],
)
```

---

### PIIMiddleware

Phát hiện và xử lý Personally Identifiable Information.

```python
from langchain.middleware import PIIMiddleware

agent = create_agent(
    "deepseek-v4-flash",
    middleware=[PIIMiddleware()],
)
# Agent sẽ tự động phát hiện và cảnh báo về PII
```

---

## Custom Middleware

Tạo middleware riêng bằng cách kế thừa `AgentMiddleware`:

```python
from langchain.agents.middleware import AgentMiddleware
from langchain.agents import AgentState

class LoggingMiddleware(AgentMiddleware):
    """Middleware ghi log tất cả tool calls."""

    def __init__(self, log_file: str = "agent.log"):
        self.log_file = log_file

    def wrap_tool_call(self, request, handler):
        """Wrap tất cả tool calls để ghi log."""
        tool_name = request.tool_call.get("name", "unknown")
        print(f"[LOG] Calling tool: {tool_name}")
        result = handler(request)
        print(f"[LOG] Tool {tool_name} completed")
        return result
```

---

## Thứ tự middleware

Thứ tự middleware trong list quyết định thứ tự thực thi. Middleware đầu tiên trong list sẽ được áp dụng trước.

```python
# Thứ tự recommended:
middleware = [
    TodoListMiddleware(),        # 1. Planning trước
    MemoryMiddleware(...),       # 2. Load memory vào context
    HumanInTheLoopMiddleware(),  # 3. Security checks
    FilesystemMiddleware(...),   # 4. File operations
    SubAgentMiddleware(...),     # 5. Task delegation
    SummarizationMiddleware(...),# 6. Context management
]
```
