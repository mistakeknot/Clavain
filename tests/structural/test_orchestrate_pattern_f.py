"""Behavioral tests for orchestrate.py --pattern-f (goal 60771535) and the
process-group timeout (mk-kj2m).

dispatch.sh, pattern-f-verdict.sh and ic are replaced by stubs through
CLAVAIN_DISPATCH_SH, CLAVAIN_VERDICT_SH and CLAVAIN_IC_BIN. The gauge and its
--apply are the real scripts/plan-gauge-lint.py, so an exact item here is
applied by the tool exactly as in a live run.
"""

import importlib.util
import json
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from test_plan_gauge_apply import APP, BRIEF, GOOD, OTHER


@pytest.fixture(scope="module")
def orc(project_root: Path):
    spec = importlib.util.spec_from_file_location(
        "orchestrate_pf", project_root / "scripts" / "orchestrate.py"
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["orchestrate_pf"] = mod
    spec.loader.exec_module(mod)
    yield mod
    sys.modules.pop("orchestrate_pf", None)


def _sh(path: Path, body: str) -> Path:
    path.write_text("#!/usr/bin/env bash\nset -uo pipefail\n" + textwrap.dedent(body))
    path.chmod(0o755)
    return path


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True,
    ).stdout.strip()


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    (r / "src").mkdir(parents=True)
    (r / "src" / "app.py").write_text(APP)
    (r / "src" / "other.py").write_text(OTHER)
    (r / ".gitignore").write_text(".clavain/\n")
    subprocess.run(["git", "init", "-q", "-b", "main", str(r)], check=True)
    _git(r, "config", "user.email", "pf@test")
    _git(r, "config", "user.name", "pf")
    _git(r, "config", "commit.gpgsign", "false")
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "init")
    return r


STUB_DISPATCH = r'''
role=""; out=""; C=""; prompt=""; dry=0
args=("$@")
while [[ $# -gt 0 ]]; do
  case "$1" in
    --role) role="$2"; shift 2;;
    -o) out="$2"; shift 2;;
    -C) C="$2"; shift 2;;
    --prompt-file) prompt="$2"; shift 2;;
    --dry-run) dry=1; shift;;
    *) shift;;
  esac
done
printf '%s\n' "${args[*]}" >> "$PF_DISPATCH_LOG"
if [[ $dry == 1 ]]; then
  if [[ $role == validation ]]; then
    if [[ -z "${PF_STUB_CODEX_SEAT:-}" ]]; then echo "claude --model stub-validator x"; else echo "codex exec -m stub-validation x"; fi
  else
    echo "codex exec -m stub-executor x"
  fi
  exit 0
fi
[[ -f "$C/.clavain/intercore.db" ]] || { echo "no intercore store in $C" >&2; exit 97; }
case "$role" in
  validation)
    rp=$(sed -n 's/.*Receipt command: cat \([^ ]*\)\..*/\1/p' "$prompt" | head -1)
    rec=$(cat "$rp")
    if [[ -n "${PF_STUB_SLEEP:-}" ]]; then
      ( sleep "$PF_STUB_SLEEP"; echo late > "$C/grandchild-survived" ) &
      sleep "$PF_STUB_SLEEP"
    fi
    if [[ -n "${PF_STUB_MUTATE:-}" ]]; then
      printf -- '--- VERDICT ---\nSTATUS: error\nSUMMARY: validation seat mutated the checkout: src/app.py\n---\n' > "$out.verdict"
      : > "$out"; exit 1
    fi
    [[ -n "${PF_STUB_TOUCH:-}" ]] && echo "seat wrote here" >> "$C/src/other.py"
    printf '%sVERDICT: %s\n%sCRITERION: %s\n%sRECEIPT: %s\n%sBEYOND THE GAUGE:\n%s\n' \
      "${PF_STUB_BULLET:-}" "${PF_STUB_VERDICT:-PASS}" "${PF_STUB_BULLET:-}" "${PF_STUB_CRITERION:-none}" "${PF_STUB_BULLET:-}" "${PF_STUB_RECEIPT:-$rec}" "${PF_STUB_BULLET:-}" "${PF_STUB_BEYOND:-- none}" > "$out"
    printf -- '--- VERDICT ---\nSTATUS: warn\nSUMMARY: stub\n---\n' > "$out.verdict"
    ;;
  routine-execution)
    [[ -n "${PF_STUB_EXEC_SLEEP:-}" ]] && sleep "$PF_STUB_EXEC_SLEEP"
    # PF_STUB_EXEC_FILE_<item id> names the file this item's executor edits (default src/app.py)
    var="PF_STUB_EXEC_FILE_$(basename "$C")"
    echo "from executor $(basename "$C")" >> "$C/${!var:-src/app.py}"
    git -C "$C" add -A && git -C "$C" commit -q -m "executor work"
    printf 'Did the thing.\nVERDICT: %s\nCRITERION: %s\n' "${PF_STUB_EXEC_VERDICT:-PASS}" "${PF_STUB_EXEC_CRITERION:-none}" > "$out"
    printf -- '--- VERDICT ---\nSTATUS: pass\nSUMMARY: stub\n---\n' > "$out.verdict"
    ;;
esac
'''


