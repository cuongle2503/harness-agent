# Harness Agent

Deep agent framework — Python + LangChain cho multi-agent orchestration, tool use, và memory management.

## Yêu cầu hệ thống

- **Python** 3.11+
- **uv** (package manager) — [cài đặt](https://docs.astral.sh/uv/getting-started/installation/)
- **Docker** (tùy chọn — cho sandbox mode)
- **DeepSeek API key** — đã config sẵn trong Claude Code global settings

## Cài đặt

```bash
# 1. Clone repo
git clone <repo-url> harness-agent
cd harness-agent

# 2. Tạo virtual environment + cài dependencies
uv sync

# 3. Kích hoạt venv
source .venv/bin/activate

# 4. Tạo file .env với API key
cat > .env << 'EOF'
DEEPSEEK_API_KEY=sk-your-key-here
EOF
```

## Chạy

### CLI mode (interactive)

```bash
# Chạy trực tiếp
uv run harness

# Hoặc sau khi activate venv
harness
```

Giao diện dòng lệnh tương tác với:
- Streaming text real-time
- Tool call display dạng box có spinner
- Memory persistence giữa các phiên
- Slash commands: `/help`, `/clear`, `/context`, `/memory`, `/exit`

```
🔥  harness-agent-cli
deepseek-v4-pro  ·  5 tools  ·  0 msgs  ·  0 mem
──────────────────────────────────────────────────

🔥  Xin chào!
Agent: Chào bạn! Tôi có thể giúp gì?

  ╭ ✦ bash ───────────────────────────────────────────────
  │  command: ls -la                                      │
  │  description: List files                              │
  ├────────────────────────────────────────────────────────┤
  │  ✓ done (45ms)                                        │
  │  total 42                                             │
  │  -rw-r--r--  1 user user  220 Jun 19 09:00 file.txt   │
  ╰────────────────────────────────────────────────────────╯
```

### Server mode (HTTP API)

```bash
# Chạy server
uv run harness-server

# Hoặc
harness-server
```

Server chạy tại `http://127.0.0.1:2024` với các endpoint:

| Endpoint | Method | Mô tả |
|----------|--------|-------|
| `/health` | GET | Health check |
| `/agent/invoke` | POST | Gọi agent |
| `/metrics` | GET | Metrics JSON |
| `/dashboard` | GET | Health dashboard |

```bash
# Test health check
curl http://127.0.0.1:2024/health

# Gọi agent
curl -X POST http://127.0.0.1:2024/agent/invoke \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Hello!"}], "thread_id": "test-1"}'
```

### Custom config

```python
from harness_agent.deployment.cli import CLIAgentConfig, CLIAgent
import asyncio

config = CLIAgentConfig(
    assistant_id="my-agent",
    max_tool_iterations=200,   # tăng loop limit
    sandbox_type="docker",     # docker | none
    enable_memory=True,
)
agent = CLIAgent(config)
asyncio.run(agent.run_interactive())
```

## Cấu trúc project

```
harness-agent/
├── src/harness_agent/
│   ├── core/           # Agent base, exceptions, orchestrator
│   ├── tools/          # Tool definitions (file, shell, search, code)
│   ├── memory/         # Hybrid memory (vector + KV + conversation)
│   ├── middleware/      # Custom LangChain middleware
│   ├── security/       # Sandbox, HITL, PII, permissions
│   ├── monitoring/     # Streaming, logging, metrics, alerting
│   ├── evaluation/     # A/B testing, evaluators
│   ├── deployment/     # CLI, Server, multi-tenant
│   ├── prompts/        # System prompt templates (.md)
│   └── config.py       # Model selection config
├── tests/              # Unit, integration, E2E tests
├── docs/               # Deep agent docs, guides, plans
└── pyproject.toml      # Project metadata & tool config
```

## Development

```bash
# Run tests
pytest tests/ -v -q

# Run single test file
pytest tests/unit/test_agent.py -v

# Lint
ruff check src/

# Type check
mypy src/

# Format
ruff format src/
```

### Quality gates (CI)

Tất cả phải pass trước khi commit:

- [ ] `pytest tests/` — toàn bộ test pass
- [ ] `ruff check src/` — không lỗi lint
- [ ] `mypy src/` — type checking sạch
- [ ] Coverage ≥ 80%

## Biến môi trường

| Variable | Mô tả | Required |
|----------|-------|----------|
| `DEEPSEEK_API_KEY` | DeepSeek API key | Yes |
| `HARNESS_HOST` | Server bind address (default: `127.0.0.1`) | No |
| `HARNESS_PORT` | Server port (default: `2024`) | No |
| `DEEPAGENTS_DEBUG` | Enable debug logging (`1`/`true`) | No |

## Docs

| Tài liệu | Mô tả |
|----------|-------|
| `docs/deep-agents/` | Framework reference (9 docs) |
| `docs/guides/aidlc-lifecycle.md` | AIDLC lifecycle: từ ý tưởng → production |
| `docs/guides/plans/` | Kế hoạch implementation từng phase (0→8) |
