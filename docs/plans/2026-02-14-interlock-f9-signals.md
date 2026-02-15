# F9: Signal File Adapter — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use clavain:executing-plans to implement this plan task-by-task.

**Goal:** Add a signal writer script to the interlock companion plugin that emits normalized append-only JSONL signal files for interline consumption, plus integration call sites in the MCP server wrapper and hook scripts.

**Architecture:** A single Bash script (`scripts/interlock-signal.sh`) constructs JSON lines with `jq -nc` and appends them to `/var/run/intermute/signals/{project-slug}-{agent-id}.jsonl` using `>>` (which uses `O_APPEND`, atomic for <4KB on Linux). Three call sites invoke this script: the MCP tool wrapper after reserve/release, the SessionStart hook after registration, and the Stop hook after cleanup. The signal directory is created with mode 0700 on first write.

**Tech Stack:** Bash, jq, bats-core (tests)

**Bead:** Clavain-rmvl

**PRD:** `docs/prds/2026-02-14-interlock-multi-agent-coordination.md` (F9)

---

### Task 1: Signal Writer Script + Tests

**Files:**
- Create: `/root/projects/interlock/scripts/interlock-signal.sh`
- Create: `/root/projects/interlock/tests/shell/interlock_signal.bats`
- Create: `/root/projects/interlock/tests/shell/test_helper.bash`

**Step 1: Create test helper**

Create `/root/projects/interlock/tests/shell/test_helper.bash`:

```bash
#!/usr/bin/env bash
# Shared test helper for interlock bats tests.

SCRIPTS_DIR="$(cd "$(dirname "${BATS_TEST_DIRNAME}")/../scripts" && pwd)"

# Override signal dir to temp for test isolation
setup() {
    export TEST_SIGNAL_DIR="$(mktemp -d)"
    export INTERLOCK_SIGNAL_DIR="$TEST_SIGNAL_DIR"
}

teardown() {
    rm -rf "$TEST_SIGNAL_DIR"
}
```

**Step 2: Write test file**

Create `/root/projects/interlock/tests/shell/interlock_signal.bats`:

```bash
#!/usr/bin/env bats
# Tests for scripts/interlock-signal.sh

setup() {
    load test_helper
    export INTERLOCK_SIGNAL_DIR="$TEST_SIGNAL_DIR"
    # Mock project slug and agent id
    export INTERLOCK_PROJECT_SLUG="my-project"
    export INTERMUTE_AGENT_ID="agent-abc123"
}

teardown() {
    rm -rf "$TEST_SIGNAL_DIR"
}

@test "signal: creates signal directory with mode 0700" {
    rm -rf "$TEST_SIGNAL_DIR"
    run bash "$SCRIPTS_DIR/interlock-signal.sh" reserve "reserved src/*.go"
    assert_success
    [[ -d "$TEST_SIGNAL_DIR" ]]
    local perms
    perms=$(stat -c '%a' "$TEST_SIGNAL_DIR" 2>/dev/null || stat -f '%Lp' "$TEST_SIGNAL_DIR")
    [[ "$perms" == "700" ]]
}

@test "signal: reserve event writes valid JSON line" {
    run bash "$SCRIPTS_DIR/interlock-signal.sh" reserve "reserved src/*.go"
    assert_success
    local file="$TEST_SIGNAL_DIR/my-project-agent-abc123.jsonl"
    [[ -f "$file" ]]
    local line
    line=$(tail -1 "$file")
    echo "$line" | jq -e '.version == 1'
    echo "$line" | jq -e '.layer == "coordination"'
    echo "$line" | jq -e '.icon == "lock"'
    echo "$line" | jq -e '.text == "reserved src/*.go"'
    echo "$line" | jq -e '.priority == 3'
    echo "$line" | jq -e '.ts | length > 0'
}

@test "signal: release event uses unlock icon" {
    run bash "$SCRIPTS_DIR/interlock-signal.sh" release "released src/*.go"
    assert_success
    local file="$TEST_SIGNAL_DIR/my-project-agent-abc123.jsonl"
    local line
    line=$(tail -1 "$file")
    echo "$line" | jq -e '.icon == "unlock"'
    echo "$line" | jq -e '.priority == 3'
}

@test "signal: message event uses mail icon and priority 4" {
    run bash "$SCRIPTS_DIR/interlock-signal.sh" message "message from claude-2"
    assert_success
    local file="$TEST_SIGNAL_DIR/my-project-agent-abc123.jsonl"
    local line
    line=$(tail -1 "$file")
    echo "$line" | jq -e '.icon == "mail"'
    echo "$line" | jq -e '.priority == 4'
}

@test "signal: append-only (multiple writes accumulate)" {
    bash "$SCRIPTS_DIR/interlock-signal.sh" reserve "reserved src/*.go"
    bash "$SCRIPTS_DIR/interlock-signal.sh" release "released src/*.go"
    bash "$SCRIPTS_DIR/interlock-signal.sh" message "message from claude-2"
    local file="$TEST_SIGNAL_DIR/my-project-agent-abc123.jsonl"
    local count
    count=$(wc -l < "$file")
    [[ "$count" -eq 3 ]]
}

@test "signal: each event is under 200 bytes" {
    bash "$SCRIPTS_DIR/interlock-signal.sh" reserve "reserved src/internal/storage/sqlite/resilient.go"
    local file="$TEST_SIGNAL_DIR/my-project-agent-abc123.jsonl"
    local line
    line=$(tail -1 "$file")
    local len=${#line}
    [[ "$len" -lt 200 ]]
}

@test "signal: ts field is ISO 8601 UTC" {
    bash "$SCRIPTS_DIR/interlock-signal.sh" reserve "reserved README.md"
    local file="$TEST_SIGNAL_DIR/my-project-agent-abc123.jsonl"
    local ts
    ts=$(tail -1 "$file" | jq -r '.ts')
    # Matches YYYY-MM-DDTHH:MM:SSZ format
    [[ "$ts" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$ ]]
}

@test "signal: unknown event type exits with error" {
    run bash "$SCRIPTS_DIR/interlock-signal.sh" unknown "some text"
    assert_failure
}

@test "signal: missing agent id exits silently" {
    unset INTERMUTE_AGENT_ID
    run bash "$SCRIPTS_DIR/interlock-signal.sh" reserve "reserved foo"
    assert_success
    # No file should be created — signal is a no-op without agent identity
    [[ ! -f "$TEST_SIGNAL_DIR/my-project-.jsonl" ]]
}

@test "signal: missing jq exits silently" {
    # Temporarily hide jq from PATH
    run bash -c "PATH=/usr/bin/nonexistent:$PATH bash '$SCRIPTS_DIR/interlock-signal.sh' reserve 'test'"
    # Should not crash — exits 0 gracefully
    assert_success
}

@test "signal: derives project slug from git if INTERLOCK_PROJECT_SLUG unset" {
    unset INTERLOCK_PROJECT_SLUG
    # Run from a git repo
    local tmpgit
    tmpgit=$(mktemp -d)
    git -C "$tmpgit" init -q
    run bash -c "cd '$tmpgit' && INTERMUTE_AGENT_ID=agent-test INTERLOCK_SIGNAL_DIR='$TEST_SIGNAL_DIR' bash '$SCRIPTS_DIR/interlock-signal.sh' reserve 'test'"
    assert_success
    # File should be named after the git dir basename
    local slug
    slug=$(basename "$tmpgit")
    [[ -f "$TEST_SIGNAL_DIR/${slug}-agent-test.jsonl" ]]
    rm -rf "$tmpgit"
}
```

**Step 3: Run tests to verify they fail**

Run: `bats /root/projects/interlock/tests/shell/interlock_signal.bats`
Expected: FAIL — `scripts/interlock-signal.sh` does not exist.

**Step 4: Create the signal writer script**

Create `/root/projects/interlock/scripts/interlock-signal.sh`:

