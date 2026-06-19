"""Unit tests for debug mode toggle."""

from __future__ import annotations

import os
from unittest.mock import patch

from harness_agent.monitoring.debug import (
    DEBUG_ENV_VAR,
    configure_debug_mode,
    is_debug_enabled,
)


class TestIsDebugEnabled:
    """Tests for is_debug_enabled()."""

    @patch.dict(os.environ, {}, clear=True)
    def test_defaults_to_false_when_env_not_set(self) -> None:
        assert is_debug_enabled() is False

    @patch.dict(os.environ, {DEBUG_ENV_VAR: "true"}, clear=True)
    def test_true_string_enables_debug(self) -> None:
        assert is_debug_enabled() is True

    @patch.dict(os.environ, {DEBUG_ENV_VAR: "1"}, clear=True)
    def test_one_enables_debug(self) -> None:
        assert is_debug_enabled() is True

    @patch.dict(os.environ, {DEBUG_ENV_VAR: "yes"}, clear=True)
    def test_yes_enables_debug(self) -> None:
        assert is_debug_enabled() is True

    @patch.dict(os.environ, {DEBUG_ENV_VAR: "on"}, clear=True)
    def test_on_enables_debug(self) -> None:
        assert is_debug_enabled() is True

    @patch.dict(os.environ, {DEBUG_ENV_VAR: "false"}, clear=True)
    def test_false_string_disables_debug(self) -> None:
        assert is_debug_enabled() is False

    @patch.dict(os.environ, {DEBUG_ENV_VAR: "0"}, clear=True)
    def test_zero_disables_debug(self) -> None:
        assert is_debug_enabled() is False

    @patch.dict(os.environ, {DEBUG_ENV_VAR: ""}, clear=True)
    def test_empty_string_disables_debug(self) -> None:
        assert is_debug_enabled() is False

    @patch.dict(os.environ, {DEBUG_ENV_VAR: "TRUE"}, clear=True)
    def test_case_insensitive(self) -> None:
        assert is_debug_enabled() is True


class TestConfigureDebugMode:
    """Tests for configure_debug_mode()."""

    @patch.dict(os.environ, {}, clear=True)
    def test_force_true_enables_debug(self) -> None:
        """force=True enables debug regardless of env var."""
        import logging
        harness_logger = logging.getLogger("harness_agent")
        configure_debug_mode(force=True)
        assert harness_logger.level == logging.DEBUG

    @patch.dict(os.environ, {DEBUG_ENV_VAR: "true"}, clear=True)
    def test_force_false_disables_debug(self) -> None:
        """force=False disables debug even when env var is set."""
        import logging
        harness_logger = logging.getLogger("harness_agent")
        configure_debug_mode(force=False)
        assert harness_logger.level == logging.WARNING

    @patch.dict(os.environ, {}, clear=True)
    def test_default_disables_debug_when_env_not_set(self) -> None:
        """When env var is not set, debug should be disabled by default."""
        import logging
        harness_logger = logging.getLogger("harness_agent")
        configure_debug_mode()
        assert harness_logger.level == logging.WARNING

    @patch.dict(os.environ, {DEBUG_ENV_VAR: "true"}, clear=True)
    def test_default_enables_debug_when_env_set(self) -> None:
        """When env var is set to truthy, debug should be enabled."""
        import logging
        harness_logger = logging.getLogger("harness_agent")
        configure_debug_mode()
        assert harness_logger.level == logging.DEBUG
