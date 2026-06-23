"""Tests for the skill invocation tool."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from harness_agent.tools.skill_tool import SkillTool, create_skill_tool


@pytest.fixture
def mock_skill_loader(tmp_path: Path) -> MagicMock:
    """Create a mock SkillLoader with two skill files on disk."""
    from harness_agent.loaders.skill_loader import SkillInfo

    skill_file_1 = tmp_path / "deploy.md"
    skill_file_1.write_text("# Deploy\n\nStep 1: Build\nStep 2: Push\n")

    skill_file_2 = tmp_path / "review.md"
    skill_file_2.write_text("# Code Review\n\nCheck style, security, tests.\n")

    loader = MagicMock()
    loader.list_skills.return_value = [
        SkillInfo(
            name="Deploy",
            path=str(skill_file_1),
            size=skill_file_1.stat().st_size,
            description="Deploy to production",
        ),
        SkillInfo(
            name="Code Review",
            path=str(skill_file_2),
            size=skill_file_2.stat().st_size,
            description="Review code for quality",
        ),
    ]
    return loader


@pytest.fixture
def empty_skill_loader() -> MagicMock:
    loader = MagicMock()
    loader.list_skills.return_value = []
    return loader


class TestSkillToolCreation:
    """Tests for create_skill_tool factory."""

    def test_create_skill_tool_returns_base_tool(
        self, mock_skill_loader: MagicMock
    ) -> None:
        tool = create_skill_tool(mock_skill_loader)
        assert tool.name == "use_skill"
        assert "skill" in tool.description.lower()

    def test_skill_tool_has_correct_schema(
        self, mock_skill_loader: MagicMock
    ) -> None:
        tool = create_skill_tool(mock_skill_loader)
        schema = tool.args_schema.model_json_schema()
        assert "skill_name" in schema["properties"]
        assert "context" in schema["properties"]


class TestSkillToolExecution:
    """Tests for skill tool invocation."""

    def test_run_returns_skill_content(
        self, mock_skill_loader: MagicMock
    ) -> None:
        tool = create_skill_tool(mock_skill_loader)
        result = tool._run(skill_name="Deploy")
        assert "# Skill: Deploy" in result
        assert "Step 1: Build" in result
        assert "Step 2: Push" in result

    def test_run_with_context(
        self, mock_skill_loader: MagicMock
    ) -> None:
        tool = create_skill_tool(mock_skill_loader)
        result = tool._run(skill_name="Deploy", context="deploy the api service")
        assert "Task context" in result
        assert "deploy the api service" in result

    def test_run_case_insensitive(
        self, mock_skill_loader: MagicMock
    ) -> None:
        tool = create_skill_tool(mock_skill_loader)
        result = tool._run(skill_name="deploy")
        assert "# Skill: Deploy" in result

    def test_run_partial_match(
        self, mock_skill_loader: MagicMock
    ) -> None:
        tool = create_skill_tool(mock_skill_loader)
        result = tool._run(skill_name="Review")
        assert "# Skill: Code Review" in result

    def test_run_unknown_skill(
        self, mock_skill_loader: MagicMock
    ) -> None:
        tool = create_skill_tool(mock_skill_loader)
        result = tool._run(skill_name="nonexistent")
        assert "Unknown skill 'nonexistent'" in result
        assert "Deploy" in result
        assert "Code Review" in result

    def test_run_no_skills_available(
        self, empty_skill_loader: MagicMock
    ) -> None:
        tool = create_skill_tool(empty_skill_loader)
        result = tool._run(skill_name="anything")
        assert "No skills available" in result

    def test_run_no_loader(self) -> None:
        tool = SkillTool(skill_loader=None)
        result = tool._run(skill_name="test")
        assert "No skill loader configured" in result


class TestSkillToolAsync:
    """Tests for async skill tool invocation."""

    @pytest.mark.asyncio
    async def test_arun_returns_skill_content(
        self, mock_skill_loader: MagicMock
    ) -> None:
        tool = create_skill_tool(mock_skill_loader)
        result = await tool._arun(skill_name="Deploy")
        assert "# Skill: Deploy" in result

    @pytest.mark.asyncio
    async def test_arun_unknown_skill(
        self, mock_skill_loader: MagicMock
    ) -> None:
        tool = create_skill_tool(mock_skill_loader)
        result = await tool._arun(skill_name="ghost")
        assert "Unknown skill 'ghost'" in result
