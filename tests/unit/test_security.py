"""Unit tests for Phase 5 security modules."""

from __future__ import annotations

from pathlib import Path

import pytest

from harness_agent.security.hitl import (
    HITLApprovalDeniedError,
    HumanInTheLoopMiddleware,
)
from harness_agent.security.permissions import PermissionBoundary
from harness_agent.security.pii import PIIMiddleware
from harness_agent.security.sandbox import SandboxConfig
from harness_agent.security.subprocess_safety import (
    SubprocessSafetyError,
    SubprocessTimeoutError,
    safe_run,
)

# ── SandboxConfig ──────────────────────────────────────────────────────────

class TestSandboxConfig:
    """Tests for SandboxConfig."""

    def test_default_is_docker_production(self) -> None:
        config = SandboxConfig()
        assert config.sandbox_type == "docker"
        assert config.auto_approve is False
        assert config.interrupt_shell_only is True

    def test_development_config(self) -> None:
        config = SandboxConfig.development()
        assert config.sandbox_type == "docker"
        assert config.auto_approve is True
        assert config.interrupt_shell_only is False

    def test_ci_config(self) -> None:
        config = SandboxConfig.ci()
        assert config.sandbox_type == "docker"
        assert config.auto_approve is False

    def test_production_config(self) -> None:
        config = SandboxConfig.production()
        assert config.sandbox_type == "docker"
        assert config.auto_approve is False
        assert config.interrupt_shell_only is True

    def test_demo_config(self) -> None:
        config = SandboxConfig.demo()
        assert config.sandbox_type == "none"
        assert config.auto_approve is True

    def test_is_command_allowed_allows_ls(self) -> None:
        config = SandboxConfig()
        assert config.is_command_allowed("ls") is True

    def test_is_command_allowed_blocks_unknown(self) -> None:
        config = SandboxConfig()
        assert config.is_command_allowed("nmap") is False

    def test_is_command_allowed_empty(self) -> None:
        config = SandboxConfig()
        assert config.is_command_allowed("") is False


# ── Subprocess Safety ──────────────────────────────────────────────────────

class TestSafeRun:
    """Tests for safe_run."""

    def test_safe_run_echo(self) -> None:
        result = safe_run(["echo", "hello"])
        assert result.returncode == 0
        assert "hello" in result.stdout

    def test_safe_run_empty_args_raises(self) -> None:
        with pytest.raises(SubprocessSafetyError, match="empty"):
            safe_run([])

    def test_safe_run_with_special_chars_is_safe(self) -> None:
        """With shell=False, metacharacters are literal argv elements."""
        result = safe_run(["echo", "hello > world"])
        assert result.returncode == 0
        assert "hello > world" in result.stdout

    def test_safe_run_with_semicolons_is_safe(self) -> None:
        """With shell=False, semicolons are literal characters, not separators."""
        result = safe_run(["echo", "a;b;c"])
        assert result.returncode == 0
        assert "a;b;c" in result.stdout

    def test_safe_run_timeout(self) -> None:
        with pytest.raises(SubprocessTimeoutError):
            safe_run(["sleep", "3"], timeout=0)  # timeout of 0 = immediate

    def test_safe_run_shell_false_by_default(self) -> None:
        """Verify safe_run never uses shell=True."""
        result = safe_run(["echo", "test"])
        assert result.returncode == 0


# ── HITL Middleware ─────────────────────────────────────────────────────────

class MockRequest:
    """Minimal mock of a tool call request."""
    def __init__(self, tool: str) -> None:
        self.tool = tool


class TestHITL:
    """Tests for HumanInTheLoopMiddleware."""

    def test_requires_approval_write_file(self) -> None:
        hitl = HumanInTheLoopMiddleware()
        assert hitl._requires_approval("write_file") is True

    def test_no_approval_read_file(self) -> None:
        hitl = HumanInTheLoopMiddleware()
        assert hitl._requires_approval("read_file") is False

    def test_requires_approval_execute_command(self) -> None:
        hitl = HumanInTheLoopMiddleware()
        assert hitl._requires_approval("execute_command") is True

    def test_production_mode_all_dangerous(self) -> None:
        hitl = HumanInTheLoopMiddleware(production_mode=True)
        assert hitl._requires_approval("read_file") is False
        assert hitl._requires_approval("write_file") is True
        assert hitl._requires_approval("execute_command") is True

    def test_custom_interrupt_on(self) -> None:
        hitl = HumanInTheLoopMiddleware(
            interrupt_on={"custom_tool": True, "safe_tool": False}
        )
        assert hitl._requires_approval("custom_tool") is True
        assert hitl._requires_approval("safe_tool") is False

    def test_denies_when_no_callback(self) -> None:
        """Without approval callback, dangerous tools are denied (fail-safe)."""
        hitl = HumanInTheLoopMiddleware()
        with pytest.raises(HITLApprovalDeniedError, match="write_file"):
            hitl.wrap_tool_call(MockRequest("write_file"), lambda r: "result")

    def test_allows_when_callback_approves(self) -> None:
        """With approval callback returning True, tool proceeds."""
        hitl = HumanInTheLoopMiddleware(
            approval_callback=lambda tool, req: True,
        )
        result = hitl.wrap_tool_call(
            MockRequest("write_file"), lambda r: "approved"
        )
        assert result == "approved"

    def test_denies_when_callback_rejects(self) -> None:
        """With approval callback returning False, tool is denied."""
        hitl = HumanInTheLoopMiddleware(
            approval_callback=lambda tool, req: False,
        )
        with pytest.raises(HITLApprovalDeniedError, match="write_file"):
            hitl.wrap_tool_call(MockRequest("write_file"), lambda r: "result")

    def test_no_approval_for_read_only_tools(self) -> None:
        """Read-only tools pass through without approval check."""
        hitl = HumanInTheLoopMiddleware()
        result = hitl.wrap_tool_call(
            MockRequest("read_file"), lambda r: "allowed"
        )
        assert result == "allowed"

    def test_production_mode_blocks_write_without_callback(self) -> None:
        """In production, dangerous tools are blocked without approval."""
        hitl = HumanInTheLoopMiddleware(production_mode=True)
        with pytest.raises(HITLApprovalDeniedError, match="write_file"):
            hitl.wrap_tool_call(MockRequest("write_file"), lambda r: "result")

    def test_callback_failure_denies_by_default(self) -> None:
        """If callback raises an exception, deny (fail-safe)."""
        def failing_callback(tool: str, req: object) -> bool:
            raise RuntimeError("callback error")

        hitl = HumanInTheLoopMiddleware(approval_callback=failing_callback)
        with pytest.raises(HITLApprovalDeniedError, match="write_file"):
            hitl.wrap_tool_call(MockRequest("write_file"), lambda r: "result")


