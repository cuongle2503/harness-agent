# Plan 2: Skill Loader — `.harness/skills/`

> **Mục tiêu**: Quét `.harness/skills/*.md`, đưa path vào `MemoryMiddleware.sources` để inject vào system prompt.
> **Package**: `src/harness_agent/loaders/skill_loader.py`
> **Deep Agents doc**: `06-memory.md` (MemoryMiddleware + sources)

---

## 1. `.harness/skills/` Convention

### 1.1 Cấu trúc

```
.harness/skills/
├── deploy-to-k8s.md       # Skill: deploy lên Kubernetes
├── db-migration.md         # Skill: tạo và chạy database migration
└── api-testing.md          # Skill: test API endpoints
```

Mỗi file `.md` là **một skill**. File name (không có `.md`) là tên skill.

### 1.2 Skill File Format

Skill file theo chuẩn markdown với cấu trúc cố định:

```markdown
# <Tên Skill>

## Description
<Mô tả ngắn gọn — khi nào agent nên dùng skill này>

## When to Use
- <Điều kiện 1>
- <Điều kiện 2>

## Instructions
1. <Bước 1>
2. <Bước 2>
3. <Bước 3>

## Examples
<VD cụ thể — input và expected output>

## Tools Used
- <tool_1>: <mô tả cách dùng>
- <tool_2>: <mô tả cách dùng>

## Constraints
- <Ràng buộc 1>
- <Ràng buộc 2>
```

### 1.3 Ví dụ thực tế

```markdown
# Database Migration

## Description
Tạo và chạy Alembic database migration cho project Python + SQLAlchemy.

## When to Use
- Người dùng yêu cầu tạo bảng mới hoặc thay đổi schema
- Người dùng nói "migration", "alembic", "database schema"

## Instructions
1. Đọc models hiện tại trong `src/models/`
2. Chạy `alembic revision --autogenerate -m "description"`
3. Review file migration được tạo trong `migrations/versions/`
4. Nếu đúng, chạy `alembic upgrade head`
5. Nếu sai, sửa file migration rồi chạy lại

## Examples
- User: "Tạo bảng users với columns id, name, email"
  → Tạo model → alembic revision → review → upgrade

## Tools Used
- read_file: Đọc models hiện tại và migration file
- execute_command: Chạy alembic commands
- write_file: Sửa migration file nếu cần

## Constraints
- Không bao giờ chạy alembic downgrade trừ khi user yêu cầu rõ ràng
- Luôn review migration file trước khi upgrade
- Backup database trước khi chạy migration trên production
```

---

## 2. Design

### 2.1 Cách tích hợp với Deep Agents

```
┌─────────────────────────────────────────────────────────────┐
│ MemoryMiddleware                                             │
│                                                              │
│  sources: [                                                  │
│      "~/.deepagents/AGENTS.md",          ← Global           │
│      "./.deepagents/AGENTS.md",          ← Project-level    │
│      ".harness/skills/deploy-to-k8s.md", ← Skill 1 (LOADED) │
│      ".harness/skills/db-migration.md",  ← Skill 2 (LOADED) │
│      ".harness/skills/api-testing.md",   ← Skill 3 (LOADED) │
│  ]                                                           │
│                                                              │
│  → Inject vào system prompt trong <agent_memory> tags       │
│  → Agent đọc và biết khi nào dùng skill nào                  │
└─────────────────────────────────────────────────────────────┘
```

Skill KHÔNG được thực thi (execute) — nó là **knowledge base** cho agent. Agent đọc skill description và tự quyết định khi nào áp dụng instructions trong skill.

### 2.2 SkillLoader chỉ làm 2 việc

1. **Quét** `.harness/skills/` lấy danh sách file `.md`
2. **Trả về** list path để HarnessBuilder đưa vào `MemoryMiddleware(sources=[...])`

Không parse, không validate nội dung — agent tự đọc và hiểu markdown.

---

## 3. Implementation

```python
# src/harness_agent/loaders/skill_loader.py

from __future__ import annotations

from pathlib import Path


class SkillLoader:
    """Quét .harness/skills/*.md và cung cấp paths cho MemoryMiddleware.

    Skills là file markdown mô tả workflow cho các task cụ thể.
    Chúng được inject vào system prompt qua MemoryMiddleware.sources.

    Agent sẽ đọc các skill này trong context và tự quyết định
    khi nào áp dụng instructions từ skill phù hợp.

    Usage:
        loader = SkillLoader(Path("my-project/.harness"))
        sources = loader.get_memory_sources()
        # sources = [
        #     "/abs/path/.harness/skills/deploy-to-k8s.md",
        #     "/abs/path/.harness/skills/db-migration.md",
        # ]
    """

    def __init__(self, harness_dir: Path) -> None:
        self.skills_dir = harness_dir / "skills"

    @property
    def exists(self) -> bool:
        """Kiểm tra skills/ folder có tồn tại không."""
        return self.skills_dir.is_dir()

    def get_memory_sources(self) -> list[str]:
        """Trả về list absolute path của tất cả skill files.

        Dùng để đưa vào MemoryMiddleware(sources=[...]).

        Returns:
            List[str] các absolute path. Empty list nếu folder không tồn tại.
        """
        if not self.exists:
            return []
        return sorted(
            str(p.resolve())
            for p in self.skills_dir.glob("*.md")
        )

    def list_skills(self) -> list[SkillInfo]:
        """Liệt kê thông tin các skill đã đăng ký.

        Returns:
            List[SkillInfo] với name và path. Dùng để hiển thị inventory.
        """
        if not self.exists:
            return []
        return [
            SkillInfo(
                name=p.stem,                # "deploy-to-k8s"
                path=str(p.resolve()),
                size=p.stat().st_size,
            )
            for p in sorted(self.skills_dir.glob("*.md"))
        ]


class SkillInfo:
    """Thông tin cơ bản về một skill."""
    name: str
    path: str
    size: int

    def __init__(self, name: str, path: str, size: int) -> None:
        self.name = name
        self.path = path
        self.size = size

    def __repr__(self) -> str:
        return f"SkillInfo(name={self.name!r}, size={self.size})"
```