STUB_IC = r"""
store="${PF_IC_STORE:?}"; mkdir -p "$store"
args=()
while [[ $# -gt 0 ]]; do
  case "$1" in --db) shift 2;; --db=*|--json) shift;; *) args+=("$1"); shift;; esac
done
set -- "${args[@]}"
if [[ "${1:-}" == init ]]; then mkdir -p .clavain && : > .clavain/intercore.db; exit 0; fi
[[ "${1:-}" == coordination ]] || { echo "stub ic: unknown $1" >&2; exit 3; }
sub="$2"; shift 2
owner=""; scope=""; pattern=""; id=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --owner=*) owner="${1#--owner=}"; shift;; --scope=*) scope="${1#--scope=}"; shift;; --pattern=*) pattern="${1#--pattern=}"; shift;;
    --owner) owner="$2"; shift 2;; --scope) scope="$2"; shift 2;; --pattern) pattern="$2"; shift 2;;
    --ttl|--reason|--run|--type|--exclusive) shift 2;; --*) shift;; *) id="$1"; shift;;
  esac
done
overlap() { [[ "$1" == "$2" || "$1" == '**' || "$2" == '**' ]]; }
# check-then-create is one step, as it is in the real store
i=0; until mkdir "$store/.mutex" 2>/dev/null; do sleep 0.02; i=$((i+1)); [[ $i -gt 500 ]] && break; done
trap 'rmdir "$store/.mutex" 2>/dev/null' EXIT
case "$sub" in
  reserve)
    if [[ -n "${PF_STUB_IC_FAIL_PATTERN:-}" && "$pattern" == "$PF_STUB_IC_FAIL_PATTERN" ]]; then
      echo "stub ic: store exploded" >&2; exit 2
    fi
    for f in "$store"/*.lock; do
      [[ -e "$f" ]] || continue
      IFS=$'\t' read -r o s p < "$f"
      [[ "$s" == "$scope" && "$o" != "$owner" ]] || continue
      if overlap "$p" "$pattern"; then
        printf '{"conflict":{"blocker_id":"%s","blocker_owner":"%s","blocker_pattern":"%s"}}\n' "$(basename "$f" .lock)" "$o" "$p"
        exit 1
      fi
    done
    id="l$RANDOM$RANDOM$RANDOM"
    printf '%s\t%s\t%s\n' "$owner" "$scope" "$pattern" > "$store/$id.lock"
    printf '%s reserve %s %s cwd=%s\n' "$(date +%s)" "$owner" "$pattern" "$PWD" >> "$store/log"
    printf '{"lock":{"id":"%s","owner":"%s","scope":"%s","pattern":"%s"}}\n' "$id" "$owner" "$scope" "$pattern"
    ;;
  release)
    n=0
    for f in "$store"/*.lock; do
      [[ -e "$f" ]] || continue
      IFS=$'\t' read -r o s p < "$f"
      if { [[ -n "$id" && "$(basename "$f" .lock)" == "$id" ]]; } || { [[ -z "$id" && "$o" == "$owner" && "$s" == "$scope" ]]; }; then
        rm -f "$f"; n=$((n+1))
      fi
    done
    printf '%s release %s\n' "$(date +%s)" "$owner" >> "$store/log"
    printf '{"released":%d}\n' "$n"
    ;;
  list)
    echo "["; first=1
    for f in "$store"/*.lock; do
      [[ -e "$f" ]] || continue
      IFS=$'\t' read -r o s p < "$f"
      [[ $first == 1 ]] || echo ","; first=0
      printf '{"id":"%s","owner":"%s","scope":"%s","pattern":"%s"}' "$(basename "$f" .lock)" "$o" "$s" "$p"
    done
    echo "]"
    ;;
  *) echo "stub ic: unknown coordination $sub" >&2; exit 3;;
esac
"""


@pytest.fixture()
def stubs(tmp_path: Path, monkeypatch) -> dict:
    t = tmp_path / "tools"
    t.mkdir()
    register_log = tmp_path / "register.log"
    dispatch_log = tmp_path / "dispatch.log"
    _sh(t / "ic", STUB_IC)
    _sh(t / "verdict.sh", f'''
        if [[ "${{1:-}}" == "--list" ]]; then cat "{register_log}" 2>/dev/null || true; exit 0; fi
        if [[ -n "${{PF_VERDICT_FAIL:-}}" ]]; then echo "pattern-f-verdict: write not visible" >&2; exit 4; fi
        printf '%s\\n' "$*" >> "{register_log}"
    ''')
    _sh(t / "dispatch.sh", STUB_DISPATCH)
    monkeypatch.setenv("CLAVAIN_IC_BIN", str(t / "ic"))
    monkeypatch.setenv("CLAVAIN_VERDICT_SH", str(t / "verdict.sh"))
    monkeypatch.setenv("CLAVAIN_DISPATCH_SH", str(t / "dispatch.sh"))
    monkeypatch.setenv("PF_DISPATCH_LOG", str(dispatch_log))
    store = tmp_path / "icstore"
    monkeypatch.setenv("PF_IC_STORE", str(store))
    monkeypatch.setenv("ORC_PF_RESERVE_POLL", "0.2")
    for k in ("PF_STUB_SLEEP", "PF_STUB_MUTATE", "PF_STUB_VERDICT", "PF_STUB_CRITERION",
              "PF_STUB_RECEIPT", "PF_STUB_BEYOND", "PF_STUB_EXEC_VERDICT", "PF_VERDICT_FAIL",
              "PF_STUB_CODEX_SEAT", "PF_STUB_TOUCH", "PF_STUB_BULLET", "PF_STUB_EXEC_SLEEP",
              "PF_STUB_IC_FAIL_PATTERN"):
        monkeypatch.delenv(k, raising=False)
    register = tmp_path / "register.db"
    register.write_text("")
    return {"register_log": register_log, "dispatch_log": dispatch_log, "register": register, "store": store}


