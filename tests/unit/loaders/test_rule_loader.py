"""Tests for RuleLoader.

Plan: docs/guides/plans-phase-2/03-rule-loader.md §6 — Testing Plan
"""

from __future__ import annotations

from pathlib import Path

import pytest

from harness_agent.loaders.rule_loader import RuleInfo, RuleLoader

# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def temp_harness_dir(tmp_path: Path) -> Path:
    """Create a temporary .harness/ directory."""
    harness_dir = tmp_path / ".harness"
    harness_dir.mkdir()
    return harness_dir


@pytest.fixture
def rules_dir_flat(temp_harness_dir: Path) -> Path:
    """Create .harness/rules/ with flat .md files."""
    rules_dir = temp_harness_dir / "rules"
    rules_dir.mkdir()
    (rules_dir / "api-naming.md").write_text("# API Naming\n\n...")
    (rules_dir / "git-workflow.md").write_text("# Git Workflow\n\n...")
    (rules_dir / "security-policy.md").write_text("# Security Policy\n\n...")
    return temp_harness_dir


@pytest.fixture
def rules_dir_with_nesting(temp_harness_dir: Path) -> Path:
    """Create .harness/rules/ with nested subdirectories."""
    rules_dir = temp_harness_dir / "rules"
    rules_dir.mkdir()
    (rules_dir / "api-naming.md").write_text("# API Naming\n\n...")
    (rules_dir / "git-workflow.md").write_text("# Git Workflow\n\n...")

    # Nested under python/
    python_dir = rules_dir / "python"
    python_dir.mkdir()
    (python_dir / "coding-style.md").write_text("# Coding Style\n\n...")
    (python_dir / "testing.md").write_text("# Testing\n\n...")

    # Non-.md file (should be ignored)
    (python_dir / "notes.txt").write_text("not a rule")

    return temp_harness_dir


@pytest.fixture
def rules_dir_deeply_nested(temp_harness_dir: Path) -> Path:
    """Create .harness/rules/ with 3+ levels of nesting."""
    rules_dir = temp_harness_dir / "rules"
    rules_dir.mkdir()
    deep_dir = rules_dir / "a" / "b" / "c"
    deep_dir.mkdir(parents=True)
    (deep_dir / "deep-rule.md").write_text("# Deep Rule\n\n...")
    return temp_harness_dir


# ── Tests ─────────────────────────────────────────────────────────────────


class TestRuleLoaderExists:
    """Tests for RuleLoader.exists property."""

    def test_no_rules_dir(self, temp_harness_dir: Path) -> None:
        """When rules/ does not exist, exists returns False."""
        loader = RuleLoader(temp_harness_dir)
        assert loader.exists is False

    def test_empty_rules_dir(self, temp_harness_dir: Path) -> None:
        """When rules/ exists but is empty, exists returns True."""
        rules_dir = temp_harness_dir / "rules"
        rules_dir.mkdir()
        loader = RuleLoader(temp_harness_dir)
        assert loader.exists is True


class TestRuleLoaderGetMemorySources:
    """Tests for RuleLoader.get_memory_sources()."""

    def test_no_rules_dir_returns_empty(self, temp_harness_dir: Path) -> None:
        """When rules/ does not exist, get_memory_sources() returns []."""
        loader = RuleLoader(temp_harness_dir)
        assert loader.get_memory_sources() == []

    def test_empty_rules_dir_returns_empty(
        self, temp_harness_dir: Path
    ) -> None:
        """When rules/ is empty, get_memory_sources() returns []."""
        (temp_harness_dir / "rules").mkdir()
        loader = RuleLoader(temp_harness_dir)
        assert loader.get_memory_sources() == []

    def test_single_rule(self, temp_harness_dir: Path) -> None:
        """A single .md file produces one source path."""
        rules_dir = temp_harness_dir / "rules"
        rules_dir.mkdir()
        (rules_dir / "my-rule.md").write_text("# My Rule\n\n...")
        loader = RuleLoader(temp_harness_dir)
        sources = loader.get_memory_sources()
        assert len(sources) == 1
        assert sources[0].endswith("my-rule.md")

    def test_multiple_rules_flat(self, rules_dir_flat: Path) -> None:
        """Multiple flat .md files are returned sorted."""
        loader = RuleLoader(rules_dir_flat)
        sources = loader.get_memory_sources()
        assert len(sources) == 3
        # Should be alphabetically sorted
        assert "api-naming.md" in sources[0]
        assert "git-workflow.md" in sources[1]
        assert "security-policy.md" in sources[2]

    def test_nested_rules(self, rules_dir_with_nesting: Path) -> None:
        """Files in subdirectories are all loaded via rglob."""
        loader = RuleLoader(rules_dir_with_nesting)
        sources = loader.get_memory_sources()
        assert len(sources) == 4  # 2 flat + 2 nested
        # Flat files come first (sorted)
        assert "api-naming.md" in sources[0]
        assert "git-workflow.md" in sources[1]
        # Nested files follow
        assert "coding-style.md" in sources[2]
        assert "testing.md" in sources[3]

    def test_ignores_non_md_files(
        self, rules_dir_with_nesting: Path
    ) -> None:
        """Only .md files are included — .txt files are ignored."""
        loader = RuleLoader(rules_dir_with_nesting)
        sources = loader.get_memory_sources()
        # Only the 4 .md files, not notes.txt
        assert len(sources) == 4
        for s in sources:
            assert s.endswith(".md")

    def test_sorted_output(self, rules_dir_flat: Path) -> None:
        """Sources are returned in sorted order."""
        loader = RuleLoader(rules_dir_flat)
        sources = loader.get_memory_sources()
        assert sources == sorted(sources)

    def test_absolute_paths(self, rules_dir_with_nesting: Path) -> None:
        """All returned paths are absolute."""
        loader = RuleLoader(rules_dir_with_nesting)
        sources = loader.get_memory_sources()
        for s in sources:
            assert Path(s).is_absolute()

    def test_deeply_nested_rules(
        self, rules_dir_deeply_nested: Path
    ) -> None:
        """Files at 3+ levels deep are still loaded."""
        loader = RuleLoader(rules_dir_deeply_nested)
        sources = loader.get_memory_sources()
        assert len(sources) == 1
        assert "deep-rule.md" in sources[0]


