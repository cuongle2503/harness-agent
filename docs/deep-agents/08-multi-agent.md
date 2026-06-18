# 8. Multi-Agent Patterns

Multi-agent systems trong LangChain được xây dựng trên LangGraph, cho phép orchestrate nhiều agent với các pattern: Handoff, Router, Swarm, và collaboration.

## Pattern 1: Handoff (Chuyển giao)

Agent có thể chuyển giao conversation cho agent khác dựa trên expertise.

### Kiến trúc

```
User → [Sales Agent] ←→ [Support Agent]
          ↕ handoff        ↕ handoff
```

### Implementation

```python
from typing import Literal
from langchain.agents import AgentState, create_agent
from langchain.messages import AIMessage, ToolMessage
from langchain.tools import tool, ToolRuntime
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command
from typing_extensions import NotRequired

# 1. State với active_agent tracker
class MultiAgentState(AgentState):
    active_agent: NotRequired[str]

# 2. Handoff tools
@tool
def transfer_to_sales(runtime: ToolRuntime) -> Command:
    """Transfer to the sales agent."""
    last_ai_message = next(
        msg for msg in reversed(runtime.state["messages"])
        if isinstance(msg, AIMessage)
    )
    transfer_message = ToolMessage(
        content="Transferred to sales agent from support agent",
        tool_call_id=runtime.tool_call_id,
    )
    return Command(
        goto="sales_agent",
        update={
            "active_agent": "sales_agent",
            "messages": [last_ai_message, transfer_message],
        },
        graph=Command.PARENT,
    )

@tool
def transfer_to_support(runtime: ToolRuntime) -> Command:
    """Transfer to the support agent."""
    last_ai_message = next(
        msg for msg in reversed(runtime.state["messages"])
        if isinstance(msg, AIMessage)
    )
    transfer_message = ToolMessage(
        content="Transferred to support agent from sales agent",
        tool_call_id=runtime.tool_call_id,
    )
    return Command(
        goto="support_agent",
        update={
            "active_agent": "support_agent",
            "messages": [last_ai_message, transfer_message],
        },
        graph=Command.PARENT,
    )

# 3. Tạo agents
sales_agent = create_agent(
    model="claude-sonnet-4-6",
    tools=[transfer_to_support],
    system_prompt="You are a sales agent. Transfer technical issues to support.",
)

support_agent = create_agent(
    model="claude-sonnet-4-6",
    tools=[transfer_to_sales],
    system_prompt="You are a support agent. Transfer pricing questions to sales.",
)

# 4. Agent nodes
def call_sales_agent(state: MultiAgentState) -> Command:
    response = sales_agent.invoke(state)
    return response

def call_support_agent(state: MultiAgentState) -> Command:
    response = support_agent.invoke(state)
    return response

# 5. Build graph
graph = StateGraph(MultiAgentState)
graph.add_node("sales_agent", call_sales_agent)
graph.add_node("support_agent", call_support_agent)
graph.add_edge(START, "sales_agent")
app = graph.compile()
```

---

## Pattern 2: Router với Multiple Knowledge Bases

Một router agent phân tích query và gửi đến đúng knowledge base agent.

### Kiến trúc

```
             User Query
                 │
                 ▼
         [Router Agent]
          /    |    \
         ▼     ▼     ▼
    [GitHub] [Notion] [Slack]
         \    |    /
          ▼   ▼   ▼
       [Synthesizer]
            │
            ▼
        Final Answer
```

### Implementation

```python
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send
from langchain.chat_models import init_chat_model

router_llm = init_chat_model("claude-sonnet-4-6")

# Structured output schema
class Classification(BaseModel):
    source: str = Field(description="Knowledge base: github, notion, or slack")
    query: str = Field(description="Targeted sub-question for this source")

class ClassificationResult(BaseModel):
    classifications: list[Classification]

def classify_query(state: RouterState) -> dict:
    """Phân tích query và chọn knowledge bases."""
    structured_llm = router_llm.with_structured_output(ClassificationResult)

    result = structured_llm.invoke([
        {
            "role": "system",
            "content": """Analyze the query and determine which knowledge bases to consult.

Available sources:
- github: Code, API references, implementation details, issues, PRs
- notion: Internal documentation, processes, policies, team wikis
- slack: Team discussions, informal knowledge, recent conversations

Return ONLY relevant sources with targeted sub-questions."""
        },
        {"role": "user", "content": state["query"]}
    ])

    return {"classifications": result.classifications}

def route_to_agents(state: RouterState) -> list[Send]:
    """Fan out to all classified agents."""
    return [
        Send(c.source, {"query": c.query})
        for c in state["classifications"]
    ]

def query_github(state: AgentInput) -> dict:
    result = github_agent.invoke({
        "messages": [{"role": "user", "content": state["query"]}]
    })
    return {"results": [{"source": "github", "result": result["messages"][-1].content}]}

def query_notion(state: AgentInput) -> dict:
    result = notion_agent.invoke({
        "messages": [{"role": "user", "content": state["query"]}]
    })
    return {"results": [{"source": "notion", "result": result["messages"][-1].content}]}

def query_slack(state: AgentInput) -> dict:
    result = slack_agent.invoke({
        "messages": [{"role": "user", "content": state["query"]}]
    })
    return {"results": [{"source": "slack", "result": result["messages"][-1].content}]}

def synthesize_results(state: RouterState) -> dict:
    """Tổng hợp kết quả từ tất cả agents."""
    if not state["results"]:
        return {"final_answer": "No results found."}

    formatted = [
        f"**From {r['source'].title()}:**\n{r['result']}"
        for r in state["results"]
    ]

    response = router_llm.invoke([
        {
            "role": "system",
            "content": f"Synthesize search results for: \"{state['query']}\"\n"
                       f"- Combine information without redundancy\n"
                       f"- Highlight most relevant information\n"
                       f"- Note discrepancies between sources"
        },
        {"role": "user", "content": "\n\n".join(formatted)}
    ])

    return {"final_answer": response.content}
```

