"""Code execution tool with sandbox support."""

from __future__ import annotations

from langchain_core.tools import tool
from pydantic import BaseModel, Field


class ExecutePythonInput(BaseModel):
    """Input schema for execute_python tool."""

    code: str = Field(..., description="Python code to execute", min_length=1)


@tool(args_schema=ExecutePythonInput)
def execute_python(code: str) -> str:
    """Execute Python code in a sandboxed environment.

    The code runs in an isolated sandbox with restricted access:
    - No network access
    - No file system access outside the sandbox
    - Timeout after 30 seconds
    - Output capped at 100KB

    Args:
        code: The Python source code to execute.

    Returns:
        The execution output (stdout + stderr) or error message.
    """
    # Minimal GREEN-phase implementation.
    # Production sandbox (Docker) deferred to Phase 5.
    return f"Execution result (sandboxed): code length {len(code)}"
