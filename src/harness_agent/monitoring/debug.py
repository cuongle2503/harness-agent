"""Debug mode toggle for development and troubleshooting.

Phase 7.7 — Controlled via DEEPAGENTS_DEBUG environment variable.
See: docs/guides/plans/07-monitoring.md §7.7
"""

from __future__ import annotations

import logging
import os

# Environment variable that toggles debug mode
DEBUG_ENV_VAR = "DEEPAGENTS_DEBUG"

# Truthy values accepted for enabling debug
_TRUTHY = frozenset({"1", "true", "yes", "on"})


def is_debug_enabled() -> bool:
    """Check if debug mode is enabled via the DEEPAGENTS_DEBUG env var.

    Returns:
        True when DEEPAGENTS_DEBUG is set to a truthy value
        ("1", "true", "yes", "on"), case-insensitive.
    """
    return os.environ.get(DEBUG_ENV_VAR, "").lower() in _TRUTHY


def configure_debug_mode(force: bool | None = None) -> None:
    """Configure verbose logging based on debug mode.

    When debug is enabled, sets the ``harness_agent`` logger to DEBUG level.
    When disabled, sets it to WARNING level (quieter production default).

    Args:
        force: Override the env-var check.
            - ``None`` (default): Read DEEPAGENTS_DEBUG env var.
            - ``True``: Force enable debug regardless of env var.
            - ``False``: Force disable debug (production safeguard).
    """
    debug = force if force is not None else is_debug_enabled()

    harness_logger = logging.getLogger("harness_agent")

    if debug:
        harness_logger.setLevel(logging.DEBUG)
        harness_logger.debug("Debug mode enabled — verbose logging active")
    else:
        harness_logger.setLevel(logging.WARNING)
        # Production safeguard warning
        if is_debug_enabled():
            harness_logger.warning(
                "DEEPAGENTS_DEBUG is set but force=False — "
                "debug mode suppressed (production safeguard)",
            )