---

## 4. Skill Name Resolution

Skill name được suy ra từ file name:

```
deploy-to-k8s.md     → skill name: "deploy-to-k8s"
db-migration.md       → skill name: "db-migration"
API Testing.md        → skill name: "API Testing"  (giữ nguyên case)
my_deploy_script.md   → skill name: "my_deploy_script"
```

File name không có `.md` = skill name. Không transform, không slugify.

---

## 5. Edge Cases

| Scenario | Behavior |
|----------|----------|
| `.harness/skills/` không tồn tại | `get_memory_sources()` trả về `[]` |
| `.harness/skills/` tồn tại nhưng rỗng | `get_memory_sources()` trả về `[]` |
| File không phải `.md` (`.txt`, `.yaml`) | Bị bỏ qua (chỉ glob `*.md`) |
| File `.md` trùng tên | Sorted alphabetically, cả hai được load |
| File `.md` rỗng | Vẫn được load (MemoryMiddleware xử lý) |
| Symlink tới file `.md` | Không follow (chỉ glob regular files) |

---

## 6. Testing Plan

### 6.1 Unit Tests (`tests/unit/loaders/test_skill_loader.py`)

| Test Case | Mô tả |
|-----------|-------|
| `test_no_skills_dir` | Không có skills/ → sources rỗng, exists=False |
| `test_empty_skills_dir` | skills/ rỗng → sources rỗng |
| `test_single_skill` | 1 file .md → sources có 1 path |
| `test_multiple_skills_sorted` | 3 files .md → sources có 3 paths, sorted |
| `test_ignores_non_md_files` | Có .txt, .yaml → chỉ load .md |
| `test_list_skills_returns_info` | `list_skills()` trả về list[SkillInfo] với name, path, size |
| `test_list_skills_empty_dir` | `list_skills()` trên dir rỗng → [] |
| `test_skill_name_from_stem` | File `deploy-to-k8s.md` → name = "deploy-to-k8s" |
| `test_absolute_paths` | Tất cả paths trong sources phải là absolute |

### 6.2 Fixtures

```python
@pytest.fixture
def temp_harness_dir(tmp_path):
    harness_dir = tmp_path / ".harness"
    harness_dir.mkdir()
    return harness_dir

@pytest.fixture
def skills_dir_with_files(temp_harness_dir):
    skills_dir = temp_harness_dir / "skills"
    skills_dir.mkdir()
    (skills_dir / "deploy-to-k8s.md").write_text("# Deploy to K8s\n\n...")
    (skills_dir / "db-migration.md").write_text("# DB Migration\n\n...")
    (skills_dir / "readme.txt").write_text("not a skill")  # Should be ignored
    return temp_harness_dir
```

---

## 7. Checklist

### Design
- [x] Skill file format spec (markdown structure) documented
- [x] Cơ chế tích hợp với `MemoryMiddleware.sources` rõ ràng
- [x] Skill name resolution rule (file stem = skill name)
- [x] Edge case table đầy đủ

### Implementation
- [x] `SkillLoader.__init__` nhận `harness_dir: Path`, lưu `self.harness_dir` + `self.skills_dir`
- [x] `SkillLoader.exists` property
- [x] `SkillLoader.get_memory_sources()` → `list[str]` (sorted absolute paths)
- [x] `SkillLoader.list_skills()` → `list[SkillInfo]`
- [x] `SkillInfo` class với `name`, `path`, `size` + `__eq__` + `__repr__`
- [x] Type hints đầy đủ (`from __future__ import annotations`, tất cả public methods)
- [x] File < 100 lines (96 lines — `src/harness_agent/loaders/skill_loader.py`)

### Testing
- [x] 16 unit tests (vượt kế hoạch 9), tổ chức thành 4 test classes:
  - `TestSkillLoaderExists` (2 tests): `test_no_skills_dir`, `test_empty_skills_dir`
  - `TestSkillLoaderGetMemorySources` (6 tests): `test_no_skills_dir_returns_empty`, `test_empty_skills_dir_returns_empty`, `test_single_skill`, `test_multiple_skills_sorted`, `test_ignores_non_md_files`, `test_absolute_paths`
  - `TestSkillLoaderListSkills` (3 tests): `test_list_skills_returns_info`, `test_list_skills_empty_dir`, `test_list_skills_no_dir`
  - `TestSkillInfo` (5 tests): `test_skill_name_from_stem`, `test_repr_format`, `test_equality`, `test_inequality`, `test_not_equal_to_other_type`
- [x] Fixtures cho temp `.harness/skills/`
- [x] Test glob pattern (`*.md` only)
- [x] Test absolute path conversion
- [x] Coverage ≥ 95% (đạt 100% — skill_loader.py: 28/28 statements)

### Integration
- [x] `SkillLoader` và `SkillInfo` được import + export trong `src/harness_agent/loaders/__init__.py`
- [x] Commit: `feat: implement SkillLoader for .harness/skills/*.md` (cb0697b)

---

## References

| Tài liệu | Section |
|----------|---------|
| [Memory docs](../../deep-agents/06-memory.md) | MemoryMiddleware + sources + agent_memory tags |
| [Memory System Prompt](../../deep-agents/06-memory.md#memory-system-prompt) | Cách skills được inject vào system prompt |
| [ADR-006: System Prompt Architecture](../../adr/006-system-prompt-architecture.md) | System prompt structure |
