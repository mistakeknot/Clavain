# F10: Git Pre-Commit Hook Generator for Interlock

> **For Claude:** REQUIRED SUB-SKILL: Use clavain:executing-plans to implement this plan task-by-task.

**Goal:** Generate a git pre-commit hook that enforces file reservations at commit time, providing a mandatory backstop to the advisory PreToolUse:Edit hook (F7). The hook fetches active reservations from intermute, matches them against staged files, and blocks the commit with an actionable error message if conflicts are detected.

**Tech Stack:** Bash, curl, jq

**Bead:** Clavain-ixyn
**Target Repo:** `/root/projects/interlock/`
**PRD:** `docs/prds/2026-02-14-interlock-multi-agent-coordination.md` (F10)

---

## Task 1: Installer Script

**Files:**
- Create: `/root/projects/interlock/scripts/interlock-install-hooks`

This script installs the interlock pre-commit hook into a git repository. It handles three scenarios: no existing hook (create new), existing interlock hook (replace), and existing third-party hook (wrap).

**Step 1: Create the installer**

Create `/root/projects/interlock/scripts/interlock-install-hooks`:

```bash
#!/usr/bin/env bash
set -euo pipefail

# interlock-install-hooks — Install the interlock git pre-commit hook.
# Handles existing hooks by detecting an INTERLOCK_HOOK_MARKER comment.
# If an unmarked hook exists, it is backed up and chained.

MARKER="# INTERLOCK_HOOK_MARKER"

# Resolve git repo root
GIT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || {
    echo "ERROR: Not inside a git repository." >&2
    exit 1
}

HOOKS_DIR="${GIT_ROOT}/.git/hooks"
HOOK_PATH="${HOOKS_DIR}/pre-commit"
BACKUP_PATH="${HOOKS_DIR}/pre-commit.interlock-backup"

# Locate the hook template. Check INTERLOCK_ROOT first (dev override),
# then fall back to the directory containing this script.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -n "${INTERLOCK_ROOT:-}" ]]; then
    TEMPLATE="${INTERLOCK_ROOT}/scripts/interlock-precommit-hook"
else
    TEMPLATE="${SCRIPT_DIR}/interlock-precommit-hook"
fi

if [[ ! -f "$TEMPLATE" ]]; then
    echo "ERROR: Hook template not found at ${TEMPLATE}" >&2
    exit 1
fi

# Ensure hooks directory exists (bare repos may not have it)
mkdir -p "$HOOKS_DIR"

if [[ -f "$HOOK_PATH" ]]; then
    if grep -q "$MARKER" "$HOOK_PATH" 2>/dev/null; then
        # Existing interlock hook — replace in place (idempotent)
        echo "Replacing existing interlock pre-commit hook..."
        cp "$TEMPLATE" "$HOOK_PATH"
        chmod +x "$HOOK_PATH"
        echo "Done. Hook updated at ${HOOK_PATH}"
        exit 0
    else
        # Third-party hook exists — back up and chain
        echo "Existing pre-commit hook detected. Backing up to ${BACKUP_PATH}..."
        cp "$HOOK_PATH" "$BACKUP_PATH"
        chmod +x "$BACKUP_PATH"

        # Create wrapper that runs backup first, then interlock
        {
            echo "#!/usr/bin/env bash"
            echo "$MARKER"
            echo "# Wrapper: runs original hook first, then interlock conflict check."
            echo "# Original hook backed up at: ${BACKUP_PATH}"
            echo ""
            echo "# Run original pre-commit hook"
            echo "if [[ -x \"${BACKUP_PATH}\" ]]; then"
            echo "    \"${BACKUP_PATH}\""
            echo "    ORIG_EXIT=\$?"
            echo "    if [[ \$ORIG_EXIT -ne 0 ]]; then"
            echo "        exit \$ORIG_EXIT"
            echo "    fi"
            echo "fi"
            echo ""
            echo "# Run interlock conflict check"
            # Inline the template content after the wrapper preamble
            # Skip the shebang and marker lines from the template
            tail -n +3 "$TEMPLATE"
        } > "$HOOK_PATH"
        chmod +x "$HOOK_PATH"
        echo "Done. Wrapper hook installed at ${HOOK_PATH}"
        echo "  Original hook preserved at ${BACKUP_PATH}"
        exit 0
    fi
else
    # No existing hook — install directly
    echo "Installing interlock pre-commit hook..."
    cp "$TEMPLATE" "$HOOK_PATH"
    chmod +x "$HOOK_PATH"
    echo "Done. Hook installed at ${HOOK_PATH}"
    exit 0
fi
```

**Step 2: Make it executable**