def _run_file(tmp_path: Path, repo: Path, items: list[tuple[str, Path, dict]],
              register: Path, timeout: int = 30, run_extra: dict | None = None) -> Path:
    body = ""
    for iid, plan, extra in items:
        body += f"  - id: {iid}\n    plan: {plan}\n"
        for k, v in extra.items():
            body += f"    {k}: {v}\n"
    head = "".join(f"{k}: {v}\n" for k, v in (run_extra or {}).items())
    text = (
        f"version: 1\nsession: sess-test\ngoal: g1\nregister: {register}\nrepo: {repo}\n"
        f"timeout: {timeout}\nproducer: author-model\n{head}trailers:\n  - 'Test-Trailer: yes'\nitems:\n{body}"
    )
    p = tmp_path / "run.pf.yaml"
    p.write_text(text)
    return p


def _packet(capsys) -> dict:
    out = capsys.readouterr().out
    return json.loads(out.strip().splitlines()[-1])


# ---------------------------------------------------------------------------
# mk-kj2m: the timeout kills the process group, not only dispatch.sh
# ---------------------------------------------------------------------------

def test_fixture_bites_without_group_kill(tmp_path: Path):
    """Control: subprocess.run(timeout=) kills the wrapper and its grandchild
    survives to write the marker. This is the bug; the fixture must bite."""
    marker = tmp_path / "survived"
    stub = _sh(tmp_path / "wrapper.sh", f"( sleep 1; echo late > {marker} ) &\nsleep 4\n")
    with pytest.raises(subprocess.TimeoutExpired):
        subprocess.run(["bash", str(stub)], timeout=0.5, capture_output=True)
    time.sleep(2)
    assert marker.exists(), "the control fixture did not reproduce the surviving grandchild"


def test_run_in_group_reaps_the_grandchild(orc, tmp_path: Path):
    marker = tmp_path / "survived"
    stub = _sh(tmp_path / "wrapper.sh", f"( sleep 1; echo late > {marker} ) &\nsleep 30\n")
    t0 = time.monotonic()
    rc, timed_out, _out, _err = orc.run_in_group(["bash", str(stub)], timeout=0.5)
    assert timed_out
    assert rc != 0
    time.sleep(2)
    assert not marker.exists(), "the grandchild outlived the timeout"
    assert time.monotonic() - t0 < 15


# ---------------------------------------------------------------------------
# --pattern-f
# ---------------------------------------------------------------------------

def test_exact_item_is_applied_by_the_tool_validated_registered_and_merged(orc, repo, tmp_path, stubs, capsys):
    plan = tmp_path / "exact.md"
    plan.write_text(GOOD)
    run_file = _run_file(tmp_path, repo, [("t1", plan, {})], stubs["register"])
    head0 = _git(repo, "rev-parse", "HEAD")

    results = orc.orchestrate_pattern_f(str(run_file))
    r = results[0]

    assert r.contract == "exact" and r.gauge_rc == 0
    assert r.status == "merged" and r.merged
    assert r.executor_model == "plan-gauge-lint.py --apply"
    assert r.executor_verdict == "PASS" and r.executor_commit
    assert r.validator_verdict == "PASS" and r.receipt_ok is True
    assert r.validator_model == "stub-validator"
    # applied and merged back into the repo, worktree gone, branch gone
    assert 'return "hello"' in (repo / "src" / "app.py").read_text()
    assert (repo / "src" / "new_module.py").exists()
    assert _git(repo, "rev-parse", "HEAD") == r.merge_commit == r.executor_commit != head0
    assert "Test-Trailer: yes" in _git(repo, "log", "-1", "--format=%B")
    assert not Path(r.worktree).exists()
    assert _git(repo, "branch", "--list", r.branch) == ""
    # register rows: executor replay, validator replay, --db explicit, commit named
    rows = stubs["register_log"].read_text().splitlines()
    assert len(rows) == 2 == r.register_rows and r.register_errors == 0
    assert "--role executor --kind replay --verdict PASS" in rows[0]
    assert f"--commit {r.executor_commit}" in rows[0]
    assert f"--db {stubs['register']}" in rows[0] and "--goal g1" in rows[0]
    assert "--role validator --kind replay --verdict PASS" in rows[1]
    # the seat got the plan, the producer identity and the worktree; no model executed the plan
    dispatch = stubs["dispatch_log"].read_text()
    assert f"--role validation --producer-identity author-model --plan {plan} -C {r.worktree}" in dispatch
    assert "--role routine-execution" not in dispatch
    packet = _packet(capsys)
    item = packet["items"][0]
    assert item["pilot"] == "t1" and item["lint_rc"] == 0 and item["register_rc"] == 0
    assert packet["register_readback"] == 2
    assert Path(packet["meter"]).exists()
    meter = json.loads(Path(packet["meter"]).read_text())
    assert meter["session"] == "sess-test" and meter["dispatches"][0]["role"] == "validation"


