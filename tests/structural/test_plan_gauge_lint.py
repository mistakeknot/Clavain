"""Regression: scripts/plan-gauge-lint.py catches the pilot-1 gauge defects.

Pilot 1 (shadow-work, 2026-07-27) ran three defects through two independently
authored plans, twice. Across four executions every one of ~60 edits applied
byte-exact and every single stop was a defect in the plan's OWN verify block —
six of them, five sharing one shape: the plan's emitted text is simultaneously
the artifact AND an input to a checker the same author wrote, and nobody
executed one against the other.

Two frontier authors, a frontier reviewer, and the harness all shipped an
instance of it, so "review the gauge" is not a control. These tests pin the
mechanical one.

The interesting property is the differential in
``test_repair_clears_only_the_repaired_class``: the linter must track the real
defect state, not merely react to plan size. A checker that fires on every long
plan would pass the six-defect replay and still be useless.
"""

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "plan-gauge-lint.py"


def run_lint(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True,
    )


def codes(out: str) -> set[str]:
    return {tok for tok in out.split() if tok.startswith("GAUGE") and tok[5:].isdigit()}


def test_script_exists_and_is_executable():
    assert SCRIPT.is_file(), f"missing {SCRIPT}"
    assert SCRIPT.stat().st_mode & 0o111, "plan-gauge-lint.py must be executable"


def test_self_test_replays_all_seven_known_defects():
    """--self-test must catch every known defect AND stay clean on the control.

    Six defects came out of pilot 1; the seventh (PF-C) is the pattern F
    new-file shape, a plan whose only edit is a Create block.
    """
    r = run_lint("--self-test")
    assert r.returncode == 0, f"self-test failed:\n{r.stdout}\n{r.stderr}"
    assert "caught 7/7 known defects" in r.stdout, r.stdout
    assert "no false positives" in r.stdout, r.stdout
    assert "SELF-TEST PASSED" in r.stdout


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """A tree with the two files the fixtures below edit."""
    (tmp_path / "src").mkdir()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "src" / "main.rs").write_text("fn main() {}\n")
    (tmp_path / "scripts" / "check.sh").write_text(
        "#!/usr/bin/env bash\n"
        "awk 'BEGIN {\n"
        "  print \"hello\"\n"
        "}'\n"
    )
    return tmp_path


SELF_MATCH_PLAN = """
## Task 1

Edit `src/main.rs`.

old_string:
```rust
fn main() {}
```

new_string:
```rust
/// `AppExit` is unreliable during teardown.
fn main() {}
```

### Verify Task 1

```bash
grep -n "AppExit" src/main.rs
```

Expected: prints NOTHING (exit code 1).
"""


def test_self_match_is_flagged(repo: Path):
    """GAUGE001 - the verify forbids a token the plan's own edit writes."""
    plan = repo / "plan.md"
    plan.write_text(SELF_MATCH_PLAN)
    r = run_lint(str(plan), "--repo-root", str(repo))
    assert r.returncode == 1
    assert "GAUGE001" in codes(r.stdout), r.stdout


def test_self_match_not_flagged_when_the_edit_removes_the_token(repo: Path):
    """The mirror image: a plan that DELETES every match must stay clean.

    This is the check that separates 'dry-runs the edits' from 'greps the
    pre-edit tree'. Without applying the edit first, the pre-existing token
    would be reported and every removal plan would be a false positive.
    """
    (repo / "src" / "main.rs").write_text("fn main() { AppExit::now(); }\n")
    plan = repo / "plan.md"
    plan.write_text("""
## Task 1

Edit `src/main.rs`.

old_string:
```rust
fn main() { AppExit::now(); }
```

new_string:
```rust
fn main() {}
```

### Verify Task 1

```bash
grep -n "AppExit" src/main.rs
```

Expected: prints NOTHING (exit code 1).
""")
    r = run_lint(str(plan), "--repo-root", str(repo))
    assert "GAUGE001" not in codes(r.stdout), (
        "a plan that removes the token must not be flagged — the linter is "
        f"reading the pre-edit tree:\n{r.stdout}"
    )


def test_unescaped_metachar_is_flagged(repo: Path):
    """GAUGE002 - `.` in a literal pattern silently over-matches."""
    plan = repo / "plan.md"
    plan.write_text("""
## Task 1

Edit `src/main.rs`.

old_string:
```rust
fn main() {}
```

new_string:
```rust
/// the owner displayed a frame, and never displayed another
fn main() { let x = r.displayed; }
```

### Verify Task 1

```bash
grep -c "r.displayed" src/main.rs
```

Expected: `grep -c "r.displayed" src/main.rs` -> `1`.
""")
    r = run_lint(str(plan), "--repo-root", str(repo))
    assert "GAUGE002" in codes(r.stdout), r.stdout
    assert "grep -F" in r.stdout


def test_grep_dash_f_is_not_flagged(repo: Path):
    """The repaired form must be clean, or the fix has nowhere to land."""
    plan = repo / "plan.md"
    plan.write_text("""
## Task 1

Edit `src/main.rs`.

old_string:
```rust
fn main() {}
```

new_string:
```rust
/// the owner displayed a frame, and never displayed another
fn main() { let x = r.displayed; }
```

### Verify Task 1

```bash
grep -cF "r.displayed" src/main.rs
```

Expected: `grep -cF "r.displayed" src/main.rs` -> `1`.
""")
    r = run_lint(str(plan), "--repo-root", str(repo))
    assert "GAUGE002" not in codes(r.stdout), r.stdout


