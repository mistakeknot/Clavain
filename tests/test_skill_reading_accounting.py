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


def test_traversal_path_not_emitted_in_json(tmp_path, skills, capsys):
    evil = "/x/plugin/skills/demo/references/../../../users/alice/private.md"
    ev = [use("1", "Skill", {"skill": "clavain:demo"}),
          use("2", "Read", {"file_path": evil}), read_res("2", 10),
          use("3", "Bash", {"command": f"cat {BASE}/references/nope-secret.md"}), res("3"),
          use("4", "Read", {"file_path": f"{BASE}/references/a.md"}), read_res("4", 10)]
    _, out = run(tmp_path, skills, ev, capsys)
    text = json.dumps(out)
    assert "alice" not in text and "private" not in text and "nope-secret" not in text
    s = out["skills"]["demo"]
    assert set(s["per_reference_bytes"]) <= {"references/a.md", "references/b.md"}
    assert s["unattributed_reasons"] == {"not_in_inventory": 2}
    assert s["reference_bytes_total"] == 10


@pytest.mark.parametrize("cmd", [
    "cat {b}/references/a.md; cat /elsewhere/other.txt",
    "cat {b}/references/a.md /elsewhere/other.txt",
    "cat {b}/references/a.md {b}/references/b.md",
    "cat {b}/references/a.md && echo done",
])
def test_combined_output_is_unattributed(tmp_path, skills, capsys, cmd):
    ev = [use("1", "Skill", {"skill": "clavain:demo"}),
          use("2", "Bash", {"command": cmd.format(b=BASE)}), res("2", "x" * 500)]
    _, out = run(tmp_path, skills, ev, capsys)
    s = out["skills"]["demo"]
    assert s["reference_bytes_total"] == 0
    assert s["unattributed_calls"] == s["skill_path_reads"] >= 1
    assert "combined_output" in s["unattributed_reasons"]


def test_call_time_binding_when_result_lands_after_skill_call(tmp_path, skills, capsys):
    ev = [use("1", "Read", {"file_path": f"{BASE}/references/a.md"}),
          use("2", "Skill", {"skill": "clavain:demo"}),
          read_res("1", 10)]
    _, out = run(tmp_path, skills, ev, capsys)
    s = out["skills"]["demo"]
    assert s["reference_bytes_total"] == 0
    assert s["unattributed_reasons"] == {"no_prior_invocation": 1}


def test_call_binds_to_invocation_active_at_call(tmp_path, skills, capsys):
    ev = [use("1", "Skill", {"skill": "clavain:demo"}),
          use("2", "Read", {"file_path": f"{BASE}/references/a.md"}),
          use("3", "Skill", {"skill": "clavain:demo"}),
          read_res("2", 10)]
    _, out = run(tmp_path, skills, ev, capsys)
    assert out["skills"]["demo"]["full_open_share"] == 0.0
    assert out["skills"]["demo"]["reference_bytes_total"] == 10


def _threshold_events(total, unattributed):
    ev = [use("s", "Skill", {"skill": "clavain:demo"})]
    for n in range(total):
        i = f"r{n}"
        if n < unattributed:
            ev += [use(i, "Bash", {"command": f"ls {BASE}/references"}), res(i)]
        else:
            ev += [use(i, "Read", {"file_path": f"{BASE}/references/a.md"}), read_res(i, 1)]
    return ev


def test_threshold_boundary_exactly_30_percent_does_not_stop(tmp_path, skills, capsys):
    rc, out = run(tmp_path, skills, _threshold_events(100, 30), capsys)
    assert out["unattributed_share"] == 0.3 and out["stop"] is False and rc == 0


def test_threshold_boundary_just_over_stops(tmp_path, skills, capsys):
    rc, out = run(tmp_path, skills, _threshold_events(100, 31), capsys)
    assert out["stop"] is True and rc == 3


# ---- round 3: pipelines, symlinks, filename prefixes, tool_use ids ----

@pytest.mark.parametrize("cmd,attributed", [
    ("cat {b}/references/a.md | head -5", True),
    ("cat {b}/references/a.md | grep foo | wc -l", True),
    ("cat {b}/references/a.md | tail -n 3", True),
    ("cat {b}/references/a.md | cat /elsewhere/o.txt", False),
    ("cat {b}/references/a.md | grep foo /elsewhere/o.txt", False),
    ("cat {b}/references/a.md | sed -n 1p /elsewhere/o.txt", False),
    ("cat {b}/references/a.md | python3 -c pass", False),
    ("cat {b}/references/a.md > /tmp/o.txt", False),
    ("cat {b}/references/a.md; cat /elsewhere/o.txt", False),
    ("cat {b}/references/a.md || cat /elsewhere/o.txt", False),
    ("cat {b}/references/a.md && cat /elsewhere/o.txt", False),
    ("cat {b}/references/a.md $(cat /elsewhere/o.txt)", False),
    ("cat {b}/references/a.md `cat /elsewhere/o.txt`", False),
    ("cat {b}/references/a.md <(cat /elsewhere/o.txt)", False),
    ("cat {b}/references/a.md 2>&1 | head", True),
    ("sed -n 1,5p {b}/references/a.md", True),
    ("grep foo {b}/references/a.md", True),
    ("grep -e foo {b}/references/a.md", False),
])
def test_pipeline_stage_inspection(tmp_path, skills, capsys, cmd, attributed):
    ev = [use("1", "Skill", {"skill": "clavain:demo"}),
          use("2", "Bash", {"command": cmd.format(b=BASE)}), res("2", "x" * 50)]
    _, out = run(tmp_path, skills, ev, capsys)
    s = out["skills"]["demo"]
    assert (s["reference_bytes_total"] == 50) is attributed, cmd
    assert (s["unattributed_calls"] == 0) is attributed, cmd