```bash
#!/usr/bin/env bash
# Signal file writer for interlock companion plugin.
#
# Emits normalized JSONL signal events for interline consumption.
# Append-only writes using >> (O_APPEND, atomic for <4KB on Linux).
#
# Usage:
#   interlock-signal.sh <event-type> <text>
#
# Event types:
#   reserve  — file reservation created (icon: lock, priority: 3)
#   release  — file reservation released (icon: unlock, priority: 3)
#   message  — message received from another agent (icon: mail, priority: 4)
#
# Environment:
#   INTERMUTE_AGENT_ID       — agent UUID (required, no-op if missing)
#   INTERLOCK_PROJECT_SLUG   — project slug (optional, derived from git if unset)
#   INTERLOCK_SIGNAL_DIR     — signal directory (default: /var/run/intermute/signals)
#
# Schema:
#   {"version":1,"layer":"coordination","icon":"...","text":"...","priority":N,"ts":"..."}
#
# Exit: 0 on success or graceful skip, 1 on invalid event type

set -euo pipefail

# Guard: fail-open if jq is missing
if ! command -v jq &>/dev/null; then
    exit 0
fi

EVENT_TYPE="${1:-}"
TEXT="${2:-}"

# Validate event type
case "$EVENT_TYPE" in
    reserve)  ICON="lock";   PRIORITY=3 ;;
    release)  ICON="unlock"; PRIORITY=3 ;;
    message)  ICON="mail";   PRIORITY=4 ;;
    *)
        echo "error: unknown event type: $EVENT_TYPE (expected: reserve, release, message)" >&2
        exit 1
        ;;
esac

# Guard: no-op without agent identity
AGENT_ID="${INTERMUTE_AGENT_ID:-}"
if [[ -z "$AGENT_ID" ]]; then
    exit 0
fi

# Derive project slug
SLUG="${INTERLOCK_PROJECT_SLUG:-}"
if [[ -z "$SLUG" ]]; then
    SLUG=$(basename "$(git rev-parse --show-toplevel 2>/dev/null)" 2>/dev/null || echo "unknown")
fi

# Signal directory (default: /var/run/intermute/signals)
SIGNAL_DIR="${INTERLOCK_SIGNAL_DIR:-/var/run/intermute/signals}"

# Create directory with mode 0700 if missing
if [[ ! -d "$SIGNAL_DIR" ]]; then
    mkdir -p -m 0700 "$SIGNAL_DIR"
fi

# ISO 8601 UTC timestamp
TS=$(date -u +%FT%TZ)

# Construct JSON line and append (>> uses O_APPEND)
jq -nc \
    --argjson version 1 \
    --arg layer "coordination" \
    --arg icon "$ICON" \
    --arg text "$TEXT" \
    --argjson priority "$PRIORITY" \
    --arg ts "$TS" \
    '{version:$version,layer:$layer,icon:$icon,text:$text,priority:$priority,ts:$ts}' \
    >> "${SIGNAL_DIR}/${SLUG}-${AGENT_ID}.jsonl"
```

**Step 5: Make executable and run tests**

Run:
```bash
chmod +x /root/projects/interlock/scripts/interlock-signal.sh
bats /root/projects/interlock/tests/shell/interlock_signal.bats
```
Expected: All 11 tests PASS.

**Step 6: Commit**

```bash
cd /root/projects/interlock
git add scripts/interlock-signal.sh tests/shell/test_helper.bash tests/shell/interlock_signal.bats
git commit -m "feat(f9): add signal file writer script with tests"
```

**Acceptance criteria:**
- [ ] `scripts/interlock-signal.sh` exists and is executable
- [ ] Signal directory created with mode 0700
- [ ] Append-only writes via `>>`
- [ ] Schema: `{"version":1,"layer":"coordination","icon":"...","text":"...","priority":N,"ts":"..."}`
- [ ] Events under 200 bytes each
- [ ] Graceful no-op when `INTERMUTE_AGENT_ID` unset or `jq` missing
- [ ] All 11 bats tests pass

---

### Task 2: Hook Integration Call Sites

**Files:**
- Modify: `/root/projects/interlock/hooks/session-start.sh` (add signal emission after registration)
- Modify: `/root/projects/interlock/hooks/stop.sh` (add signal emission after cleanup)
- Create: `/root/projects/interlock/tests/shell/hook_signals.bats`

**Step 1: Write test file**

Create `/root/projects/interlock/tests/shell/hook_signals.bats`:

```bash
#!/usr/bin/env bats
# Tests for signal emission from hooks

setup() {
    load test_helper
    export INTERLOCK_SIGNAL_DIR="$TEST_SIGNAL_DIR"
    export INTERLOCK_PROJECT_SLUG="test-project"
    export INTERMUTE_AGENT_ID="agent-hook-test"
}

teardown() {
    rm -rf "$TEST_SIGNAL_DIR"
}

@test "hook-signals: session-start emits register signal" {
    # Simulate what session-start.sh does after registration
    bash "$SCRIPTS_DIR/interlock-signal.sh" reserve "agent registered: claude-dev"
    local file="$TEST_SIGNAL_DIR/test-project-agent-hook-test.jsonl"
    [[ -f "$file" ]]
    tail -1 "$file" | jq -e '.icon == "lock"'
}

@test "hook-signals: stop emits release-all signal" {
    # Simulate what stop.sh does after cleanup
    bash "$SCRIPTS_DIR/interlock-signal.sh" release "agent deregistered: all reservations released"
    local file="$TEST_SIGNAL_DIR/test-project-agent-hook-test.jsonl"
    [[ -f "$file" ]]
    tail -1 "$file" | jq -e '.icon == "unlock"'
}

@test "hook-signals: signal file accumulates across hook lifecycle" {
    bash "$SCRIPTS_DIR/interlock-signal.sh" reserve "agent registered: claude-dev"
    bash "$SCRIPTS_DIR/interlock-signal.sh" reserve "reserved src/*.go"
    bash "$SCRIPTS_DIR/interlock-signal.sh" message "message from claude-2"
    bash "$SCRIPTS_DIR/interlock-signal.sh" release "released src/*.go"
    bash "$SCRIPTS_DIR/interlock-signal.sh" release "agent deregistered: all reservations released"
    local file="$TEST_SIGNAL_DIR/test-project-agent-hook-test.jsonl"
    local count
    count=$(wc -l < "$file")
    [[ "$count" -eq 5 ]]
}
```

**Step 2: Add signal emission to session-start.sh**

In `/root/projects/interlock/hooks/session-start.sh`, after the agent registration block (where `INTERMUTE_AGENT_ID` is set and exported to `CLAUDE_ENV_FILE`), add:

```bash
# Emit signal: agent registered
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SIGNAL_SCRIPT="${SCRIPT_DIR}/../scripts/interlock-signal.sh"
if [[ -x "$SIGNAL_SCRIPT" ]]; then
    bash "$SIGNAL_SCRIPT" reserve "agent registered: ${AGENT_NAME}" 2>/dev/null || true
fi
```

**Step 3: Add signal emission to stop.sh**

In `/root/projects/interlock/hooks/stop.sh`, after the release-all and deregistration block, add:

```bash
# Emit signal: agent deregistered
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SIGNAL_SCRIPT="${SCRIPT_DIR}/../scripts/interlock-signal.sh"
if [[ -x "$SIGNAL_SCRIPT" ]]; then
    bash "$SIGNAL_SCRIPT" release "agent deregistered: all reservations released" 2>/dev/null || true
fi
```

**Step 4: Run tests**

Run: `bats /root/projects/interlock/tests/shell/hook_signals.bats`
Expected: All 3 tests PASS.

**Step 5: Commit**

```bash
cd /root/projects/interlock
git add hooks/session-start.sh hooks/stop.sh tests/shell/hook_signals.bats
git commit -m "feat(f9): emit signals from session-start and stop hooks"
```

**Acceptance criteria:**
- [ ] SessionStart hook emits signal after agent registration
- [ ] Stop hook emits signal after deregistration/cleanup
- [ ] Signal emission uses `2>/dev/null || true` (fire-and-forget, never crashes hooks)
- [ ] All 3 hook signal tests pass

---

### Task 3: MCP Tool Wrapper Signal Emission + Structural Tests

**Files:**
- Modify: `/root/projects/interlock/bin/interlock-mcp` (add signal calls after reserve/release/message tools)
- Create: `/root/projects/interlock/tests/structural/test_f9_signals.py`

**Step 1: Write structural test file**

Create `/root/projects/interlock/tests/structural/test_f9_signals.py`:

```python
"""Structural tests for F9 signal file adapter."""
import json
import os
import re
import stat
import subprocess

INTERLOCK_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS_DIR = os.path.join(INTERLOCK_ROOT, "scripts")
SIGNAL_SCRIPT = os.path.join(SCRIPTS_DIR, "interlock-signal.sh")


class TestSignalScriptExists:
    """Verify the signal writer script exists and is well-formed."""

    def test_script_exists(self):
        assert os.path.isfile(SIGNAL_SCRIPT), f"Missing: {SIGNAL_SCRIPT}"

    def test_script_is_executable(self):
        mode = os.stat(SIGNAL_SCRIPT).st_mode
        assert mode & stat.S_IXUSR, "interlock-signal.sh must be executable"

    def test_script_passes_syntax_check(self):
        result = subprocess.run(
            ["bash", "-n", SIGNAL_SCRIPT], capture_output=True, text=True
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"

    def test_script_has_shebang(self):
        with open(SIGNAL_SCRIPT) as f:
            first_line = f.readline().strip()
        assert first_line.startswith("#!/"), "Missing shebang"

    def test_script_uses_set_euo_pipefail(self):
        with open(SIGNAL_SCRIPT) as f:
            content = f.read()
        assert "set -euo pipefail" in content, "Must use strict bash mode"


class TestSignalSchema:
    """Verify signal events match the normalized schema."""

    def test_reserve_event_schema(self):
        """Run the script and validate JSON output."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            env = os.environ.copy()
            env["INTERLOCK_SIGNAL_DIR"] = tmpdir
            env["INTERLOCK_PROJECT_SLUG"] = "test-project"
            env["INTERMUTE_AGENT_ID"] = "agent-test"
            result = subprocess.run(
                ["bash", SIGNAL_SCRIPT, "reserve", "reserved src/*.go"],
                env=env,
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, f"Script failed: {result.stderr}"

            signal_file = os.path.join(tmpdir, "test-project-agent-test.jsonl")
            assert os.path.isfile(signal_file), "Signal file not created"

            with open(signal_file) as f:
                line = f.readline().strip()

            event = json.loads(line)
            assert event["version"] == 1, "version must be 1"
            assert event["layer"] == "coordination", "layer must be coordination"
            assert event["icon"] == "lock", "reserve icon must be lock"
            assert event["priority"] == 3, "reserve priority must be 3"
            assert "ts" in event, "Must have timestamp"
            assert re.match(
                r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", event["ts"]
            ), "ts must be ISO 8601 UTC"

    def test_event_under_200_bytes(self):
        """Each signal event must be under 200 bytes."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            env = os.environ.copy()
            env["INTERLOCK_SIGNAL_DIR"] = tmpdir
            env["INTERLOCK_PROJECT_SLUG"] = "test-project"
            env["INTERMUTE_AGENT_ID"] = "agent-test"
            # Use a reasonably long text to stress-test size
            long_text = "reserved src/internal/storage/sqlite/resilient_integration_test.go"
            subprocess.run(
                ["bash", SIGNAL_SCRIPT, "reserve", long_text],
                env=env,
                capture_output=True,
                text=True,
            )
            signal_file = os.path.join(tmpdir, "test-project-agent-test.jsonl")
            with open(signal_file) as f:
                line = f.readline().strip()
            assert len(line) < 200, f"Event is {len(line)} bytes, must be <200"

    def test_all_three_event_types(self):
        """Verify all event types produce valid JSON with correct icons."""
        import tempfile

        expected = {
            "reserve": ("lock", 3),
            "release": ("unlock", 3),
            "message": ("mail", 4),
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            env = os.environ.copy()
            env["INTERLOCK_SIGNAL_DIR"] = tmpdir
            env["INTERLOCK_PROJECT_SLUG"] = "test-project"
            env["INTERMUTE_AGENT_ID"] = "agent-test"
            for event_type, (icon, priority) in expected.items():
                subprocess.run(
                    ["bash", SIGNAL_SCRIPT, event_type, f"test {event_type}"],
                    env=env,
                    capture_output=True,
                    text=True,
                )
            signal_file = os.path.join(tmpdir, "test-project-agent-test.jsonl")
            with open(signal_file) as f:
                lines = f.readlines()
            assert len(lines) == 3, f"Expected 3 lines, got {len(lines)}"
            for i, (event_type, (icon, priority)) in enumerate(expected.items()):
                event = json.loads(lines[i])
                assert event["icon"] == icon, f"{event_type}: icon should be {icon}"
                assert event["priority"] == priority, f"{event_type}: priority should be {priority}"


class TestSignalDirectoryCreation:
    """Verify signal directory is created with correct permissions."""

    def test_directory_created_with_0700(self):
        import tempfile

        parent = tempfile.mkdtemp()
        signal_dir = os.path.join(parent, "signals")
        env = os.environ.copy()
        env["INTERLOCK_SIGNAL_DIR"] = signal_dir
        env["INTERLOCK_PROJECT_SLUG"] = "test-project"
        env["INTERMUTE_AGENT_ID"] = "agent-test"
        subprocess.run(
            ["bash", SIGNAL_SCRIPT, "reserve", "test"],
            env=env,
            capture_output=True,
            text=True,
        )
        assert os.path.isdir(signal_dir), "Signal directory not created"
        mode = stat.S_IMODE(os.stat(signal_dir).st_mode)
        assert mode == 0o700, f"Directory mode is {oct(mode)}, expected 0700"
        # Cleanup
        import shutil

        shutil.rmtree(parent)


class TestGracefulDegradation:
    """Verify the script fails gracefully in edge cases."""

    def test_no_agent_id_is_noop(self):
        """Without INTERMUTE_AGENT_ID, script should exit 0 and write nothing."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            env = os.environ.copy()
            env["INTERLOCK_SIGNAL_DIR"] = tmpdir
            env["INTERLOCK_PROJECT_SLUG"] = "test-project"
            env.pop("INTERMUTE_AGENT_ID", None)
            result = subprocess.run(
                ["bash", SIGNAL_SCRIPT, "reserve", "test"],
                env=env,
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0
            # No files should be created
            assert len(os.listdir(tmpdir)) == 0

    def test_unknown_event_type_fails(self):
        """Unknown event type should exit non-zero."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            env = os.environ.copy()
            env["INTERLOCK_SIGNAL_DIR"] = tmpdir
            env["INTERLOCK_PROJECT_SLUG"] = "test-project"
            env["INTERMUTE_AGENT_ID"] = "agent-test"
            result = subprocess.run(
                ["bash", SIGNAL_SCRIPT, "badtype", "test"],
                env=env,
                capture_output=True,
                text=True,
            )
            assert result.returncode != 0


class TestMCPIntegration:
    """Verify MCP wrapper references the signal script."""

    def test_mcp_wrapper_calls_signal_script(self):
        """The MCP wrapper should reference interlock-signal.sh for reserve/release/message."""
        mcp_bin = os.path.join(INTERLOCK_ROOT, "bin", "interlock-mcp")
        if not os.path.isfile(mcp_bin):
            import pytest

            pytest.skip("MCP wrapper not yet created (F6 dependency)")
        with open(mcp_bin) as f:
            content = f.read()
        assert "interlock-signal.sh" in content, (
            "MCP wrapper must call interlock-signal.sh"
        )


class TestHookIntegration:
    """Verify hooks reference the signal script."""

    def test_session_start_hook_emits_signal(self):
        hook = os.path.join(INTERLOCK_ROOT, "hooks", "session-start.sh")
        if not os.path.isfile(hook):
            import pytest

            pytest.skip("SessionStart hook not yet created (F7 dependency)")
        with open(hook) as f:
            content = f.read()
        assert "interlock-signal.sh" in content, (
            "SessionStart hook must call interlock-signal.sh"
        )

    def test_stop_hook_emits_signal(self):
        hook = os.path.join(INTERLOCK_ROOT, "hooks", "stop.sh")
        if not os.path.isfile(hook):
            import pytest

            pytest.skip("Stop hook not yet created (F7 dependency)")
        with open(hook) as f:
            content = f.read()
        assert "interlock-signal.sh" in content, (
            "Stop hook must call interlock-signal.sh"
        )
```