def test_shell_quote_collision_is_flagged(repo: Path):
    """GAUGE003 - an apostrophe in emitted text closes the enclosing quote."""
    plan = repo / "plan.md"
    plan.write_text("""
## Task 1

Edit `scripts/check.sh`.

Old:
```bash
  print "hello"
```

New:
```bash
  print "hello"
  # the sink's rate must equal presents per frame
  if (x > 1) {
    print "more"
  }
```

### Verify Task 1

```bash
bash -n scripts/check.sh && echo SYNTAX_OK
```

Expected: `SYNTAX_OK`.
""")
    r = run_lint(str(plan), "--repo-root", str(repo))
    assert "GAUGE003" in codes(r.stdout), r.stdout
    assert "will not parse" in r.stdout


def test_repair_clears_only_the_repaired_class(repo: Path):
    """The differential that proves the linter tracks defects, not plan size.

    One plan carries two independent defects. Repairing exactly one must clear
    exactly one code and leave the other standing.
    """
    body = """
## Task 1

Edit `src/main.rs`.

old_string:
```rust
fn main() {}
```

new_string:
```rust
/// the owner displayed a frame, and never displayed another
/// `AppExit` is unreliable during teardown.
fn main() { let x = r.displayed; }
```

### Verify Task 1

```bash
%GREP% "r.displayed" src/main.rs
grep -n "AppExit" src/main.rs
```

Expected: `%GREP% "r.displayed" src/main.rs` -> `1`; the second grep prints
NOTHING (exit code 1).
"""
    plan = repo / "plan.md"

    plan.write_text(body.replace("%GREP%", "grep -c"))
    before = codes(run_lint(str(plan), "--repo-root", str(repo)).stdout)
    assert {"GAUGE001", "GAUGE002"} <= before, f"expected both defects, got {before}"

    plan.write_text(body.replace("%GREP%", "grep -cF"))
    after = codes(run_lint(str(plan), "--repo-root", str(repo)).stdout)
    assert "GAUGE002" not in after, f"the repaired class should be gone: {after}"
    assert "GAUGE001" in after, (
        f"the UNrepaired class must survive; a linter that clears everything "
        f"when one thing is fixed is not measuring defects: {after}"
    )


def test_exit_code_is_zero_on_a_clean_plan(repo: Path):
    plan = repo / "plan.md"
    plan.write_text("""
## Task 1

Edit `src/main.rs`.

old_string:
```rust
fn main() {}
```

new_string:
```rust
fn main() { let x = 1; }
```

### Verify Task 1

```bash
grep -cF "let x = 1" src/main.rs
```

Expected: `grep -cF "let x = 1" src/main.rs` -> `1`.
""")
    r = run_lint(str(plan), "--repo-root", str(repo))
    assert r.returncode == 0, f"clean plan should exit 0:\n{r.stdout}"


def test_json_output_is_machine_readable(repo: Path):
    import json
    plan = repo / "plan.md"
    plan.write_text(SELF_MATCH_PLAN)
    r = run_lint(str(plan), "--repo-root", str(repo), "--json")
    payload = json.loads(r.stdout)
    assert payload["findings"], payload
    assert all({"code", "title", "line", "detail"} <= set(f) for f in payload["findings"])


CREATE_PLAN = """
## Task 1

Create `scripts/hello.sh` with:
```bash
#!/usr/bin/env bash
echo "TODO: replace me"
```

### Verify Task 1

```bash
grep -c "TODO" scripts/hello.sh
```

Expected: %EXPECT%
"""


def test_create_block_enters_the_virtual_tree(repo: Path):
    """GAUGE001 on a plan whose ONLY edit is a Create block.

    Before the linter learned the new-file grammar the created file never
    entered the virtual tree, so a verify that forbids text the file
    contains was ungauged.
    """
    import json
    plan = repo / "plan.md"
    plan.write_text(CREATE_PLAN.replace("%EXPECT%", "prints NOTHING (exit 1)."))
    r = run_lint(str(plan), "--repo-root", str(repo), "--json")
    assert r.returncode == 1, r.stdout
    payload = json.loads(r.stdout)
    assert any(f["code"] == "GAUGE001" for f in payload["findings"]), payload


def test_create_block_is_clean_when_verify_expects_the_text(repo: Path):
    """The same new-file plan is clean when the verify expects the match."""
    import json
    plan = repo / "plan.md"
    plan.write_text(CREATE_PLAN.replace("%EXPECT%", '`grep -c "TODO" scripts/hello.sh` -> `1`.'))
    r = run_lint(str(plan), "--repo-root", str(repo), "--json")
    assert r.returncode == 0, r.stdout
    payload = json.loads(r.stdout)
    assert payload["findings"] == [], payload


def test_bats_path_is_attributed(repo: Path):
    """An edit to a .bats file is attributed to its own path.

    PATH_RE had no bats in its extension allowlist, so the edit inherited
    whatever path the plan named last (or none), dropped out of the virtual
    tree, and the self-match went unreported.
    """
    (repo / "tests" / "shell").mkdir(parents=True)
    (repo / "tests" / "shell" / "x.bats").write_text("run true\n")
    plan = repo / "plan.md"
    plan.write_text("""
## Task 1

Edit `tests/shell/x.bats`.

old_string:
```bash
run true
```

new_string:
```bash
run true # MARK
```

### Verify Task 1

```bash
grep -c MARK tests/shell/x.bats
```

Expected: prints NOTHING (exit 1).
""")
    r = run_lint(str(plan), "--repo-root", str(repo))
    assert r.returncode == 1, r.stdout
    assert "GAUGE001" in codes(r.stdout), r.stdout
