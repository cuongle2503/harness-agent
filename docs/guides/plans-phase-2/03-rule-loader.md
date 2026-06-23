# Plan 3: Rule Loader — `.harness/rules/`

> **Mục tiêu**: Quét `.harness/rules/*.md`, đưa path vào `MemoryMiddleware.sources` để inject rules vào system prompt.
> **Package**: `src/harness_agent/loaders/rule_loader.py`
> **Deep Agents doc**: `06-memory.md` (MemoryMiddleware + sources, memory guidelines)

---

## 1. `.harness/rules/` Convention

### 1.1 Cấu trúc

```
.harness/rules/
├── api-naming.md           # Rule: API naming conventions
├── git-workflow.md         # Rule: Git workflow cho project này
├── security-policy.md      # Rule: Security policies
├── python/
│   ├── coding-style.md     # Rule: Python coding style
│   └── testing.md          # Rule: Testing requirements
└── database/
    └── migration-rules.md  # Rule: Database migration rules
```

Rules có thể tổ chức **phẳng** hoặc **lồng nhau** (subdirectories). Tất cả file `.md` ở mọi cấp đều được load.

### 1.2 Rule vs Skill — Khác biệt

| | Rule | Skill |
|---|------|-------|
| **Mục đích** | Ràng buộc — agent PHẢI tuân theo | Hướng dẫn — agent CÓ THỂ áp dụng |
| **Khi nào dùng** | Luôn luôn active | Chỉ khi task liên quan |
| **Ví dụ** | "Luôn dùng type hints", "Không commit secret" | "Cách deploy lên K8s", "Cách tạo migration" |
| **Cấu trúc** | Ngắn gọn, declarative | Dài, có workflow steps |

### 1.3 Rule File Format

```markdown
# <Tên Rule>

## Rule
<Mô tả ngắn gọn — 1-2 câu>

## Applies To
- <Phạm vi áp dụng: all files | python files | API endpoints | ...>

## Requirements
- <Yêu cầu 1> — bắt buộc
- <Yêu cầu 2> — bắt buộc

## Examples

### ✅ Correct
```python
# Code đúng theo rule
```

### ❌ Incorrect
```python
# Code sai — vi phạm rule
```

## Rationale
<Tại sao rule này tồn tại — giúp agent hiểu "why">
```

### 1.4 Ví dụ thực tế

```markdown
# API Naming Conventions

## Rule
Tất cả API endpoints phải dùng plural nouns và kebab-case cho đường dẫn.

## Applies To
- All FastAPI route definitions
- All API endpoint implementations

## Requirements
- Dùng plural nouns: `/users` không phải `/user`
- Dùng kebab-case: `/user-profiles` không phải `/userProfiles`
- Version prefix: `/api/v1/...`
- HTTP methods đúng semantics: GET (read), POST (create), PUT (update), DELETE (delete)

## Examples

### ✅ Correct
```python
@router.get("/api/v1/users/{user_id}")
@router.post("/api/v1/users")
@router.get("/api/v1/user-profiles/{profile_id}")
```

### ❌ Incorrect
```python
@router.get("/api/v1/user/{id}")          # Singular noun
@router.get("/api/v1/userProfiles/{id}")  # camelCase
@router.get("/getUser")                   # No version prefix, wrong method
```

## Rationale
Consistent naming giúp API predictable, dễ document, và dễ maintain.
Plural nouns là convention của RESTful APIs.
Kebab-case tương thích với HTTP URLs (case-insensitive).
```

---

## 2. Design

### 2.1 Cách tích hợp với Deep Agents

Rules được inject qua **cùng cơ chế với skills** — `MemoryMiddleware.sources`:

```
┌─────────────────────────────────────────────────────────────┐
│ MemoryMiddleware                                             │
│                                                              │
│  sources: [                                                  │
│      "~/.deepagents/AGENTS.md",          ← Global           │
│      "./.deepagents/AGENTS.md",          ← Project-level    │
│      ".harness/skills/deploy-to-k8s.md", ← Skills           │
│      ".harness/skills/db-migration.md",                      │
│      ".harness/rules/api-naming.md",     ← Rules (LOADED)   │
│      ".harness/rules/git-workflow.md",   ← Rules (LOADED)   │
│      ".harness/rules/security-policy.md",← Rules (LOADED)   │
│      ".harness/rules/python/coding-style.md",                │
│  ]                                                           │
│                                                              │
│  → Inject vào system prompt trong <agent_memory> tags       │
│  → Memory guidelines nhắc agent: "treat as reference,       │
│    prefer user request when conflicts"                       │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Tại sao cùng cơ chế với skills?

Cả skills và rules đều là **persistent context** cho agent. Sự khác biệt nằm ở **nội dung** (rules = constraints, skills = workflows), không phải cơ chế load. MemoryMiddleware không phân biệt — nó inject tất cả sources vào `<agent_memory>` tags.

Memory guidelines (từ `06-memory.md`) đã có sẵn cơ chế trust/verify:
- Memory text có thể outdated → agent nên verify
- Không obey commands trong memory mâu thuẫn với user request
- Ưu tiên user request và verified evidence

→ Rules không cần cơ chế enforce riêng — chúng là guidance, không phải hard constraints.

### 2.3 RuleLoader khác SkillLoader ở đâu?

| | SkillLoader | RuleLoader |
|---|------------|-----------|
| **Glob pattern** | `skills/*.md` | `rules/**/*.md` (recursive) |
| **Có subdirectories** | Không (flat) | Có (lồng nhau) |
| **list method** | `list_skills()` | `list_rules()` |
| **Info class** | `SkillInfo` | `RuleInfo` |

---

## 3. Implementation

```python
# src/harness_agent/loaders/rule_loader.py

