"""Backend factory for hybrid memory storage.

Creates the CompositeBackend configuration per ADR-003.
"""

from __future__ import annotations

from typing import Any

from deepagents.backends import (
    CompositeBackend,
    FilesystemBackend,
    StateBackend,
    StoreBackend,
)


def create_hybrid_backend(
    store: Any = None,
    output_dir: str = "/data/agent-output",
) -> CompositeBackend:
    """Create the hybrid backend per ADR-003.

    Routes:
        /memories/*  → StoreBackend (persistent, user-scoped)
        /output/*    → FilesystemBackend (real disk output)
        /* (default) → StateBackend (ephemeral session)

    Args:
        store: A BaseStore instance for persistent storage (optional).
        output_dir: Root directory for FilesystemBackend output.

    Returns:
        A configured CompositeBackend instance.
    """
    routes: dict[str, Any] = {}
    if store is not None:
        routes["/memories/"] = StoreBackend(
            store=store,
            file_format="v2",
        )
    routes["/output/"] = FilesystemBackend(root_dir=output_dir, virtual_mode=True)

    return CompositeBackend(
        default=StateBackend(),
        routes=routes,
    )
