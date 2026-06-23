"""Tests for SkillLoader.

Plan: docs/guides/plans-phase-2/02-skill-loader.md §6 — Testing Plan
"""

from __future__ import annotations

from pathlib import Path

import pytest

from harness_agent.loaders.skill_loader import SkillInfo, SkillLoader

# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def temp_harness_dir(tmp_path: Path) -> Path:
    """Create a temporary .harness/ directory."""
    harness_dir = tmp_path / ".harness"
    harness_dir.mkdir()
    return harness_dir


@pytest.fixture
def skills_dir_with_files(temp_harness_dir: Path) -> Path:
    """Create .harness/skills/ with .md files and one non-.md file."""
    skills_dir = temp_harness_dir / "skills"
    skills_dir.mkdir()
    (skills_dir / "deploy-to-k8s.md").write_text("# Deploy to K8s\n\n...")
    (skills_dir / "db-migration.md").write_text("# DB Migration\n\n...")
    (skills_dir / "readme.txt").write_text("not a skill")  # Should be ignored
    return temp_harness_dir


# ── Tests ─────────────────────────────────────────────────────────────────


class TestSkillLoaderExists:
    """Tests for SkillLoader.exists property."""

    def test_no_skills_dir(self, temp_harness_dir: Path) -> None:
        """When skills/ does not exist, exists returns False."""
        loader = SkillLoader(temp_harness_dir)
        assert loader.exists is False

    def test_empty_skills_dir(self, temp_harness_dir: Path) -> None:
        """When skills/ exists but is empty, exists returns True."""
        skills_dir = temp_harness_dir / "skills"
        skills_dir.mkdir()
        loader = SkillLoader(temp_harness_dir)
        assert loader.exists is True


class TestSkillLoaderGetMemorySources:
    """Tests for SkillLoader.get_memory_sources()."""

    def test_no_skills_dir_returns_empty(self, temp_harness_dir: Path) -> None:
        """When skills/ does not exist, get_memory_sources() returns []."""
        loader = SkillLoader(temp_harness_dir)
        assert loader.get_memory_sources() == []

    def test_empty_skills_dir_returns_empty(
        self, temp_harness_dir: Path
    ) -> None:
        """When skills/ is empty, get_memory_sources() returns []."""
        (temp_harness_dir / "skills").mkdir()
        loader = SkillLoader(temp_harness_dir)
        assert loader.get_memory_sources() == []

    def test_single_skill(self, temp_harness_dir: Path) -> None:
        """A single .md file produces one source path."""
        skills_dir = temp_harness_dir / "skills"
        skills_dir.mkdir()
        (skills_dir / "my-skill.md").write_text("# My Skill\n\n...")
        loader = SkillLoader(temp_harness_dir)
        sources = loader.get_memory_sources()
        assert len(sources) == 1
        assert sources[0].endswith("my-skill.md")

    def test_multiple_skills_sorted(self, skills_dir_with_files: Path) -> None:
        """Multiple .md files are returned sorted."""
        loader = SkillLoader(skills_dir_with_files)
        sources = loader.get_memory_sources()
        assert len(sources) == 2
        # Should be alphabetically sorted
        assert "db-migration.md" in sources[0]
        assert "deploy-to-k8s.md" in sources[1]

    def test_ignores_non_md_files(
        self, skills_dir_with_files: Path
    ) -> None:
        """Only .md files are included — .txt files are ignored."""
        loader = SkillLoader(skills_dir_with_files)
        sources = loader.get_memory_sources()
        # Only the 2 .md files, not readme.txt
        assert len(sources) == 2
        for s in sources:
            assert s.endswith(".md")

    def test_absolute_paths(self, skills_dir_with_files: Path) -> None:
        """All returned paths are absolute."""
        loader = SkillLoader(skills_dir_with_files)
        sources = loader.get_memory_sources()
        for s in sources:
            assert Path(s).is_absolute()


class TestSkillLoaderListSkills:
    """Tests for SkillLoader.list_skills()."""

    def test_list_skills_returns_info(
        self, skills_dir_with_files: Path
    ) -> None:
        """list_skills() returns a list of SkillInfo objects."""
        loader = SkillLoader(skills_dir_with_files)
        skills = loader.list_skills()
        assert len(skills) == 2
        for skill in skills:
            assert isinstance(skill, SkillInfo)
            assert isinstance(skill.name, str)
            assert isinstance(skill.path, str)
            assert isinstance(skill.size, int)
            assert skill.size > 0

    def test_list_skills_empty_dir(self, temp_harness_dir: Path) -> None:
        """list_skills() on an empty directory returns []."""
        (temp_harness_dir / "skills").mkdir()
        loader = SkillLoader(temp_harness_dir)
        assert loader.list_skills() == []

    def test_list_skills_no_dir(self, temp_harness_dir: Path) -> None:
        """list_skills() when skills/ does not exist returns []."""
        loader = SkillLoader(temp_harness_dir)
        assert loader.list_skills() == []


class TestSkillInfo:
    """Tests for SkillInfo class."""

    def test_skill_name_from_stem(self) -> None:
        """Skill name comes from file stem — no transformation applied."""
        info = SkillInfo(name="deploy-to-k8s", path="/tmp/skills/deploy-to-k8s.md", size=100)
        assert info.name == "deploy-to-k8s"

    def test_repr_format(self) -> None:
        """SkillInfo.__repr__ shows name and size."""
        info = SkillInfo(name="my-skill", path="/tmp/skills/my-skill.md", size=42)
        assert repr(info) == "SkillInfo(name='my-skill', size=42)"

    def test_equality(self) -> None:
        """Two SkillInfo with same fields are equal."""
        a = SkillInfo(name="x", path="/p/x.md", size=10)
        b = SkillInfo(name="x", path="/p/x.md", size=10)
        assert a == b

    def test_inequality(self) -> None:
        """Two SkillInfo with different fields are not equal."""
        a = SkillInfo(name="x", path="/p/x.md", size=10)
        b = SkillInfo(name="y", path="/p/y.md", size=20)
        assert a != b

    def test_not_equal_to_other_type(self) -> None:
        """SkillInfo compared to a non-SkillInfo returns not equal."""
        info = SkillInfo(name="x", path="/p/x.md", size=10)
        assert info != "not a skill info"
