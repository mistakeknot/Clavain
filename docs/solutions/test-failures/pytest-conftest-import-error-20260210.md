---
module: System
date: 2026-02-10
problem_type: test_failure
component: testing_framework
symptoms:
  - "ModuleNotFoundError: No module named 'conftest'"
  - "from conftest import parse_frontmatter fails in test files"
  - "Tests pass individually but fail when run as suite"
root_cause: wrong_api
resolution_type: code_fix
severity: medium
tags: [pytest, conftest, imports, test-helpers, python]
---

# Troubleshooting: Cannot Import Functions from conftest.py in Pytest

## Problem
After extracting a shared `parse_frontmatter` function into `conftest.py`, test files that try to import it with `from conftest import parse_frontmatter` fail with `ModuleNotFoundError`. This happens because pytest's `conftest.py` is a special plugin file, not a regular Python module.

## Environment
- Module: System-wide (test suite)
- Framework Version: pytest 8.x
- Affected Component: `tests/structural/conftest.py`
- Date: 2026-02-10

## Symptoms
- `from conftest import parse_frontmatter` raises `ModuleNotFoundError: No module named 'conftest'`
- The function exists in `conftest.py` and fixtures from the same file work fine
- Running a single test file might work, but the full suite fails

## What Didn't Work

**Attempted Solution 1:** Direct import from conftest (`from conftest import parse_frontmatter`)
- **Why it failed:** `conftest.py` is not a regular Python module — pytest loads it as a plugin. Python's import system cannot find it because it's not on `sys.path` as a module, and pytest explicitly prevents this.

## Solution

Create a separate helper module and configure pytest to find it:

**Step 1:** Create `tests/structural/helpers.py`:
```python
"""Shared helpers for structural tests."""
import yaml

def parse_frontmatter(path):
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None, text
    fm = yaml.safe_load(parts[1])
    body = parts[2]
    return fm, body
```

**Step 2:** Add `pythonpath` to `pyproject.toml`:
```toml
[tool.pytest.ini_options]
testpaths = ["structural"]
pythonpath = ["structural"]
```

**Step 3:** Import from helpers in test files:
```python
# Before (broken):
from conftest import parse_frontmatter

# After (fixed):
from helpers import parse_frontmatter
```

## Why This Works

pytest's `conftest.py` is a **plugin file**, not a regular Python module. pytest discovers and loads conftest files through its own plugin mechanism — they're never added to `sys.modules` as importable modules. This is by design: conftest files can exist at multiple directory levels and are loaded hierarchically.

The `pythonpath` setting in `pyproject.toml` tells pytest to add the `structural/` directory to `sys.path` before running tests, making `helpers.py` importable as a regular module. This is the officially recommended approach for shared test utilities.

## Prevention

- **Never put importable utility functions in conftest.py** — only put pytest fixtures and hooks there
- Use a `helpers.py` or `utils.py` module for shared test utilities
- Always add the helpers directory to `pythonpath` in `pyproject.toml`
- If a function needs to be both a fixture AND a utility, put the logic in helpers.py and have the fixture call it

## Related Issues

No related issues documented yet.
