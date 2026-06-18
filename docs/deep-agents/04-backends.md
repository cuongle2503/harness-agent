# 4. Hệ thống Backends

Backends kiểm soát cách Deep Agents lưu trữ file và quản lý state. Mỗi backend implement `BackendProtocol` và cung cấp các operations: đọc, ghi, xóa, list, search file.

## Các loại Backend

### 1. StateBackend — Ephemeral Storage

Lưu file trong state của LangGraph. **Mất khi session kết thúc**.

```python
from deepagents.backends import StateBackend
from deepagents.middleware.filesystem import FilesystemMiddleware

backend = StateBackend()

agent = create_agent(
    "deepseek-v4-flash",
    middleware=[FilesystemMiddleware(backend=backend)],
)
```

**Dùng khi**: Phát triển, testing, hoặc agent không cần persistent storage.

---

### 2. StoreBackend — Persistent Cross-Thread Storage

Lưu file vào LangGraph `BaseStore`. **Persistent và có thể chia sẻ giữa các thread**.

```python
from deepagents.backends import StoreBackend
from langgraph.store.memory import InMemoryStore  # Hoặc PostgresSaver, etc.

store = InMemoryStore()

backend = StoreBackend(
    store=store,                             # BaseStore instance
    namespace=lambda rt: ["user", rt.user_id], # Namespace để scope storage
    file_format="v2",                        # "v1" hoặc "v2"
)

agent = create_deep_agent(
    model="deepseek-v4-flash",
    backend=backend,
    store=store,
)
```

**Constructor parameters**:

```python
StoreBackend(
    runtime: object = None,       # Deprecated — bỏ qua
    *,
    store: BaseStore | None = None,    # BaseStore instance
    namespace: NamespaceFactory | None = None,  # Callable nhận Runtime, trả về tuple
    file_format: FileFormat = "v2",    # "v1": list[str], "v2": str + encoding
)
```

**Namespace Factory**:
```python
# Namespace nhận Runtime, trả về tuple để scope storage
namespace = lambda rt: [rt.context.org_id, rt.user_id]

# Cho user-specific storage
namespace = lambda rt: [rt.server_info.user.identity]

# Cho organization-level storage
namespace = lambda rt: [rt.context.org_id]
```

**File Format**:
- `"v1"` — content lưu dưới dạng `list[str]` (lines split on `\n`), không có `encoding`
- `"v2"` — content lưu dưới dạng `str` với `encoding` field (recommended)

---

### 3. FilesystemBackend — Real Disk Storage

Lưu file trực tiếp vào ổ đĩa. **Cần sandbox hoặc HITL để đảm bảo an toàn**.

```python
from deepagents.backends import FilesystemBackend

# ⚠️ Security: FilesystemBackend cho phép đọc/ghi toàn bộ filesystem.
# Luôn chạy trong sandbox HOẶC thêm HITL approval cho file operations.

backend = FilesystemBackend(root_dir="/data/agent-workspace")

agent = create_deep_agent(
    model="deepseek-v4-flash",
    middleware=[FilesystemMiddleware(backend=backend)],
)
```

**Dùng khi**: Agent cần truy cập file system thật (code generation, data processing).

---

### 4. CompositeBackend — Hybrid Storage

Kết hợp nhiều backend dựa trên path prefix. **Pattern phổ biến nhất cho production**.

```python
from deepagents.backends import StateBackend, StoreBackend, CompositeBackend

backend = CompositeBackend(
    default=StateBackend(),         # Default: ephemeral cho mọi thứ
    routes={
        "/memories/": StoreBackend(
            namespace=lambda rt: [rt.server_info.user.identity],
        ),                          # Persistent cho memories
        "/policies/": StoreBackend(
            namespace=lambda rt: [rt.context.org_id],
        ),                          # Org-level cho policies
        "/temp/": StateBackend(),   # Explicit ephemeral
    },
)

agent = create_deep_agent(
    model="deepseek-v4-flash",
    middleware=[FilesystemMiddleware(backend=backend)],
    memory=[
        "/memories/preferences.md",
        "/policies/compliance.md",
    ],
)
```

**Routing logic**:
```
File path: "/memories/user_info.md"
  → Matches route "/memories/" → StoreBackend (persistent, user-scoped)

File path: "/workspace/analysis.py"
  → No matching route → StateBackend (ephemeral)

File path: "/policies/rules.md"
  → Matches route "/policies/" → StoreBackend (persistent, org-scoped)
```

---

### 5. Sandbox Backends — Execution Support

Backend đặc biệt hỗ trợ **code execution** trong sandbox (Docker, VM).

```python
from deepagents.backends import FilesystemMiddleware

# Với Docker Sandbox
sandbox = DockerSandboxBackend(container_id="my-container")
agent = create_agent(
    middleware=[FilesystemMiddleware(backend=sandbox)],
)

# Backend implement SandboxBackendProtocol có thể:
# - Đọc/ghi file trong sandbox
# - Execute commands
# - Quản lý processes
```

---

## So sánh Backends

| Backend | Persistent | Cross-Thread | Disk Access | Execution | Use Case |
|---------|-----------|--------------|-------------|-----------|----------|
| **StateBackend** | ❌ | ❌ | ❌ | ❌ | Dev, testing |
| **StoreBackend** | ✅ | ✅ | ❌ | ❌ | Memory, preferences |
| **FilesystemBackend** | ✅ | ✅ | ✅ | ❌ | Code gen, data |
| **CompositeBackend** | Hybrid | Hybrid | Tùy route | ❌ | Production |
| **Sandbox** | ✅ | ✅ | ✅ | ✅ | Code execution |

---

## Backend Protocol

Tạo custom backend bằng cách implement `BackendProtocol`:

```python
from typing import Protocol

class BackendProtocol(Protocol):
    """Protocol cho Deep Agents backends."""

    async def read(self, path: str) -> str:
        """Đọc nội dung file."""
        ...

    async def write(self, path: str, content: str) -> None:
        """Ghi nội dung vào file."""
        ...

    async def delete(self, path: str) -> None:
        """Xóa file."""
        ...

    async def list(self, path: str) -> list[str]:
        """Liệt kê file trong thư mục."""
        ...

    async def search(self, pattern: str) -> list[str]:
        """Tìm file theo glob pattern."""
        ...
```

---

## Backend với Memory & Subagents

```python
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend

# Setup cho multi-tenant SaaS app
backend = CompositeBackend(
    default=StateBackend(),  # Ephemeral cho session
    routes={
        f"/tenants/{tenant_id}/memories/": StoreBackend(
            namespace=lambda rt, tid=tenant_id: [tid, "memories"],
        ),
        f"/tenants/{tenant_id}/policies/": StoreBackend(
            namespace=lambda rt, tid=tenant_id: [tid, "policies"],
        ),
        "/shared/": StoreBackend(
            namespace=lambda rt: ["shared"],
        ),
    },
)

# Subagent dùng chung backend với main agent
agent = create_deep_agent(
    model="deepseek-v4-flash",
    backend=backend,
    middleware=[
        FilesystemMiddleware(backend=backend),
        SubAgentMiddleware(
            backend=backend,  # Subagent dùng chung backend
            subagents=[...],
        ),
    ],
)
```