def test_symlinks_excluded_from_inventory(tmp_path, capsys):
    skills = tmp_path / "skills"
    d = skills / "demo"
    (d / "references").mkdir(parents=True)
    (d / "references" / "a.md").write_text("A")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "leaky-secret-name.md").write_text("x")
    (d / "references" / "linkfile.md").symlink_to(outside / "leaky-secret-name.md")
    (d / "references" / "linkdir").symlink_to(outside, target_is_directory=True)
    (d / "SKILL.md").write_text("s")
    (d / "SKILL-linked.md").symlink_to(outside / "leaky-secret-name.md")
    (skills / "extlink").symlink_to(outside, target_is_directory=True)
    inv = sra.skill_files(str(skills))
    assert set(inv) == {"demo"}
    assert inv["demo"]["keys"] == {"references/a.md", "SKILL.md"}
    ev = [use("1", "Skill", {"skill": "clavain:demo"}),
          use("2", "Read", {"file_path": f"{BASE}/references/linkfile.md"}), read_res("2", 3),
          use("3", "Read", {"file_path": f"{BASE}/references/linkdir/leaky-secret-name.md"}), read_res("3", 3)]
    session(tmp_path, ev)
    rc = sra.main(["--transcripts", str(tmp_path), "--skills-dir", str(skills), "--json"])
    j = capsys.readouterr().out
    sra.main(["--transcripts", str(tmp_path), "--skills-dir", str(skills)])
    text = capsys.readouterr().out
    assert "leaky" not in j and "leaky" not in text and "extlink" not in j + text
    assert json.loads(j)["skills"]["demo"]["unattributed_calls"] == 2


@pytest.mark.parametrize("name", ["SKILL.md.private", "SKILL-compact.md.bak", "references/a.md.secret", "references/a.md.secret/x"])
def test_filename_suffix_not_matched(tmp_path, skills, capsys, name):
    ev = [use("1", "Skill", {"skill": "clavain:demo"}),
          use("2", "Read", {"file_path": f"{BASE}/{name}"}), read_res("2", 3),
          use("3", "Bash", {"command": f"cat {BASE}/{name}"}), res("3")]
    _, out = run(tmp_path, skills, ev, capsys)
    s = out["skills"]["demo"]
    assert s["reference_bytes_total"] == 0 and s["compact_reads"] == 0 and s["skill_md_reads"] == 0
    assert "secret" not in json.dumps(out) and "private" not in json.dumps(out) and ".bak" not in json.dumps(out)


def test_duplicate_tool_use_id_unattributed(tmp_path, skills, capsys):
    ev = [use("1", "Skill", {"skill": "clavain:demo"}),
          use("d", "Read", {"file_path": f"{BASE}/references/a.md"}),
          use("d", "Bash", {"command": "echo hi"}), read_res("d", 10)]
    _, out = run(tmp_path, skills, ev, capsys)
    s = out["skills"]["demo"]
    assert s["reference_bytes_total"] == 0
    assert s["unattributed_reasons"] == {"duplicate_tool_use_id": 1}


def test_missing_tool_use_id_unattributed(tmp_path, skills, capsys):
    ev = [use("1", "Skill", {"skill": "clavain:demo"}),
          use(None, "Read", {"file_path": f"{BASE}/references/a.md"}), read_res("zzz", 10)]
    ev[1]["message"]["content"][0].pop("id")
    _, out = run(tmp_path, skills, ev, capsys)
    s = out["skills"]["demo"]
    assert s["reference_bytes_total"] == 0
    assert s["unattributed_reasons"] == {"missing_tool_use_id": 1}
    assert out["orphan_results"] == 1


def test_unknown_result_id_not_charged(tmp_path, skills, capsys):
    ev = [use("1", "Skill", {"skill": "clavain:demo"}),
          use("2", "Read", {"file_path": f"{BASE}/references/a.md"}), read_res("other", 10)]
    _, out = run(tmp_path, skills, ev, capsys)
    assert out["skills"]["demo"]["reference_bytes_total"] == 0
    assert out["orphan_results"] == 1


def test_symlinked_references_dir_excluded(tmp_path):
    skills = tmp_path / "skills"
    d = skills / "demo"
    d.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "ext.md").write_text("x")
    (d / "references").symlink_to(outside, target_is_directory=True)
    (d / "SKILL.md").write_text("s")
    inv = sra.skill_files(str(skills))
    assert inv["demo"]["keys"] == {"SKILL.md"}


def test_unparseable_command_not_attributed(tmp_path, skills, capsys):
    ev = [use("1", "Skill", {"skill": "clavain:demo"}),
          use("2", "Bash", {"command": f"cat {BASE}/references/a.md 'unterminated"}), res("2", "x" * 9)]
    _, out = run(tmp_path, skills, ev, capsys)
    assert out["skills"]["demo"]["reference_bytes_total"] == 0