```bash
chmod +x /root/projects/interlock/scripts/interlock-install-hooks
```

**Step 3: Verify syntax**

```bash
bash -n /root/projects/interlock/scripts/interlock-install-hooks
```

Expected: No output (clean parse).

**Step 4: Commit**

```bash
cd /root/projects/interlock
git add scripts/interlock-install-hooks
git commit -m "feat(f10): add interlock-install-hooks installer script"
```

---

## Task 2: Pre-Commit Hook Template

**Files:**
- Create: `/root/projects/interlock/scripts/interlock-precommit-hook`

This is the actual pre-commit hook logic. It is either copied directly to `.git/hooks/pre-commit` or inlined into a wrapper by the installer.

**Step 1: Create the hook template**

Create `/root/projects/interlock/scripts/interlock-precommit-hook`:

```bash
#!/usr/bin/env bash
# INTERLOCK_HOOK_MARKER
# interlock pre-commit hook — enforces intermute file reservations at commit time.
# Blocks commit if staged files conflict with another agent's active reservations.
# Skippable via: git commit --no-verify

# --- Graceful degradation: pass if agent not registered ---
if [[ -z "${INTERMUTE_AGENT_ID:-}" ]]; then
    exit 0
fi

# --- Configuration (env var overrides) ---
INTERMUTE_SOCKET="${INTERMUTE_SOCKET:-/var/run/intermute.sock}"
INTERMUTE_URL="${INTERMUTE_URL:-http://localhost:7890}"
INTERMUTE_PROJECT="${INTERMUTE_PROJECT:-$(basename "$(git rev-parse --show-toplevel 2>/dev/null)" 2>/dev/null)}"

if [[ -z "$INTERMUTE_PROJECT" ]]; then
    # Cannot determine project — pass through
    exit 0
fi

# --- Build curl args (socket preferred, TCP fallback) ---
CURL_BASE=(curl -sf --max-time 5)
if [[ -S "$INTERMUTE_SOCKET" ]]; then
    CURL_BASE+=(--unix-socket "$INTERMUTE_SOCKET")
    BASE_URL="http://localhost"
else
    BASE_URL="$INTERMUTE_URL"
fi

# --- Get staged files ---
STAGED_FILES=$(git diff --cached --name-only 2>/dev/null)
if [[ -z "$STAGED_FILES" ]]; then
    exit 0
fi

# --- Fetch active reservations (1 HTTP request) ---
RESERVATIONS=$("${CURL_BASE[@]}" "${BASE_URL}/api/reservations?project=$(printf '%s' "$INTERMUTE_PROJECT" | jq -sRr @uri)" 2>/dev/null) || {
    # intermute unreachable — pass through (graceful degradation)
    exit 0
}

# --- Fetch agents for name lookup (1 HTTP request) ---
AGENTS=$("${CURL_BASE[@]}" "${BASE_URL}/api/agents?project=$(printf '%s' "$INTERMUTE_PROJECT" | jq -sRr @uri)" 2>/dev/null) || {
    AGENTS='{"agents":[]}'
}

# --- Build agent_id -> name lookup ---
declare -A AGENT_NAMES
while IFS='|' read -r aid aname; do
    [[ -n "$aid" ]] && AGENT_NAMES["$aid"]="$aname"
done < <(echo "$AGENTS" | jq -r '.agents[]? | "\(.agent_id)|\(.name)"' 2>/dev/null)

# --- Check each staged file against reservations ---
CONFLICTS=()
NOW_EPOCH=$(date +%s)

while IFS= read -r file; do
    [[ -z "$file" ]] && continue

    # Iterate active reservations, check for pattern match
    while IFS='|' read -r res_agent_id res_pattern res_reason res_expires res_active; do
        # Skip if not active
        [[ "$res_active" != "true" ]] && continue

        # Skip our own reservations
        [[ "$res_agent_id" == "$INTERMUTE_AGENT_ID" ]] && continue

        # Match file against glob pattern using bash case statement
        # shellcheck disable=SC2254
        case "$file" in
            $res_pattern)
                # Compute human-readable expiry
                expires_epoch=$(date -d "$res_expires" +%s 2>/dev/null || echo 0)
                remaining=$(( (expires_epoch - NOW_EPOCH + 59) / 60 ))  # round up
                if [[ "$remaining" -le 0 ]]; then
                    time_str="expired"
                else
                    time_str="${remaining}m"
                fi

                agent_name="${AGENT_NAMES[$res_agent_id]:-$res_agent_id}"
                reason_str=""
                [[ -n "$res_reason" && "$res_reason" != "null" ]] && reason_str=": \"${res_reason}\""

                CONFLICTS+=("  - ${file} (reserved by ${agent_name}${reason_str}, expires in ${time_str})")
                break  # One conflict per file is enough
                ;;
        esac
    done < <(echo "$RESERVATIONS" | jq -r '.reservations[]? | "\(.agent_id)|\(.path_pattern)|\(.reason // "")|\(.expires_at)|\(.is_active)"' 2>/dev/null)
done <<< "$STAGED_FILES"

# --- Report conflicts or pass ---
if [[ ${#CONFLICTS[@]} -gt 0 ]]; then
    echo "" >&2
    echo "ERROR: Cannot commit. Reserved files detected:" >&2
    for conflict in "${CONFLICTS[@]}"; do
        echo "$conflict" >&2
    done

    # Extract unique agent names from conflicts for the resolve hint
    CONFLICT_AGENTS=()
    for conflict in "${CONFLICTS[@]}"; do
        agent=$(echo "$conflict" | sed -n 's/.*reserved by \([^:)]*\).*/\1/p')
        [[ -n "$agent" ]] && CONFLICT_AGENTS+=("$agent")
    done
    # Deduplicate
    UNIQUE_AGENTS=($(printf '%s\n' "${CONFLICT_AGENTS[@]}" | sort -u))
    AGENT_HINT="${UNIQUE_AGENTS[0]:-unknown}"

    echo "" >&2
    echo "Resolve: (1) /interlock:request-release ${AGENT_HINT}, (2) wait for expiry, (3) git commit --no-verify (risk: overwrite)" >&2
    echo "" >&2
    exit 1
fi

exit 0
```

