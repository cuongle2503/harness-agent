# 9. Deep Agents Code (CLI/Server)

`deepagents-code` là package mở rộng cho Deep Agents, cung cấp CLI agent, server mode, sandbox, và MCP integration.

## Tổng quan

```
deepagents-code
├── CLI Agent (create_cli_agent)
├── Server Session (server_session)
├── Remote Agent (RemoteAgent — client)
├── Sandbox Backends
└── MCP Integration
```

## create_cli_agent

Tạo agent chạy trong môi trường CLI với sandbox và MCP tools.

```python
from deepagents_code.agent import create_cli_agent

agent, backend = create_cli_agent(
    model: str | BaseChatModel,
    assistant_id: str,
    *,
    # Tools
    tools: Sequence[BaseTool | Callable | dict] | None = None,

    # Sandbox
    sandbox: SandboxBackendProtocol | None = None,
    sandbox_type: str | None = None,  # "docker", "none", etc.

    # Agent config
    system_prompt: str | None = None,
    interactive: bool = True,
    auto_approve: bool = False,
    interrupt_shell_only: bool = False,
    shell_allow_list: list[str] | None = None,

    # Features
    enable_ask_user: bool = True,
    enable_memory: bool = True,
    enable_skills: bool = True,
    enable_shell: bool = True,
    enable_interpreter: bool = False,

    # Persistence
    checkpointer: BaseCheckpointSaver | None = None,

    # MCP
    mcp_server_info: list[MCPServerInfo] | None = None,

    # Context
    cwd: str | Path | None = None,
    project_context: ProjectContext | None = None,

    # Async subagents
    async_subagents: list[AsyncSubAgent] | None = None,
) -> tuple[Pregel, CompositeBackend]
```

### Ví dụ: CLI Agent với Sandbox

```python
from deepagents_code.agent import create_cli_agent
from langchain_deepseek import ChatDeepSeek

model = ChatDeepSeek(model="deepseek-v4-flash")

agent, backend = create_cli_agent(
    model=model,
    assistant_id="my-assistant",
    sandbox_type="docker",
    system_prompt="You are a coding assistant.",
    enable_shell=True,
    enable_memory=True,
    enable_skills=True,
    mcp_server_info=[
        MCPServerInfo(
            name="filesystem",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem", "/workspace"],
        ),
    ],
)

# Chạy agent
result = agent.invoke(
    {"messages": [{"role": "user", "content": "Create a Python web server"}]},
)
```

---

## Server Session

Chạy Deep Agent như một server với HTTP API.

```python
from deepagents_code.server_manager import server_session

async with server_session(
    *,
    assistant_id: str,
    model_name: str | None = None,
    model_params: dict[str, Any] | None = None,

    # Security
    auto_approve: bool = False,
    interrupt_shell_only: bool = False,
    shell_allow_list: list[str] | None = None,

    # Sandbox
    sandbox_type: str = "none",  # "none", "docker"
    sandbox_id: str | None = None,
    sandbox_snapshot_name: str | None = None,
    sandbox_setup: str | None = None,

    # Features
    enable_shell: bool = True,
    enable_ask_user: bool = False,
    enable_interpreter: bool = False,
    interpreter_ptc: str | list[str] | None = None,
    interpreter_ptc_acknowledge_unsafe: bool = False,

    # MCP
    mcp_config_path: str | None = None,
    no_mcp: bool = False,
    trust_project_mcp: bool | None = None,

    # Network
    interactive: bool = True,
    host: str = "127.0.0.1",
    port: int = 2024,
) -> AsyncIterator[tuple[RemoteAgent, ServerProcess]]:
    ...

# Usage:
# async with server_session(assistant_id="...") as (remote_agent, server):
#     async for msg in remote_agent.astream():
#         ...
```

---

## RemoteAgent

Client để tương tác với Deep Agent server từ xa.

```python
from deepagents_code.remote_client import RemoteAgent

# RemoteAgent.astream
async for message in remote_agent.astream(
    input: dict | Any,
    *,
    stream_mode: list[str] | None = None,
    subgraphs: bool = False,
    config: dict[str, Any] | None = None,
    context: Any | None = None,
    durability: str | None = None,
) -> AsyncIterator[tuple[tuple[str, ...], str, Any]]:
    """Stream agent execution."""
    ...
```

---

## ServerConfig

Cấu hình server từ CLI args.

```python
from deepagents_code._server_config import ServerConfig

config = ServerConfig.from_cli_args(
    project_context: ProjectContext | None,
    model_name: str | None,
    model_params: dict[str, Any] | None,
    assistant_id: str,

    # Security
    auto_approve: bool,
    interrupt_shell_only: bool = False,
    shell_allow_list: list[str] | None = None,

    # Sandbox
    sandbox_type: str = "none",
    sandbox_id: str | None = None,
    sandbox_snapshot_name: str | None = None,
    sandbox_setup: str | None = None,

    # Features
    enable_shell: bool,
    enable_ask_user: bool,
    enable_interpreter: bool = False,
    interpreter_ptc: str | list[str] | None = None,
    interpreter_ptc_acknowledge_unsafe: bool = False,

    # MCP
    mcp_config_path: str | None = None,
    no_mcp: bool = False,
    trust_project_mcp: bool | None = None,

    interactive: bool,
)
```