def test_receipt_mismatch_is_unrun_and_keeps_the_worktree(orc, repo, tmp_path, stubs, monkeypatch):
    monkeypatch.setenv("PF_STUB_RECEIPT", "receipt-bogus")
    plan = tmp_path / "exact.md"
    plan.write_text(GOOD)
    head0 = _git(repo, "rev-parse", "HEAD")
    r = orc.orchestrate_pattern_f(str(_run_file(tmp_path, repo, [("t1", plan, {})], stubs["register"])))[0]
    assert r.status == "validator_unrun" and r.validator_verdict == "UNRUN"
    assert r.receipt_ok is False and not r.merged
    assert _git(repo, "rev-parse", "HEAD") == head0
    assert Path(r.worktree).exists()
    rows = stubs["register_log"].read_text().splitlines()
    assert "--role validator --kind replay --verdict UNRUN" in rows[1]
    assert "receipt mismatch" in rows[1]


def test_brief_goes_to_the_role_executor_and_findings_become_rows(orc, repo, tmp_path, stubs, monkeypatch):
    monkeypatch.setenv("PF_STUB_BEYOND", "- the executor also touched src/other.py\n- no test covers the new branch")
    plan = tmp_path / "brief.md"
    plan.write_text(BRIEF)
    r = orc.orchestrate_pattern_f(str(_run_file(tmp_path, repo, [("b1", plan, {})], stubs["register"])))[0]
    assert r.contract == "brief" and r.status == "merged"
    assert r.executor_model == "stub-executor"
    assert "from executor" in (repo / "src" / "app.py").read_text()
    dispatch = stubs["dispatch_log"].read_text()
    assert "--role routine-execution" in dispatch and "-s workspace-write" in dispatch
    assert "--role validation --producer-identity stub-executor" in dispatch
    rows = stubs["register_log"].read_text().splitlines()
    assert len(rows) == 4
    assert "--role validator --kind independent --verdict FAIL" in rows[2]
    assert "the executor also touched src/other.py" in rows[2]
    assert "--note pf " in rows[2], "rows carry the run and item ids"
    assert r.independent_findings == 2 and r.beyond_gauge[1] == "no test covers the new branch"


def test_gauge_finding_writes_a_gate_row_and_spawns_nothing(orc, repo, tmp_path, stubs):
    # A brief with no Verification section: the brief gauge refuses it, so no
    # worktree, executor or seat ever exists for the item.
    plan = tmp_path / "brief.md"
    plan.write_text(BRIEF.replace("## Verification\n\n```bash\ntrue\n```\n\n", ""))
    r = orc.orchestrate_pattern_f(str(_run_file(tmp_path, repo, [("t1", plan, {})], stubs["register"])))[0]
    assert r.status == "gauge_failed" and r.gauge_rc != 0, r
    assert r.worktree is None and r.executor_commit is None
    rows = stubs["register_log"].read_text().splitlines()
    assert len(rows) == 1
    assert "--role gate --kind gate --verdict FAIL" in rows[0] and "--commit none" in rows[0]
    assert not stubs["dispatch_log"].exists()


def test_validator_timeout_kills_the_group_and_is_unrun(orc, repo, tmp_path, stubs, monkeypatch):
    monkeypatch.setenv("PF_STUB_SLEEP", "6")
    plan = tmp_path / "exact.md"
    plan.write_text(GOOD)
    t0 = time.monotonic()
    r = orc.orchestrate_pattern_f(str(_run_file(tmp_path, repo, [("t1", plan, {})], stubs["register"], timeout=2)))[0]
    assert r.status == "validator_unrun"
    assert "timed out" in (stubs["register_log"].read_text().splitlines()[1])
    while time.monotonic() - t0 < 8:
        time.sleep(0.5)
    assert not (Path(r.worktree) / "grandchild-survived").exists(), "the seat's grandchild outlived the timeout"


def test_mutating_seat_is_unrun(orc, repo, tmp_path, stubs, monkeypatch):
    monkeypatch.setenv("PF_STUB_MUTATE", "1")
    plan = tmp_path / "exact.md"
    plan.write_text(GOOD)
    r = orc.orchestrate_pattern_f(str(_run_file(tmp_path, repo, [("t1", plan, {})], stubs["register"])))[0]
    assert r.status == "validator_unrun" and not r.merged
    assert "mutated the checkout" in stubs["register_log"].read_text().splitlines()[1]


