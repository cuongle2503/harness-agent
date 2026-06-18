# 5. Subagents & Task Delegation

Subagents là cơ chế cốt lõi để Deep Agents xử lý các task phức tạp bằng cách spawn các ephemeral agent chuyên biệt.

## Cơ chế hoạt động

```
Main Agent (Coordinator)
    │
    ├── Gọi task("researcher", "Research quantum computing")
    │       │
    │       └── Researcher Subagent (ephemeral)
    │               ├── Gọi search tool
    │               ├── Đọc web pages
    │               └── Return: synthesized report
    │
    ├── Gọi task("coder", "Write Python script for...")  ← song song
    │       │
    │       └── Coder Subagent (ephemeral)
    │               ├── Gọi execute_code tool
    │               └── Return: working code
    │
    └── Synthesize kết quả từ cả hai subagent
```

## SubAgentMiddleware

```python
from deepagents.middleware.subagents import SubAgentMiddleware
from deepagents.backends import StateBackend

backend = StateBackend()

agent = create_agent(
    "claude-sonnet-4-6",
    middleware=[
        SubAgentMiddleware(
            backend=backend,
            subagents=[
                {
                    "name": "researcher",
                    "description": "Searches the web and returns structured research summaries.",
                    "system_prompt": "You are a thorough researcher. Use available search tools...",
                    "tools": [search_tool, fetch_url_tool],
                    "model": "claude-sonnet-4-6",
                    "middleware": [],  # Subagent-specific middleware
                },
            ],
        ),
    ],
)
```

### Cấu trúc SubAgent Definition

```python
subagent_definition = {
    "name": str,              # Tên duy nhất, dùng trong task tool
    "description": str,       # Mô tả — agent dùng để chọn subagent phù hợp
    "system_prompt": str,     # System prompt riêng cho subagent
    "tools": list[BaseTool],  # Tools riêng cho subagent
    "model": str | BaseChatModel,  # Model riêng (có thể khác main agent)
    "middleware": list[AgentMiddleware],  # Middleware riêng (thường [])
}
```

## Task Tool — Cách spawn subagent

`SubAgentMiddleware` tự động thêm `task` tool vào agent. Agent gọi tool này để spawn subagent.

### Task Tool Description (nội dung system prompt)

```
## `task` (subagent spawner)

You have access to a `task` tool to launch short-lived subagents that handle
isolated tasks. These agents are ephemeral — they live only for the duration
of the task and return a single result.

### When to use the task tool:
- When a task is complex and multi-step, and can be fully delegated in isolation
- When a task is independent of other tasks and can run in parallel
- When a task requires focused reasoning or heavy token/context usage
- When sandboxing improves reliability (e.g. code execution)
- When you only care about the output of the subagent, not intermediate steps

### Subagent lifecycle:
1. **Spawn** → Provide clear role, instructions, and expected output
2. **Run** → The subagent completes the task autonomously
3. **Return** → The subagent provides a single structured result
4. **Reconcile** → Incorporate or synthesize the result into the main thread

### When NOT to use:
- If you need to see intermediate reasoning/steps
- If the task is trivial (a few tool calls or simple lookup)
- If delegating does not reduce token usage, complexity, or context switching
- If splitting would add latency without benefit

### Important:
- Whenever possible, parallelize! Launch multiple subagents concurrently.
- Use task tool to silo independent tasks within a multi-part objective.
```

## Patterns

### Pattern 1: Parallel Research

```python
# User: "Research AI advances, quantum computing, and biotech"
# Agent gọi 3 subagents SONG SONG:

# Trong main agent's reasoning:
# task("research-agent", "Research recent AI advances in 2025-2026")
# task("research-agent", "Research quantum computing breakthroughs")
# task("research-agent", "Research biotech innovations")
# → 3 subagents chạy độc lập, trả về 3 báo cáo
# → Main agent tổng hợp
```

### Pattern 2: Isolated Code Execution

```python
# User: "Analyze this repo for security vulnerabilities"
# Agent spawns một subagent duy nhất (context-heavy task):

# task("code-reviewer", "Analyze repo X for security vulnerabilities...")
# → Subagent phân tích toàn bộ repo
# → Trả về report
# → Main agent trình bày kết quả
```

### Pattern 3: Multi-Agent Handoff

