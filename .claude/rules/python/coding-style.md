# Python Coding Style

## Core Principles

### PEP 8 Compliance
- 4 spaces for indentation (no tabs)
- 88 character line length (Black default)
- Imports ordered: stdlib → third-party → local
- Module-level dunder names before imports

### Type Hints (MANDATORY)
Every public function must have complete type annotations:

```python
from typing import Optional, Any

def process_agent(
    agent_id: str,
    config: dict[str, Any],
    memory_backend: str = "vector",
) -> Optional[Agent]:
    """Process an agent by ID and return it, or None if not found."""
    ...
```

### Pythonic Patterns
- **EAFP**: Easier to Ask Forgiveness Than Permission — use `try/except` over `if/else` checks
- **Context Managers**: Always use `with` for files, connections, locks
- **Dataclasses**: For data containers — `@dataclass` over plain dicts
- **f-strings**: For string formatting (Python 3.6+)
- **`pathlib.Path`**: For all path operations

### Anti-Patterns to Avoid
- ❌ Bare `except:` — always catch specific exceptions
- ❌ Mutable default arguments: `def f(items=[])` → `def f(items=None)`
- ❌ `from module import *` — namespace pollution
- ❌ `type(obj) == str` → `isinstance(obj, str)`
- ❌ `value == None` → `value is None`
- ❌ String concatenation in loops → `"".join()`

### File Organization
- Many small files (200-400 lines) > few large files (>800 max)
- Organize by feature/domain, not by type
- `__init__.py` should export public API via `__all__`

### Code Quality Checklist
- [ ] Type hints on all public functions
- [ ] Functions < 50 lines
- [ ] Files < 800 lines
- [ ] No deep nesting (>4 levels)
- [ ] Proper error handling (specific exceptions)
- [ ] Context managers for resources
- [ ] Docstrings on public functions