def test_validator_fail_parks_the_item_with_its_criterion(orc, repo, tmp_path, stubs, monkeypatch, capsys):
    monkeypatch.setenv("PF_STUB_VERDICT", "FAIL")
    monkeypatch.setenv("PF_STUB_CRITERION", "grep -n 'return \"hello\"' src/app.py")
    plan = tmp_path / "exact.md"
    plan.write_text(GOOD)
    r = orc.orchestrate_pattern_f(str(_run_file(tmp_path, repo, [("t1", plan, {})], stubs["register"])))[0]
    assert r.status == "validator_fail" and r.validator_criterion.startswith("grep -n")
    assert "--role validator --kind replay --verdict FAIL" in stubs["register_log"].read_text().splitlines()[1]
    assert _packet(capsys)["items"][0]["validator_strikes"] == 1


def test_register_write_failure_is_loud_but_does_not_stop_the_run(orc, repo, tmp_path, stubs, monkeypatch, capsys):
    monkeypatch.setenv("PF_VERDICT_FAIL", "1")
    plan = tmp_path / "exact.md"
    plan.write_text(GOOD)
    r = orc.orchestrate_pattern_f(str(_run_file(tmp_path, repo, [("t1", plan, {})], stubs["register"])))[0]
    assert r.status == "merged"
    assert r.register_rows == 0 and r.register_errors == 2
    captured = capsys.readouterr()
    assert "REGISTER WRITE FAILED" in captured.err
    packet = json.loads(captured.out.strip().splitlines()[-1])
    assert packet["items"][0]["register_rc"] == 4


def test_two_items_run_in_order_each_from_the_merged_head(orc, repo, tmp_path, stubs):
    exact = tmp_path / "exact.md"
    exact.write_text(GOOD)
    brief = tmp_path / "brief.md"
    brief.write_text(BRIEF)
    results = orc.orchestrate_pattern_f(str(_run_file(tmp_path, repo, [("b1", brief, {}), ("t2", exact, {})], stubs["register"])))
    assert [r.status for r in results] == ["merged", "merged"]
    text = (repo / "src" / "app.py").read_text()
    assert 'return "hello"' in text and "from executor" in text
    assert _git(repo, "log", "--format=%s", "-3").splitlines()[0].startswith("pf(t2)")


def test_dry_run_lists_items_without_dispatching(orc, repo, tmp_path, stubs, capsys):
    plan = tmp_path / "exact.md"
    plan.write_text(GOOD)
    assert orc.orchestrate_pattern_f(str(_run_file(tmp_path, repo, [("t1", plan, {})], stubs["register"])), dry_run=True) == []
    out = capsys.readouterr().out
    assert "plan-gauge-lint.py --apply (no model)" in out
    assert not stubs["dispatch_log"].exists()
    assert _git(repo, "worktree", "list").count("\n") == 0


def test_run_file_validation(orc, repo, tmp_path, stubs):
    bad = tmp_path / "bad.pf.yaml"
    bad.write_text(f"register: {stubs['register']}\nrepo: {repo}\nitems:\n  - id: 'a b'\n    plan: missing.md\n")
    with pytest.raises(ValueError) as ei:
        orc.load_pf_run(str(bad))
    msg = str(ei.value)
    assert "session is required" in msg and "plan not found" in msg and "branch-safe" in msg


def test_codex_seat_gets_workspace_write_and_a_bulleted_verdict_still_parses(orc, repo, tmp_path, stubs, monkeypatch):
    monkeypatch.setenv("PF_STUB_CODEX_SEAT", "1")
    monkeypatch.setenv("PF_STUB_BULLET", "• ")
    plan = tmp_path / "exact.md"
    plan.write_text(GOOD)
    r = orc.orchestrate_pattern_f(str(_run_file(tmp_path, repo, [("t1", plan, {})], stubs["register"])))[0]
    assert r.status == "merged" and r.validator_verdict == "PASS" and r.receipt_ok is True
    assert r.validator_model == "stub-validation"
    lines = [l for l in stubs["dispatch_log"].read_text().splitlines() if "--role validation" in l and "--dry-run" not in l]
    assert lines and "-s workspace-write" in lines[0]


def test_claude_seat_never_gets_the_codex_sandbox_flag(orc, repo, tmp_path, stubs):
    plan = tmp_path / "exact.md"
    plan.write_text(GOOD)
    orc.orchestrate_pattern_f(str(_run_file(tmp_path, repo, [("t1", plan, {})], stubs["register"])))
    lines = [l for l in stubs["dispatch_log"].read_text().splitlines() if "--role validation" in l and "--dry-run" not in l]
    assert lines and "-s workspace-write" not in lines[0]


def test_seat_that_writes_to_the_worktree_is_unrun(orc, repo, tmp_path, stubs, monkeypatch):
    monkeypatch.setenv("PF_STUB_TOUCH", "1")
    plan = tmp_path / "exact.md"
    plan.write_text(GOOD)
    r = orc.orchestrate_pattern_f(str(_run_file(tmp_path, repo, [("t1", plan, {})], stubs["register"])))[0]
    assert r.status == "validator_unrun" and not r.merged
    assert "mutated the worktree" in stubs["register_log"].read_text().splitlines()[1]


