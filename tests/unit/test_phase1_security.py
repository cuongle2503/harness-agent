"""Tests for Phase 1 security boundary fixes."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from harness_agent.security.hitl import (
    HITLApprovalDeniedError,
    HumanInTheLoopMiddleware,
)
from harness_agent.security.permissions import PermissionBoundary, _path_matches
from harness_agent.security.pii import PIIMiddleware
from harness_agent.security.sandbox import SandboxConfig
from harness_agent.security.subprocess_safety import (
    SubprocessSafetyError,
    safe_run,
)


class TestPathTraversalBypass:
    """Fix 1.1: is_path_safe must use path-level comparison."""

    def test_rejects_prefix_overlap(self, tmp_path: Path) -> None:
        workspace = tmp_path / "project"
        workspace.mkdir()
        evil = tmp_path / "project-evil"
        evil.mkdir()

        boundary = PermissionBoundary(workspace_root=workspace)
        assert boundary.is_path_safe(str(evil / "secret")) is False

    def test_allows_valid_subpath(self, tmp_path: Path) -> None:
        workspace = tmp_path / "project"
        workspace.mkdir()
        subdir = workspace / "src"
        subdir.mkdir()

        boundary = PermissionBoundary(workspace_root=workspace)
        assert boundary.is_path_safe(str(subdir / "main.py")) is True

    def test_rejects_parent_traversal(self, tmp_path: Path) -> None:
        workspace = tmp_path / "project"
        workspace.mkdir()

        boundary = PermissionBoundary(workspace_root=workspace)
        assert boundary.is_path_safe(str(tmp_path / "other")) is False


class TestPathMatchesPattern:
    """Fix 1.2: _path_matches must not match prefix overlaps."""

    def test_glob_star_rejects_prefix_overlap(self) -> None:
        assert _path_matches("/workspace-other/file", "/workspace/**") is False

    def test_glob_star_allows_valid_subpath(self) -> None:
        assert _path_matches("/workspace/src/main.py", "/workspace/**") is True

    def test_glob_star_allows_exact_child(self) -> None:
        assert _path_matches("/workspace/file.txt", "/workspace/**") is True

    def test_glob_star_rejects_sibling(self) -> None:
        assert _path_matches("/workspace2/file.txt", "/workspace/**") is False


class TestPIIAccumulation:
    """Fix 1.3: scan() must clear _detected each call."""

    def test_has_pii_resets_after_clean_scan(self) -> None:
        scanner = PIIMiddleware()
        scanner.scan("contact me at user@example.com")
        assert scanner.has_pii() is True

        scanner.scan("clean text with no PII")
        assert scanner.has_pii() is False

    def test_detected_list_reflects_current_scan(self) -> None:
        scanner = PIIMiddleware()
        scanner.scan("user@example.com and admin@test.org")
        assert len(scanner.get_detected()) == 2

        scanner.scan("just one: a@b.com")
        assert len(scanner.get_detected()) == 1


class TestValuePreviewEllipsis:
    """Fix 1.4: value_preview only appends ... when truncated."""

    def test_short_match_no_ellipsis(self) -> None:
        scanner = PIIMiddleware()
        scanner.scan("user@example.com")
        detected = scanner.get_detected()
        assert len(detected) == 1
        assert not detected[0]["value_preview"].endswith("...")

    def test_long_match_has_ellipsis(self) -> None:
        scanner = PIIMiddleware()
        long_email = "a" * 45 + "@example.com"
        scanner.scan(long_email)
        detected = scanner.get_detected()
        assert len(detected) == 1
        assert detected[0]["value_preview"].endswith("...")


class TestHITLExceptionChain:
    """Fix 1.5: HITLApprovalDeniedError must chain original exception."""

    def test_exception_chain_preserved(self) -> None:
        def failing_callback(tool_name: str, request: object) -> bool:
            raise ValueError("callback exploded")

        middleware = HumanInTheLoopMiddleware(
            interrupt_on={"dangerous_tool": True},
            approval_callback=failing_callback,
        )

        request = MagicMock()
        request.tool = "dangerous_tool"

        with pytest.raises(HITLApprovalDeniedError) as exc_info:
            middleware.wrap_tool_call(request, lambda r: r)

        assert exc_info.value.__cause__ is not None
        assert isinstance(exc_info.value.__cause__, ValueError)
        assert "callback exploded" in str(exc_info.value.__cause__)


class TestSafeRunAllowList:
    """Fix 1.6: safe_run() must enforce sandbox allow-list."""

    def test_rejects_disallowed_command(self) -> None:
        sandbox = SandboxConfig(shell_allow_list=["ls", "cat"])
        with pytest.raises(SubprocessSafetyError, match="not in the sandbox allow-list"):
            safe_run(["curl", "http://evil.com"], sandbox=sandbox)

    def test_allows_permitted_command(self) -> None:
        sandbox = SandboxConfig(shell_allow_list=["echo"])
        result = safe_run(["echo", "hello"], sandbox=sandbox)
        assert "hello" in result.stdout

    def test_no_sandbox_allows_all(self) -> None:
        result = safe_run(["echo", "unrestricted"])
        assert "unrestricted" in result.stdout

    def test_rejects_empty_args_regardless(self) -> None:
        sandbox = SandboxConfig()
        with pytest.raises(SubprocessSafetyError, match="must not be empty"):
            safe_run([], sandbox=sandbox)