```python
from langchain.agents import AgentState, create_agent
from typing_extensions import NotRequired

class MultiAgentState(AgentState):
    active_agent: NotRequired[str]

@tool
def transfer_to_sales(runtime: ToolRuntime) -> Command:
    """Transfer to the sales agent."""
    return Command(
        goto="sales_agent",
        update={"active_agent": "sales_agent", "messages": [...]},
        graph=Command.PARENT,
    )

@tool
def transfer_to_support(runtime: ToolRuntime) -> Command:
    """Transfer to the support agent."""
    return Command(
        goto="support_agent",
        update={"active_agent": "support_agent", "messages": [...]},
        graph=Command.PARENT,
    )

# Tạo agents với handoff tools
sales_agent = create_agent(
    "claude-sonnet-4-6",
    tools=[transfer_to_support],
    system_prompt="You are a sales agent. Transfer to support for technical issues.",
)

support_agent = create_agent(
    "claude-sonnet-4-6",
    tools=[transfer_to_sales],
    system_prompt="You are a support agent. Transfer to sales for pricing.",
)
```

### Pattern 4: Router với Multiple Knowledge Bases

```python
from pydantic import BaseModel, Field

class ClassificationResult(BaseModel):
    classifications: list[Classification]

class Classification(BaseModel):
    source: str   # "github" | "notion" | "slack"
    query: str    # Targeted sub-question

# Router phân tích query và gửi đến đúng agents
def classify_query(state: RouterState) -> dict:
    structured_llm = router_llm.with_structured_output(ClassificationResult)
    result = structured_llm.invoke([...])
    return {"classifications": result.classifications}

def route_to_agents(state: RouterState) -> list[Send]:
    return [Send(c.source, {"query": c.query}) for c in state.classifications]
```

## Async Subagents

Deep agents cũng hỗ trợ subagent chạy bất đồng bộ trên remote server:

```python
# ASYNC_TASK_TOOL_DESCRIPTION — constant từ deepagents.middleware.async_subagents

# Usage flow:
# 1. task("async-analyzer", "Analyze large dataset...") → returns task_id
# 2. Agent báo cáo task_id cho user
# 3. check_async_task(task_id) — khi user hỏi status
# 4. update_async_task(task_id, "New instructions...") — gửi thêm instructions
```

## Best Practices

1. **Mô tả task rõ ràng**: Subagent không có context của user intent — mô tả chi tiết expected output
2. **Song song hóa**: Luôn spawn subagents song song khi có thể
3. **Subagent model**: Có thể dùng model nhỏ hơn/rẻ hơn cho subagent
4. **Middleware cho subagent**: Thường để `[]` trừ khi cần capability đặc biệt
5. **Backend sharing**: Subagent dùng chung backend với main agent
6. **Trust outputs**: Kết quả từ subagent nên được tin cậy (đã được validate bởi chính subagent đó)

## Ví dụ hoàn chỉnh

```python
from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend
from deepagents.middleware import FilesystemMiddleware, SubAgentMiddleware
from deepagents.middleware.summarization import SummarizationMiddleware
from langchain.agents.middleware import TodoListMiddleware
from langchain.tools import tool

@tool
def search(query: str) -> str:
    """Search for information."""
    return f"Results for: {query}"

@tool
def execute_python(code: str) -> str:
    """Execute Python code."""
    return str(eval(code))

backend = CompositeBackend(
    default=StateBackend(),
    routes={"/memories/": StoreBackend()},
)

agent = create_deep_agent(
    model="claude-sonnet-4-6",
    tools=[search],
    system_prompt="You are a project coordinator. Delegate research to researcher subagent.",
    middleware=[
        TodoListMiddleware(),
        FilesystemMiddleware(backend=backend),
        SubAgentMiddleware(
            backend=backend,
            subagents=[
                {
                    "name": "researcher",
                    "description": "Research topics and return structured summaries.",
                    "system_prompt": "Conduct thorough research and synthesize findings.",
                    "tools": [search],
                    "model": "claude-sonnet-4-6",
                    "middleware": [],
                },
                {
                    "name": "coder",
                    "description": "Write and execute Python code.",
                    "system_prompt": "Write clean, well-documented Python code.",
                    "tools": [execute_python],
                    "model": "claude-sonnet-4-6",
                    "middleware": [],
                },
            ],
        ),
    ],
    backend=backend,
)

# User request sẽ tự động được main agent phân tích
# và delegate đến researcher hoặc coder subagent phù hợp
result = agent.invoke({
    "messages": [{
        "role": "user",
        "content": "Research Python async patterns and write an example"
    }]
})
```
