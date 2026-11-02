"""Skill-eval harness: grading, exit codes, and the guest/API-key refusal. No live session runs here."""
import importlib.util, json, os
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("skill_eval", ROOT / "scripts" / "skill-eval.py")
se = importlib.util.module_from_spec(spec); spec.loader.exec_module(se)


def stream(*blocks, final="done"):
    ev = [{"type": "assistant", "message": {"content": list(blocks)}}]
    ev.append({"type": "result", "result": final})
    return "\n".join(json.dumps(e) for e in ev)


def tool(name, **inp):
    return {"type": "tool_use", "name": name, "input": inp}


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
    for c in cases:
        assert (se.EVAL_DIR / "fixtures" / c["fixture"]).is_dir()
        assert (ROOT / "skills" / c["skill"] / "SKILL.md").is_file()


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
