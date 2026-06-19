"""Security package for the agent harness.

Phase 5 security modules:
- sandbox: Docker sandbox configuration
- subprocess_safety: Safe subprocess execution
- hitl: Human-in-the-Loop middleware
- pii: PII detection middleware
- permissions: File system permission boundaries
"""

from harness_agent.security.hitl import (
    HITLApprovalDeniedError,
    HumanInTheLoopMiddleware,
)
from harness_agent.security.permissions import PermissionBoundary
from harness_agent.security.pii import PIIMiddleware
from harness_agent.security.sandbox import SandboxConfig
from harness_agent.security.subprocess_safety import safe_run

__all__ = [
    "HITLApprovalDeniedError",
    "HumanInTheLoopMiddleware",
    "PIIMiddleware",
    "PermissionBoundary",
    "SandboxConfig",
    "safe_run",
]
