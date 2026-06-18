---
name: langchain-patterns
description: LangChain and LangGraph patterns for building AI agents — Runnable protocol, tool definition, state graphs, memory, and streaming.
origin: harness-agent
---

# LangChain & LangGraph Patterns

Best practices for building AI agents with LangChain and LangGraph.

## When to Activate

- Building new agents
- Adding tools to an agent
- Designing multi-agent orchestration
- Implementing memory systems
- Setting up streaming or callbacks

## Core Patterns

### 1. Runnable Protocol

Every agent implements `Runnable`:

```python
from langchain_core.runnables import Runnable, RunnableConfig
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool

class HarnessAgent(Runnable):
    def __init__(self, llm: BaseChatModel, tools: list[BaseTool], prompt: ChatPromptTemplate):
        self.llm = llm
        self.tools = tools
        self.prompt = prompt

    def invoke(self, input: dict, config: RunnableConfig | None = None) -> dict:
        chain = self.prompt | self.llm.bind_tools(self.tools)
        return chain.invoke(input, config)

    async def ainvoke(self, input: dict, config: RunnableConfig | None = None) -> dict:
        chain = self.prompt | self.llm.bind_tools(self.tools)
        return await chain.ainvoke(input, config)
```

### 2. Tool Definition with Pydantic

```python
from langchain_core.tools import tool
from pydantic import BaseModel, Field

class FileReadInput(BaseModel):
    """Input for reading a file."""
    path: str = Field(..., description="Absolute path to the file")
    encoding: str = Field(default="utf-8", description="File encoding")

@tool(args_schema=FileReadInput)
def read_file(path: str, encoding: str = "utf-8") -> str:
    """Read contents of a file at the given path."""
    with open(path, encoding=encoding) as f:
        return f.read()
```

### 3. MCP Tool Integration

```python
from langchain_core.tools import BaseTool
import json

class MCPToolAdapter(BaseTool):
    """Adapts an MCP tool to the LangChain BaseTool interface."""

    name: str
    description: str
    mcp_server: str
    mcp_tool_name: str

    async def _arun(self, **kwargs) -> str:
        result = await mcp_client.call_tool(
            self.mcp_server, self.mcp_tool_name, kwargs
        )
        return json.dumps(result)
```

### 4. State Graph (LangGraph)

```python
from langgraph.graph import StateGraph, END
from typing import TypedDict, Literal

class AgentState(TypedDict):
    messages: list
    next_agent: str
    tool_results: list
    final_output: str | None

def create_orchestrator(agents: dict[str, Runnable]) -> StateGraph:
    graph = StateGraph(AgentState)

    for name, agent in agents.items():
        graph.add_node(name, agent.invoke)

    graph.add_conditional_edges(
        "router",
        lambda state: state["next_agent"],
        {name: name for name in agents} | {"end": END}
    )

    graph.set_entry_point("router")
    return graph.compile()
```

### 5. Hybrid Memory

```python
from langchain.memory import ConversationBufferMemory
from langchain_community.vectorstores import Chroma

class HybridMemory:
    def __init__(self, embeddings, persist_dir: str):
        self.conversation = ConversationBufferMemory(return_messages=True)
        self.vectorstore = Chroma(
            embedding_function=embeddings,
            persist_directory=persist_dir,
        )
        self.kv_store: dict[str, Any] = {}

    def remember(self, key: str, value: Any) -> None:
        self.kv_store[key] = value

    def recall(self, query: str, k: int = 5) -> list:
        return self.vectorstore.similarity_search(query, k=k)

    def get_history(self) -> list:
        return self.conversation.load_memory_variables({})["history"]
```

## Anti-Patterns

- ❌ Not implementing full Runnable protocol (missing `ainvoke`, `batch`, etc.)
- ❌ Tools without Pydantic input validation
- ❌ State graphs without error edges
- ❌ Blocking I/O in async agent methods
- ❌ Monolithic agents instead of composable graphs

## Streaming

```python
async for event in agent.astream_events(input, version="v2"):
    if event["event"] == "on_tool_start":
        print(f"Calling tool: {event['name']}")
    elif event["event"] == "on_tool_end":
        print(f"Tool result: {event['data']['output']}")
```
