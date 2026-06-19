"""LangChain/LangSmith tracing configuration.

Phase 7.5 — Sets environment variables for LangChain tracing.
See: docs/guides/plans/07-monitoring.md §7.5
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class TracingConfig:
    """LangChain tracing configuration.

    Attributes:
        enabled: Whether to enable LangChain tracing (LANGCHAIN_TRACING_V2).
        project: LangSmith project name for this deployment.
        endpoint: LangSmith API endpoint URL.
        sample_rate: Fraction of traces to sample (1.0 = 100%, 0.1 = 10%).
    """

    enabled: bool = True
    project: str = "harness-agent-prod"
    endpoint: str = "https://api.smith.langchain.com"
    sample_rate: float = 1.0


def configure_tracing(config: TracingConfig | None = None) -> None:
    """Set LangChain tracing environment variables.

    When enabled, sets ``LANGCHAIN_TRACING_V2``, ``LANGCHAIN_PROJECT``,
    and ``LANGCHAIN_ENDPOINT``. The sampling rate is handled by
    LangChain's callback system.

    Args:
        config: Tracing configuration. Uses production defaults when None.
    """
    cfg = config or TracingConfig()
    if cfg.enabled:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_PROJECT"] = cfg.project
        os.environ["LANGCHAIN_ENDPOINT"] = cfg.endpoint
