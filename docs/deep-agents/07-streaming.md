# 7. Streaming & Events

Deep Agents hỗ trợ streaming toàn diện qua LangGraph, bao gồm streaming message thời gian thực, tool call progress, subagent progress, và custom events.

## Stream Modes

```python
# Các stream mode có sẵn:
stream_modes = [
    "values",       # State sau mỗi bước
    "updates",      # Updates từ mỗi node/task
    "messages",     # LLM tokens token-by-token + metadata
    "custom",       # Custom events từ bên trong nodes (StreamWriter)
    "checkpoints",  # Event khi checkpoint được tạo
    "tasks",        # Events khi tasks start/finish
    "debug",        # Debug events chi tiết
]
```

## Basic Streaming

### Stream values — state updates

```python
for step in agent.stream(
    {"messages": [{"role": "user", "content": "Research AI"}]},
    stream_mode="values",
):
    # step chứa toàn bộ state sau mỗi bước
    print(step["messages"][-1].content)
```

### Stream messages — tokens

```python
for token, metadata in agent.stream(
    {"messages": [{"role": "user", "content": "Hello"}]},
    stream_mode="messages",
):
    # token: LLM token text
    # metadata: thông tin về token (model, node, etc.)
    print(token, end="", flush=True)
```

### Stream updates — node outputs

```python
for update in agent.stream(
    {"messages": [{"role": "user", "content": "Analyze this"}]},
    stream_mode="updates",
):
    # update: {"node_name": {"messages": [...], ...}}
    print(update)
```

### Multiple stream modes

```python
for mode, data in agent.stream(
    {"messages": [{"role": "user", "content": "Hello"}]},
    stream_mode=["messages", "updates"],
):
    if mode == "messages":
        token, metadata = data
        print(token, end="")
    elif mode == "updates":
        print(f"\n[Node: {list(data.keys())[0]}]")
```

## Async Streaming

```python
async for step in agent.astream(
    {"messages": [{"role": "user", "content": "Research AI"}]},
    stream_mode="values",
):
    print(step["messages"][-1].content)
```

### astream signature

```python
agent.astream(
    input: dict | Any,
    *,
    stream_mode: list[str] | None = None,
    subgraphs: bool = False,
    config: dict[str, Any] | None = None,
    context: Any | None = None,
    durability: str | None = None,
) -> AsyncIterator[tuple[tuple[str, ...], str, Any]]
```

## Subagent Streaming

Deep Agents hỗ trợ **stream riêng biệt cho từng subagent**, cho phép theo dõi real-time tiến độ của cả main agent và subagents.

### JavaScript Example (concept)

```typescript
const stream = await agent.streamEvents(
  { messages: [{ role: "user", content: "Research quantum computing" }] },
  { version: "v3" }
);

const coordinatorMessages: string[] = [];
const subagentHandles: { name: string }[] = [];

await Promise.all([
  // Stream main agent messages
  (async () => {
    for await (const message of stream.messages) {
      console.log("[coordinator]", await message.text);
      coordinatorMessages.push(await message.text);
    }
  })(),

  // Stream subagent messages — mỗi subagent có stream handle riêng
  (async () => {
    for await (const subagent of stream.subagents) {
      console.log(`[${subagent.name}] started`);
      subagentHandles.push({ name: subagent.name });
      for await (const message of subagent.messages) {
        console.log(`[${subagent.name}]`, await message.text);
      }
    }
  })(),
]);
```

### Python Pattern — Custom Events trong Subagent

```python
from langchain_core.callbacks.manager import adispatch_custom_event
from langchain_core.runnables import RunnableLambda
import asyncio

async def slow_task(some_input: str, config) -> str:
    """Task dài với progress events."""
    await asyncio.sleep(1)
    await adispatch_custom_event(
        "progress_event",
        {"message": "Finished step 1 of 3"},
        config=config,
    )
    await asyncio.sleep(1)
    await adispatch_custom_event(
        "progress_event",
        {"message": "Finished step 2 of 3"},
        config=config,
    )
    await asyncio.sleep(1)
    return "Done"

# Stream custom events
async for event in slow_task.astream_events("some_input", version="v2"):
    print(event)
```

## Stream Events v3 (Protocol Events)

LangChain v3 streaming cung cấp granular events:

| Event | Mô tả |
|-------|-------|
| `message-start` | Bắt đầu message mới |
| `content-block-start` | Bắt đầu content block (text, tool_use, thinking...) |
| `content-block-delta` | Delta update của content block |
| `content-block-finish` | Kết thúc content block |
| `message-finish` | Kết thúc message |

```python
from langchain_core.callbacks.base import LLMManagerMixin

class StreamObserver(LLMManagerMixin):
    def on_stream_event(self, event, *, run_id, parent_run_id=None, tags=None, **kwargs):
        """Xử lý từng protocol event."""
        match event.type:
            case "message-start":
                print(f"\n[Message Start] {event.message.id}")
            case "content-block-start":
                print(f"\n[Block Start] {event.content_block.type}")
            case "content-block-delta":
                if hasattr(event.content_block, 'text'):
                    print(event.content_block.text, end="")
            case "content-block-finish":
                print(f"\n[Block Finish]")
            case "message-finish":
                print(f"\n[Message Finish] stop_reason={event.message.stop_reason}")
```

## Streaming Configurations

```python
agent.stream(
    input,
    config=config,
    stream_mode="values",
    subgraphs=True,           # Stream cả events từ subgraphs
    interrupt_before=["tools"], # Dừng trước khi gọi tools
    interrupt_after=["agent"],  # Dừng sau khi agent chạy
    debug=True,               # Debug events
    version="v2",             # v1: cũ, v2: mới với protocol events
)
```

## Complete Streaming Example

```python
from deepagents import create_deep_agent
from langchain_deepseek import ChatDeepSeek
import asyncio

async def main():
    model = ChatDeepSeek(model="deepseek-v4-flash")
    agent = create_deep_agent(model=model)

    config = {"configurable": {"thread_id": "stream-demo"}}

    # Stream với multiple modes
    async for mode, data in agent.astream(
        {
            "messages": [{
                "role": "user",
                "content": "Write a Python function to calculate Fibonacci numbers"
            }]
        },
        config=config,
        stream_mode=["messages", "updates", "custom"],
        subgraphs=True,
        version="v2",
    ):
        if mode == "messages":
            token, metadata = data
            print(token, end="", flush=True)

        elif mode == "updates":
            node_name = list(data.keys())[0] if data else "unknown"
            print(f"\n--- Node completed: {node_name} ---")

        elif mode == "custom":
            print(f"\n[Custom Event] {data}")

asyncio.run(main())
```

## Best Practices

1. **Chọn stream mode phù hợp**: `messages` cho real-time text, `updates` cho progress tracking, `values` cho full state snapshot
2. **Dùng subgraphs=True** khi cần track subagent progress
3. **Multiple modes**: Stream nhiều mode cùng lúc để có cả progress + output
4. **Custom events**: Dùng `adispatch_custom_event` để emit progress từ long-running tasks
5. **Version v2**: Dùng `version="v2"` cho protocol events chi tiết hơn
6. **Async ưu tiên**: Dùng `astream` trong production để không blocking
