"""Skill-eval harness: grading, exit codes, and the guest/API-key refusal. No live session runs here."""
import importlib.util, json, os
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("skill_eval", ROOT / "scripts" / "skill-eval.py")
se = importlib.util.module_from_spec(spec); spec.loader.exec_module(se)


def stream(*blocks, final="done", results=(), subtype="success", is_error=False, result_event=True):
    ev = [{"type": "assistant", "message": {"content": list(blocks)}}]
    for tid, err, text in results:
        ev.append({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": tid, "is_error": err, "content": text}]}})
    if result_event:
        ev.append({"type": "result", "subtype": subtype, "is_error": is_error, "result": final})
    return "\n".join(json.dumps(e) for e in ev)


def tool(name, _id=None, **inp):
    return {"type": "tool_use", "name": name, "id": _id or name, "input": inp}


def replay(tmp_path, case_id, raw, files=None):
    (tmp_path / f"{case_id}.jsonl").write_text(raw)
    if files:
        d = tmp_path / f"{case_id}.files"
        for rel, body in files.items():
            (d / rel).parent.mkdir(parents=True, exist_ok=True)
            (d / rel).write_text(body)


def test_shipped_cases_load_and_fixtures_exist():
    cases = se.load_cases(se.EVAL_DIR / "cases.json")
    assert 2 <= len(cases) <= 3
    seen = set()
    for c in cases:
        se.validate_case(c, seen)


def test_pass_and_fail_by_case(tmp_path):
    cases = {c["id"]: c for c in se.load_cases(se.EVAL_DIR / "cases.json")}
    c = cases["using-clavain-routes-plan-request"]
    good = stream(tool("Skill", skill="clavain:writing-plans"))
    replay(tmp_path, c["id"], good)
    assert se.run_case(c, replay=tmp_path)["status"] == "pass"
    replay(tmp_path, c["id"], stream(tool("Skill", skill="clavain:brainstorm")))
    assert se.run_case(c, replay=tmp_path)["status"] == "fail"
    # a side effect the case forbids
    replay(tmp_path, c["id"], good, files={"src/x.py": "x"})
    assert se.run_case(c, replay=tmp_path)["status"] == "fail"


def test_files_and_last_message_checks(tmp_path):
    c = {c["id"]: c for c in se.load_cases(se.EVAL_DIR / "cases.json")}["writing-plans-writes-plan-not-code"]
    raw = stream(tool("Write", file_path="PLAN.md"), final="Wrote PLAN.md")
    replay(tmp_path, c["id"], raw, files={"PLAN.md": "step 1\nverify with tests"})
    assert se.run_case(c, replay=tmp_path)["status"] == "pass"
    # source edited -> fail
    replay(tmp_path, c["id"], raw, files={"PLAN.md": "verify", "app.py": "def add(a, b):\n    return a + b\n"})
    assert se.run_case(c, replay=tmp_path)["status"] == "fail"


ROUTE = "using-clavain-routes-plan-request"


def case(cid):
    return {c["id"]: c for c in se.load_cases(se.EVAL_DIR / "cases.json")}[cid]


def test_error_sessions_never_pass_even_with_matching_call(tmp_path):
    c = case(ROUTE)
    call = tool("Skill", skill="clavain:writing-plans")
    # nonzero exit with otherwise matching transcript
    replay(tmp_path, c["id"], stream(call))
    (tmp_path / f"{c['id']}.rc").write_text("1")
    assert se.run_case(c, replay=tmp_path)["status"] == "not-run"
    (tmp_path / f"{c['id']}.rc").unlink()
    # error result event, non-success subtype, missing result event
    for raw in (stream(call, is_error=True), stream(call, subtype="error_max_turns"),
                stream(call, result_event=False)):
        replay(tmp_path, c["id"], raw)
        assert se.run_case(c, replay=tmp_path)["status"] == "not-run"


def test_executing_plans_requires_real_passing_verification(tmp_path):
    c = case("executing-plans-follows-plan-and-verifies")
    files = {"app.py": "def add(a, b):\n    return a + b\n",
             "test_app.py": "from app import add\ndef test_add():\n    assert add(2, 3) == 5\n"}
    run = tool("Bash", "t1", command="pytest -q")
    good = stream(run, results=[("t1", False, "1 passed in 0.01s")], final="Verified: tests pass")
    replay(tmp_path, c["id"], good, files=files)
    assert se.run_case(c, replay=tmp_path)["status"] == "pass"
    # negative: files fixed and test written but pytest never run
    denial = stream(final="Did not run pytest; tests should pass")
    replay(tmp_path, c["id"], denial, files=files)
    assert se.run_case(c, replay=tmp_path)["status"] == "fail"
    # pytest ran but failed
    bad = stream(run, results=[("t1", True, "1 failed")], final="verified")
    replay(tmp_path, c["id"], bad, files=files)
    assert se.run_case(c, replay=tmp_path)["status"] == "fail"
    # test artifact missing
    import shutil; shutil.rmtree(tmp_path / f"{c['id']}.files")
    replay(tmp_path, c["id"], good, files={"app.py": files["app.py"]})
    assert se.run_case(c, replay=tmp_path)["status"] == "fail"


def test_malformed_cases_are_not_run_and_others_still_run(tmp_path, monkeypatch):
    good = case(ROUTE)
    bad_rx = dict(good, id="bad-rx", checks=[{"type": "trace", "regex": "("}])
    bad_fx = dict(good, id="bad-fx", fixture="nope")
    dup = dict(good)
    replay(tmp_path, good["id"], stream(tool("Skill", skill="clavain:writing-plans")))
    res = se.run_all([bad_rx, bad_fx, good, dup], replay=tmp_path)
    st = {r["id"]: r["status"] for r in res[:3]}
    assert st["bad-rx"] == st["bad-fx"] == "not-run"
    assert st[ROUTE] == "pass" and [r["status"] for r in res].count("not-run") == 3
    assert se.exit_code(res) == 2


def test_main_writes_summary_with_invalid_case(tmp_path):
    cf = tmp_path / "c.json"
    cf.write_text(json.dumps([{"id": "x"}]))
    out = tmp_path / "o.json"
    assert se.main(["--cases", str(cf), "--out", str(out)]) == 2
    assert json.loads(out.read_text())[0]["status"] == "not-run"


def test_missing_or_empty_transcript_is_not_run(tmp_path):
    c = se.load_cases(se.EVAL_DIR / "cases.json")[0]
    assert se.run_case(c, replay=tmp_path)["status"] == "not-run"
    replay(tmp_path, c["id"], "garbage, no json")
    assert se.run_case(c, replay=tmp_path)["status"] == "not-run"


def test_exit_codes():
    R = lambda *s: [{"status": x} for x in s]
    assert se.exit_code(R("pass", "pass")) == 0
    assert se.exit_code(R("pass", "fail")) == 1
    assert se.exit_code(R("pass", "not-run")) == 2
    assert se.exit_code(R("fail", "not-run")) == 1
    assert se.exit_code([]) == 2


def test_live_refused_outside_guest_or_with_api_key(monkeypatch):
    with pytest.raises(se.NotRun, match="not inside"):
        se.guard_live({})
    with pytest.raises(se.NotRun, match="ANTHROPIC_API_KEY"):
        se.guard_live({"CLAVAIN_SKILL_EVAL_GUEST": "1", "ANTHROPIC_API_KEY": "x"})


def test_main_live_without_guest_exits_2(monkeypatch, capsys):
    monkeypatch.delenv("CLAVAIN_SKILL_EVAL_GUEST", raising=False)
    assert se.main([]) == 2
    assert "NOT RUN" in capsys.readouterr().out
