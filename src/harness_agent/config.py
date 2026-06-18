"""Model selection and configuration for agent orchestration.

Phase 0.2 — Model Selection Decision Matrix
See: AIDLC Lifecycle §0.2, docs/guides/plans/00-foundation.md §0.2
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ModelConfig:
    """Configuration for a single model in the agent system.

    Attributes:
        model_id: Fully-qualified model identifier (e.g. "claude-sonnet-4-6").
        provider: "anthropic" | "openai" | "google".
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
    ┌─────────────────────────┬─────────────────────┬────────────────────────────┐
    │ Role                    │ Model               │ Rationale                  │
    ├─────────────────────────┼─────────────────────┼────────────────────────────┤
    │ Main orchestrator       │ claude-sonnet-4-6   │ Best tool-calling          │
    │                         │                     │ reliability, subagent      │
    │                         │                     │ delegation accuracy        │
    ├─────────────────────────┼─────────────────────┼────────────────────────────┤
    │ Subagents (heavy)       │ claude-sonnet-4-6   │ Complex reasoning,         │
    │                         │                     │ code generation            │
    ├─────────────────────────┼─────────────────────┼────────────────────────────┤
    │ Subagents (light)       │ claude-haiku-4-5    │ Cost efficiency for        │
    │                         │                     │ simple tasks               │
    ├─────────────────────────┼─────────────────────┼────────────────────────────┤
    │ Summarization           │ claude-haiku-4-5    │ Text summarization only;   │
    │                         │                     │ fast, cheap (no OpenAI key) │
    ├─────────────────────────┼─────────────────────┼────────────────────────────┤
    │ Router / Classifier     │ claude-haiku-4-5    │ Fast structured output     │
    └─────────────────────────┴─────────────────────┴────────────────────────────┘

    Note: The original plan recommends gpt-5.4-mini for summarization,
    but OPENAI_API_KEY is not available in this environment. We fall back
    to claude-haiku-4-5 which is also fast, cheap, and already configured.
    """

    orchestrator: ModelConfig = field(default_factory=lambda: ModelConfig(
        model_id="claude-sonnet-4-6",
        provider="anthropic",
        temperature=0.0,
        purpose="Main orchestrator — planning, routing, delegation decisions",
    ))

    subagent_heavy: ModelConfig = field(default_factory=lambda: ModelConfig(
        model_id="claude-sonnet-4-6",
        provider="anthropic",
        temperature=0.0,
        purpose="Heavy subagents — complex reasoning, code generation, research",
    ))

    subagent_light: ModelConfig = field(default_factory=lambda: ModelConfig(
        model_id="claude-haiku-4-5",
        provider="anthropic",
        temperature=0.0,
        purpose="Light subagents — simple lookups, formatting, classification",
    ))

    summarization: ModelConfig = field(default_factory=lambda: ModelConfig(
        model_id="claude-haiku-4-5",
        provider="anthropic",
        temperature=0.0,
        max_tokens=4096,
        purpose="Summarization — compress long context; fast and cost-efficient",
    ))

    router: ModelConfig = field(default_factory=lambda: ModelConfig(
        model_id="claude-haiku-4-5",
        provider="anthropic",
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
            if (
                provider == "anthropic"
                and not os.environ.get("ANTHROPIC_API_KEY")
            ):
                warnings.append(
                    "ANTHROPIC_API_KEY not set — Anthropic models unavailable"
                )
            elif (
                provider == "openai"
                and not os.environ.get("OPENAI_API_KEY")
            ):
                warnings.append(
                    "OPENAI_API_KEY not set — OpenAI models unavailable"
                )

        return warnings

    def to_langchain_model(self, config: ModelConfig) -> Any:
        """Convert a ModelConfig to a LangChain BaseChatModel instance.

        Example:
            selection = AgentModelSelection()
            main_model = selection.to_langchain_model(selection.orchestrator)
        """
        from langchain.chat_models import init_chat_model

        return init_chat_model(
            config.model_id,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )
