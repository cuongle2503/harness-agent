# Phase 5: Security Hardening Plan

> **Mục tiêu**: Hardening security: secrets management, input validation, sandbox, HITL, PII detection. Pass security review.

## Prerequisites

- [x] Phase 4: Testing hoàn thành
- [x] Tất cả tests passing
- [x] Code đã được implement
- [x] Đã đọc [AIDLC Lifecycle §5](../aidlc-lifecycle.md#5-security-hardening)
- [x] Đã đọc [Python Security Rules](../../../.claude/rules/python/security.md)

---

## CRITICAL: Security Response Protocol

Nếu phát hiện security issue:
1. **STOP** ngay lập tức
2. Gọi `/security-scan` hoặc **Agent `security-reviewer`**
3. Fix CRITICAL issues trước khi tiếp tục
4. Rotate bất kỳ secrets nào có thể đã bị exposed
5. Review toàn bộ codebase cho similar issues

---

## Step-by-Step Workflow

### Step 5.1: Secrets Management Audit

**Mục tiêu**: Đảm bảo không có hardcoded secrets.

**Cách thực hiện**:

```bash
# Manual checks (từ AIDLC §5.2)
grep -r "sk-" src/ tests/          # Không được có Anthropic API keys
grep -r "api_key" src/ tests/      # Check hardcoded keys
grep -r "password" src/ tests/     # Không được có passwords
grep -r "token" src/ tests/        # Check hardcoded tokens
grep -r "secret" src/ tests/       # Check hardcoded secrets
grep -r "BEGIN.*PRIVATE KEY" src/  # Không được có private keys
```

**Implementation**:

```python
# ✅ GOOD: Secrets từ environment
import os
DEEPSEEK_API_KEY = os.environ["DEEPSEEK_API_KEY"]
DATABASE_URL = os.environ.get("DATABASE_URL")

# ✅ GOOD: Validate secrets at startup
def validate_secrets() -> None:
    required = ["DEEPSEEK_API_KEY"]
    missing = [k for k in required if k not in os.environ]
    if missing:
        raise RuntimeError(f"Missing required secrets: {missing}")

# ❌ BAD: NEVER hardcode
# API_KEY = "sk-ant-abc123..."
# DB_PASSWORD = "admin123"
```

**Tools hỗ trợ**:
- **Agent `security-reviewer`**: CHỦ LỰC — comprehensive security audit
- **Skill `security-scan`**: `/security-scan` command
- **Rule**: `.claude/rules/python/security.md` — Mandatory checks
- **Rule**: `.claude/rules/common/security.md` — General security
- **Hook `PreToolUse`**: Bash safety warning

**Checklist**:
- [x] `grep -r "sk-" src/ tests/` → NO RESULTS
- [x] `grep -r "api_key" src/ tests/` → Only `os.environ[...]` patterns
- [x] `grep -r "password" src/ tests/` → Only in test fixtures (fake)
- [x] `grep -r "BEGIN.*PRIVATE KEY" src/` → NO RESULTS
- [x] All secrets use `os.environ` or secret manager
- [x] `.env` files in `.gitignore`
- [x] Secrets validated at startup
- [x] No secrets in git history (check with `git log -p`)

---

### Step 5.2: Tool Input Validation

**Mục tiêu**: Validate tất cả tool inputs với Pydantic.

**Cách thực hiện**:

```python
from pydantic import BaseModel, Field, field_validator
from pathlib import Path

# File write — path traversal prevention
class FileWriteInput(BaseModel):
    file_path: str = Field(..., max_length=1024)
    content: str = Field(..., max_length=100_000)

    @field_validator("file_path")
    @classmethod
    def no_path_traversal(cls, v: str) -> str:
        resolved = Path(v).resolve()
        # Prevent traversal outside workspace
        workspace = Path("/workspace").resolve()
        if not str(resolved).startswith(str(workspace)):
            raise ValueError(f"Path traversal detected: {v}")
        return str(resolved)

# Shell command — allow list validation
class ShellInput(BaseModel):
    command: str = Field(..., max_length=2000)

    @field_validator("command")
    @classmethod
    def validate_command(cls, v: str) -> str:
        allowed = {"ls", "cat", "grep", "find", "python", "pip", "git"}
        base_cmd = v.split()[0] if v else ""
        if base_cmd not in allowed:
            raise ValueError(f"Command not allowed: {base_cmd}")
        return v

# Search query — sanitization
class SearchInput(BaseModel):
    query: str = Field(..., max_length=500)
    max_results: int = Field(default=10, ge=1, le=50)

    @field_validator("query")
    @classmethod
    def sanitize_query(cls, v: str) -> str:
        # Strip HTML/script tags
        import re
        v = re.sub(r'<[^>]*>', '', v)
        # Limit length
        return v[:500]
```

**Checklist**:
- [x] Tất cả tools có Pydantic input schema
- [x] Path traversal prevention trong file tools
- [x] Shell command allow list validation
- [x] Input sanitization (HTML, script, SQL)
- [x] Length limits trên tất cả string inputs
- [x] Range limits trên numeric inputs
- [x] `@field_validator` cho business logic validation

---

### Step 5.3: Subprocess Safety

**Mục tiêu**: Đảm bảo subprocess calls an toàn.

```python
# ❌ BAD: Shell injection risk
import subprocess
subprocess.run(f"ls {user_input}", shell=True)

# ✅ GOOD: List args, no shell
import subprocess
subprocess.run(["ls", user_input], shell=False, timeout=30)

# ✅ GOOD: Use pathlib
from pathlib import Path
safe_path = Path(user_input).resolve()
subprocess.run(["cat", str(safe_path)], timeout=10)
```

**Checklist**:
- [x] `grep -r "shell=True" src/` → NO RESULTS (trừ khi documented + safe)
- [x] `grep -r "pickle.load" src/` → NO RESULTS
- [x] `grep -r "eval(" src/` → NO RESULTS (trừ khi sandboxed)
- [x] `grep -r "exec(" src/` → NO RESULTS (trừ khi sandboxed)
- [x] Subprocess calls có timeout
- [x] Subprocess calls dùng list args

---

### Step 5.4: Sandbox Configuration

**Mục tiêu**: Cấu hình sandbox cho code execution.

**Cách thực hiện**: Dựa trên [AIDLC Lifecycle §5 Sandbox](../aidlc-lifecycle.md#sandbox-configuration)

```python
# Production sandbox config
agent, backend = create_cli_agent(
    model=model,
    assistant_id="prod-agent",
    sandbox_type="docker",               # Docker isolation
    shell_allow_list=[
        "ls", "cat", "grep", "find",
        "python", "pip", "git",
    ],
    interrupt_shell_only=True,            # Interrupt mọi shell command
    permissions=[
        {"path": "/workspace/**", "permissions": ["read", "write"]},
        {"path": "/data/**", "permissions": ["read"]},
    ],
)
```

**Sandbox Decision**:

| Environment | sandbox_type | auto_approve | Use Case |
|-------------|-------------|--------------|----------|
| **Development** | `"docker"` | `True` | Fast iteration, trusted code |
| **CI/Testing** | `"docker"` | `False` | Automated testing |
| **Production** | `"docker"` | `False` | Maximum security |
| **Demo/POC** | `"none"` | `True` | Trusted environment only |

**Checklist**:
- [x] Sandbox type selected (`"docker"` cho production)
- [x] Shell allow list configured
- [x] File system permissions scoped
- [x] `interrupt_shell_only=True` cho production
- [x] `auto_approve=False` cho production
- [x] Sandbox tested với malicious commands

---

### Step 5.5: Human-in-the-Loop Configuration

**Mục tiêu**: Cấu hình HITL approval cho dangerous tools.

**Cách thực hiện**:

```python
from langchain.middleware import HumanInTheLoopMiddleware

# Các tool cần approval
dangerous_tools = {
    "write_file": True,       # Ghi file — cần approval
    "execute_command": True,  # Chạy command — cần approval
    "task": True,             # Spawn subagent — cần approval
    "edit_file": True,        # Sửa file — cần approval
}

agent = create_deep_agent(
    model=model,
    middleware=[
        HumanInTheLoopMiddleware(interrupt_on=dangerous_tools),
    ],
)
```

**HITL Decision Matrix**:

| Tool | Development | Production |
|------|------------|------------|
| `read_file` | No approval | No approval |
| `write_file` | No approval | **APPROVAL** |
| `edit_file` | No approval | **APPROVAL** |
| `execute_command` | No approval | **APPROVAL** |
| `task` (subagent) | No approval | **APPROVAL** |
| `glob`/`grep` | No approval | No approval |

**Checklist**:
- [x] Dangerous tools identified
- [x] HITL configured cho production
- [x] `interrupt_on` dict configured
- [x] HITL flow tested

---

### Step 5.6: PII Protection

**Mục tiêu**: Enable PII detection middleware.

```python
from langchain.middleware import PIIMiddleware

agent = create_deep_agent(
    model=model,
    middleware=[
        PIIMiddleware(),  # Auto-detect and warn about PII
    ],
)
```

**Checklist**:
- [x] `PIIMiddleware` enabled
- [x] PII detection patterns verified
- [x] Memory KHÔNG lưu PII
- [x] Logs KHÔNG chứa PII

---

### Step 5.7: Permission Boundary Enforcement

**Mục tiêu**: Giới hạn file system permissions.

```python
permissions = [
    {
        "path": "/workspace/**",
        "permissions": ["read", "write"],
    },
    {
        "path": "/workspace/.git/**",
        "permissions": [],  # Deny access to .git
    },
    {
        "path": "/data/**",
        "permissions": ["read"],
    },
    {
        "path": "/memories/**",
        "permissions": ["read", "write"],
    },
    # Default: no access to everything else
]
```

**Checklist**:
- [x] Permission boundaries defined
- [x] `.git/` directory protected
- [x] `.env` and secrets files protected
- [x] System directories (`/etc/`, `/proc/`) inaccessible
- [x] Permission config tested

---

### Step 5.8: Full Security Review

**Mục tiêu**: Complete security audit trước khi deploy.

**Cách thực hiện**:

```bash
# Gọi security-reviewer agent
/security-scan

# Hoặc:
# Agent: security-reviewer với prompt "Review all code for security vulnerabilities"
```

**Security Review Checklist** (từ [AIDLC Lifecycle §5.1](../aidlc-lifecycle.md#51-security-checklist)):

#### Secrets Management
- [x] No hardcoded API keys/passwords/tokens
- [x] All secrets via `os.environ` or secret manager
- [x] Secrets validated at startup
- [x] `.env` in `.gitignore`
- [x] No secrets in git history

#### Input Validation
- [x] All tools have Pydantic input schema
- [x] Path traversal prevention
- [x] SQL injection prevention (parameterized queries)
- [x] Subprocess: list args, no shell string
- [x] Input sanitization (HTML, scripts, SQL)

#### Sandbox
- [x] Production: Docker sandbox (`sandbox_type="docker"`)
- [x] Shell allow list configured
- [x] File system permissions limited
- [x] Sandbox tested

#### HITL
- [x] Dangerous tools require approval
- [x] Production: `auto_approve=False`
- [x] HITL flow tested

#### PII
- [x] PIIMiddleware enabled
- [x] Memory does not store PII
- [x] Logs do not contain PII

#### Code Safety
- [x] No `shell=True` in subprocess
- [x] No `pickle.load()` on untrusted data
- [x] No `eval()`/`exec()` outside sandbox
- [x] HTTP requests have timeouts
- [x] Error messages don't leak internals

#### Dependencies
- [x] Dependencies up to date
- [x] Known vulnerabilities checked (`pip-audit` or similar)
- [x] Minimum version pins in requirements

---

### Step 5.9: Security Documentation

**Mục tiêu**: Document security configuration cho operations team.

**Output**: `docs/security/security-configuration.md`

```markdown
# Security Configuration

## Secrets
- DEEPSEEK_API_KEY: Set via environment variable
- Rotation schedule: Every 90 days

## Sandbox
- Type: Docker
- Allow list: ls, cat, grep, find, python, pip, git

## HITL
- Tools requiring approval: write_file, execute_command, task, edit_file
- Approval flow: CLI prompt / API webhook

## Permissions
- /workspace/: read, write
- /data/: read
- /memories/: read, write
- Everything else: denied
```

**Checklist**:
- [x] Security configuration documented
- [x] Secrets rotation schedule defined
- [x] Incident response plan outlined
- [x] Security contact identified

---

## Phase 5 Completion Checklist

### Secrets
- [x] No hardcoded secrets (verified with grep)
- [x] All secrets from environment
- [x] Startup validation
- [x] `.env` in `.gitignore`

### Input Validation
- [x] All tools validated
- [x] Path traversal prevented
- [x] Shell allow list
- [x] Input sanitization

### Sandbox & HITL
- [x] Docker sandbox configured
- [x] Shell allow list
- [x] File permissions scoped
- [x] HITL enabled for dangerous tools

### PII & Code Safety
- [x] PIIMiddleware enabled
- [x] No unsafe subprocess/serialization
- [x] Timeouts on external calls

### Review
- [x] `security-reviewer` agent audit completed
- [x] All CRITICAL issues fixed
- [x] All HIGH issues fixed
- [x] Security documentation written

---

## Next Phase

→ [Phase 6: Deployment](06-deployment.md)

## References

| Tài liệu | Section |
|----------|---------|
| [AIDLC Lifecycle](../aidlc-lifecycle.md) | §5 Security Hardening |
| [Rules: Python Security](../../../.claude/rules/python/security.md) | Mandatory checks, validation |
| [Rules: Common Security](../../../.claude/rules/common/security.md) | Security response protocol |
| [Middleware](../../deep-agents/03-middleware.md) | HITL, PII, Sandbox middleware |
| [CLI/Server](../../deep-agents/09-deepagents-code.md) | Sandbox, security config |
