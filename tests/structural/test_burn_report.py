"""Weighted burn from synthetic Claude Code transcripts."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/burn-report.py"
WORKSPACE = "-home-mk--bb-machines-host-data-workspaces-thr-ay39nh2cpv"
WORKTREE = "-home-mk--bb-machines-host-data-worktrees-thr-3rezw7dwvy-1-Aleph"


def line(msg, req, ts, model="claude-sonnet-5", **usage):
    return json.dumps(dict(type="assistant", requestId=req, timestamp=ts,
                           message=dict(id=msg, model=model, usage=usage)))


def write(root, rel, *lines):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def run(root, *args):
    r = subprocess.run([sys.executable, str(SCRIPT), "--root", str(root), "--json", *args],
                       capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def test_weights_dedup_and_window(tmp_path):
    usage = dict(input_tokens=10, cache_creation_input_tokens=100,
                 cache_read_input_tokens=1000, output_tokens=2)
    write(tmp_path, f"{WORKSPACE}/s.jsonl",
          line("m1", "r1", "2026-09-24T23:10:00Z", **usage),
          line("m1", "r1", "2026-09-24T23:10:01Z", **usage),
          line("m0", "r0", "2026-09-24T22:59:59Z", **usage),
          line("m9", "r9", "2026-09-25T02:00:00Z", **usage),
          line("m2", "r2", "2026-09-25T00:30:00Z", model="<synthetic>", **usage),
          "not json {\"usage\"")
    data = run(tmp_path, "--since", "2026-09-24T23:00Z", "--until", "2026-09-25T02:00Z")
    # 10 + 100*1.25 + 1000*0.1 + 2*5, counted once, window end exclusive.
    assert data["calls"] == 1
    assert data["weighted_total"] == 245
    assert data["by_token_type"]["output_tokens"] == 10
    assert data["by_hour"] == {"2026-09-24T23:00Z": 245}


def test_subagents_and_successors_group_by_workspace_lineage(tmp_path):
    write(tmp_path, f"{WORKSPACE}/a.jsonl", line("m1", "r1", "2026-09-25T00:00:00Z", output_tokens=1))
    write(tmp_path, f"{WORKSPACE}/a/subagents/x.jsonl", line("m2", "r2", "2026-09-25T00:01:00Z", output_tokens=1))
    write(tmp_path, f"{WORKTREE}/b.jsonl", line("m3", "r3", "2026-09-25T00:02:00Z", output_tokens=1))
    write(tmp_path, "-home-mk-projects-Quilan/c.jsonl", line("m4", "r4", "2026-09-25T00:03:00Z", output_tokens=1))
    data = run(tmp_path, "--since", "2026-09-25T00:00Z", "--until", "2026-09-25T01:00Z")
    groups = {g["lineage"]: (g["weighted"], g["calls"]) for g in data["by_lineage"]}
    assert groups == {"thr_ay39nh2cpv": (10, 2), "thr_3rezw7dwvy": (5, 1), "projects-Quilan": (5, 1)}


def test_context_buckets_and_pace(tmp_path):
    write(tmp_path, f"{WORKSPACE}/a.jsonl",
          line("m1", "r1", "2026-09-24T17:00:00Z", cache_read_input_tokens=160_000),
          line("m2", "r2", "2026-09-24T22:00:00Z", cache_read_input_tokens=40_000))
    data = run(tmp_path, "--since", "2026-09-24T12:00Z", "--until", "2026-09-24T23:00Z")
    assert data["by_context"] == {">150k": 16_000, "<50k": 4_000}
    # The pace covers only the last 5h: the 17:00 call is outside it.
    assert data["pace"] == {"hours": 5, "weighted": 4_000, "per_hour": 800}


def test_text_report_and_bad_window(tmp_path):
    write(tmp_path, f"{WORKSPACE}/a.jsonl", line("m1", "r1", "2026-09-25T00:00:00Z", output_tokens=200_000))
    r = subprocess.run([sys.executable, str(SCRIPT), "--root", str(tmp_path),
                        "--since", "2026-09-25T00:00Z", "--until", "2026-09-25T01:00Z"],
                       capture_output=True, text=True, check=True)
    assert "1.0M over 1 calls" in r.stdout and "thr_ay39nh2cpv" in r.stdout
    bad = subprocess.run([sys.executable, str(SCRIPT), "--root", str(tmp_path),
                          "--since", "2026-09-25T01:00Z", "--until", "2026-09-25T00:00Z"],
                         capture_output=True, text=True)
    assert bad.returncode == 2 and "--since must be before --until" in bad.stderr
