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
  if [[ $role == validation ]]; then echo "claude --model stub-validator x"; else echo "codex exec -m stub-executor x"; fi
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
    printf 'VERDICT: %s\nCRITERION: %s\nRECEIPT: %s\nBEYOND THE GAUGE:\n%s\n' \
      "${PF_STUB_VERDICT:-PASS}" "${PF_STUB_CRITERION:-none}" "${PF_STUB_RECEIPT:-$rec}" "${PF_STUB_BEYOND:-- none}" > "$out"
    printf -- '--- VERDICT ---\nSTATUS: warn\nSUMMARY: stub\n---\n' > "$out.verdict"
    ;;
  routine-execution)
    echo "from executor" >> "$C/src/app.py"
    git -C "$C" add -A && git -C "$C" commit -q -m "executor work"
    printf 'Did the thing.\nVERDICT: %s\nCRITERION: %s\n' "${PF_STUB_EXEC_VERDICT:-PASS}" "${PF_STUB_EXEC_CRITERION:-none}" > "$out"
    printf -- '--- VERDICT ---\nSTATUS: pass\nSUMMARY: stub\n---\n' > "$out.verdict"
    ;;
esac
'''


@pytest.fixture()
def stubs(tmp_path: Path, monkeypatch) -> dict:
    t = tmp_path / "tools"
    t.mkdir()
    register_log = tmp_path / "register.log"
    dispatch_log = tmp_path / "dispatch.log"
    _sh(t / "ic", "mkdir -p .clavain && : > .clavain/intercore.db\n")
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
    for k in ("PF_STUB_SLEEP", "PF_STUB_MUTATE", "PF_STUB_VERDICT", "PF_STUB_CRITERION",
              "PF_STUB_RECEIPT", "PF_STUB_BEYOND", "PF_STUB_EXEC_VERDICT", "PF_VERDICT_FAIL"):
        monkeypatch.delenv(k, raising=False)
    register = tmp_path / "register.db"
    register.write_text("")
    return {"register_log": register_log, "dispatch_log": dispatch_log, "register": register}


def _run_file(tmp_path: Path, repo: Path, items: list[tuple[str, Path, dict]],
              register: Path, timeout: int = 30) -> Path:
    body = ""
    for iid, plan, extra in items:
        body += f"  - id: {iid}\n    plan: {plan}\n"
        for k, v in extra.items():
            body += f"    {k}: {v}\n"
    text = (
        f"version: 1\nsession: sess-test\ngoal: g1\nregister: {register}\nrepo: {repo}\n"
        f"timeout: {timeout}\nproducer: author-model\ntrailers:\n  - 'Test-Trailer: yes'\nitems:\n{body}"
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
    assert "--note the executor also touched src/other.py" in rows[2]
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
