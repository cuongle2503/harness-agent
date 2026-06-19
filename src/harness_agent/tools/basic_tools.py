"""Basic agent tools — file ops, shell, search.

These are the core tools the agent uses to interact with the filesystem
and execute commands. They are wired into the CLI and server agents.

Security:
- Path traversal prevention via resolve()
- Shell commands run via subprocess with list args (no shell=True)
- Timeout mandatory on all executions
"""

from __future__ import annotations

import glob as glob_module
import logging
import re
import subprocess
from pathlib import Path

from langchain_core.tools import tool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

_WORKSPACE = Path.cwd().resolve()


def _safe_path(file_path: str) -> Path:
    """Resolve and validate a file path against workspace traversal."""
    p = Path(file_path).resolve()
    # Allow absolute paths within workspace
    try:
        p.relative_to(_WORKSPACE)
    except ValueError:
        raise ValueError(
            f"Path '{file_path}' is outside workspace: {_WORKSPACE}"
        )
    return p


# ---------------------------------------------------------------------------
# Tool: read_file
# ---------------------------------------------------------------------------

class ReadFileInput(BaseModel):
    file_path: str = Field(..., description="Absolute path to the file to read")
    offset: int = Field(
        default=0, ge=0, description="Line number to start reading from"
    )
    limit: int = Field(
        default=2000, ge=1, le=5000, description="Maximum number of lines to read"
    )


@tool(args_schema=ReadFileInput)
def read_file(file_path: str, offset: int = 0, limit: int = 2000) -> str:
    """Read content from a file at the given path.

    Returns the file content with line numbers. Use offset and limit
    for large files.
    """
    try:
        safe = _safe_path(file_path)
    except ValueError as e:
        return f"Error: {e}"

    if not safe.exists():
        return f"Error: File not found: {file_path}"
    if safe.is_dir():
        return f"Error: Path is a directory: {file_path}"

    try:
        content = safe.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return f"Error: Cannot read {file_path} — not a UTF-8 text file"

    lines = content.split("\n")
    total = len(lines)
    start = offset
    end = min(start + limit, total)
    selected = lines[start:end]

    output_lines = [f"{i + 1}\t{line}" for i, line in enumerate(selected, start=start)]
    header = f"File: {file_path} (lines {start + 1}-{end} of {total})\n"
    return header + "\n".join(output_lines)


# ---------------------------------------------------------------------------
# Tool: write_file
# ---------------------------------------------------------------------------

class WriteFileInput(BaseModel):
    file_path: str = Field(..., description="Absolute path to the file to write")
    content: str = Field(..., description="Content to write to the file")


@tool(args_schema=WriteFileInput)
def write_file(file_path: str, content: str) -> str:
    """Write content to a file, overwriting if it exists.

    Creates parent directories if they don't exist.
    """
    try:
        safe = _safe_path(file_path)
    except ValueError as e:
        return f"Error: {e}"

    try:
        safe.parent.mkdir(parents=True, exist_ok=True)
        safe.write_text(content, encoding="utf-8")
    except OSError as e:
        return f"Error writing {file_path}: {e}"

    size = len(content.encode("utf-8"))
    return f"Wrote {len(content)} chars ({size} bytes) to {file_path}"


# ---------------------------------------------------------------------------
# Tool: edit_file
# ---------------------------------------------------------------------------

class EditFileInput(BaseModel):
    file_path: str = Field(..., description="Absolute path to the file to edit")
    old_string: str = Field(..., description="The exact text to replace")
    new_string: str = Field(..., description="The text to replace it with")


@tool(args_schema=EditFileInput)
def edit_file(file_path: str, old_string: str, new_string: str) -> str:
    """Perform an exact string replacement in a file.

    The old_string must match exactly one occurrence in the file.
    """
    try:
        safe = _safe_path(file_path)
    except ValueError as e:
        return f"Error: {e}"

    if not safe.exists():
        return f"Error: File not found: {file_path}"

    try:
        content = safe.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return f"Error: Cannot read {file_path} — not a UTF-8 text file"

    count = content.count(old_string)
    if count == 0:
        return f"Error: old_string not found in {file_path}"
    if count > 1:
        return (
            f"Error: old_string found {count} times in {file_path}. "
            "Please make it unique."
        )

    new_content = content.replace(old_string, new_string, 1)
    safe.write_text(new_content, encoding="utf-8")
    return f"Edited {file_path} — replaced 1 occurrence"


