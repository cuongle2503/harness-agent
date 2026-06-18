"""Tests for ModelConfig and AgentModelSelection."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from harness_agent.config import AgentModelSelection, ModelConfig


class TestModelConfig:
    """Tests for the ModelConfig dataclass."""

    def test_default_values(self) -> None:
        """ModelConfig has correct defaults for optional fields."""
        config = ModelConfig(model_id="deepseek-v4-flash", provider="deepseek")
        assert config.model_id == "deepseek-v4-flash"
        assert config.provider == "deepseek"
        assert config.temperature == 0.0
        assert config.max_tokens is None
        assert config.purpose == ""

    def test_custom_temperature(self) -> None:
        """Temperature can be overridden."""
        config = ModelConfig(
            model_id="deepseek-v4-pro",
            provider="deepseek",
            temperature=0.7,
        )
        assert config.temperature == 0.7

    def test_custom_max_tokens(self) -> None:
        """max_tokens can be set explicitly."""
        config = ModelConfig(
            model_id="deepseek-v4-pro",
            provider="deepseek",
            max_tokens=4096,
        )
        assert config.max_tokens == 4096

    def test_purpose_is_stored(self) -> None:
        """Purpose field records the model's role."""
        config = ModelConfig(
            model_id="deepseek-v4-flash",
            provider="deepseek",
            purpose="Main orchestrator",
        )
        assert config.purpose == "Main orchestrator"

    def test_equality(self) -> None:
        """Two ModelConfigs with same fields are equal."""
        a = ModelConfig(model_id="x", provider="p")
        b = ModelConfig(model_id="x", provider="p")
        assert a == b

    def test_inequality(self) -> None:
        """Two ModelConfigs with different fields are not equal."""
        a = ModelConfig(model_id="x", provider="p")
        b = ModelConfig(model_id="y", provider="p")
        assert a != b


class TestAgentModelSelectionDefaults:
    """Tests for AgentModelSelection default model configurations."""

    @pytest.fixture
    def selection(self) -> AgentModelSelection:
        return AgentModelSelection()

    def test_orchestrator_uses_v4_flash(self, selection: AgentModelSelection) -> None:
        assert selection.orchestrator.model_id == "deepseek-v4-flash"
        assert selection.orchestrator.temperature == 0.0
        assert "orchestrator" in selection.orchestrator.purpose.lower()

    def test_subagent_heavy_uses_v4_pro(self, selection: AgentModelSelection) -> None:
        assert selection.subagent_heavy.model_id == "deepseek-v4-pro"
        assert selection.subagent_heavy.temperature == 0.0

    def test_subagent_light_uses_v4_flash(self, selection: AgentModelSelection) -> None:
        assert selection.subagent_light.model_id == "deepseek-v4-flash"

    def test_summarization_has_max_tokens(self, selection: AgentModelSelection) -> None:
        assert selection.summarization.max_tokens == 4096
        assert "summar" in selection.summarization.purpose.lower()

    def test_router_has_low_max_tokens(self, selection: AgentModelSelection) -> None:
        assert selection.router.max_tokens == 1024
        assert "router" in selection.router.purpose.lower()


class TestAgentModelSelectionAllModels:
    """Tests for the all_models property."""

    def test_all_models_returns_five_configs(self) -> None:
        selection = AgentModelSelection()
        result = selection.all_models
        assert len(result) == 5

    def test_all_models_are_model_configs(self) -> None:
        selection = AgentModelSelection()
        for model in selection.all_models:
            assert isinstance(model, ModelConfig)

    @pytest.mark.parametrize("attr_name", [
        "orchestrator",
        "subagent_heavy",
        "subagent_light",
        "summarization",
        "router",
    ])
    def test_all_models_includes_each_config(
        self, attr_name: str
    ) -> None:
        selection = AgentModelSelection()
        expected = getattr(selection, attr_name)
        assert expected in selection.all_models


class TestAgentModelSelectionValidate:
    """Tests for the validate() method."""

    def test_validate_with_key_set_returns_empty_warnings(self) -> None:
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-test"}):
            selection = AgentModelSelection()
            warnings = selection.validate()
            assert warnings == []

    def test_validate_without_key_returns_warning(self) -> None:
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""}, clear=False),
        ):
            # Temporarily clear the key
            pass

        # Actually test with env cleared
        original = os.environ.get("DEEPSEEK_API_KEY")
        if "DEEPSEEK_API_KEY" in os.environ:
            del os.environ["DEEPSEEK_API_KEY"]

        try:
            selection = AgentModelSelection()
            warnings = selection.validate()
            assert len(warnings) >= 1
            assert any("DEEPSEEK_API_KEY" in w for w in warnings)
        finally:
            if original is not None:
                os.environ["DEEPSEEK_API_KEY"] = original


class TestAgentModelSelectionToLangchainModel:
    """Tests for to_langchain_model()."""

    def test_returns_chat_deepseek_instance(self) -> None:
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-test-dummy"}):
            selection = AgentModelSelection()
            model = selection.to_langchain_model(selection.orchestrator)
            from langchain_deepseek import ChatDeepSeek

            assert isinstance(model, ChatDeepSeek)

    def test_model_id_passed_through(self) -> None:
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-test-dummy"}):
            selection = AgentModelSelection()
            model = selection.to_langchain_model(selection.orchestrator)
            assert model.model_name == "deepseek-v4-flash"  # type: ignore[attr-defined]

    def test_max_tokens_passed_when_set(self) -> None:
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-test-dummy"}):
            selection = AgentModelSelection()
            model = selection.to_langchain_model(selection.summarization)
            assert model.max_tokens == 4096  # type: ignore[attr-defined]

    def test_max_tokens_omitted_when_none(self) -> None:
        """When max_tokens is None, ChatDeepSeek uses default."""
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-test-dummy"}):
            config = ModelConfig(model_id="test", provider="deepseek")
            selection = AgentModelSelection()
            model = selection.to_langchain_model(config)
            assert model.max_tokens is None  # type: ignore[attr-defined]
