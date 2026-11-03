import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "review-receipt-reclassify.py"


def snapshot(d: Path) -> dict:
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(d.rglob("*")) if p.is_file()}


def run(src, out, *extra):
    return subprocess.run(
        ["python3", str(SCRIPT), "--reviews-dir", str(src), "--out-dir", str(out), *extra],
        text=True, capture_output=True, check=False,
    )


def make(tmp_path):
    src = tmp_path / "reviews"
    (src / "o__r").mkdir(parents=True)
    for name, verdict in [("1-a", "PASS"), ("2-b", "PASS WITH NOTES"), ("3-c", "BLOCK"),
                          ("4-d", "approve"), ("5-e", None)]:
        (src / "o__r" / f"{name}.json").write_text(json.dumps({"verdict": verdict, "pr": 1}))
    (src / "o__r" / "6-f.json").write_text("{not json")
    return src


def test_check_writes_nothing_and_counts(tmp_path):
    src, out = make(tmp_path), tmp_path / "reclass"
    before = snapshot(src)
    r = run(src, out, "--check")
    assert r.returncode == 0, r.stderr
    assert not out.exists()
    assert "approve-unrecognised: 1" in r.stdout
    assert "null-verdict: 1" in r.stdout
    assert "block-unverified: 1" in r.stdout
    assert "unreadable: 1" in r.stdout
    assert snapshot(src) == before


def test_apply_writes_notes_only_and_is_idempotent(tmp_path):
    src, out = make(tmp_path), tmp_path / "reclass"
    before = snapshot(src)
    assert run(src, out).returncode == 0
    assert snapshot(src) == before  # receipts untouched
    notes = {p.name: json.loads(p.read_text()) for p in out.rglob("*.note.json")}
    assert set(notes) == {"3-c.note.json", "4-d.note.json", "5-e.note.json"}
    assert notes["4-d.note.json"]["verdict_reclass"] == "approve-unrecognised"
    assert notes["5-e.note.json"]["verdict_reclass"] == "null-verdict"
    assert notes["3-c.note.json"]["verdict_reclass"] == "block-unverified"
    assert all(n["reason"] for n in notes.values())
    first = snapshot(out)
    r = run(src, out)
    assert snapshot(out) == first
    assert "unchanged" in r.stdout


def test_refuses_out_dir_inside_reviews_dir(tmp_path):
    src = make(tmp_path)
    assert run(src, src / "notes").returncode == 2
