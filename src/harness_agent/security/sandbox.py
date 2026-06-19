"""Sandbox configuration for code execution.

Phase 5 — Security Hardening (per AIDLC §5 Sandbox Configuration).

Provides SandboxConfig for Docker-based isolation with:
- Shell command allow-list
- File system permission scoping
- Mandatory timeouts
- Environment-specific defaults (dev/CI/prod)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

SandboxType = Literal["docker", "none"]


@dataclass
class SandboxConfig:
    """Configuration for the execution sandbox.

    Attributes:
        sandbox_type: "docker" for Docker isolation, "none" for trusted env.
        shell_allow_list: Allowed shell commands.
        interrupt_shell_only: If True, interrupt every shell command for approval.
        auto_approve: If True, auto-approve commands (dev only).
        file_permissions: Scoped file system permission rules.
        execution_timeout: Default timeout in seconds for subprocess calls.
        output_max_bytes: Maximum output size from sandboxed executions.
    """

    sandbox_type: SandboxType = "docker"
    shell_allow_list: list[str] = field(default_factory=lambda: [
        "ls", "cat", "grep", "find",
        "python", "pip", "git",
        "echo", "head", "tail", "wc",
    ])
    interrupt_shell_only: bool = True
    auto_approve: bool = False
    file_permissions: list[dict[str, object]] = field(default_factory=list)
    execution_timeout: int = 30
    output_max_bytes: int = 100_000

    @classmethod
    def development(cls) -> SandboxConfig:
        """Development sandbox — Docker, auto-approve for fast iteration."""
        return cls(
            sandbox_type="docker",
            auto_approve=True,
            interrupt_shell_only=False,
            execution_timeout=60,
        )

    @classmethod
    def ci(cls) -> SandboxConfig:
        """CI/testing sandbox — Docker, no auto-approve."""
        return cls(
            sandbox_type="docker",
            auto_approve=False,
            interrupt_shell_only=False,
            execution_timeout=120,
        )

    @classmethod
    def production(cls) -> SandboxConfig:
        """Production sandbox — Docker, max security."""
        return cls(
            sandbox_type="docker",
            auto_approve=False,
            interrupt_shell_only=True,
            execution_timeout=30,
        )

    @classmethod
    def demo(cls) -> SandboxConfig:
        """Demo/POC — no Docker, trusted environment only."""
        return cls(
            sandbox_type="none",
            auto_approve=True,
            interrupt_shell_only=False,
            execution_timeout=60,
        )

    def is_command_allowed(self, command: str) -> bool:
        """Check if a command is in the shell allow list.

        Args:
            command: The base command to check.

        Returns:
            True if the command is allowed.
        """
        base_cmd = command.strip().split()[0] if command.strip() else ""
        return base_cmd in self.shell_allow_list


__all__ = ["SandboxConfig", "SandboxType"]
