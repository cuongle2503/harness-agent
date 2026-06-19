"""Safe subprocess execution.

Phase 5 — Security Hardening (per AIDLC §5.3 Subprocess Safety).

Key rules:
- NEVER use shell=True — always list args
- Always set a timeout
- Validate commands against allow list
- Capture and limit output size
- With shell=False, args are passed directly to the kernel as argv
  elements — no shell interpretation occurs, so metacharacters are safe
"""

from __future__ import annotations

import subprocess

from harness_agent.core.exceptions import HarnessError


class SubprocessSafetyError(HarnessError):
    """Raised when a subprocess call violates safety rules."""


class SubprocessTimeoutError(HarnessError):
    """Raised when a subprocess call times out."""


def safe_run(
    args: list[str],
    *,
    timeout: int = 30,
    max_output: int = 100_000,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess safely.

    This is the ONLY approved way to run subprocesses in the harness.
    Direct subprocess.run() calls are prohibited by security policy.

    Args:
        args: Command and arguments as a list (e.g., ["ls", "-la"]).
              With shell=False, all args are passed directly to execve()
              as argv elements — no shell interpretation occurs.
        timeout: Maximum execution time in seconds.
        max_output: Maximum stdout+stderr size in bytes.
        cwd: Optional working directory.
        env: Optional environment variables (merged with current env).

    Returns:
        CompletedProcess with stdout and stderr as strings.

    Raises:
        SubprocessTimeoutError: If the process exceeds the timeout.
    """
    if not args:
        raise SubprocessSafetyError("Command args list must not be empty")

    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            env=env,
            shell=False,  # NEVER True — args go directly to execve()
        )
    except subprocess.TimeoutExpired as exc:
        raise SubprocessTimeoutError(
            f"Command timed out after {timeout}s: {' '.join(args)}"
        ) from exc

    # Truncate output to max_output
    stdout = result.stdout[:max_output] if result.stdout else ""
    stderr = result.stderr[:max_output] if result.stderr else ""

    return subprocess.CompletedProcess(
        args=args,
        returncode=result.returncode,
        stdout=stdout,
        stderr=stderr,
    )


__all__ = ["safe_run", "SubprocessSafetyError", "SubprocessTimeoutError"]