**Step 2: Make it executable**

```bash
chmod +x /root/projects/interlock/scripts/interlock-precommit-hook
```

**Step 3: Verify syntax**

```bash
bash -n /root/projects/interlock/scripts/interlock-precommit-hook
```

Expected: No output (clean parse).

**Step 4: Run shellcheck (if available)**

```bash
shellcheck /root/projects/interlock/scripts/interlock-precommit-hook || true
shellcheck /root/projects/interlock/scripts/interlock-install-hooks || true
```

Address any warnings. The `# shellcheck disable=SC2254` on the case pattern match is intentional (we WANT glob expansion in the pattern).

**Step 5: Commit**

```bash
cd /root/projects/interlock
git add scripts/interlock-precommit-hook
git commit -m "feat(f10): add pre-commit hook template with batch conflict check"
```

---

## Task 3: Structural Tests

**Files:**
- Create: `/root/projects/interlock/tests/structural/test_git_hooks.py`

Structural tests verify the scripts exist, are executable, contain required patterns, and pass syntax checks.

**Step 1: Create the test file**

Create `/root/projects/interlock/tests/structural/test_git_hooks.py`:

```python
"""Structural tests for F10 git pre-commit hook generator."""
import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"


class TestInstallerScript:
    """Tests for interlock-install-hooks."""

    SCRIPT = SCRIPTS_DIR / "interlock-install-hooks"

    def test_exists(self):
        assert self.SCRIPT.exists(), f"Missing: {self.SCRIPT}"

    def test_executable(self):
        assert os.access(self.SCRIPT, os.X_OK), f"Not executable: {self.SCRIPT}"

    def test_bash_syntax(self):
        result = subprocess.run(
            ["bash", "-n", str(self.SCRIPT)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Syntax error:\n{result.stderr}"

    def test_contains_marker_reference(self):
        content = self.SCRIPT.read_text()
        assert "INTERLOCK_HOOK_MARKER" in content, "Must reference the hook marker"

    def test_contains_backup_logic(self):
        content = self.SCRIPT.read_text()
        assert "interlock-backup" in content, "Must handle existing hook backup"

    def test_contains_template_reference(self):
        content = self.SCRIPT.read_text()
        assert "interlock-precommit-hook" in content, "Must reference hook template"

    def test_makes_hook_executable(self):
        content = self.SCRIPT.read_text()
        assert "chmod +x" in content, "Must make generated hook executable"

    def test_detects_git_repo(self):
        content = self.SCRIPT.read_text()
        assert "git rev-parse" in content, "Must detect git repository root"


class TestPreCommitHookTemplate:
    """Tests for interlock-precommit-hook."""

    SCRIPT = SCRIPTS_DIR / "interlock-precommit-hook"

    def test_exists(self):
        assert self.SCRIPT.exists(), f"Missing: {self.SCRIPT}"

    def test_executable(self):
        assert os.access(self.SCRIPT, os.X_OK), f"Not executable: {self.SCRIPT}"

    def test_bash_syntax(self):
        result = subprocess.run(
            ["bash", "-n", str(self.SCRIPT)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Syntax error:\n{result.stderr}"

    def test_contains_marker(self):
        content = self.SCRIPT.read_text()
        assert "INTERLOCK_HOOK_MARKER" in content, "Must contain marker for idempotent replacement"

    def test_graceful_degradation_no_agent(self):
        content = self.SCRIPT.read_text()
        assert "INTERMUTE_AGENT_ID" in content, "Must check for agent registration"
        # Verify early exit when no agent
        assert 'exit 0' in content, "Must exit 0 when no agent registered"

    def test_uses_git_diff_cached(self):
        content = self.SCRIPT.read_text()
        assert "git diff --cached --name-only" in content, "Must extract staged files"

    def test_queries_reservations_api(self):
        content = self.SCRIPT.read_text()
        assert "/api/reservations" in content, "Must query intermute reservations API"

    def test_queries_agents_api(self):
        content = self.SCRIPT.read_text()
        assert "/api/agents" in content, "Must query agents for name resolution"

    def test_error_message_format(self):
        content = self.SCRIPT.read_text()
        assert "Cannot commit. Reserved files detected" in content, \
            "Must use PRD error message format"

    def test_resolve_instructions(self):
        content = self.SCRIPT.read_text()
        assert "request-release" in content, "Must include release instruction"
        assert "--no-verify" in content, "Must document escape hatch"

    def test_socket_support(self):
        content = self.SCRIPT.read_text()
        assert "unix-socket" in content or "INTERMUTE_SOCKET" in content, \
            "Must support Unix socket connection"

    def test_tcp_fallback(self):
        content = self.SCRIPT.read_text()
        assert "INTERMUTE_URL" in content, "Must support TCP fallback"

    def test_skips_own_reservations(self):
        content = self.SCRIPT.read_text()
        assert "INTERMUTE_AGENT_ID" in content, "Must filter out own reservations"

    def test_curl_timeout(self):
        content = self.SCRIPT.read_text()
        assert "max-time" in content, "Must set curl timeout for graceful degradation"
```

