---
title: "External Tool and API Pitfalls"
category: integration-issues
tags: [codex-cli, glob, monorepo, pytest, conftest, deprecated-flags, api-changes]
date: 2026-03-19
synthesized_from:
  - integration-issues/codex-cli-deprecated-flags-clodex-20260211.md
  - integration-issues/glob-misses-subproject-files-galiana-20260215.md
  - test-failures/pytest-conftest-import-error-20260210.md
---

# External Tool and API Pitfalls

Three classes of integration failure caused by misunderstanding external tool APIs: CLI flag hallucination, glob pattern assumptions, and pytest special-file semantics.

## 1. AI Agents Hallucinate Deprecated CLI Flags

LLMs trained on old documentation generate outdated Codex CLI syntax (`codex --approval-mode full-auto` instead of `codex exec --full-auto`). This causes `unexpected argument` errors or opens interactive mode instead of executing.

**Three-layer defense:**
- **SKILL.md guard:** Explicit wrong-to-right mapping table in the skill that dispatches Codex
- **CLI reference doc:** Deprecated flags table with current equivalents
- **Troubleshooting doc:** Error pattern rows for each deprecated flag error message

**Rule:** Always route through a wrapper script (`dispatch.sh`) rather than constructing CLI commands directly in prompts. The wrapper validates flags and abstracts API changes.

## 2. Glob Patterns Must Account for Monorepo Depth

`glob.glob("project_root/docs/research/**/*.json", recursive=True)` finds nothing in a monorepo where files live under subprojects (`os/clavain/docs/research/...`, `plugins/interkasten/docs/research/...`).

**Fix:** Prefix the glob with `**` to search at any depth:
```python
# Before (broken -- anchored to project root):
pattern = project_root / "docs" / "research" / "**" / "findings.json"

# After (fixed -- searches all subprojects):
pattern = project_root / "**" / "docs" / "research" / "**" / "findings.json"
```

**Rule:** In monorepos, never assume a fixed depth between project root and target files. Always test glob patterns against actual file locations.

## 3. pytest conftest.py Is Not an Importable Module

`from conftest import parse_frontmatter` fails with `ModuleNotFoundError` because pytest's `conftest.py` is a plugin file loaded through pytest's own mechanism, not a regular Python module on `sys.path`.

**Fix:** Put shared test utilities in a separate `helpers.py` module, not in `conftest.py`. Add the directory to `pythonpath` in `pyproject.toml`:
```toml
[tool.pytest.ini_options]
pythonpath = ["structural"]
```

**Rule:** Only put fixtures and hooks in `conftest.py`. Importable utility functions belong in a separate module.

## Common Thread

All three issues share the same root cause: assuming an external tool works the way you expect rather than the way it actually works. The fixes all involve the same strategy: add an abstraction layer (wrapper script, helper module, leading `**`) that insulates your code from the tool's actual behavior.

**Before integrating any external tool:**
1. Read the current `--help` or docs, not training data
2. Test the actual behavior, not the expected behavior
3. Wrap the tool in an abstraction that you control