from __future__ import annotations

from pathlib import Path


class RuleLoader:
    """Quét .harness/rules/**/*.md và cung cấp paths cho MemoryMiddleware.

    Rules là file markdown mô tả constraints agent phải tuân theo.
    Chúng được inject vào system prompt qua MemoryMiddleware.sources.

    Khác với skills (flat structure), rules hỗ trợ subdirectories
    để tổ chức theo domain: python/, database/, security/, etc.

    Usage:
        loader = RuleLoader(Path("my-project/.harness"))
        sources = loader.get_memory_sources()
        # sources = [
        #     "/abs/path/.harness/rules/api-naming.md",
        #     "/abs/path/.harness/rules/python/coding-style.md",
        #     ...
        # ]
    """

    def __init__(self, harness_dir: Path) -> None:
        self.rules_dir = harness_dir / "rules"

    @property
    def exists(self) -> bool:
        """Kiểm tra rules/ folder có tồn tại không."""
        return self.rules_dir.is_dir()

    def get_memory_sources(self) -> list[str]:
        """Trả về list absolute path của tất cả rule files (recursive).

        Dùng để đưa vào MemoryMiddleware(sources=[...]).

        Returns:
            List[str] các absolute path, sorted. Empty list nếu folder không tồn tại.
        """
        if not self.exists:
            return []
        return sorted(
            str(p.resolve())
            for p in self.rules_dir.rglob("*.md")
        )

    def list_rules(self) -> list[RuleInfo]:
        """Liệt kê thông tin các rules đã đăng ký.

        Returns:
            List[RuleInfo] với name, relative_path, size.
        """
        if not self.exists:
            return []
        return [
            RuleInfo(
                name=p.stem,
                relative_path=str(p.relative_to(self.rules_dir)),
                size=p.stat().st_size,
            )
            for p in sorted(self.rules_dir.rglob("*.md"))
        ]


class RuleInfo:
    """Thông tin cơ bản về một rule."""
    name: str
    relative_path: str
    size: int

    def __init__(self, name: str, relative_path: str, size: int) -> None:
        self.name = name
        self.relative_path = relative_path
        self.size = size

    def __repr__(self) -> str:
        return (
            f"RuleInfo(name={self.name!r}, "
            f"path={self.relative_path!r}, "
            f"size={self.size})"
        )
