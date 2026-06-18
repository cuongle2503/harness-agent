# Python Architecture Patterns

## Agent Pattern (LangChain)

```python
from langchain_core.runnables import Runnable
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool

class HarnessAgent(Runnable):
    """Base agent following LangChain Runnable protocol."""

    def __init__(self, llm: BaseChatModel, tools: list[BaseTool]):
        self.llm = llm
        self.tools = tools

    def invoke(self, input: dict, config: RunnableConfig | None = None) -> dict:
        ...
```

## Tool Registry Pattern

```python
class ToolRegistry:
    """Central registry for MCP-compatible tools."""

    def register(self, tool: BaseTool) -> None: ...
    def get(self, name: str) -> BaseTool: ...
    def list_tools(self) -> list[ToolSchema]: ...
    def invoke_tool(self, name: str, **kwargs) -> Any: ...
```

## Memory Pattern

```python
class HybridMemory:
    """Hybrid memory: vector store + key-value + conversation buffer."""

    def store(self, key: str, value: Any, embedding: list[float] | None = None) -> None: ...
    def retrieve(self, query: str, k: int = 5) -> list[MemoryItem]: ...
    def get_context(self, session_id: str) -> ConversationContext: ...
```

## Orchestrator Pattern (LangGraph)

```python
from langgraph.graph import StateGraph

class AgentOrchestrator:
    """Multi-agent orchestration using LangGraph state machines."""

    def __init__(self, agents: dict[str, HarnessAgent]):
        self.graph = StateGraph(OrchestratorState)
        self._build_graph()

    def _build_graph(self) -> None:
        # Add agent nodes, routing edges, and conditional branches
        ...

    def run(self, task: Task, config: RunConfig) -> TaskResult:
        ...
```

## Error Handling Pattern

```python
class HarnessError(Exception):
    """Base exception for all harness errors."""

class ToolNotFoundError(HarnessError):
    """Raised when a tool is not found in the registry."""

class AgentExecutionError(HarnessError):
    """Raised when an agent execution fails."""
    def __init__(self, agent_id: str, original_error: Exception):
        self.agent_id = agent_id
        self.original_error = original_error
        super().__init__(f"Agent {agent_id} failed: {original_error}")
```
