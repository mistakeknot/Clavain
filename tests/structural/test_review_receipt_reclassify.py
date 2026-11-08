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


def test_refuses_nested_symlink_into_receipts(tmp_path):
    src = make(tmp_path)
    out = tmp_path / "notes"
    out.mkdir()
    (out / "o__r").symlink_to(src / "o__r")
    before = {p: p.read_bytes() for p in sorted(src.rglob("*")) if p.is_file()}
    listing = sorted(str(p) for p in src.rglob("*"))
    r = run(src, out)
    assert r.returncode == 2
    assert "unsafe" in r.stderr
    assert {p: p.read_bytes() for p in sorted(src.rglob("*")) if p.is_file()} == before
    assert sorted(str(p) for p in src.rglob("*")) == listing


def test_refuses_symlinked_out_dir(tmp_path):
    src = make(tmp_path)
    real = tmp_path / "real-notes"
    real.mkdir()
    link = tmp_path / "notes"
    link.symlink_to(real)
    assert run(src, link).returncode == 2
    assert not any(real.iterdir())


def test_refuses_symlinked_destination_file(tmp_path):
    src = make(tmp_path)
    out = tmp_path / "notes"
    (out / "o__r").mkdir(parents=True)
    (out / "o__r" / "3-c.note.json").symlink_to(src / "o__r" / "1-a.json")
    before = (src / "o__r" / "1-a.json").read_bytes()
    assert run(src, out).returncode == 2
    assert (src / "o__r" / "1-a.json").read_bytes() == before


def test_receipts_with_verdict_raw_are_verified_and_get_no_note(tmp_path):
    """mk-0qjva: the writer stores the word it read, so a BLOCK whose
    verdict_raw is FAIL/BLOCK is verified, and UNKNOWN is already explicit."""
    src, out = tmp_path / "reviews", tmp_path / "reclass"
    (src / "o__r").mkdir(parents=True)
    docs = {
        "1-a": {"verdict": "BLOCK", "verdict_raw": "BLOCK"},
        "2-b": {"verdict": "BLOCK", "verdict_raw": "FAIL (data loss)"},
        "3-c": {"verdict": "UNKNOWN", "verdict_raw": "APPROVE"},
        "4-d": {"verdict": "BLOCK"},                              # old receipt: still unverified
        "5-e": {"verdict": "BLOCK", "verdict_raw": "APPROVE"},    # contradictory: still unverified
    }
    for name, doc in docs.items():
        (src / "o__r" / f"{name}.json").write_text(json.dumps(doc))
    r = run(src, out, "--check")
    assert r.returncode == 0, r.stderr
    assert "block-unverified: 2" in r.stdout
    assert run(src, out).returncode == 0
    assert {p.name for p in out.rglob("*.note.json")} == {"4-d.note.json", "5-e.note.json"}