**Step 2: Add signal emission to MCP tool wrapper**

In `/root/projects/interlock/bin/interlock-mcp` (the MCP stdio wrapper from F6), add signal calls after each relevant tool invocation. The MCP wrapper dispatches tools to intermute's HTTP API. After successful responses, emit signals.

If the MCP wrapper is a shell script, add after the `reserve_files` handler:
```bash
# Emit signal after successful reserve
if [[ "$http_status" == "201" ]]; then
    SIGNAL_SCRIPT="${SCRIPT_DIR}/../scripts/interlock-signal.sh"
    bash "$SIGNAL_SCRIPT" reserve "reserved ${pattern}" 2>/dev/null || true
fi
```

After the `release_files` handler:
```bash
# Emit signal after successful release
if [[ "$http_status" == "200" ]]; then
    SIGNAL_SCRIPT="${SCRIPT_DIR}/../scripts/interlock-signal.sh"
    bash "$SIGNAL_SCRIPT" release "released ${pattern}" 2>/dev/null || true
fi
```

After the `fetch_inbox` handler (when messages are present):
```bash
# Emit signal for new messages
if [[ "$message_count" -gt 0 ]]; then
    SIGNAL_SCRIPT="${SCRIPT_DIR}/../scripts/interlock-signal.sh"
    bash "$SIGNAL_SCRIPT" message "received ${message_count} message(s)" 2>/dev/null || true
fi
```

