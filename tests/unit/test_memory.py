"""Tests for HybridMemory."""


from harness_agent.memory.hybrid_memory import HybridMemory, MemoryItem


class TestMemoryItem:
    """Tests for the MemoryItem dataclass."""

    def test_create_with_key_value(self) -> None:
        item = MemoryItem(key="k", value="v")
        assert item.key == "k"
        assert item.value == "v"
        assert item.embedding is None

    def test_create_with_embedding(self) -> None:
        emb = [0.1, 0.2, 0.3]
        item = MemoryItem(key="k", value="v", embedding=emb)
        assert item.embedding == emb


class TestHybridMemoryStoreAndGet:
    """Tests for store() and get()."""

    def test_store_and_retrieve_by_key(
        self, hybrid_memory: HybridMemory
    ) -> None:
        hybrid_memory.store("key1", "value1")
        assert hybrid_memory.get("key1") == "value1"

    def test_get_missing_returns_none(
        self, hybrid_memory: HybridMemory
    ) -> None:
        assert hybrid_memory.get("nonexistent") is None

    def test_store_multiple_values(
        self, hybrid_memory: HybridMemory
    ) -> None:
        hybrid_memory.store("a", 1)
        hybrid_memory.store("b", 2)
        hybrid_memory.store("c", 3)
        assert hybrid_memory.get("a") == 1
        assert hybrid_memory.get("b") == 2
        assert hybrid_memory.get("c") == 3

    def test_store_overwrites_existing(
        self, hybrid_memory: HybridMemory
    ) -> None:
        hybrid_memory.store("key", "old")
        hybrid_memory.store("key", "new")
        assert hybrid_memory.get("key") == "new"


class TestHybridMemoryVectorRetrieval:
    """Tests for vector-based retrieval."""

    def test_retrieve_no_embeddings_returns_empty(
        self, hybrid_memory: HybridMemory
    ) -> None:
        hybrid_memory.store("k1", "v1")  # no embedding
        results = hybrid_memory.retrieve("query", k=5)
        assert results == []

    def test_retrieve_with_embeddings_returns_items(
        self, hybrid_memory_with_data: HybridMemory
    ) -> None:
        # hybrid_memory_with_data has 3 items with embeddings
        results = hybrid_memory_with_data.retrieve("query", k=2)
        assert len(results) == 2
        for item in results:
            assert isinstance(item, MemoryItem)

    def test_retrieve_returns_most_recent(
        self, hybrid_memory: HybridMemory
    ) -> None:
        hybrid_memory.store("k1", "v1", embedding=[0.1])
        hybrid_memory.store("k2", "v2", embedding=[0.2])
        hybrid_memory.store("k3", "v3", embedding=[0.3])
        results = hybrid_memory.retrieve("query", k=1)
        assert len(results) == 1
        assert results[0].key == "k3"

    def test_retrieve_k_limits_results(
        self, hybrid_memory_with_data: HybridMemory
    ) -> None:
        results = hybrid_memory_with_data.retrieve("query", k=1)
        assert len(results) == 1

    def test_retrieve_k_larger_than_stored(
        self, hybrid_memory_with_data: HybridMemory
    ) -> None:
        results = hybrid_memory_with_data.retrieve("query", k=100)
        assert len(results) == 3  # only 3 items have embeddings


class TestHybridMemoryDelete:
    """Tests for delete()."""

    def test_delete_existing_key(
        self, hybrid_memory_with_data: HybridMemory
    ) -> None:
        assert hybrid_memory_with_data.get("key1") is not None
        hybrid_memory_with_data.delete("key1")
        assert hybrid_memory_with_data.get("key1") is None

    def test_delete_nonexistent_no_error(
        self, hybrid_memory: HybridMemory
    ) -> None:
        hybrid_memory.delete("nonexistent")  # should not raise

    def test_delete_removes_from_vector(
        self, hybrid_memory_with_data: HybridMemory
    ) -> None:
        initial_count = len(
            hybrid_memory_with_data.retrieve("query", k=100)
        )
        # "key2" has an embedding
        hybrid_memory_with_data.delete("key2")
        after_count = len(
            hybrid_memory_with_data.retrieve("query", k=100)
        )
        assert after_count == initial_count - 1


class TestHybridMemoryClear:
    """Tests for clear()."""

    def test_clear_removes_all(
        self, hybrid_memory_with_data: HybridMemory
    ) -> None:
        assert len(hybrid_memory_with_data) == 4
        hybrid_memory_with_data.clear()
        assert len(hybrid_memory_with_data) == 0
        assert hybrid_memory_with_data.get("key1") is None
        assert hybrid_memory_with_data.retrieve("query") == []

    def test_clear_empty_is_safe(self, hybrid_memory: HybridMemory) -> None:
        hybrid_memory.clear()  # should not raise
        assert len(hybrid_memory) == 0


class TestHybridMemoryContext:
    """Tests for get_context()."""

    def test_get_context_returns_session_id(
        self, hybrid_memory_with_data: HybridMemory
    ) -> None:
        ctx = hybrid_memory_with_data.get_context("session-123")
        assert ctx["session_id"] == "session-123"

    def test_get_context_returns_keys(
        self, hybrid_memory_with_data: HybridMemory
    ) -> None:
        ctx = hybrid_memory_with_data.get_context("s1")
        assert "items" in ctx
        assert set(ctx["items"]) == {"key1", "key2", "key3", "key4"}

    def test_get_context_empty_memory(
        self, hybrid_memory: HybridMemory
    ) -> None:
        ctx = hybrid_memory.get_context("empty-session")
        assert ctx["session_id"] == "empty-session"
        assert ctx["items"] == []


class TestHybridMemoryLen:
    """Tests for __len__."""

    def test_len_empty(self, hybrid_memory: HybridMemory) -> None:
        assert len(hybrid_memory) == 0

    def test_len_with_data(
        self, hybrid_memory_with_data: HybridMemory
    ) -> None:
        assert len(hybrid_memory_with_data) == 4

    def test_len_after_delete(
        self, hybrid_memory_with_data: HybridMemory
    ) -> None:
        hybrid_memory_with_data.delete("key1")
        assert len(hybrid_memory_with_data) == 3
