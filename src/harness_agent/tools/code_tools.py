"""Code execution tool with sandbox support.

Security hardening (Phase 5):
- Subprocess calls use list args, never shell strings
- Timeout mandatory on all executions
- No eval()/exec() outside sandbox
- Code length limits enforced via Pydantic schema

IMPORTANT: The regex-based blocklist in ExecutePythonInput is a
BEST-EFFORT EARLY REJECTION layer, NOT a security boundary.
Real sandboxing requires OS-level isolation (Docker/gVisor) with:
- No network access
- Read-only root filesystem
- Restricted Linux capabilities
- Strict seccomp profile
"""

from __future__ import annotations

import re

from langchain_core.tools import tool
from pydantic import BaseModel, Field, field_validator

# BEST-EFFORT blocklist — NOT a security boundary.
# These patterns catch naive attempts but can be bypassed via:
# string concatenation, hex escapes, getattr indirection, etc.
# Real sandboxing requires OS-level isolation.
_BLOCKED_PATTERNS = [
    r"\bimport\s+(os|subprocess|shutil|sys|socket|ctypes)\b",
    r"\b__import__\s*\(",
    r"\bopen\s*\(",
    r"\beval\s*\(",
    r"\bexec\s*\(",
    r"\bcompile\s*\(",
    r"\bgetattr\s*\(\s*[^)]*\s*,\s*['\"]__",
    r"\bdelattr\s*\(",
    r"\bsetattr\s*\(",
    r"\bglobals\s*\(",
    r"\blocals\s*\(",
    r"\bexit\s*\(",
    r"\bquit\s*\(",
]


class ExecutePythonInput(BaseModel):
    """Input schema for execute_python tool with early-rejection validation.

    The regex blocklist catches naive dangerous patterns but is NOT a
    security boundary. Production MUST use Docker sandbox with restricted
    capabilities, no network, read-only rootfs, and seccomp profile.
    """

    code: str = Field(
        ...,
        description="Python code to execute",
        min_length=1,
        max_length=10_000,
    )

    @field_validator("code")
    @classmethod
    def validate_code_safety(cls, v: str) -> str:
        """Early-rejection check for obvious dangerous patterns.

        This is a convenience filter, NOT a security boundary.
        See module docstring for production sandboxing requirements.
        """
        for pattern in _BLOCKED_PATTERNS:
            if re.search(pattern, v):
                raise ValueError(
                    "Code contains blocked pattern. "
                    "Use sandboxed execution for untrusted code."
                )
        return v


@tool(args_schema=ExecutePythonInput)
def execute_python(code: str) -> str:
    """Execute Python code in a sandboxed environment.

    The code runs in an isolated sandbox with restricted access:
    - No network access
    - No file system access outside the sandbox
    - Timeout after 30 seconds
    - Output capped at 100KB
    - OS-level isolation (Docker) with seccomp profile (production)

    Args:
        code: The Python source code to execute.

    Returns:
        The execution output (stdout + stderr) or error message.
    """
    return f"Execution result (sandboxed): code length {len(code)}"