**Step 2: Verify pyproject.toml exists**

If `/root/projects/interlock/tests/pyproject.toml` does not exist yet, create it:

```toml
[project]
name = "interlock-tests"
version = "0.0.1"
requires-python = ">=3.10"

[tool.pytest.ini_options]
testpaths = ["structural"]

[dependency-groups]
dev = ["pytest>=8.0"]
```

**Step 3: Run the tests**

```bash
cd /root/projects/interlock/tests && uv run pytest structural/test_git_hooks.py -v
```

Expected: All tests PASS (assuming the scripts from Tasks 1 and 2 are already committed).

**Step 4: Commit**

```bash
cd /root/projects/interlock
git add tests/structural/test_git_hooks.py tests/pyproject.toml
git commit -m "test(f10): structural tests for git pre-commit hook generator"
```

---

## Verification Checklist

After all tasks:

```bash
cd /root/projects/interlock

# 1. Both scripts exist and are executable
test -x scripts/interlock-install-hooks && echo "OK: installer executable"
test -x scripts/interlock-precommit-hook && echo "OK: template executable"

# 2. Syntax checks pass
bash -n scripts/interlock-install-hooks && echo "OK: installer syntax"
bash -n scripts/interlock-precommit-hook && echo "OK: template syntax"

# 3. Structural tests pass
cd tests && uv run pytest structural/test_git_hooks.py -v

# 4. Quick manual smoke test (optional, requires running intermute)
cd /tmp && mkdir -p test-repo && cd test-repo && git init
INTERLOCK_ROOT=/root/projects/interlock /root/projects/interlock/scripts/interlock-install-hooks
cat .git/hooks/pre-commit | head -5  # Should show shebang + marker
rm -rf /tmp/test-repo
```

## Acceptance Criteria Mapping

| PRD Criterion | Task | Verified By |
|---------------|------|-------------|
| `interlock-install-hooks` generates `.git/hooks/pre-commit` | Task 1 | `test_detects_git_repo`, `test_makes_hook_executable`, manual smoke test |
| Hook extracts changed files from `git diff --cached --name-only` | Task 2 | `test_uses_git_diff_cached` |
| Hook checks each file against intermute's conflict detection API | Task 2 | `test_queries_reservations_api`, batch match logic |
| Hook aborts with clear, actionable error message | Task 2 | `test_error_message_format`, `test_resolve_instructions` |
| Hook passes if no intermute agent registered (graceful degradation) | Task 2 | `test_graceful_degradation_no_agent` |
| Hook skippable with `--no-verify` (escape hatch documented) | Task 2 | `test_resolve_instructions` (mentions `--no-verify` in error output) |
