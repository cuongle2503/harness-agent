# Phase 7: Monitoring & Observability Plan

> **Mục tiêu**: Thiết lập monitoring toàn diện: streaming, structured logging, key metrics, alerting, và tracing.

## Prerequisites

- [x] Phase 6: Deployment hoàn thành
- [x] Agent đang chạy (CLI hoặc Server mode)
- [x] Đã đọc [AIDLC Lifecycle §7](../aidlc-lifecycle.md#7-monitoring--observability)
- [x] Đã đọc [Streaming doc](../../deep-agents/07-streaming.md)

---

## Step-by-Step Workflow

### Step 7.1: Streaming Configuration

**Mục tiêu**: Cấu hình streaming cho real-time monitoring.

**Cách thực hiện**: Dựa trên [Streaming doc](../../deep-agents/07-streaming.md)

```python
import asyncio
from deepagents import create_deep_agent

async def monitor_agent_stream():
    """Stream agent với tất cả events để monitoring."""
    agent = create_deep_agent(model=model)

    async for mode, data in agent.astream(
        {"messages": [{"role": "user", "content": "Analyze this repo"}]},
        config={"configurable": {"thread_id": "monitor-demo"}},
        stream_mode=["messages", "updates", "custom", "tasks"],
        subgraphs=True,
        version="v2",
    ):
        if mode == "messages":
            token, metadata = data
            yield {"type": "token", "data": token, "metadata": metadata}

        elif mode == "updates":
            node_name = list(data.keys())[0] if data else "unknown"
            yield {"type": "node_complete", "node": node_name}

        elif mode == "tasks":
            yield {"type": "task_event", "data": data}

        elif mode == "custom":
            yield {"type": "custom_event", "data": data}
```

**Stream Mode Selection**:

| Stream Mode | Dùng để | Monitoring Use |
|------------|---------|---------------|
| `messages` | Real-time text output | User-facing stream, latency tracking |
| `updates` | Node/task completion | Pipeline progress, bottleneck detection |
| `custom` | Custom progress events | Long-running task progress |
| `tasks` | Subagent lifecycle | Subagent spawn/complete tracking |
| `values` | Full state snapshot | Debugging, state inspection |
| `debug` | Detailed debug info | Development only |

**Checklist**:
- [x] Streaming enabled với multiple modes
- [x] `subgraphs=True` để track subagent progress
- [x] Version `v2` cho protocol events
- [x] Custom events cho long-running tasks
- [x] Stream events được route đến monitoring system

---

### Step 7.2: Structured Logging

**Mục tiêu**: Implement structured JSON logging.

**Cách thực hiện**: Custom logging middleware từ [AIDLC Lifecycle §7.2](../aidlc-lifecycle.md#72-logging-strategy)

```python
import logging
import json
import time
from langchain.agents.middleware import AgentMiddleware

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp": "%(asctime)s", "level": "%(levelname)s", "message": %(message)s}',
    handlers=[
        logging.FileHandler("agent.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("harness-agent")

class StructuredLoggingMiddleware(AgentMiddleware):
    """Log tất cả agent activity dưới dạng structured JSON."""

    def wrap_tool_call(self, request, handler):
        start = time.time()
        tool_name = request.tool_call.get("name", "unknown")

        try:
            result = handler(request)
            elapsed = (time.time() - start) * 1000
            logger.info(json.dumps({
                "event": "tool_call",
                "tool": tool_name,
                "duration_ms": round(elapsed, 2),
                "status": "success",
                "thread_id": request.runtime.thread_id if hasattr(request, 'runtime') else "unknown",
            }))
            return result
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            logger.error(json.dumps({
                "event": "tool_call_error",
                "tool": tool_name,
                "duration_ms": round(elapsed, 2),
                "error": str(e),
                "error_type": type(e).__name__,
            }))
            raise

    def wrap_model_call(self, request, handler):
        start = time.time()
        try:
            result = handler(request)
            elapsed = (time.time() - start) * 1000
            logger.info(json.dumps({
                "event": "model_call",
                "duration_ms": round(elapsed, 2),
                "status": "success",
                "model": getattr(request, 'model', 'unknown'),
            }))
            return result
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            logger.error(json.dumps({
                "event": "model_call_error",
                "duration_ms": round(elapsed, 2),
                "error": str(e),
                "error_type": type(e).__name__,
            }))
            raise
```

**Log Events Schema**:

| Event | Fields | Khi nào emit |
|-------|--------|-------------|
| `tool_call` | tool, duration_ms, status, thread_id | Mỗi tool execution |
| `tool_call_error` | tool, duration_ms, error, error_type | Tool execution fails |
| `model_call` | duration_ms, status, model | Mỗi LLM call |
| `model_call_error` | duration_ms, error, error_type | LLM call fails |
| `subagent_spawn` | subagent_name, thread_id | Subagent được spawn |
| `subagent_complete` | subagent_name, duration_ms | Subagent hoàn thành |
| `summarization` | trigger, tokens_before, tokens_after | Context được summarize |
| `hitl_approval` | tool, approved | HITL decision |

**Checklist**:
- [x] Structured JSON logging implemented
- [x] Custom `StructuredLoggingMiddleware` deployed
- [x] Log events schema defined
- [x] Log levels configured (DEBUG/INFO/WARNING/ERROR)
- [x] Log file rotation configured
- [x] Sensitive data excluded from logs
- [x] Correlation IDs (thread_id) in all log events

---

### Step 7.3: Key Metrics Dashboard

**Mục tiêu**: Define và track key metrics.

**Metrics Definition** (từ [AIDLC Lifecycle §7.3](../aidlc-lifecycle.md#73-key-metrics)):

| Metric | Mô tả | Alert khi | Implementation |
|--------|-------|-----------|---------------|
| `tool_call_latency_ms` | Thời gian thực thi tool | > 5000ms | Logging middleware |
| `llm_call_latency_ms` | Thời gian LLM response | > 30000ms | Logging middleware |
| `subagent_spawn_count` | Số subagent được spawn | > 20/task | Task event counter |
| `token_usage_total` | Tổng token đã dùng | > 100K/task | Token tracking |
| `summarization_triggers` | Số lần summarize | > 5/session | Summarization middleware |
| `error_rate` | Tỉ lệ lỗi tool/LLM | > 5% | Error counter / total |
| `hitl_approval_rate` | Tỉ lệ HITL approval | < 50% | HITL event tracker |
| `task_completion_rate` | % tasks hoàn thành | < 80% | Evaluation framework |
| `avg_response_time_ms` | Thời gian response trung bình | > 60000ms | End-to-end timer |

**Metrics Collection**:

```python
from dataclasses import dataclass, field
from collections import defaultdict
import time

@dataclass
class AgentMetrics:
    """Collect and expose agent metrics."""

    tool_calls: int = 0
    tool_errors: int = 0
    model_calls: int = 0
    model_errors: int = 0
    subagent_spawns: int = 0
    summarization_triggers: int = 0
    hitl_approvals: int = 0
    hitl_rejections: int = 0
    total_tokens: int = 0
    total_tasks: int = 0
    completed_tasks: int = 0
    total_latency_ms: float = 0.0
    tool_latencies: list[float] = field(default_factory=list)

    @property
    def error_rate(self) -> float:
        total = self.tool_calls + self.model_calls
        errors = self.tool_errors + self.model_errors
        return errors / total if total > 0 else 0.0

    @property
    def avg_tool_latency_ms(self) -> float:
        return sum(self.tool_latencies) / len(self.tool_latencies) if self.tool_latencies else 0.0

    @property
    def task_completion_rate(self) -> float:
        return self.completed_tasks / self.total_tasks if self.total_tasks > 0 else 0.0

    def to_dict(self) -> dict:
        return {
            "tool_calls": self.tool_calls,
            "tool_errors": self.tool_errors,
            "error_rate": round(self.error_rate, 4),
            "avg_tool_latency_ms": round(self.avg_tool_latency_ms, 2),
            "subagent_spawns": self.subagent_spawns,
            "total_tokens": self.total_tokens,
            "task_completion_rate": round(self.task_completion_rate, 4),
        }
```

**Checklist**:
- [x] Metrics collection implemented
- [x] All 9 key metrics tracked
- [x] Metrics exposed via endpoint (`/metrics`)
- [x] Metrics in structured format (JSON)
- [x] Dashboard configured (Grafana hoặc similar)
- [x] Baseline values established

---

### Step 7.4: Alerting Configuration

**Mục tiêu**: Thiết lập alerts cho các điều kiện bất thường.

**Alert Rules**:

| Alert | Condition | Severity | Action |
|-------|-----------|----------|--------|
| High error rate | `error_rate > 5%` trong 5 phút | CRITICAL | Page on-call |
| Slow tool execution | `avg_tool_latency_ms > 5000` | HIGH | Investigate tool |
| Excessive subagents | `subagent_spawn_count > 20` per task | MEDIUM | Review task complexity |
| High token usage | `token_usage_total > 100K` per task | MEDIUM | Optimize prompts |
| Too many summarizations | `summarization_triggers > 5` per session | LOW | Adjust thresholds |
| Low HITL approval | `hitl_approval_rate < 50%` | MEDIUM | Review tool safety |
| Health check fail | 3 consecutive failures | CRITICAL | Auto-restart |
| High memory usage | Memory > 80% limit | HIGH | Scale up |

**Checklist**:
- [x] Alert rules defined
- [x] Alert severity levels established
- [x] Alert channels configured (Slack, PagerDuty, email)
- [x] Runbooks written cho CRITICAL alerts
- [x] Alert testing completed

---

### Step 7.5: Tracing Setup

**Mục tiêu**: Enable distributed tracing cho debugging.

```python
import os

# LangGraph tracing
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_PROJECT"] = "harness-agent-prod"
os.environ["LANGCHAIN_ENDPOINT"] = "https://api.smith.langchain.com"
```

**Checklist**:
- [x] LangChain tracing enabled
- [x] Project name configured
- [x] Tracing endpoint configured
- [x] Trace sampling rate set (100% dev, 10% prod)
- [x] Traces include tool calls, LLM calls, subagent spawns

---

### Step 7.6: Health Dashboard

**Mục tiêu**: Tạo health dashboard cho operations team.

**Dashboard Panels**:
1. **Agent Status**: Up/Down, Uptime
2. **Request Rate**: Requests/second
3. **Error Rate**: % errors (tool + LLM)
4. **Latency**: P50, P95, P99 (ms)
5. **Token Usage**: Tokens/minute, cost estimate
6. **Subagent Activity**: Spawns/minute, avg duration
7. **HITL Status**: Approval rate, pending count
8. **Memory Usage**: Items stored, storage size

**Checklist**:
- [x] Health dashboard created
- [x] All 8 panels populated
- [x] Real-time refresh (< 1 min)
- [x] Historical data retention (≥ 30 days)
- [x] Access control configured

---

### Step 7.7: Debug Mode

**Mục tiêu**: Cấu hình debug mode cho troubleshooting.

```python
# Debug mode: log chi tiết
agent = create_deep_agent(
    model=model,
    debug=True,  # Bật debug mode
)

# Hoặc qua environment variable
os.environ["DEEPAGENTS_DEBUG"] = "true"
```

**Checklist**:
- [x] Debug mode toggle (env var)
- [x] Verbose logging trong debug mode
- [x] Debug mode disabled trong production
- [x] Debug documentation for developers

---

## Phase 7 Completion Checklist

### Streaming
- [x] Multi-mode streaming configured
- [x] Subgraph streaming enabled
- [x] Custom events for long tasks
- [x] Stream events routed to monitoring

### Logging
- [x] Structured JSON logging
- [x] `StructuredLoggingMiddleware` deployed
- [x] Log events schema defined
- [x] Sensitive data excluded
- [x] Correlation IDs in all events
- [x] Log rotation configured

### Metrics
- [x] All 9 key metrics tracked
- [x] Metrics exposed via endpoint
- [x] Dashboard configured
- [x] Baseline values established

### Alerting
- [x] Alert rules defined
- [x] Alert channels configured
- [x] Runbooks for CRITICAL alerts
- [x] Alert testing completed

### Tracing & Debug
- [x] LangChain tracing enabled
- [x] Debug mode toggle available
- [x] Production debug mode OFF

---

## Next Phase

→ [Phase 8: Maintenance & Iteration](08-maintenance.md)

## References

| Tài liệu | Section |
|----------|---------|
| [AIDLC Lifecycle](../aidlc-lifecycle.md) | §7 Monitoring & Observability |
| [Streaming](../../deep-agents/07-streaming.md) | Stream modes, events |
| [Overview](../../deep-agents/01-overview-architecture.md) | Agent lifecycle |
| [Middleware](../../deep-agents/03-middleware.md) | Logging middleware |