---

## Sandbox Configuration

### Sandbox Types

| Type | Mô tả |
|------|-------|
| `"none"` | Không sandbox (chỉ dùng cho dev trusted) |
| `"docker"` | Docker container sandbox |
| Custom | `SandboxBackendProtocol` implementation |

### Docker Sandbox

```python
# Docker sandbox
create_cli_agent(
    model=model,
    sandbox_type="docker",
    sandbox_id="my-container-id",
    sandbox_snapshot_name="clean-snapshot",
    sandbox_setup="pip install requests && apt-get update",
)
```

### Custom Sandbox Protocol

```python
class SandboxBackendProtocol(BackendProtocol):
    """Giao diện cho sandbox backends có execution capability."""

    async def execute(self, command: str) -> str:
        """Execute command trong sandbox."""
        ...

    async def start_process(self, command: str) -> ProcessHandle:
        """Start long-running process."""
        ...

    async def stop_process(self, handle: ProcessHandle) -> None:
        """Stop process."""
        ...
```

---

## MCP Integration

Deep Agents Code hỗ trợ MCP (Model Context Protocol) servers:

```python
# CLI agent với MCP
agent, backend = create_cli_agent(
    model=model,
    assistant_id="my-assistant",
    mcp_server_info=[
        MCPServerInfo(
            name="filesystem",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem", "/workspace"],
        ),
        MCPServerInfo(
            name="github",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-github"],
            env={"GITHUB_TOKEN": "..."},
        ),
    ],
    trust_project_mcp=True,  # Trust MCP config từ project
)

# Server session với MCP
async with server_session(
    assistant_id="...",
    mcp_config_path=".mcp/config.json",
    trust_project_mcp=True,
) as (agent, server):
    ...
```

---

## Security Configuration

### Shell Allow List

```python
create_cli_agent(
    model=model,
    enable_shell=True,
    shell_allow_list=[
        "ls", "cat", "grep", "find",
        "python", "pip", "npm",
    ],
    interrupt_shell_only=True,  # Chỉ interrupt shell commands
)
```

### Auto Approve vs Interactive

```python
# Production: auto_approve=False (an toàn)
create_cli_agent(model=model, auto_approve=False)

# Development: auto_approve=True (nhanh)
create_cli_agent(model=model, auto_approve=True, sandbox_type="docker")
```

### Interpreter Security

```python
create_cli_agent(
    model=model,
    enable_interpreter=True,
    interpreter_ptc=["path_traversal_check", "dangerous_imports"],
    interpreter_ptc_acknowledge_unsafe=False,  # Từ chối code unsafe
)
```

---

## Deployment Patterns

### Pattern 1: Local CLI Development

```python
agent, backend = create_cli_agent(
    model="deepseek-v4-flash",
    assistant_id="dev-assistant",
    sandbox_type="docker",
    auto_approve=True,
    enable_shell=True,
    enable_memory=True,
    cwd="/home/dev/project",
)
```

### Pattern 2: Server with HTTP API

```python
async with server_session(
    assistant_id="prod-assistant",
    model_name="deepseek-v4-flash",
    sandbox_type="docker",
    host="0.0.0.0",
    port=2024,
    auto_approve=False,
    interrupt_shell_only=True,
    enable_memory=True,
) as (agent, server):
    # Server chạy trên port 2024
    # Client kết nối qua RemoteAgent
    ...
```

### Pattern 3: Multi-Tenant Server

```python
async def handle_user(user_id: str, query: str):
    async with server_session(
        assistant_id=f"user-{user_id}",
        sandbox_type="docker",
        sandbox_id=f"sandbox-{user_id}",  # Mỗi user một sandbox
        host="127.0.0.1",
        port=2024 + hash(user_id) % 100,   # Port riêng
    ) as (agent, server):
        result = await agent.ainvoke({
            "messages": [{"role": "user", "content": query}]
        })
        return result["messages"][-1].content
```

---

## So sánh: create_deep_agent vs create_cli_agent

| Tính năng | `create_deep_agent` | `create_cli_agent` |
|-----------|---------------------|-------------------|
| Sandbox | Manual config | Built-in (`sandbox_type`) |
| MCP | Manual integration | Built-in (`mcp_server_info`) |
| Shell | Qua middleware | Built-in (`enable_shell`) |
| Interpreter | Qua middleware | Built-in (`enable_interpreter`) |
| Skills | Manual | Built-in (`enable_skills`) |
| Ask User | Qua HITL middleware | Built-in (`enable_ask_user`) |
| Server mode | Manual LangGraph Server | `server_session()` |
| Use case | Library/SDK | CLI/Server Application |