# ---------------------------------------------------------------------------
# goal a7f02287: max_parallel over reservations, one merge lock
# ---------------------------------------------------------------------------

def _executors(packet: dict) -> dict:
    with open(packet["meter"]) as f:
        meter = json.load(f)
    return meter, {d["item"]: d for d in meter["dispatches"] if d["role"] == "routine-execution"}


def _brief(tmp_path: Path, name: str = "brief.md") -> Path:
    p = tmp_path / name
    p.write_text(BRIEF)
    return p


def test_two_items_declaring_the_same_path_never_overlap(orc, repo, stubs, tmp_path, monkeypatch, capsys):
    """GATE fixture: both items declare src/app.py; the second waits for the
    first's release, and neither executor runs while the other holds it."""
    monkeypatch.setenv("PF_STUB_EXEC_SLEEP", "1.5")
    plan = _brief(tmp_path)
    rf = _run_file(tmp_path, repo, [("a", plan, {"files": "[src/app.py]"}), ("b", plan, {"files": "[src/app.py]"})],
                   stubs["register"], run_extra={"max_parallel": 2})
    orc.orchestrate_pattern_f(str(rf))
    packet = _packet(capsys)
    by = {i["id"]: i for i in packet["items"]}
    assert by["a"]["status"] == "merged" and by["b"]["status"] == "merged", by
    assert packet["max_parallel"] == 2
    meter, ex = _executors(packet)
    first, second = sorted(ex.values(), key=lambda d: d["started"])
    assert second["started"] >= first["finished"], (first, second)
    waited = [i for i in packet["items"] if i["wait_s"] >= 1.0]
    assert len(waited) == 1 and waited[0]["blocked_by"].startswith("pf/"), packet["items"]
    assert not list(stubs["store"].glob("*.lock")), "reservations were not released"
    text = (repo / "src" / "app.py").read_text()
    assert "from executor a" in text and "from executor b" in text