If the MCP wrapper is a Go binary, the signal emission is a `exec.Command` call to `interlock-signal.sh` with the same arguments. Use `cmd.Start()` (fire-and-forget, no `cmd.Wait()`).

**Note:** If F6 (MCP server) has not been implemented yet, this step creates the signal call pattern as code comments or a separate `scripts/mcp-signal-hooks.sh` that the MCP server will source. Mark the structural test with `pytest.skip` for MCP integration until F6 lands.

**Step 3: Run structural tests**

Run:
```bash
cd /root/projects/interlock && python3 -m pytest tests/structural/test_f9_signals.py -v
```
Expected: All tests PASS (MCP integration tests may skip if F6 not yet built).

**Step 4: Run all tests together**

Run:
```bash
bats /root/projects/interlock/tests/shell/*.bats
python3 -m pytest /root/projects/interlock/tests/structural/ -v
```
Expected: All shell and structural tests PASS.

**Step 5: Commit**

```bash
cd /root/projects/interlock
git add bin/interlock-mcp tests/structural/test_f9_signals.py
git commit -m "feat(f9): add MCP signal emission and structural tests"
```

**Acceptance criteria:**
- [ ] MCP wrapper emits signals after reserve, release, and message tools
- [ ] Signal emission is fire-and-forget (`2>/dev/null || true` or Go `cmd.Start()`)
- [ ] 15 structural tests pass (5 script, 3 schema, 1 directory, 2 degradation, 1 MCP, 2 hooks, 1 event types)
- [ ] All bats tests pass
- [ ] MCP integration tests skip gracefully if F6 not yet implemented

---

## Pre-flight Checklist

- [ ] Verify interlock project directory exists: `ls /root/projects/interlock/`
- [ ] Verify `jq` is installed: `jq --version`
- [ ] Verify `bats` is installed: `bats --version`
- [ ] Verify bash 4+ for `set -euo pipefail`: `bash --version`
- [ ] Read existing hook scripts if they exist: `ls /root/projects/interlock/hooks/`
- [ ] Read existing MCP wrapper if it exists: `ls /root/projects/interlock/bin/`
- [ ] Confirm no existing signal code: `grep -r 'interlock-signal' /root/projects/interlock/ 2>/dev/null || echo "clean"`

## Post-execution Checklist

- [ ] All 3 tasks completed
- [ ] `scripts/interlock-signal.sh` exists and is executable
- [ ] `bash -n scripts/interlock-signal.sh` passes
- [ ] Signal directory created with mode 0700
- [ ] Events are <200 bytes each
- [ ] Schema matches: `{"version":1,"layer":"coordination","icon":"...","text":"...","priority":N,"ts":"..."}`
- [ ] 3 event types: reserve (lock/3), release (unlock/3), message (mail/4)
- [ ] All bats tests pass: `bats tests/shell/*.bats`
- [ ] All structural tests pass: `python3 -m pytest tests/structural/ -v`
- [ ] Signal emission is fire-and-forget in all call sites (never crashes callers)
- [ ] Bead Clavain-rmvl updated with completion status
