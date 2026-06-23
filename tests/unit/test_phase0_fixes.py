"""Tests for Phase 0 critical fixes: shell injection, mutable dict, bare except."""

from __future__ import annotations

import types

import pytest

from harness_agent.tools.basic_tools import execute_command


class TestShellInjection:
    """Fix 0.1: execute_command must reject injection payloads."""

    def test_rejects_shell_metachar_semicolon(self) -> None:
        result = execute_command.invoke({"command": "ls; cat /etc/passwd"})
        assert "Error" in result
        assert "/etc/passwd" not in result or "not in the allowed list" in result

    def test_rejects_pipe_injection(self) -> None:
        result = execute_command.invoke({"command": "ncat -l 4444"})
        assert "not in the allowed list" in result

    def test_rejects_subshell_injection(self) -> None:
        result = execute_command.invoke({"command": "$(cat /etc/shadow)"})
        assert "Error" in result

    def test_rejects_disallowed_command(self) -> None:
        result = execute_command.invoke({"command": "nc -l 4444"})
        assert "not in the allowed list" in result

    def test_allows_safe_command(self) -> None:
        result = execute_command.invoke({"command": "echo hello"})
        assert "hello" in result

    def test_allows_ls(self) -> None:
        result = execute_command.invoke({"command": "ls"})
        assert "Error" not in result or "not in the allowed list" not in result

    def test_rejects_empty_command(self) -> None:
        result = execute_command.invoke({"command": ""})
        assert "Error" in result


class TestMutableClassDict:
    """Fix 0.2: harness_info must be immutable after assignment."""

    def test_harness_info_is_frozen(self) -> None:
        from harness_agent.deployment.cli_metrics_server import _MetricsHandler

        assert isinstance(
            _MetricsHandler.harness_info, types.MappingProxyType
        )

    def test_harness_info_rejects_mutation(self) -> None:
        from harness_agent.deployment.cli_metrics_server import _MetricsHandler

        with pytest.raises(TypeError):
            _MetricsHandler.harness_info["new_key"] = "value"  # type: ignore[index]

    def test_start_metrics_server_freezes_info(self) -> None:
        from harness_agent.deployment.cli_metrics_server import (
            _MetricsHandler,
            start_metrics_server,
        )
        from harness_agent.monitoring.metrics import AgentMetrics

        import time

        metrics = AgentMetrics()
        info = {"skills": ["a", "b"], "rules": ["r1"]}
        server, port = start_metrics_server(
            metrics=metrics,
            start_time=time.monotonic(),
            memory=None,
            port=0,
            harness_info=info,
        )
        try:
            assert isinstance(
                _MetricsHandler.harness_info, types.MappingProxyType
            )
            assert _MetricsHandler.harness_info["skills"] == ["a", "b"]
        finally:
            server.shutdown()


class TestBareExcept:
    """Fix 0.3: server.py must log warning instead of silently passing."""

    def test_source_has_no_bare_except_pass(self) -> None:
        import inspect

        import harness_agent.deployment.server as server_mod

        source = inspect.getsource(server_mod)
        assert "except Exception:\n                        pass" not in source

    def test_source_logs_warning_on_exception(self) -> None:
        import inspect

        import harness_agent.deployment.server as server_mod

        source = inspect.getsource(server_mod)
        assert 'logger.warning(\n                            "Failed to load system prompt' in source
