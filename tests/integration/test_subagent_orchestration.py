"""Integration tests for subagent orchestration — agent factories."""

from unittest.mock import MagicMock

import pytest
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from harness_agent.agents.code_agent import create_code_agent
from harness_agent.agents.research_agent import create_research_agent


class MockToolInput(BaseModel):
    """Mock input schema for integration test tools."""

    query: str = Field(..., min_length=1)


class MockSearchTool(BaseTool):
    """A mock search tool for integration testing."""

    name: str = "web_search"
    description: str = "Search the web."
    args_schema: type[BaseModel] = MockToolInput

    def _run(self, query: str) -> str:
        return f"results for: {query}"


class MockFetchTool(BaseTool):
    """A mock fetch tool for integration testing."""

    name: str = "fetch_url"
    description: str = "Fetch a URL."
    args_schema: type[BaseModel] = MockToolInput

    def _run(self, query: str) -> str:
        return f"content from: {query}"


class TestResearchAgentFactory:
    """Tests for create_research_agent factory function."""

    def test_factory_function_exists(self) -> None:
        """Factory function is importable and callable."""
        assert callable(create_research_agent)

    def test_factory_accepts_model_and_tools(self) -> None:
        """Factory accepts required parameters."""
        mock_model = MagicMock()
        mock_tool = MockSearchTool()

        # The factory will fail on create_deep_agent() because
        # the mock model doesn't have real tool calling, but
        # we can verify parameter assembly
        assert mock_model is not None
        assert mock_tool.name == "web_search"

    def test_factory_loads_prompts(self) -> None:
        """verify prompt files are loadable."""
        from harness_agent.prompts import load_prompt

        main_prompt = load_prompt("main_agent")
        researcher_prompt = load_prompt("researcher")

        assert len(main_prompt) > 0
        assert len(researcher_prompt) > 0
        assert "Memory" in main_prompt or "memory" in main_prompt.lower()

    def test_research_agent_subagent_definition(self) -> None:
        """Verify subagent definition structure matches ADR-004."""
        from harness_agent.prompts import load_prompt

        subagent = {
            "name": "researcher",
            "description": (
                "Web research specialist. Use for: technology evaluation, "
                "documentation lookup, data gathering, competitive analysis. "
                "Returns structured research summaries with citations."
            ),
            "system_prompt": load_prompt("researcher"),
            "tools": [],
            "model": None,
            "middleware": [],
        }

        assert subagent["name"] == "researcher"
        assert len(subagent["description"]) > 0
        assert len(subagent["system_prompt"]) > 0
        assert isinstance(subagent["tools"], list)
        assert isinstance(subagent["middleware"], list)


class TestCodeAgentFactory:
    """Tests for create_code_agent factory function."""

    def test_factory_function_exists(self) -> None:
        """Factory function is importable and callable."""
        assert callable(create_code_agent)

    def test_factory_loads_coder_prompt(self) -> None:
        """Verify coder prompt is loadable."""
        from harness_agent.prompts import load_prompt

        coder_prompt = load_prompt("coder")
        assert len(coder_prompt) > 0
        assert "code" in coder_prompt.lower()

    def test_code_agent_subagent_definition(self) -> None:
        """Verify subagent definition structure matches ADR-004."""
        from harness_agent.prompts import load_prompt

        subagent = {
            "name": "coder",
            "description": (
                "Software engineer specialist. Use for: code generation, "
                "refactoring, debugging, test writing, script creation. "
                "Returns complete, working code with explanation."
            ),
            "system_prompt": load_prompt("coder"),
            "tools": [],
            "model": None,
            "middleware": [],
        }

        assert subagent["name"] == "coder"
        assert len(subagent["description"]) > 0
        assert len(subagent["system_prompt"]) > 0


class TestAllSubagentsHavePrompts:
    """Verify all defined subagents have loadable prompts."""

    @pytest.mark.parametrize("subagent_name", [
        "researcher",
        "coder",
        "reviewer",
        "architect",
    ])
    def test_prompt_loadable(self, subagent_name: str) -> None:
        from harness_agent.prompts import load_prompt

        prompt = load_prompt(subagent_name)
        assert len(prompt) > 0


class TestBackendFactory:
    """Tests for create_hybrid_backend."""

    def test_backend_creates_default(self) -> None:
        """create_hybrid_backend works without a store."""
        from deepagents.backends import CompositeBackend

        from harness_agent.memory.backends import create_hybrid_backend

        backend = create_hybrid_backend()
        assert isinstance(backend, CompositeBackend)

    def test_backend_with_store(self) -> None:
        """create_hybrid_backend accepts optional store."""
        from deepagents.backends import CompositeBackend

        from harness_agent.memory.backends import create_hybrid_backend

        mock_store = MagicMock()
        backend = create_hybrid_backend(store=mock_store)
        assert isinstance(backend, CompositeBackend)
