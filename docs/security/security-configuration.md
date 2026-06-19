# Security Configuration

> Phase 5 — Security Hardening (completed 2026-06-18)

## Secrets

| Secret | Source | Rotation |
|--------|--------|----------|
| `DEEPSEEK_API_KEY` | Environment variable | Every 90 days |
| `TAVILY_API_KEY` | Environment variable | Every 90 days |

### Validation

Secrets are validated at startup by `AgentModelSelection.validate_secrets()` in `src/harness_agent/config.py`. Missing required secrets raise `RuntimeError` with a clear message.

```python
from harness_agent.config import AgentModelSelection

selection = AgentModelSelection()
selection.validate_secrets()  # Raises RuntimeError if secrets missing
```

### Rules
- NEVER hardcode secrets in source files
- `.env` files must be in `.gitignore` ✅ (verified)
- Test fixtures use fake keys (`sk-test`, `sk-test-dummy`) ✅
- Use `os.environ` or a secret manager for all secrets ✅

---

## Sandbox

| Setting | Development | CI/Testing | Production |
|---------|------------|------------|------------|
| **Type** | Docker | Docker | Docker |
| **Auto-approve** | True | False | False |
| **Interrupt shell** | False | False | True |
| **Timeout** | 60s | 120s | 30s |

### Shell Allow List
```
ls, cat, grep, find, echo, head, tail, wc, sort, uniq, cut,
mkdir, cp, mv, chmod, python, pytest, ruff, mypy, git, gh
```

**Excluded commands**: `rm`, `curl`, `wget`, `docker`, `npm`, `pip`, `uv` (require explicit opt-in)

### Configuration

```python
from harness_agent.security.sandbox import SandboxConfig

# Production
config = SandboxConfig.production()

# Development
config = SandboxConfig.development()

# CI
config = SandboxConfig.ci()

# Demo/POC (no Docker)
config = SandboxConfig.demo()
```

---

## Human-in-the-Loop (HITL)

### Tools Requiring Approval

| Tool | Dev | Production |
|------|-----|------------|
| `read_file` | No | No |
| `glob` | No | No |
| `grep` | No | No |
| `web_search` | No | No |
| `write_file` | **Yes** | **Yes** |
| `edit_file` | **Yes** | **Yes** |
| `execute_command` | **Yes** | **Yes** |
| `execute_python` | **Yes** | **Yes** |
| `task` (subagent) | **Yes** | **Yes** |
| `fetch_url` | No | **Yes** |

### Approval Flow

1. Tool call is intercepted by `HumanInTheLoopMiddleware`
2. `approval_callback(tool_name, request)` is invoked
3. If callback returns `True` → tool proceeds
4. If callback returns `False` or no callback configured → `HITLApprovalDeniedError` (fail-safe)

```python
from harness_agent.security.hitl import HumanInTheLoopMiddleware

def cli_approval(tool_name: str, request: object) -> bool:
    """Example: CLI-based approval."""
    answer = input(f"Approve tool '{tool_name}'? [y/N]: ")
    return answer.lower() == "y"

hitl = HumanInTheLoopMiddleware(
    production_mode=True,
    approval_callback=cli_approval,
)
```

---

## PII Protection

### Detection Patterns

| Pattern | Example |
|---------|---------|
| Email | `user@example.com` |
| Credit Card | `4111-1111-1111-1111` |
| SSN | `123-45-6789` |
| Phone | `555-123-4567` |
| API Key | `sk-abcdef...` |
| IP Address | `192.168.1.1` |
| AWS Key | `AKIA...` |
| GitHub Token | `ghp_...` |

### Usage

```python
from harness_agent.security.pii import PIIMiddleware

pii = PIIMiddleware(redact=True)
clean_text = pii.scan(user_input, source="tool_input")
if pii.has_pii():
    print("PII detected:", pii.get_detected())
    pii.clear()
```

---

## Permission Boundaries

### Production Permissions

| Path | Read | Write |
|------|------|-------|
| `/workspace/**` | ✅ | ✅ |
| `/workspace/.git/**` | ❌ | ❌ |
| `/workspace/.env*` | ❌ | ❌ |
| `/memories/**` | ✅ | ✅ |
| `/data/**` | ✅ | ❌ |
| `/etc/**` | ❌ | ❌ |
| `/proc/**` | ❌ | ❌ |
| `/sys/**` | ❌ | ❌ |
| Everything else | ❌ | ❌ |

### Usage

```python
from harness_agent.security.permissions import PermissionBoundary

boundary = PermissionBoundary.production()

if boundary.is_allowed("/workspace/src/app.py", "read"):
    # allowed
    ...

if not boundary.is_path_safe("/etc/passwd"):
    raise ValueError("Path outside workspace")
```

---

## Subprocess Safety

ALL subprocess calls must use `safe_run()` — direct `subprocess.run()` is prohibited.

```python
from harness_agent.security.subprocess_safety import safe_run

# ✅ Correct: list args, shell=False, timeout set
result = safe_run(["ls", "-la"], timeout=30)

# ❌ Wrong: shell=True
# subprocess.run(f"ls {user_input}", shell=True)

# ❌ Wrong: no timeout
# subprocess.run(["ls"])
```

---

## Tool Input Validation

All tools have Pydantic input schemas with:

- **Path traversal prevention**: `_resolve_safe_path()` in `file_tools.py`
- **SSRF protection**: DNS resolution + IP validation in `FetchUrlInput`
- **Shell allow list**: `ShellInput` in `file_tools.py`
- **Code safety**: Early-rejection blocklist in `ExecutePythonInput`
- **Query sanitization**: HTML/script tag stripping in `WebSearchInput` and `SearchInput`

---

## Security Review Summary

| Severity | Issues Found | Issues Fixed |
|----------|-------------|--------------|
| **HIGH** | 2 | 2 |
| **MEDIUM** | 5 | 5 |
| **LOW** | 3 | 3 |

### Key Fixes Applied
1. ✅ SSRF: DNS rebinding protection with socket.getaddrinfo()
2. ✅ HITL: Real blocking — raises HITLApprovalDeniedError when denied
3. ✅ Allow-list: Removed rm/curl/wget/docker/npm/pip/uv
4. ✅ Error messages: Opaque for external consumers, details in DEBUG logs
5. ✅ Regex sandbox: Documented as best-effort early rejection only
6. ✅ Shell metacharacter: Removed false-sense-of-security validator
7. ✅ JSON output: json.dumps() instead of f-strings
8. ✅ Workspace: Configurable via HARNESS_WORKSPACE_ROOT env var
9. ✅ Logging: logging module instead of print()

---

## Incident Response

### If a security issue is found:
1. **STOP** immediately
2. Run `security-reviewer` agent: `Agent(security-reviewer)`
3. Fix CRITICAL issues before continuing
4. Rotate any exposed secrets
5. Review entire codebase for similar issues

### Security Contacts
- Project maintainer: cuongle2503
- Review tool: `/security-scan` or `security-reviewer` agent

---

## References

| Document | Section |
|----------|---------|
| AIDLC Lifecycle | §5 Security Hardening |
| Python Security Rules | `.claude/rules/python/security.md` |
| Common Security Rules | `.claude/rules/common/security.md` |
| Middleware Reference | `docs/deep-agents/03-middleware.md` |
