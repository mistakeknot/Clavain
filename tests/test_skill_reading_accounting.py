"""Structural tests for scripts/skill-reading-accounting.py on synthetic transcripts."""
import importlib.util
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("sra", ROOT / "scripts" / "skill-reading-accounting.py")
sra = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sra)

BASE = "/x/plugin/skills/demo"


def use(i, name, inp):
    return {"message": {"content": [{"type": "tool_use", "id": i, "name": name, "input": inp}]}}


def res(i, text="a" * 100, err=False):
    return {"toolUseResult": {"stdout": text}, "message": {"content": [
        {"type": "tool_result", "tool_use_id": i, "content": text, "is_error": err}]}}


def read_res(i, n):
    return {"toolUseResult": {"file": {"content": "b" * n}}, "message": {"content": [
        {"type": "tool_result", "tool_use_id": i, "content": "ignored"}]}}


@pytest.fixture
def skills(tmp_path):
    d = tmp_path / "skills" / "demo"
    (d / "references").mkdir(parents=True)
    (d / "references" / "a.md").write_text("A" * 10)
    (d / "references" / "b.md").write_text("B" * 10)
    (d / "SKILL-compact.md").write_text("c")
    (d / "SKILL.md").write_text("s")
    return tmp_path / "skills"


def session(tmp_path, events):
    p = tmp_path / "proj"
    p.mkdir(exist_ok=True)
    f = p / "s.jsonl"
    f.write_text("\n".join(json.dumps(e) for e in events) + "\n")
    return tmp_path


def run(tmp_path, skills, events, capsys):
    session(tmp_path, events)
    rc = sra.main(["--transcripts", str(tmp_path), "--skills-dir", str(skills), "--json"])
    return rc, json.loads(capsys.readouterr().out)


def test_inventory(skills):
    inv = sra.skill_files(str(skills))
    assert set(inv["demo"]["refs"]) == {"references/a.md", "references/b.md"}
    assert inv["demo"]["compact"] is True


def test_full_open_and_bytes(tmp_path, skills, capsys):
    ev = [use("1", "Skill", {"skill": "clavain:demo"}),
          use("2", "Read", {"file_path": f"{BASE}/references/a.md"}), read_res("2", 40),
          use("3", "Bash", {"command": f"cat {BASE}/references/b.md | head -5"}), res("3", "x" * 60),
          use("4", "Read", {"file_path": f"{BASE}/SKILL-compact.md"}), read_res("4", 5)]
    rc, out = run(tmp_path, skills, ev, capsys)
    s = out["skills"]["demo"]
    assert s["invocations"] == 1
    assert s["reference_bytes_total"] == 100
    assert s["full_open_share"] == 1.0
    assert s["compact_reads"] == 1 and s["compact_invocation_share"] == 1.0
    assert s["unattributed_calls"] == 0 and rc == 0


def test_partial_open_per_invocation(tmp_path, skills, capsys):
    ev = [use("1", "Skill", {"skill": "clavain:demo"}),
          use("2", "Read", {"file_path": f"{BASE}/references/a.md"}), read_res("2", 10),
          use("3", "Skill", {"skill": "clavain:demo"}),
          use("4", "Read", {"file_path": f"{BASE}/references/a.md"}), read_res("4", 10),
          use("5", "Read", {"file_path": f"{BASE}/references/b.md"}), read_res("5", 10)]
    _, out = run(tmp_path, skills, ev, capsys)
    s = out["skills"]["demo"]
    assert s["invocations"] == 2
    assert s["full_open_share"] == 0.5
    assert s["reference_bytes_per_invocation"] == 15.0


def test_glob_and_recursive_grep_unattributed(tmp_path, skills, capsys):
    ev = [use("1", "Skill", {"skill": "clavain:demo"}),
          use("2", "Bash", {"command": f"cat {BASE}/references/*.md"}), res("2"),
          use("3", "Bash", {"command": f"grep -rn foo {BASE}"}), res("3"),
          use("4", "Bash", {"command": f"ls {BASE}/references"}), res("4"),
          use("5", "Read", {"file_path": f"{BASE}/references/a.md"}), read_res("5", 10)]
    rc, out = run(tmp_path, skills, ev, capsys)
    s = out["skills"]["demo"]
    assert s["unattributed_calls"] == 3 and s["skill_path_reads"] == 4
    assert out["stop"] is True and rc == 3


def test_read_without_invocation_is_unattributed(tmp_path, skills, capsys):
    ev = [use("1", "Read", {"file_path": f"{BASE}/references/a.md"}), read_res("1", 10)]
    _, out = run(tmp_path, skills, ev, capsys)
    assert out["skills"]["demo"]["unattributed_reasons"] == {"no_prior_invocation": 1}


def test_non_clavain_skill_and_unknown_skill_ignored(tmp_path, skills, capsys):
    ev = [use("1", "Skill", {"skill": "other:demo"}),
          use("2", "Read", {"file_path": "/y/skills/nope/references/z.md"}), read_res("2", 10)]
    rc, out = run(tmp_path, skills, ev, capsys)
    assert out["skills"]["demo"]["invocations"] == 0
    assert out["skill_path_reads"] == 0 and rc == 0


def test_non_read_commands_ignored():
    assert sra.classify_bash(f"rm {BASE}/references/a.md") == []
    assert sra.classify_bash(f"cat {BASE}/references/a.md")[0][:2] == ("path", "demo")


def test_output_has_no_transcript_text(tmp_path, skills, capsys):
    secret = "TOPSECRETTEXT"
    ev = [use("1", "Skill", {"skill": "clavain:demo"}),
          use("2", "Read", {"file_path": f"{BASE}/references/a.md"}), read_res("2", 3)]
    ev[2]["toolUseResult"]["file"]["content"] = secret
    rc = None
    session(tmp_path, ev)
    sra.main(["--transcripts", str(tmp_path), "--skills-dir", str(skills)])
    assert secret not in capsys.readouterr().out