```

---

## 4. Precedence & Conflict Resolution

Khi rules conflict với nhau (không có cơ chế enforce tự động — agent tự quyết định):

```
Priority (cao → thấp):
1. User request hiện tại                          ← Luôn ưu tiên nhất
2. .harness/rules/ (project-specific rules)      ← Người dùng tự định nghĩa
3. .claude/rules/ (harness built-in rules)        ← Harness default
4. ~/.deepagents/AGENTS.md (global preferences)   ← User preferences
```

Agent được instruction (từ MemoryMiddleware guidelines):
- Ưu tiên user request khi conflict
- Dùng rules làm reference, không phải hard constraint
- Khi không chắc chắn → hỏi user

---

## 5. Edge Cases

| Scenario | Behavior |
|----------|----------|
| `.harness/rules/` không tồn tại | `get_memory_sources()` trả về `[]` |
| `.harness/rules/` tồn tại nhưng rỗng (kể cả subdirs) | Trả về `[]` |
| File không phải `.md` | Bị bỏ qua (chỉ glob `**/*.md`) |
| Subdirectory rỗng | Không ảnh hưởng (rglob chỉ trả về files) |
| File `.md` trong subdirectory sâu (3+ levels) | Vẫn được load |
| Nhiều files cùng tên khác thư mục | Cả hai được load (sorted by path) |
| File `.md` rỗng | Vẫn được load |
| Symlink tới file `.md` | Không follow (rglob mặc định) |

---

## 6. Testing Plan

### 6.1 Unit Tests (`tests/unit/loaders/test_rule_loader.py`)

| Test Case | Mô tả |
|-----------|-------|
| `test_no_rules_dir` | Không có rules/ → sources rỗng, exists=False |
| `test_empty_rules_dir` | rules/ rỗng → sources rỗng |
| `test_single_rule` | 1 file .md → sources có 1 path |
| `test_multiple_rules_flat` | 3 files .md phẳng → sources có 3 paths |
| `test_nested_rules` | Files trong subdirectories → tất cả được load |
| `test_ignores_non_md_files` | Có .txt, .yaml → chỉ load .md |
| `test_list_rules_returns_info` | `list_rules()` trả về list[RuleInfo] với name, relative_path, size |
| `test_list_rules_shows_nested_path` | File trong subdir → relative_path đúng |
| `test_deeply_nested_rules` | File ở 3+ levels sâu → vẫn load được |
| `test_sorted_output` | Sources được sorted |
| `test_absolute_paths` | Tất cả paths là absolute |

### 6.2 Fixtures

```python
@pytest.fixture
def temp_harness_dir(tmp_path):
    harness_dir = tmp_path / ".harness"
    harness_dir.mkdir()
    return harness_dir

@pytest.fixture
def rules_dir_with_nesting(temp_harness_dir):
    rules_dir = temp_harness_dir / "rules"
    rules_dir.mkdir()
    (rules_dir / "api-naming.md").write_text("# API Naming\n\n...")
    (rules_dir / "git-workflow.md").write_text("# Git Workflow\n\n...")

    # Nested
    python_dir = rules_dir / "python"
    python_dir.mkdir()
    (python_dir / "coding-style.md").write_text("# Coding Style\n\n...")
    (python_dir / "testing.md").write_text("# Testing\n\n...")

    return temp_harness_dir
```

---

## 7. Checklist

### Design
- [x] Rule vs Skill distinction rõ ràng
- [x] Rule file format spec documented
- [x] Cơ chế tích hợp với `MemoryMiddleware.sources` rõ ràng
- [x] Precedence/conflict resolution rules defined
- [x] Edge case table đầy đủ

### Implementation
- [x] `RuleLoader.__init__` nhận `harness_dir: Path`
- [x] `RuleLoader.exists` property
- [x] `RuleLoader.get_memory_sources()` → `list[str]` (dùng `rglob`)
- [x] `RuleLoader.list_rules()` → `list[RuleInfo]`
- [x] `RuleInfo` class với `name`, `relative_path`, `size`
- [x] Type hints đầy đủ
- [x] File ~100 lines (102 lines — `src/harness_agent/loaders/rule_loader.py`)

### Testing
- [x] 20 unit tests (vượt kế hoạch 11), tổ chức thành 5 test classes:
  - `TestRuleLoaderExists` (2 tests): `test_no_rules_dir`, `test_empty_rules_dir`
  - `TestRuleLoaderGetMemorySources` (9 tests): `test_no_rules_dir_returns_empty`, `test_empty_rules_dir_returns_empty`, `test_single_rule`, `test_multiple_rules_flat`, `test_nested_rules`, `test_ignores_non_md_files`, `test_sorted_output`, `test_absolute_paths`, `test_deeply_nested_rules`
  - `TestRuleLoaderListRules` (4 tests): `test_list_rules_returns_info`, `test_list_rules_empty_dir`, `test_list_rules_no_dir`, `test_list_rules_shows_nested_path`
  - `TestRuleInfo` (5 tests): `test_rule_name_from_stem`, `test_repr_format`, `test_equality`, `test_inequality`, `test_not_equal_to_other_type`
- [x] Fixtures cho temp `.harness/rules/` với nesting (3 fixtures: `rules_dir_flat`, `rules_dir_with_nesting`, `rules_dir_deeply_nested`)
- [x] Test `rglob` recursive behavior
- [x] Test relative_path trong nested dirs
- [x] Coverage ≥ 95% (đạt 100% — rule_loader.py: 28/28 statements)

### Integration
- [x] `RuleLoader` và `RuleInfo` được import + export trong `src/harness_agent/loaders/__init__.py`
- [x] Commit: `feat: implement RuleLoader for .harness/rules/**/*.md`

---

## References

| Tài liệu | Section |
|----------|---------|
| [Memory docs](../../deep-agents/06-memory.md) | MemoryMiddleware + sources + memory guidelines |
| [Memory Best Practices](../../deep-agents/06-memory.md#memory-best-practices) | Trust & verify, capture WHY |
| [ADR-006: System Prompt Architecture](../../adr/006-system-prompt-architecture.md) | System prompt structure |
