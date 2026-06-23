"""Tests for the fallback task delegation tool."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from harness_agent.tools.task_tool import TaskTool, create_task_tool


@pytest.fixture
def sample_subagent_defs() -> list[dict]:
    return [
        {
            "name": "researcher",
            "description": "Web research specialist",
            "system_prompt": "You are a research assistant.",
            "tools": [],
            "model": "deepseek-v4-flash",
            "middleware": [],
        },
        {
            "name": "coder",
            "description": "Code generation specialist",
            "system_prompt": "You are a code assistant.",
            "tools": [],
            "model": "deepseek-v4-pro",
            "middleware": [],
        },
    ]


@pytest.fixture
def mock_llm() -> MagicMock:
    llm = MagicMock()
    llm.bind_tools.return_value = llm
    response = MagicMock()
    response.content = "Research result: found 3 papers"
    response.tool_calls = None
    llm.invoke.return_value = response
    return llm


class TestTaskToolCreation:
    """Tests for create_task_tool factory."""

    def test_create_task_tool_returns_base_tool(
        self, sample_subagent_defs: list[dict], mock_llm: MagicMock
    ) -> None:
        tool = create_task_tool(sample_subagent_defs, mock_llm)
        assert tool.name == "task"
        assert "subagent" in tool.description.lower()

    def test_task_tool_has_correct_schema(
        self, sample_subagent_defs: list[dict], mock_llm: MagicMock
    ) -> None:
        tool = create_task_tool(sample_subagent_defs, mock_llm)
        schema = tool.args_schema.model_json_schema()
        assert "subagent_type" in schema["properties"]
        assert "task" in schema["properties"]

    def test_create_task_tool_with_empty_defs(self, mock_llm: MagicMock) -> None:
        tool = create_task_tool([], mock_llm)
        assert tool.name == "task"
        assert isinstance(tool, TaskTool)


class TestTaskToolExecution:
    """Tests for task tool invocation."""

    def test_run_delegates_to_subagent(
        self, sample_subagent_defs: list[dict], mock_llm: MagicMock
    ) -> None:
        tool = create_task_tool(sample_subagent_defs, mock_llm)
        result = tool._run(subagent_type="researcher", task="Find papers on AI")
        assert "Research result" in result

    def test_run_unknown_subagent_returns_error(
        self, sample_subagent_defs: list[dict], mock_llm: MagicMock
    ) -> None:
        tool = create_task_tool(sample_subagent_defs, mock_llm)
        result = tool._run(subagent_type="nonexistent", task="Do something")
        assert "Unknown subagent 'nonexistent'" in result
        assert "researcher" in result
        assert "coder" in result

    def test_run_handles_subagent_error(
        self, sample_subagent_defs: list[dict], mock_llm: MagicMock
    ) -> None:
        mock_llm.invoke.side_effect = RuntimeError("API timeout")
        tool = create_task_tool(sample_subagent_defs, mock_llm)
        result = tool._run(subagent_type="researcher", task="Find papers")
        assert "Subagent error" in result

    def test_run_with_no_response(
        self, sample_subagent_defs: list[dict], mock_llm: MagicMock
    ) -> None:
        mock_llm.invoke.return_value = MagicMock(content="", tool_calls=None)
        tool = create_task_tool(sample_subagent_defs, mock_llm)
        result = tool._run(subagent_type="researcher", task="Find papers")
        assert isinstance(result, str)


class TestTaskToolAsync:
    """Tests for async task tool invocation."""

    @pytest.mark.asyncio
    async def test_arun_delegates_to_subagent(
        self, sample_subagent_defs: list[dict], mock_llm: MagicMock
    ) -> None:
        response = MagicMock()
        response.content = "Async research result"
        response.tool_calls = None
        mock_llm.ainvoke = MagicMock(return_value=response)

        # Patch ainvoke to be a coroutine
        async def fake_ainvoke(*args, **kwargs):
            return response

        mock_llm.ainvoke = fake_ainvoke
        # Also need bind_tools to return the mock
        mock_llm.bind_tools.return_value = mock_llm

        tool = create_task_tool(sample_subagent_defs, mock_llm)
        result = await tool._arun(subagent_type="researcher", task="Find papers")
        assert "Async research result" in result

    @pytest.mark.asyncio
    async def test_arun_unknown_subagent(
        self, sample_subagent_defs: list[dict], mock_llm: MagicMock
    ) -> None:
        tool = create_task_tool(sample_subagent_defs, mock_llm)
        result = await tool._arun(subagent_type="ghost", task="Do X")
        assert "Unknown subagent 'ghost'" in result


class TestTaskToolSubagentLookup:
    """Tests for internal subagent resolution."""

    def test_find_subagent_by_name(
        self, sample_subagent_defs: list[dict], mock_llm: MagicMock
    ) -> None:
        tool = TaskTool(subagent_defs=sample_subagent_defs, llm=mock_llm)
        found = tool._find_subagent("coder")
        assert found is not None
        assert found["name"] == "coder"

    def test_find_subagent_not_found(
        self, sample_subagent_defs: list[dict], mock_llm: MagicMock
    ) -> None:
        tool = TaskTool(subagent_defs=sample_subagent_defs, llm=mock_llm)
        assert tool._find_subagent("unknown") is None

    def test_create_subagent_uses_system_prompt(
        self, sample_subagent_defs: list[dict], mock_llm: MagicMock
    ) -> None:
        tool = TaskTool(subagent_defs=sample_subagent_defs, llm=mock_llm)
        agent = tool._create_subagent(sample_subagent_defs[0])
        assert agent.system_prompt == "You are a research assistant."