def test_disjoint_items_run_at_once_and_both_merge(orc, repo, stubs, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PF_STUB_EXEC_SLEEP", "1.5")
    monkeypatch.setenv("PF_STUB_EXEC_FILE_b", "src/other.py")
    plan = _brief(tmp_path)
    rf = _run_file(tmp_path, repo, [("a", plan, {"files": "[src/app.py]"}), ("b", plan, {"files": "[src/other.py]"})],
                   stubs["register"], run_extra={"max_parallel": 2})
    orc.orchestrate_pattern_f(str(rf))
    packet = _packet(capsys)
    assert [i["status"] for i in packet["items"]] == ["merged", "merged"], packet["items"]
    meter, ex = _executors(packet)
    first, second = sorted(ex.values(), key=lambda d: d["started"])
    assert second["started"] < first["finished"], "executors did not overlap"
    assert all(i["wait_s"] < 1.0 for i in packet["items"])
    log = _git(repo, "log", "--oneline", "main")
    assert log.count("executor work") == 2
    assert "Merge pf/" in log, "the second merge should be a merge commit in completion order"
    assert packet["wall_s"] < 6


def test_a_sibling_reservation_parks_the_item_without_a_worktree(orc, repo, stubs, tmp_path, capsys):
    stubs["store"].mkdir(exist_ok=True)
    # the hook scopes by the checkout's absolute path; so does the orchestrator by default
    (stubs["store"] / "sib.lock").write_text(f"sibling-session\t{repo.resolve()}\tsrc/app.py\n")
    plan = _brief(tmp_path)
    rf = _run_file(tmp_path, repo, [("a", plan, {"files": "[src/app.py]"}), ("b", plan, {"files": "[src/other.py]"})],
                   stubs["register"], timeout=2, run_extra={"max_parallel": 2})
    orc.orchestrate_pattern_f(str(rf))
    packet = _packet(capsys)
    by = {i["id"]: i for i in packet["items"]}
    assert by["a"]["status"] == "reservation_timeout", by["a"]
    assert by["a"]["blocked_by"].startswith("sibling-session on src/app.py")
    assert by["a"]["worktree"] is None and by["a"]["wait_s"] >= 1.5
    assert by["b"]["status"] == "merged"
    locks = [p.read_text().split("\t")[0] for p in stubs["store"].glob("*.lock")]
    assert locks == ["sibling-session"], locks


def test_a_merge_conflict_parks_the_second_item_and_keeps_its_worktree(orc, repo, stubs, tmp_path, monkeypatch, capsys):
    """Item a mis-declares src/other.py while both stub executors write
    different lines to src/app.py at once (nothing to reserve against): the
    first merge lands, the second conflicts and is parked with its worktree
    and branch intact."""
    monkeypatch.setenv("PF_STUB_EXEC_SLEEP", "1")
    plan = _brief(tmp_path)
    rf = _run_file(tmp_path, repo, [("a", plan, {"files": "[src/other.py]"}), ("b", plan, {"files": "[src/app.py]"})],
                   stubs["register"], run_extra={"max_parallel": 2})
    orc.orchestrate_pattern_f(str(rf))
    packet = _packet(capsys)
    statuses = sorted(i["status"] for i in packet["items"])
    assert statuses == ["merge_conflict", "merged"], packet["items"]
    parked = next(i for i in packet["items"] if i["status"] == "merge_conflict")
    assert parked["merge_outcome"] == "conflict" and "src/app.py" in parked["notes"]
    assert Path(parked["worktree"]).is_dir()
    assert parked["branch"] in _git(repo, "branch", "--list", "pf/*")
    assert _git(repo, "log", "--oneline", "main").count("executor work") == 1
    assert not list(stubs["store"].glob("*.lock"))


def test_an_undeclared_item_reserves_the_whole_tree(orc, repo, stubs, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PF_STUB_EXEC_SLEEP", "1.5")
    monkeypatch.setenv("PF_STUB_EXEC_FILE_b", "src/other.py")
    plan = _brief(tmp_path)
    rf = _run_file(tmp_path, repo, [("a", plan, {}), ("b", plan, {"files": "[src/other.py]"})],
                   stubs["register"], run_extra={"max_parallel": 2})
    orc.orchestrate_pattern_f(str(rf))
    packet = _packet(capsys)
    by = {i["id"]: i for i in packet["items"]}
    assert by["a"]["files"] == ["**"]
    assert by["a"]["status"] == "merged" and by["b"]["status"] == "merged"
    waited = [i for i in packet["items"] if i["wait_s"] >= 1.0]
    assert len(waited) == 1 and waited[0]["blocked_by"].startswith("pf/"), packet["items"]
    _meter, ex = _executors(packet)
    first, second = sorted(ex.values(), key=lambda d: d["started"])
    assert second["started"] >= first["finished"], "an executor ran while the other held its reservation"


def test_a_parked_item_releases_its_reservations(orc, repo, stubs, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PF_STUB_EXEC_VERDICT", "FAIL")
    plan = _brief(tmp_path)
    rf = _run_file(tmp_path, repo, [("a", plan, {"files": "[src/app.py]"})], stubs["register"])
    orc.orchestrate_pattern_f(str(rf))
    packet = _packet(capsys)
    assert packet["items"][0]["status"] == "executor_failed"
    assert packet["items"][0]["reservations"] == 1
    assert not list(stubs["store"].glob("*.lock"))
    log = (stubs["store"] / "log").read_text()
    assert "reserve pf/" in log and "release pf/" in log


def test_register_rows_carry_the_run_and_item_ids(orc, repo, stubs, tmp_path, capsys):
    plan = _brief(tmp_path)
    rf = _run_file(tmp_path, repo, [("a", plan, {"files": "[src/app.py]"})], stubs["register"])
    orc.orchestrate_pattern_f(str(rf))
    packet = _packet(capsys)
    rows = stubs["register_log"].read_text().splitlines()
    assert rows and all(f"--note pf {packet['run']}/a" in r for r in rows), rows


def test_max_parallel_and_files_are_validated(orc, repo, stubs, tmp_path):
    plan = _brief(tmp_path)
    rf = _run_file(tmp_path, repo, [("a", plan, {})], stubs["register"], run_extra={"max_parallel": 0})
    with pytest.raises(ValueError, match="max_parallel"):
        orc.load_pf_run(str(rf))
    rf = _run_file(tmp_path, repo, [("a", plan, {})], stubs["register"], run_extra={"max_parallel": "two"})
    with pytest.raises(ValueError, match="max_parallel"):
        orc.load_pf_run(str(rf))
    rf = _run_file(tmp_path, repo, [("a", plan, {"files": "src/app.py"})], stubs["register"])
    with pytest.raises(ValueError, match="files must be a list"):
        orc.load_pf_run(str(rf))
    rf = _run_file(tmp_path, repo, [("a", plan, {"files": "[/etc/passwd]"})], stubs["register"])
    with pytest.raises(ValueError, match="relative"):
        orc.load_pf_run(str(rf))
    run = orc.load_pf_run(str(_run_file(tmp_path, repo, [("a", plan, {})], stubs["register"])))
    assert run.max_parallel == 1


def test_dry_run_prints_the_declared_files_and_parallelism(orc, repo, stubs, tmp_path, capsys):
    plan = _brief(tmp_path)
    rf = _run_file(tmp_path, repo, [("a", plan, {"files": "[src/app.py, src/other.py]"}), ("b", plan, {})],
                   stubs["register"], run_extra={"max_parallel": 3})
    orc.orchestrate_pattern_f(str(rf), dry_run=True)
    out = capsys.readouterr().out
    assert "max_parallel 3" in out and f"reservation scope {repo}" in out
    assert "files=src/app.py src/other.py" in out and "files=**" in out


def test_declared_files_come_from_the_plan_when_not_given(orc, tmp_path):
    p = tmp_path / "exact.md"
    p.write_text("# Plan\n\nContract: exact\n\n## Commit\n\nPathspec: `scripts/a.py tests/b_test.py`.\n")
    assert orc._pf_declared_files(orc.PFItem(id="x", plan=str(p))) == ["scripts/a.py", "tests/b_test.py"]
    p.write_text("## Authority\nCommit with `git commit -F <message file> -- scripts/d.sh tests/shell/d.bats`; no push.\n")
    assert orc._pf_declared_files(orc.PFItem(id="x", plan=str(p))) == ["scripts/d.sh", "tests/shell/d.bats"]
    p.write_text("Touch `src/app.py` and `docs/x.md`, never `/abs/p.py`.\n")
    assert orc._pf_declared_files(orc.PFItem(id="x", plan=str(p))) == ["src/app.py", "docs/x.md"]
    assert orc._pf_declared_files(orc.PFItem(id="x", plan=str(p), files=["a.py", "a.py"])) == ["a.py"]


def test_reservation_db_runs_ic_from_the_store_root(orc, repo, stubs, tmp_path, capsys):
    root = tmp_path / "shared-root"
    (root / ".clavain").mkdir(parents=True)
    db = root / ".clavain" / "intercore.db"
    db.write_text("")
    plan = _brief(tmp_path)
    rf = _run_file(tmp_path, repo, [("a", plan, {"files": "[src/app.py]"})], stubs["register"],
                   run_extra={"reservation_db": str(db), "reservation_scope": "shared"})
    orc.orchestrate_pattern_f(str(rf))
    packet = _packet(capsys)
    assert packet["items"][0]["status"] == "merged"
    log = (stubs["store"] / "log").read_text()
    assert f"cwd={root}" in log, log


def test_long_paths_are_reserved_as_their_parent_directory(orc, tmp_path):
    long = "tests/structural/test_orchestrate_fresh_output_size_and_more.py"
    assert len(long) > orc.PF_MAX_PATTERN_TOKENS
    assert orc._pf_reservable(long) == "tests/structural/**"
    assert orc._pf_reservable("scripts/orchestrate.py") == "scripts/orchestrate.py"
    assert orc._pf_reservable("x" * 60) == "**"
    p = tmp_path / "exact.md"
    p.write_text("## Commit\n\nMessage file: written by the orchestrator. Pathspec: `scripts/a.py tests/b.py`.\n")
    assert orc._pf_declared_files(orc.PFItem(id="x", plan=str(p))) == ["scripts/a.py", "tests/b.py"]


def test_a_failed_reserve_leaves_no_partial_reservation(orc, repo, stubs, tmp_path, monkeypatch, capsys):
    """Seen live on run 91621bac: the first path reserved, the second was
    refused by ic, and the first stayed held until its TTL."""
    monkeypatch.setenv("PF_STUB_IC_FAIL_PATTERN", "src/other.py")
    plan = _brief(tmp_path)
    rf = _run_file(tmp_path, repo, [("a", plan, {"files": "[src/app.py, src/other.py]"})], stubs["register"])
    orc.orchestrate_pattern_f(str(rf))
    packet = _packet(capsys)
    assert packet["items"][0]["status"] == "error"
    assert "ic coordination reserve failed" in packet["items"][0]["notes"]
    assert not list(stubs["store"].glob("*.lock")), "a partial reservation outlived the failure"


def test_an_environment_failure_in_the_validator_is_unrun(orc, repo, stubs, tmp_path, monkeypatch, capsys):
    """mk's ruling on Sylveste-ypvl: a runner that crashed before the test ran is UNRUN, never FAIL."""
    monkeypatch.setenv("PF_STUB_VERDICT", "FAIL")
    monkeypatch.setenv("PF_STUB_CRITERION", "Verify Task 1: Expected exit 0; uv exited 101 after a Tokio executor failed panic")
    plan = _brief(tmp_path)
    rf = _run_file(tmp_path, repo, [("a", plan, {"files": "[src/app.py]"})], stubs["register"])
    orc.orchestrate_pattern_f(str(rf))
    packet = _packet(capsys)
    item = packet["items"][0]
    assert item["status"] == "validator_unrun", item
    assert item["validator_verdict"] == "UNRUN"
    assert "environment failure" in (item["notes"] or "")
    rows = stubs["register_log"].read_text()
    assert "--role validator --kind replay --verdict UNRUN" in rows
    assert Path(item["worktree"]).is_dir()


def test_a_plain_validator_fail_stays_a_fail(orc, repo, stubs, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PF_STUB_VERDICT", "FAIL")
    monkeypatch.setenv("PF_STUB_CRITERION", "Acceptance criterion 2: the helper returns 3, got 4")
    plan = _brief(tmp_path)
    rf = _run_file(tmp_path, repo, [("a", plan, {"files": "[src/app.py]"})], stubs["register"])
    orc.orchestrate_pattern_f(str(rf))
    packet = _packet(capsys)
    assert packet["items"][0]["status"] == "validator_fail"


def test_the_default_reservation_scope_is_the_checkout_path(orc, repo, stubs, tmp_path):
    """The pre-edit hook scopes by the checkout's absolute path; a name-only
    scope never met the hook's rows (found 2026-09-07 in the ic store)."""
    plan = _brief(tmp_path)
    run = orc.load_pf_run(str(_run_file(tmp_path, repo, [("a", plan, {})], stubs["register"])))
    assert orc._pf_scope(run) == str(repo.resolve())