# ── PII Middleware ──────────────────────────────────────────────────────────

class TestPIIMiddleware:
    """Tests for PIIMiddleware."""

    def test_detect_email(self) -> None:
        pii = PIIMiddleware()
        pii.scan("Contact: user@example.com for help", source="test")
        assert pii.has_pii() is True
        detected = pii.get_detected()
        assert any(d["type"] == "email" for d in detected)

    def test_detect_no_pii(self) -> None:
        pii = PIIMiddleware()
        pii.scan("Hello, world! This is a clean text.", source="test")
        assert pii.has_pii() is False

    def test_redact_email(self) -> None:
        pii = PIIMiddleware(redact=True)
        result = pii.scan("Email: test@example.com", source="test")
        assert "test@example.com" not in result
        assert "[REDACTED_EMAIL]" in result

    def test_clear_resets_detected(self) -> None:
        pii = PIIMiddleware()
        pii.scan("Email: test@example.com", source="test")
        assert pii.has_pii() is True
        pii.clear()
        assert pii.has_pii() is False

    def test_detect_credit_card(self) -> None:
        pii = PIIMiddleware()
        pii.scan("Card: 4111-1111-1111-1111", source="test")
        detected = pii.get_detected()
        assert any(d["type"] == "credit_card" for d in detected)

    def test_detect_phone(self) -> None:
        pii = PIIMiddleware()
        pii.scan("Call: 555-123-4567", source="test")
        detected = pii.get_detected()
        assert any(d["type"] == "phone" for d in detected)

    def test_detect_api_key(self) -> None:
        pii = PIIMiddleware()
        pii.scan("Authorization: sk-abcdef12345678901234567890", source="test")
        detected = pii.get_detected()
        assert any(d["type"] == "api_key" for d in detected)


# ── Permission Boundary ─────────────────────────────────────────────────────

class TestPermissionBoundary:
    """Tests for PermissionBoundary."""

    def test_production_denies_git(self) -> None:
        boundary = PermissionBoundary.production()
        assert boundary.is_allowed("/workspace/.git/config", "read") is False
        assert boundary.is_allowed("/workspace/.git/HEAD", "write") is False

    def test_production_allows_workspace_read(self) -> None:
        boundary = PermissionBoundary.production()
        assert boundary.is_allowed("/workspace/src/main.py", "read") is True

    def test_production_allows_workspace_write(self) -> None:
        boundary = PermissionBoundary.production()
        assert boundary.is_allowed("/workspace/src/output.txt", "write") is True

    def test_blocks_env_file(self) -> None:
        boundary = PermissionBoundary()
        assert boundary.is_allowed("/workspace/.env", "read") is False
        assert boundary.is_allowed("/workspace/.env.production", "read") is False

    def test_blocks_system_directories(self) -> None:
        boundary = PermissionBoundary()
        assert boundary.is_allowed("/etc/passwd", "read") is False
        assert boundary.is_allowed("/proc/cpuinfo", "read") is False
        assert boundary.is_allowed("/sys/kernel", "read") is False

    def test_is_path_safe_in_workspace(self) -> None:
        boundary = PermissionBoundary(
            workspace_root=Path("/workspace")
        )
        assert boundary.is_path_safe("/workspace/src/app.py") is True

    def test_is_path_safe_outside_workspace(self) -> None:
        boundary = PermissionBoundary(
            workspace_root=Path("/workspace")
        )
        assert boundary.is_path_safe("/etc/passwd") is False

    def test_development_allows_tmp(self) -> None:
        boundary = PermissionBoundary.development()
        assert boundary.is_allowed("/tmp/build.log", "write") is True

    def test_development_allows_git_read(self) -> None:
        boundary = PermissionBoundary.development()
        assert boundary.is_allowed("/workspace/.git/HEAD", "read") is True

    def test_default_denies_unknown(self) -> None:
        boundary = PermissionBoundary()
        assert boundary.is_allowed("/random/path/file.txt", "read") is False