class TestRuleLoaderListRules:
    """Tests for RuleLoader.list_rules()."""

    def test_list_rules_returns_info(
        self, rules_dir_with_nesting: Path
    ) -> None:
        """list_rules() returns a list of RuleInfo objects."""
        loader = RuleLoader(rules_dir_with_nesting)
        rules = loader.list_rules()
        assert len(rules) == 4
        for rule in rules:
            assert isinstance(rule, RuleInfo)
            assert isinstance(rule.name, str)
            assert isinstance(rule.relative_path, str)
            assert isinstance(rule.size, int)
            assert rule.size > 0

    def test_list_rules_empty_dir(self, temp_harness_dir: Path) -> None:
        """list_rules() on an empty directory returns []."""
        (temp_harness_dir / "rules").mkdir()
        loader = RuleLoader(temp_harness_dir)
        assert loader.list_rules() == []

    def test_list_rules_no_dir(self, temp_harness_dir: Path) -> None:
        """list_rules() when rules/ does not exist returns []."""
        loader = RuleLoader(temp_harness_dir)
        assert loader.list_rules() == []

    def test_list_rules_shows_nested_path(
        self, rules_dir_with_nesting: Path
    ) -> None:
        """Nested files have correct relative_path."""
        loader = RuleLoader(rules_dir_with_nesting)
        rules = loader.list_rules()
        # Find the nested coding-style rule
        coding_rule = next(
            r for r in rules if r.name == "coding-style"
        )
        assert coding_rule.relative_path == "python/coding-style.md"
        # Find the nested testing rule
        testing_rule = next(
            r for r in rules if r.name == "testing"
        )
        assert testing_rule.relative_path == "python/testing.md"


class TestRuleInfo:
    """Tests for RuleInfo class."""

    def test_rule_name_from_stem(self) -> None:
        """Rule name comes from file stem — no transformation applied."""
        info = RuleInfo(
            name="api-naming", relative_path="api-naming.md", size=100
        )
        assert info.name == "api-naming"

    def test_repr_format(self) -> None:
        """RuleInfo.__repr__ shows name, path, and size."""
        info = RuleInfo(
            name="my-rule", relative_path="python/my-rule.md", size=42
        )
        assert repr(info) == (
            "RuleInfo(name='my-rule', path='python/my-rule.md', size=42)"
        )

    def test_equality(self) -> None:
        """Two RuleInfo with same fields are equal."""
        a = RuleInfo(name="x", relative_path="x.md", size=10)
        b = RuleInfo(name="x", relative_path="x.md", size=10)
        assert a == b

    def test_inequality(self) -> None:
        """Two RuleInfo with different fields are not equal."""
        a = RuleInfo(name="x", relative_path="x.md", size=10)
        b = RuleInfo(name="y", relative_path="y.md", size=20)
        assert a != b

    def test_not_equal_to_other_type(self) -> None:
        """RuleInfo compared to a non-RuleInfo returns not equal."""
        info = RuleInfo(name="x", relative_path="x.md", size=10)
        assert info != "not a rule info"