---

## Pattern 3: Swarm (Active Agent Router)

Swarm pattern cho phép chuyển đổi giữa các agent dựa trên active agent state.

```python
from langgraph_swarm import SwarmState, create_handoff_tool, add_active_agent_router
from langchain.agents import create_agent
from langgraph.graph import StateGraph
from langchain.checkpoint.memory import InMemorySaver

# Tạo agents
alice = create_agent(
    "claude-sonnet-4-6",
    tools=[
        add,
        create_handoff_tool(
            agent_name="Bob",
            description="Transfer to Bob for complex questions",
        ),
    ],
    system_prompt="You are Alice, an addition expert.",
    name="Alice",
)

bob = create_agent(
    "claude-sonnet-4-6",
    tools=[
        create_handoff_tool(
            agent_name="Alice",
            description="Transfer to Alice for math help",
        ),
    ],
    system_prompt="You are Bob, you speak like a pirate.",
    name="Bob",
)

# Build swarm
checkpointer = InMemorySaver()
workflow = (
    StateGraph(SwarmState)
    .add_node(alice, destinations=("Bob",))
    .add_node(bob, destinations=("Alice",))
)

# Add active agent router
workflow = add_active_agent_router(
    builder=workflow,
    route_to=["Alice", "Bob"],
    default_active_agent="Alice",
)

app = workflow.compile(checkpointer=checkpointer)

# Sử dụng
config = {"configurable": {"thread_id": "1"}}

# Turn 1: User muốn nói chuyện với Bob
turn_1 = app.invoke(
    {"messages": [{"role": "user", "content": "I'd like to speak to Bob"}]},
    config,
)

# Turn 2: Hỏi toán — nhưng đang ở Bob, Bob có thể handoff về Alice
turn_2 = app.invoke(
    {"messages": [{"role": "user", "content": "What's 5 + 7?"}]},
    config,
)
```

---

## Pattern 4: Supervisor-Worker

```
              [Supervisor Agent]
               /    |    \
              ▼     ▼     ▼
        [Worker A] [Worker B] [Worker C]
              \    |    /
               ▼   ▼   ▼
            [Final Result]
```

```python
from langgraph.graph import StateGraph
from langgraph.types import Command

def supervisor(state: SupervisorState) -> Command:
    """Supervisor quyết định worker nào xử lý tiếp theo."""
    if state["next"] == "FINISH":
        return Command(goto=END)
    return Command(goto=state["next"])

def worker_a(state: SupervisorState) -> dict:
    """Worker A thực hiện task."""
    result = agent_a.invoke(state)
    # Supervisor đánh giá và quyết định next step
    next_step = supervisor_llm.invoke(f"Next step based on: {result}")
    return {"results": [result], "next": next_step}

# Build graph
graph = StateGraph(SupervisorState)
graph.add_node("supervisor", supervisor)
graph.add_node("worker_a", worker_a)
graph.add_node("worker_b", worker_b)
graph.add_node("worker_c", worker_c)
graph.add_edge(START, "supervisor")
graph.add_conditional_edges("supervisor", lambda s: s["next"])
app = graph.compile()
```

---

## Pattern Comparison

| Pattern | Use Case | Pros | Cons |
|---------|----------|------|------|
| **Handoff** | Domain-specific agents | Simple, clear ownership | No parallel execution |
| **Router** | Multi-source queries | Parallel, scalable | Needs classifier LLM |
| **Swarm** | Dynamic team switching | Automatic routing, memory | Complex setup |
| **Supervisor-Worker** | Complex multi-step workflows | Centralized control | Bottleneck at supervisor |
| **Deep Agent Subagents** | Task isolation | Parallel, ephemeral, context isolation | No inter-agent communication |

---

## Chọn Pattern Phù Hợp

- **1 domain per request** → Handoff
- **Multiple knowledge sources, 1 query** → Router
- **Dynamic role switching, conversation** → Swarm
- **Complex multi-step orchestration** → Supervisor-Worker
- **Independent parallel tasks** → Deep Agent Subagents
- **Mixed**: Kết hợp nhiều pattern trong cùng một LangGraph

---

## Ví dụ: Handoff + Subagents Hybrid

```python
# Agent Sales có thể:
# 1. Handoff sang Support cho technical issues
# 2. Spawn researcher subagent cho product research

sales_agent = create_deep_agent(
    model="claude-sonnet-4-6",
    tools=[transfer_to_support],
    middleware=[
        SubAgentMiddleware(
            backend=backend,
            subagents=[{
                "name": "product-researcher",
                "description": "Research product details",
                "system_prompt": "Research product features and pricing...",
                "tools": [search_product_db],
                "model": "claude-sonnet-4-6",
            }],
        ),
    ],
    system_prompt="You are a sales agent. Handoff to support for technical issues.",
)
```
