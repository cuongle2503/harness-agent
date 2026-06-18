# Phase 6: Deployment Plan

> **Mục tiêu**: Deploy agent ở mode phù hợp: CLI, Server, Docker, hoặc multi-tenant. Đảm bảo production-ready.

## Prerequisites

- [ ] Phase 5: Security Hardening hoàn thành
- [ ] Security review passed
- [ ] Tất cả tests passing
- [ ] Đã đọc [AIDLC Lifecycle §6](../aidlc-lifecycle.md#6-deployment)
- [ ] Đã đọc [CLI/Server doc](../../deep-agents/09-deepagents-code.md)

---

## Step-by-Step Workflow

### Step 6.1: Deployment Mode Decision

**Mục tiêu**: Chọn deployment mode phù hợp.

**Decision Matrix** (từ [AIDLC Lifecycle §6.1](../aidlc-lifecycle.md#61-deployment-mode-decision)):

| Mode | Dùng khi | Pros | Cons |
|------|----------|------|------|
| **Library SDK** | Tích hợp vào app Python | Đơn giản, linh hoạt | Tự quản lý lifecycle |
| **CLI Tool** | Dev tool, local assistant | Nhanh, interactive | Không scalable |
| **HTTP Server** | Production service | Scalable, API-driven | Phức tạp hơn |
| **LangGraph Server** | Managed deployment | Managed, auto-scale | Vendor lock-in |

**Checklist**:
- [ ] Deployment mode selected with rationale
- [ ] Trade-offs documented
- [ ] Target environment identified

---

### Step 6.2: CLI Mode Setup (Development/Internal)

**Mục tiêu**: Deploy agent dưới dạng CLI tool.

**Cách thực hiện**:

```python
# cli_agent.py
from deepagents_code.agent import create_cli_agent
from langchain_deepseek import ChatDeepSeek
from deepagents_code._server_config import MCPServerInfo
import os

def main() -> None:
    model = ChatDeepSeek(
        model="deepseek-v4-flash",
        api_key=os.environ["DEEPSEEK_API_KEY"],
    )

    agent, backend = create_cli_agent(
        model=model,
        assistant_id="harness-agent-cli",
        sandbox_type="docker",
        system_prompt="You are a helpful coding assistant for the Harness Agent project.",
        enable_shell=True,
        enable_memory=True,
        enable_skills=True,
        shell_allow_list=[
            "ls", "cat", "grep", "find",
            "python", "pip", "uv", "git",
            "pytest", "ruff", "mypy",
        ],
        cwd="/home/dev/project",
        mcp_server_info=[
            MCPServerInfo(
                name="codegraph",
                command="codegraph",
                args=["serve", "--mcp", "--path", "."],
            ),
        ],
    )

    # Interactive loop
    import asyncio
    asyncio.run(interactive_loop(agent))

async def interactive_loop(agent) -> None:
    """Simple interactive CLI loop."""
    config = {"configurable": {"thread_id": "cli-session"}}
    print("Harness Agent CLI — type 'exit' to quit")
    while True:
        user_input = input("\n> ")
        if user_input.lower() == "exit":
            break
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": user_input}]},
            config=config,
        )
        print(result["messages"][-1].content)

if __name__ == "__main__":
    main()
```

**Checklist**:
- [ ] CLI agent script created
- [ ] Model configured with env var
- [ ] Sandbox configured (Docker)
- [ ] Shell allow list scoped
- [ ] MCP servers integrated
- [ ] Memory enabled
- [ ] Interactive loop working
- [ ] CLI tested locally

---

### Step 6.3: Server Mode Setup (Production)

**Mục tiêu**: Deploy agent dưới dạng HTTP server.

**Cách thực hiện**:

```python
# server_app.py
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from deepagents_code.server_manager import server_session
from deepagents_code.remote_client import RemoteAgent
from pydantic import BaseModel, Field
import logging

logger = logging.getLogger(__name__)
agent_pool: dict[str, RemoteAgent] = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: khởi tạo agent server."""
    async with server_session(
        assistant_id="harness-agent-prod",
        model_name="deepseek-v4-flash",
        sandbox_type="docker",
        host="127.0.0.1",
        port=2024,
        auto_approve=False,
        interrupt_shell_only=True,
        shell_allow_list=["ls", "cat", "grep", "find", "python", "pip", "git"],
        enable_memory=True,
    ) as (remote_agent, server):
        agent_pool["default"] = remote_agent
        logger.info("Agent server ready on port 2024")
        yield
    agent_pool.clear()
    logger.info("Agent server shut down")

app = FastAPI(lifespan=lifespan, title="Harness Agent Server")

class AgentRequest(BaseModel):
    messages: list[dict]
    thread_id: str | None = "default"

class AgentResponse(BaseModel):
    content: str
    thread_id: str
    tokens_used: int = 0

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    if "default" not in agent_pool:
        raise HTTPException(status_code=503, detail="Agent not ready")
    return {"status": "healthy"}

@app.post("/agent/invoke", response_model=AgentResponse)
async def invoke_agent(request: AgentRequest):
    """Invoke agent with messages."""
    agent = agent_pool.get("default")
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not ready")

    config = {"configurable": {"thread_id": request.thread_id}}
    result = await agent.ainvoke(
        {"messages": request.messages},
        config=config,
    )

    return AgentResponse(
        content=result["messages"][-1].content,
        thread_id=request.thread_id,
        tokens_used=result.get("token_usage", {}).get("total_tokens", 0),
    )
```

**Checklist**:
- [ ] FastAPI server created
- [ ] `server_session()` configured
- [ ] Health check endpoint
- [ ] Invoke endpoint with request/response models
- [ ] Graceful shutdown (lifespan)
- [ ] Error handling (503 when not ready)
- [ ] Thread ID support for multi-session

---

### Step 6.4: Docker Deployment

**Mục tiêu**: Containerize agent cho production deployment.

**Cách thực hiện**:

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY src/ src/
COPY agents/ agents/
COPY docs/ docs/

# Create non-root user
RUN useradd -m -s /bin/bash agent && chown -R agent:agent /app
USER agent

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:2024/health || exit 1

EXPOSE 2024

CMD ["python", "-m", "src.server"]
```

```yaml
# docker-compose.yml
version: "3.8"

services:
  agent-server:
    build: .
    ports:
      - "2024:2024"
    environment:
      - DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}
      - AGENT_ENV=production
      - LOG_LEVEL=INFO
    volumes:
      - agent-memory:/memories
      - agent-policies:/policies
      - /var/run/docker.sock:/var/run/docker.sock  # Docker sandbox
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:2024/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    deploy:
      resources:
        limits:
          cpus: "2"
          memory: "4G"
        reservations:
          cpus: "1"
          memory: "2G"

volumes:
  agent-memory:
  agent-policies:
```

**Tools hỗ trợ**:
- **MCP `context7`**: `resolve-library-id` → `query-docs` cho Docker/docker-compose best practices
- **Skill `verify`**: Verify deployment hoạt động

**Checklist**:
- [ ] `Dockerfile` created
- [ ] Non-root user (`agent`)
- [ ] Health check configured
- [ ] `.dockerignore` excludes `.env`, `.git`, `__pycache__`
- [ ] `docker-compose.yml` created
- [ ] Resource limits set (CPU, memory)
- [ ] Volumes cho persistent data
- [ ] Docker socket mounted (cho Docker sandbox)
- [ ] `docker compose build` thành công
- [ ] `docker compose up` — health check pass
- [ ] Agent xử lý requests trong container

---

### Step 6.5: Multi-Tenant Deployment (Optional)

**Mục tiêu**: Deploy agent hỗ trợ nhiều tenants (nếu cần).

```python
# multi_tenant_manager.py
from dataclasses import dataclass
from deepagents_code.server_manager import server_session
from deepagents_code.remote_client import RemoteAgent

@dataclass
class TenantAgent:
    agent: RemoteAgent
    port: int

class TenantAgentManager:
    """Quản lý agent instances cho nhiều tenants."""

    def __init__(self) -> None:
        self._agents: dict[str, TenantAgent] = {}

    async def get_agent(self, tenant_id: str) -> RemoteAgent:
        if tenant_id not in self._agents:
            port = 2024 + hash(tenant_id) % 100
            async with server_session(
                assistant_id=f"tenant-{tenant_id}",
                sandbox_type="docker",
                sandbox_id=f"sandbox-{tenant_id}",
                host="127.0.0.1",
                port=port,
                enable_memory=True,
            ) as (agent, server):
                self._agents[tenant_id] = TenantAgent(agent, port)
        return self._agents[tenant_id].agent

    async def cleanup_tenant(self, tenant_id: str) -> None:
        if tenant_id in self._agents:
            del self._agents[tenant_id]
```

**Checklist**:
- [ ] Tenant isolation strategy defined
- [ ] Separate sandbox per tenant
- [ ] Separate port per tenant
- [ ] Memory namespaced by tenant
- [ ] Cleanup mechanism implemented

---

### Step 6.6: Production Readiness Checklist

**Tổng hợp tất cả production requirements**:

#### Security
- [ ] Secrets from environment variables (không hardcoded)
- [ ] Docker sandbox enabled
- [ ] Shell allow list configured
- [ ] HITL enabled cho dangerous tools
- [ ] `auto_approve=False`
- [ ] Non-root user trong container
- [ ] File permissions scoped
- [ ] SSL/TLS cho external traffic

#### Reliability
- [ ] Health check endpoint responding
- [ ] Graceful shutdown (SIGTERM handled)
- [ ] Restart policy: `unless-stopped`
- [ ] Resource limits (CPU, memory)
- [ ] Error handling — không crash trên single failure

#### Observability
- [ ] Structured logging (JSON format)
- [ ] Log level configurable via env var
- [ ] Health check metrics exposed
- [ ] Token usage tracking

#### Performance
- [ ] Rate limiting configured
- [ ] Connection pooling (nếu multi-tenant)
- [ ] Response time monitoring

#### Documentation
- [ ] Deployment guide written
- [ ] Environment variables documented
- [ ] Health check endpoint documented
- [ ] Scaling recommendations

---

### Step 6.7: Deploy & Verify

**Mục tiêu**: Deploy và verify agent hoạt động.

```bash
# Build và run
docker compose up -d

# Verify health
curl http://localhost:2024/health

# Test invoke
curl -X POST http://localhost:2024/agent/invoke \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Hello, are you working?"}], "thread_id": "test-1"}'

# Check logs
docker compose logs -f
```

**Tools hỗ trợ**:
- **Skill `verify`**: Verify deployment hoạt động đúng
- **Skill `update-config`**: Cập nhật settings nếu cần thay đổi config

**Checklist**:
- [ ] `docker compose up -d` thành công
- [ ] Health check returns 200
- [ ] Invoke endpoint returns valid response
- [ ] Logs không có errors
- [ ] Memory persists across container restart
- [ ] Sandbox hoạt động
- [ ] `verify` skill confirms deployment working

---

## Phase 6 Completion Checklist

### Deployment Mode
- [ ] Mode selected and deployed (CLI / Server / Docker)

### Docker
- [ ] Dockerfile with non-root user
- [ ] Health check
- [ ] docker-compose.yml with resource limits
- [ ] Volumes for persistence
- [ ] Build & run successful

### Production Readiness
- [ ] Security: sandbox, HITL, no secrets, non-root
- [ ] Reliability: health check, graceful shutdown, restart policy
- [ ] Observability: structured logging, metrics
- [ ] Performance: rate limiting, resource limits

### Verification
- [ ] Health check pass
- [ ] Agent responds correctly
- [ ] Memory persists
- [ ] Sandbox functional
- [ ] `verify` skill confirms

---

## Next Phase

→ [Phase 7: Monitoring & Observability](07-monitoring.md)

## References

| Tài liệu | Section |
|----------|---------|
| [AIDLC Lifecycle](../aidlc-lifecycle.md) | §6 Deployment |
| [CLI/Server](../../deep-agents/09-deepagents-code.md) | Full deployment API |
| [API Reference](../../deep-agents/02-api-reference.md) | `create_deep_agent()` |
| [Backends](../../deep-agents/04-backends.md) | Persistent storage |
| [Memory](../../deep-agents/06-memory.md) | Cross-session memory |
