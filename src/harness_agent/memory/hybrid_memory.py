"""HybridMemory — key-value + vector store + conversation buffer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class MemoryItem:
    """A single memory item.

    Attributes:
        key: Unique identifier for the memory item.
        value: The stored value (any type).
        embedding: Optional vector embedding for similarity search.
    """

    key: str
    value: Any
    embedding: list[float] | None = None


class HybridMemory:
    """Hybrid memory: key-value store + vector store + conversation buffer.

    Provides simple key-value storage with optional vector embeddings
    for similarity-based retrieval. The vector retrieval is simplified
    in Phase 3 (most-recent-k); full vector similarity is deferred to
    Phase 4+.
    """

    def __init__(self) -> None:
        self._kv: dict[str, MemoryItem] = {}
        self._vector_items: list[MemoryItem] = []

    def store(
        self, key: str, value: Any, embedding: list[float] | None = None
    ) -> None:
        """Store a value with optional vector embedding.

        Args:
            key: Unique identifier.
            value: The value to store.
            embedding: Optional float list for vector similarity search.
        """
        item = MemoryItem(key=key, value=value, embedding=embedding)
        self._kv[key] = item
        if embedding is not None:
            self._vector_items.append(item)

    def get(self, key: str) -> Any | None:
        """Retrieve a value by key.

        Args:
            key: The key to look up.

        Returns:
            The stored value, or None if not found.
        """
        item = self._kv.get(key)
        return item.value if item else None

    def retrieve(self, query: str, k: int = 5) -> list[MemoryItem]:
        """Retrieve items by vector similarity.

        Simplified Phase 3 implementation: returns the k most recent
        items with embeddings. Full cosine-similarity retrieval is
        deferred to Phase 4+.

        Args:
            query: Search query (unused in simplified retrieval).
            k: Maximum number of items to return.

        Returns:
            Up to k MemoryItem objects with embeddings.
        """
        if k <= 0:
            return []
        return self._vector_items[-k:]

    def delete(self, key: str) -> None:
        """Delete a memory item by key.

        Args:
            key: The key to delete.
        """
        item = self._kv.pop(key, None)
        if item and item.embedding is not None:
            self._vector_items = [
                i for i in self._vector_items if i.key != key
            ]

    def clear(self) -> None:
        """Clear all stored data."""
        self._kv.clear()
        self._vector_items.clear()

    def get_context(self, session_id: str) -> dict[str, Any]:
        """Get session context summary.

        Args:
            session_id: The session identifier.

        Returns:
            A dict with session_id and list of stored keys.
        """
        return {
            "session_id": session_id,
            "items": list(self._kv.keys()),
        }

    def __len__(self) -> int:
        return len(self._kv)
