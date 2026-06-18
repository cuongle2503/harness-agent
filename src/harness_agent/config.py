"""Model selection and configuration for agent orchestration.

Phase 0.2 — Model Selection Decision Matrix
See: AIDLC Lifecycle §0.2, docs/guides/plans/00-foundation.md §0.2

All models use DeepSeek V4 family (released 2026-04-24).
Provider: DeepSeek API (OpenAI-compatible endpoint).

DeepSeek V4 Model Comparison:
┌──────────────────────┬──────────────────────┬──────────────────────┐
│                      │ deepseek-v4-flash    │ deepseek-v4-pro      │
├──────────────────────┼──────────────────────┼──────────────────────┤
│ Total params         │ 284B                 │ 1.6T                 │
│ Active params        │ 13B                  │ 49B                  │
│ Context window       │ 1M tokens            │ 1M tokens            │
│ Max output           │ 384K tokens          │ 384K tokens          │
│ Tool calling         │ ✅ Yes               │ ✅ Yes               │
│ Structured output    │ ✅ Yes               │ ✅ Yes               │
│ Thinking mode        │ Optional (off by     │ Default on           │
│                      │ default)             │                      │
│ Input (cache miss)   │ $0.14/1M             │ $0.435/1M            │
│ Input (cache hit)    │ $0.0028/1M           │ $0.003625/1M         │
│ Output               │ $0.28/1M             │ $0.87/1M             │
│ Concurrency          │ 2500                 │ 500                  │
└──────────────────────┴──────────────────────┴──────────────────────┘

References:
- https://api-docs.deepseek.com/quick_start/pricing
- https://api-docs.deepseek.com/updates
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ModelConfig:
    """Configuration for a single model in the agent system.

    Attributes:
        model_id: Fully-qualified DeepSeek model ID (e.g. "deepseek-v4-pro").
        provider: "deepseek" (all models share the same DeepSeek API).
        temperature: Sampling temperature (0.0 = deterministic).
        max_tokens: Maximum output tokens (None = provider default).
        purpose: Short description of this model's role.
    """

    model_id: str
    provider: str
    temperature: float = 0.0
    max_tokens: int | None = None
    purpose: str = ""


@dataclass
class AgentModelSelection:
    """Complete model selection for the agent harness.

    Selection Rationale (per AIDLC §0.2 Decision Matrix):
    ┌─────────────────────────┬──────────────────────┬───────────────────────────┐
    │ Role                    │ Model                │ Rationale                 │
    ├─────────────────────────┼──────────────────────┼───────────────────────────┤
    │ Main orchestrator       │ deepseek-v4-flash    │ Fast tool calling,        │
    │                         │                      │ low cost, high concurrency │
    │                         │                      │ for routing & delegation  │
    ├─────────────────────────┼──────────────────────┼───────────────────────────┤
    │ Subagents (heavy)       │ deepseek-v4-pro      │ Strongest reasoning for   │
    │                         │                      │ complex analysis, code    │
    │                         │                      │ generation, architecture  │
    ├─────────────────────────┼──────────────────────┼───────────────────────────┤
    │ Subagents (light)       │ deepseek-v4-flash    │ Cost efficiency for       │
    │                         │                      │ simple tasks, 2500 QPS    │
    ├─────────────────────────┼──────────────────────┼───────────────────────────┤
    │ Summarization           │ deepseek-v4-flash    │ 1M context, cheap output  │
    │                         │                      │ for compressing long ctx  │
    ├─────────────────────────┼──────────────────────┼───────────────────────────┤
    │ Router / Classifier     │ deepseek-v4-flash    │ Fast structured output,   │
    │                         │                      │ intent classification     │
    └─────────────────────────┴──────────────────────┴───────────────────────────┘

    Why orchestrator uses v4-flash (not v4-pro):
    - Orchestration is primarily a tool-calling task, not deep reasoning
    - v4-flash is 3x cheaper and 5x higher concurrency than v4-pro
    - Fast response matters for the agent's perceived performance
    - v4-pro reserved for subagents doing truly complex work

    Only one API key needed: DEEPSEEK_API_KEY
    """

    orchestrator: ModelConfig = field(default_factory=lambda: ModelConfig(
        model_id="deepseek-v4-flash",
        provider="deepseek",
        temperature=0.0,
        purpose="Main orchestrator — planning, routing, delegation decisions",
    ))

    subagent_heavy: ModelConfig = field(default_factory=lambda: ModelConfig(
        model_id="deepseek-v4-pro",
        provider="deepseek",
        temperature=0.0,
        purpose="Heavy subagents — complex reasoning, code generation, architecture",
    ))

    subagent_light: ModelConfig = field(default_factory=lambda: ModelConfig(
        model_id="deepseek-v4-flash",
        provider="deepseek",
        temperature=0.0,
        purpose="Light subagents — simple lookups, formatting, classification",
    ))

    summarization: ModelConfig = field(default_factory=lambda: ModelConfig(
        model_id="deepseek-v4-flash",
        provider="deepseek",
        temperature=0.0,
        max_tokens=4096,
        purpose="Summarization — compress long context; 1M context window, cheap",
    ))

    router: ModelConfig = field(default_factory=lambda: ModelConfig(
        model_id="deepseek-v4-flash",
        provider="deepseek",
        temperature=0.0,
        max_tokens=1024,
        purpose="Router / Classifier — structured output, intent classification",
    ))

    @property
    def all_models(self) -> list[ModelConfig]:
        """All configured models for validation."""
        return [
            self.orchestrator,
            self.subagent_heavy,
            self.subagent_light,
            self.summarization,
            self.router,
        ]

    def validate(self) -> list[str]:
        """Validate that required API keys are set. Returns list of warnings."""
        warnings: list[str] = []

        providers_needed = {m.provider for m in self.all_models}
        for provider in providers_needed:
            if provider == "deepseek" and not os.environ.get("DEEPSEEK_API_KEY"):
                warnings.append(
                    "DEEPSEEK_API_KEY not set — DeepSeek models unavailable"
                )

        return warnings

    def to_langchain_model(self, config: ModelConfig) -> Any:
        """Convert a ModelConfig to a LangChain BaseChatModel instance.

        Uses ChatDeepSeek from langchain_deepseek package for native
        DeepSeek API integration (OpenAI-compatible endpoint).

        Example:
            selection = AgentModelSelection()
            main_model = selection.to_langchain_model(selection.orchestrator)
        """
        from langchain_deepseek import ChatDeepSeek

        kwargs: dict[str, Any] = {
            "model": config.model_id,
            "temperature": config.temperature,
        }
        if config.max_tokens is not None:
            kwargs["max_tokens"] = config.max_tokens

        return ChatDeepSeek(**kwargs)