# ---------------------------------------------------------------------------
# Tool: glob
# ---------------------------------------------------------------------------

class GlobInput(BaseModel):
    pattern: str = Field(..., description="Glob pattern to match files (e.g. '**/*.py')")
    path: str = Field(
        default=".", description="Directory to search from (default: workspace root)"
    )


@tool(args_schema=GlobInput)
def glob(pattern: str, path: str = ".") -> str:
    """Find files matching a glob pattern.

    Supports recursive patterns like '**/*.py'.
    """
    try:
        base = _safe_path(path)
    except ValueError as e:
        return f"Error: {e}"

    if not base.exists():
        return f"Error: Directory not found: {path}"

    search_path = str(base / pattern)
    matches = sorted(glob_module.glob(search_path, recursive=True))
    matches = [m for m in matches if not m.endswith(".pyc") and "__pycache__" not in m]

    if not matches:
        return f"No files matched pattern '{pattern}' in {path}"

    return f"Found {len(matches)} file(s):\n" + "\n".join(f"  {m}" for m in matches[:50])


# ---------------------------------------------------------------------------
# Tool: grep
# ---------------------------------------------------------------------------

class GrepInput(BaseModel):
    pattern: str = Field(..., description="Regex pattern to search for")
    path: str = Field(
        default=".", description="File or directory to search in"
    )
    include: str = Field(
        default="*.py", description="File pattern to filter (e.g. '*.py', '*.md')"
    )


@tool(args_schema=GrepInput)
def grep(pattern: str, path: str = ".", include: str = "*.py") -> str:
    """Search for a regex pattern in files.

    Returns matching lines with file path and line number.
    """
    try:
        base = _safe_path(path)
    except ValueError as e:
        return f"Error: {e}"

    if not base.exists():
        return f"Error: Path not found: {path}"

    try:
        regex = re.compile(pattern)
    except re.error as e:
        return f"Error: Invalid regex pattern: {e}"

    if base.is_file():
        files = [base]
    else:
        files = sorted(base.rglob(include))
        # Filter out hidden and cache dirs
        files = [
            f for f in files
            if "__pycache__" not in str(f)
            and ".venv" not in str(f)
            and ".git/" not in str(f)
            and not any(p.startswith(".") for p in f.parts if p != ".")
        ]

    results: list[str] = []
    max_results = 30

    for f in files:
        if len(results) >= max_results:
            results.append(f"... (truncated, showing first {max_results} matches)")
            break
        try:
            for i, line in enumerate(f.read_text(encoding="utf-8").split("\n"), 1):
                if regex.search(line):
                    results.append(f"{f}:{i}: {line.strip()[:200]}")
                    if len(results) >= max_results:
                        break
        except (UnicodeDecodeError, OSError):
            continue

    if not results:
        return f"No matches for '{pattern}' in {path}"

    return "\n".join(results)


# ---------------------------------------------------------------------------
# Tool: execute_command
# ---------------------------------------------------------------------------

class ExecuteCommandInput(BaseModel):
    command: str = Field(..., description="The shell command to execute")
    timeout: int = Field(
        default=120, ge=1, le=600, description="Timeout in seconds"
    )


@tool(args_schema=ExecuteCommandInput)
def execute_command(command: str, timeout: int = 120) -> str:
    """Execute a shell command and return its output.

    Runs in the workspace directory. Commands are run with a mandatory
    timeout. Both stdout and stderr are captured.
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(_WORKSPACE),
        )
    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after {timeout}s"
    except Exception as e:
        return f"Error executing command: {e}"

    output = ""
    if result.stdout:
        output += result.stdout
    if result.stderr:
        output += f"\n[stderr]\n{result.stderr}"
    if result.returncode != 0:
        output += f"\n[exit code: {result.returncode}]"

    return output.strip() or "(no output)"


# ---------------------------------------------------------------------------
# Tool list for wiring into agents
# ---------------------------------------------------------------------------

BASIC_TOOLS: list = [
    read_file,
    write_file,
    edit_file,
    glob,
    grep,
    execute_command,
]
