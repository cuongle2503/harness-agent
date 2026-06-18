# Python Security Rules

## Mandatory Checks (Before ANY commit)

- [ ] No hardcoded secrets (API keys, passwords, tokens, connection strings)
- [ ] All user inputs validated (tool inputs, API parameters, file paths)
- [ ] Path traversal prevented — use `pathlib.Path.resolve()` and validate
- [ ] Unsafe deserialization avoided — never `pickle.load()` untrusted data
- [ ] Subprocess calls use list args, not shell strings
- [ ] SQL queries use parameterized statements
- [ ] Error messages don't leak sensitive data (paths, keys, internals)

## Secret Management

```python
# BAD
API_KEY = "sk-abc123"

# GOOD
import os
API_KEY = os.environ["HARNESS_API_KEY"]
```

## Tool Input Validation

```python
from pydantic import BaseModel, Field, validator

class ToolInput(BaseModel):
    """Validate all tool inputs with Pydantic."""
    file_path: str = Field(..., max_length=1024)
    content: str = Field(..., max_length=100_000)

    @validator("file_path")
    def no_path_traversal(cls, v: str) -> str:
        resolved = Path(v).resolve()
        if ".." in resolved.parts:
            raise ValueError("Path traversal detected")
        return str(resolved)
```

## Security Response Protocol

If security issue found:
1. **STOP** immediately
2. Use **security-reviewer** agent
3. Fix CRITICAL issues before continuing
4. Rotate any exposed secrets
5. Review entire codebase for similar issues
