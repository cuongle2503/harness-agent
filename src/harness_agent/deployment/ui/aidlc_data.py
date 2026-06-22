"""AIDLC phase data parser.

Reads the phase plan markdown files from ``docs/guides/plans/`` and
extracts structured data (phase metadata, checklist items, status)
that the AIDLC Lifecycle UI consumes via the ``/aidlc`` JSON endpoint.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ChecklistItem:
    """A single checklist entry from a phase plan."""

    text: str
    checked: bool


@dataclass
class PhaseData:
    """Structured data for one AIDLC phase."""

    number: int
    title: str
    subtitle: str
    status: str  # "completed" | "in_progress" | "pending"
    objective: str
    outputs: str
    checklists: list[ChecklistItem] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    agents: list[str] = field(default_factory=list)
    mcp_tools: list[str] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)
    hooks: list[str] = field(default_factory=list)

    @property
    def total_checks(self) -> int:
        return len(self.checklists)

    @property
    def completed_checks(self) -> int:
        return sum(1 for c in self.checklists if c.checked)

    @property
    def progress_pct(self) -> float:
        if not self.checklists:
            # If no checklists, use status to infer
            status_map = {"completed": 100.0, "in_progress": 50.0, "pending": 0.0}
            return status_map.get(self.status, 0.0)
        return (self.completed_checks / self.total_checks) * 100

    def to_dict(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "title": self.title,
            "subtitle": self.subtitle,
            "status": self.status,
            "objective": self.objective,
            "outputs": self.outputs,
            "total_checks": self.total_checks,
            "completed_checks": self.completed_checks,
            "progress_pct": round(self.progress_pct, 1),
            "checklists": [
                {"text": c.text, "checked": c.checked} for c in self.checklists
            ],
            "capabilities": {
                "tools": self.tools,
                "skills": self.skills,
                "agents": self.agents,
                "mcp_tools": self.mcp_tools,
                "rules": self.rules,
                "hooks": self.hooks,
            },
        }


# ---------------------------------------------------------------------------
# Phase metadata — hand-curated from plan README + file headers
# ---------------------------------------------------------------------------

_PHASE_META: dict[int, dict[str, Any]] = {
    0: {
        "subtitle": "Foundation",
        "skills": ["update-config"],
        "agents": [],
        "mcp_tools": ["context7:resolve-library-id", "context7:query-docs"],
        "rules": ["development-workflow.md"],
        "hooks": ["SessionStart"],
    },
    1: {
        "subtitle": "Requirements",
        "skills": ["deep-research", "plan"],
        "agents": ["Explore"],
        "mcp_tools": ["codegraph:codegraph_explore", "codegraph:codegraph_search"],
        "rules": ["development-workflow.md"],
        "hooks": [],
    },
    2: {
        "subtitle": "Architecture",
        "skills": ["agent-harness-construction", "langchain-patterns", "plan"],
        "agents": ["harness-architect", "Explore"],
        "mcp_tools": [
            "codegraph:codegraph_explore",
            "codegraph:codegraph_callers",
            "codegraph:codegraph_callees",
            "codegraph:codegraph_impact",
        ],
        "rules": ["python/patterns.md", "development-workflow.md"],
        "hooks": [],
    },
    3: {
        "subtitle": "Implementation",
        "skills": [
            "agent-harness-construction",
            "langchain-patterns",
            "python-patterns",
            "tdd-workflow",
            "test",
            "code-review",
            "python-review",
            "simplify",
            "plan",
        ],
        "agents": ["python-reviewer", "code-reviewer"],
        "mcp_tools": [
            "codegraph:codegraph_explore",
            "codegraph:codegraph_search",
            "codegraph:codegraph_callers",
            "codegraph:codegraph_callees",
            "context7:resolve-library-id",
            "context7:query-docs",
        ],
        "rules": [
            "python/coding-style.md",
            "python/patterns.md",
            "python/testing.md",
            "development-workflow.md",
            "git-workflow.md",
        ],
        "hooks": ["PostToolUse"],
    },
    4: {
        "subtitle": "Testing",
        "skills": ["python-testing", "tdd-workflow", "test", "verify"],
        "agents": ["python-reviewer", "code-reviewer", "Explore"],
        "mcp_tools": [],
        "rules": ["python/testing.md", "development-workflow.md"],
        "hooks": ["Stop"],
    },
    5: {
        "subtitle": "Security",
        "skills": ["security-scan", "code-review"],
        "agents": ["security-reviewer"],
        "mcp_tools": [],
        "rules": [
            "security.md",
            "python/security.md",
            "common/security.md",
        ],
        "hooks": ["PreToolUse"],
    },
    6: {
        "subtitle": "Deployment",
        "skills": ["langchain-patterns", "verify", "update-config"],
        "agents": [],
        "mcp_tools": ["context7:resolve-library-id", "context7:query-docs"],
        "rules": ["development-workflow.md", "git-workflow.md"],
        "hooks": ["SessionStart"],
    },
    7: {
        "subtitle": "Monitoring",
        "skills": [],
        "agents": [],
        "mcp_tools": [],
        "rules": [],
        "hooks": [],
    },
    8: {
        "subtitle": "Maintenance",
        "skills": ["python-patterns", "code-review", "python-review", "simplify"],
        "agents": ["python-reviewer", "code-reviewer"],
        "mcp_tools": ["codegraph:codegraph_impact"],
        "rules": ["development-workflow.md"],
        "hooks": [],
    },
}

# Tool categories used across all phases
_SHARED_TOOLS = [
    "read_file", "write_file", "edit_file", "glob", "grep",
    "execute_command", "web_search",
]

_PHASE_TOOLS: dict[int, list[str]] = {
    0: ["read_file", "write_file", "execute_command"],
    1: ["read_file", "glob", "grep", "web_search"],
    2: ["read_file", "write_file", "glob", "grep"],
    3: _SHARED_TOOLS,
    4: ["read_file", "execute_command", "glob", "grep"],
    5: ["read_file", "glob", "grep"],
    6: ["read_file", "write_file", "execute_command"],
    7: ["read_file", "glob", "grep"],
    8: _SHARED_TOOLS,
}


def _resolve_plans_dir() -> Path:
    """Find the plans directory relative to this source file."""
    this_file = Path(__file__).resolve()
    # ui/aidlc_data.py → ui → deployment → harness_agent → src → project root
    project_root = this_file.parent.parent.parent.parent.parent
    return project_root / "docs" / "guides" / "plans"


def _parse_phase_file(path: Path) -> PhaseData | None:
    """Parse a single phase plan markdown file.

    Returns None if the file doesn't match the expected phase pattern.
    """
    m = re.match(r"0(\d)-", path.name)
    if not m:
        return None
    number = int(m.group(1))

    text = path.read_text(encoding="utf-8")

    # --- Title ---
    title_match = re.search(r"^# Phase \d+: (.+?) Plan", text, re.MULTILINE)
    title = title_match.group(1) if title_match else f"Phase {number}"

    # --- Objective ---
    obj_match = re.search(
        r"> \*\*Mục tiêu\*\*: (.+?)(?:\n>|$)", text
    )
    objective = obj_match.group(1).strip() if obj_match else ""

    # --- Status ---
    status_match = re.search(
        r"> \*\*Trạng thái\*\*: (.+?)(?:\n|$)", text
    )
    status_text = status_match.group(1).strip() if status_match else ""

    if "✅" in status_text or "Hoàn thành" in status_text:
        status = "completed"
    elif "🚧" in status_text or "In Progress" in status_text:
        status = "in_progress"
    else:
        # Infer from checklists: if no explicit status, compute
        status = "in_progress"  # default for phases without status marker

    # --- Outputs ---
    output_match = re.search(
        r"> \*\*Outputs?\*\*: (.+?)(?:\n>|\n\n|$)", text
    )
    outputs = output_match.group(1).strip() if output_match else ""

    # --- Checklists ---
    checklists: list[ChecklistItem] = []
    for line in text.splitlines():
        checked_match = re.match(r"^- \[x\] (.+)$", line.strip())
        unchecked_match = re.match(r"^- \[ \] (.+)$", line.strip())
        if checked_match:
            checklists.append(ChecklistItem(text=checked_match.group(1), checked=True))
        elif unchecked_match:
            checklists.append(
                ChecklistItem(text=unchecked_match.group(1), checked=False)
            )

    # --- Capabilities from curated metadata ---
    meta = _PHASE_META.get(number, {})
    subtitle = meta.get("subtitle", f"Phase {number}")
    skills = meta.get("skills", [])
    agents = meta.get("agents", [])
    mcp_tools = meta.get("mcp_tools", [])
    rules = meta.get("rules", [])
    hooks = meta.get("hooks", [])
    tools = _PHASE_TOOLS.get(number, [])

    return PhaseData(
        number=number,
        title=title,
        subtitle=subtitle,
        status=status,
        objective=objective,
        outputs=outputs,
        checklists=checklists,
        tools=tools,
        skills=skills,
        agents=agents,
        mcp_tools=mcp_tools,
        rules=rules,
        hooks=hooks,
    )


def parse_all_phases() -> list[PhaseData]:
    """Parse all phase plan files and return sorted list.

    Returns:
        List of PhaseData sorted by phase number (0-8).
    """
    plans_dir = _resolve_plans_dir()
    phases: list[PhaseData] = []

    for path in sorted(plans_dir.glob("0*-*.md")):
        phase = _parse_phase_file(path)
        if phase is not None:
            phases.append(phase)

    phases.sort(key=lambda p: p.number)
    return phases


def get_aidlc_summary() -> dict[str, Any]:
    """Build the full AIDLC summary for the ``/aidlc`` JSON endpoint.

    Returns a dict with all phases, aggregated stats, and capabilities overview.
    """
    phases = parse_all_phases()

    total_checklists = sum(p.total_checks for p in phases)
    completed_checklists = sum(p.completed_checks for p in phases)
    completed_phases = sum(1 for p in phases if p.status == "completed")
    in_progress_phases = sum(1 for p in phases if p.status == "in_progress")
    pending_phases = sum(1 for p in phases if p.status == "pending")

    # Aggregate unique capabilities across all phases
    all_skills = sorted(set(s for p in phases for s in p.skills))
    all_agents = sorted(set(a for p in phases for a in p.agents))
    all_mcp = sorted(set(m for p in phases for m in p.mcp_tools))
    all_rules = sorted(set(r for p in phases for r in p.rules))
    all_tools = sorted(set(t for p in phases for t in p.tools))
    all_hooks = sorted(set(h for p in phases for h in p.hooks))

    return {
        "phases": [p.to_dict() for p in phases],
        "summary": {
            "total_phases": len(phases),
            "completed_phases": completed_phases,
            "in_progress_phases": in_progress_phases,
            "pending_phases": pending_phases,
            "total_checklists": total_checklists,
            "completed_checklists": completed_checklists,
            "overall_progress_pct": round(
                (completed_checklists / total_checklists * 100) if total_checklists else 0, 1
            ),
        },
        "capabilities_overview": {
            "total_skills": len(all_skills),
            "total_agents": len(all_agents),
            "total_mcp_tools": len(all_mcp),
            "total_rules": len(all_rules),
            "total_tools": len(all_tools),
            "total_hooks": len(all_hooks),
            "skills": all_skills,
            "agents": all_agents,
            "mcp_tools": all_mcp,
            "rules": all_rules,
            "tools": all_tools,
            "hooks": all_hooks,
        },
    }
