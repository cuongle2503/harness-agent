# ADR-003: Backend Strategy — CompositeBackend with Hybrid Routing

> **Status**: ✅ Accepted
> **Date**: 2026-06-18
> **Phase**: 2 — Architecture & Design
> **Deciders**: harness-architect agent

---

## Context

Deep Agents cần quyết định cách lưu trữ file: ephemeral (mất khi session kết thúc) hay persistent (tồn tại qua các session). Harness Agent có các nhu cầu lưu trữ khác nhau:

- **Memory** (`/memories/*`): Cần persistent, cross-session, user-scoped
- **Policies** (`/policies/*`): Cần persistent, org-scoped (future multi-tenant)
- **Workspace** (`/workspace/*`): Ephemeral, per-session là đủ
- **Output** (`/output/*`): Real filesystem cho artifacts (test reports, generated code)

Câu hỏi: dùng một backend duy nhất cho tất cả, hay hybrid?

## Decision

**Chọn CompositeBackend với 4 routes** — kết hợp StateBackend (default), StoreBackend (memory/policies), và FilesystemBackend (output).

```python
from deepagents.backends import (
    CompositeBackend,
    StateBackend,
    StoreBackend,
    FilesystemBackend,
)

backend = CompositeBackend(
    default=StateBackend(),            # Ephemeral cho mọi thứ khác
    routes={
        # Persistent user-scoped memory
        "/memories/": StoreBackend(
            store=store,
            namespace=lambda rt: [rt.server_info.user.identity],
            file_format="v2",
        ),
        # Persistent org-scoped policies (future multi-tenant)
        "/policies/": StoreBackend(
            store=store,
            namespace=lambda rt: [rt.context.org_id],
            file_format="v2",
        ),
        # Real filesystem output (generated artifacts)
        "/output/": FilesystemBackend(
            root_dir="/data/agent-output",
        ),
    },
)
```

### Backend Routing Diagram

```
File Path                          → Backend              → Persistence
─────────────────────────────────────────────────────────────────────────
/memories/preferences.md           → StoreBackend         → Persistent, user-scoped
/memories/feedback.md              → StoreBackend         → Persistent, user-scoped
/policies/compliance.md            → StoreBackend         → Persistent, org-scoped
/policies/coding-standards.md      → StoreBackend         → Persistent, org-scoped
/output/test-results.xml           → FilesystemBackend    → Real disk
/output/generated/app.py           → FilesystemBackend    → Real disk
/workspace/temp/analysis.py        → StateBackend         → Ephemeral session
/temp/intermediate.json            → StateBackend         → Ephemeral session
/any/other/path.md                 → StateBackend         → Ephemeral session
```

### Backend Selection Rationale

| Path Pattern | Backend | Why |
|-------------|---------|-----|
| `/memories/*` | `StoreBackend` | User preferences & feedback must persist across sessions. User-scoped via namespace. |
| `/policies/*` | `StoreBackend` | Org-wide rules must be shared across users. Org-scoped via namespace. |
| `/output/*` | `FilesystemBackend` | Generated artifacts cần có trên disk thật để user/service khác đọc. |
| `/*` (default) | `StateBackend` | Hầu hết file operations là temporary — không cần persist. |

### File Format: v2

Chọn `file_format="v2"` vì:
- Content lưu dưới dạng `str` với `encoding` field — dễ đọc/ghi
- Hỗ trợ non-UTF-8 encodings
- Recommended bởi Deep Agents docs
- Tương thích tốt hơn với binary content

## Alternatives Considered

### 1. StateBackend Only (Rejected)

**Mô tả**: Dùng StateBackend cho tất cả file operations. Mọi thứ mất khi session kết thúc.

**Pros**:
- Đơn giản nhất
- Không cần setup store
- Phù hợp cho development

**Cons**:
- Memory không persist → mỗi session bắt đầu từ đầu
- Không có cross-session learning
- Không phù hợp production

**Lý do reject**: Harness Agent cần memory để học user preferences qua thời gian. StateBackend-only phá hỏng memory system.

### 2. FilesystemBackend Only (Rejected)

**Mô tả**: Dùng FilesystemBackend với root_dir cho tất cả.

**Pros**:
- Tất cả file trên disk thật — dễ inspect
- Persistent mặc định

**Cons**:
- **Security risk**: Agent có thể đọc/ghi toàn bộ filesystem
- Không có user-scoping tự nhiên
- Không có namespace isolation
- Cần sandbox HOẶC HITL cho mọi file operation

**Lý do reject**: Quá nguy hiểm nếu không có sandbox. CompositeBackend cho phép giới hạn disk access chỉ ở `/output/`.

### 3. StoreBackend Only (Rejected)

**Mô tả**: Dùng StoreBackend cho tất cả, kể cả temporary files.

**Pros**:
- Persistent
- Cross-thread sharing

**Cons**:
- Store overhead cho ephemeral files là không cần thiết
- Tất cả file đều persistent → cần cleanup
- StoreBackend không hỗ trợ file execution

**Lý do reject**: Temporary files không cần persist. StateBackend nhanh hơn và tự cleanup. CompositeBackend cho phép chọn đúng backend cho đúng loại file.

## Consequences

### Positive
- ✅ **Đúng backend cho đúng use case**: Memory persistent, temp ephemeral, output real disk
- ✅ **Security**: Agent không có disk access trừ `/output/` route
- ✅ **User isolation**: StoreBackend namespace scoped per user
- ✅ **Clean separation**: Temporary data tự cleanup khi session kết thúc
- ✅ **Scalable**: Dễ thêm route mới (vd: `/shared/` cho cross-user)
- ✅ **Production-ready**: Pattern được recommend bởi Deep Agents docs

### Negative
- ⚠️ **Complexity**: 3 loại backend + 4 routes = phức tạp hơn 1 backend đơn
- ⚠️ **Store dependency**: Cần LangGraph Store (InMemoryStore hoặc PostgresSaver)
- ⚠️ **Namespace logic**: Namespace factory cần access đến runtime context
- ⚠️ **FilesystemBackend security**: `/output/` route vẫn có disk access — cần sandbox hoặc HITL

### Mitigation
- **Complexity**: CompositeBackend API rõ ràng — routing logic minh bạch
- **Store dependency**: Development dùng InMemoryStore; Production dùng PostgresSaver
- **Namespace logic**: Lambda factory đơn giản, testable
- **FilesystemBackend security**: `/output/` root_dir giới hạn trong `/data/agent-output/`; thêm HITL approval cho write_file vào `/output/`

---

## Store Configuration

```python
# Development: In-Memory
from langgraph.store.memory import InMemoryStore
store = InMemoryStore()

# Production: PostgreSQL
from langgraph.store.postgres import PostgresStore
store = PostgresStore.from_conn_string(os.environ["DATABASE_URL"])
```

---

## References

- [AIDLC Lifecycle §2.3](../guides/aidlc-lifecycle.md#23-backend-strategy)
- [Deep Agents Backends](../deep-agents/04-backends.md)
- [Backend Selection Matrix](../deep-agents/04-backends.md#so-sánh-backends)
- [CompositeBackend Routing](../deep-agents/04-backends.md#4-compositebackend--hybrid-storage)
- [Harness Agent Requirements §4](../requirements/harness-agent-requirements.md#4-memory-requirements)
