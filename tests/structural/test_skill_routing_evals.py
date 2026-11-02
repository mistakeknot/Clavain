"""Pins tests/evals/skill-routing.json: schema, real skill names, negatives, no duplicates."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVALS = ROOT / "tests" / "evals" / "skill-routing.json"
EXTERNAL = {"interflux:flux-drive"}  # skills shipped by other plugins


def _known():
    names = {p.parent.name for p in (ROOT / "skills").glob("*/SKILL.md")}
    names |= {p.stem for p in (ROOT / "commands").glob("*.md")}
    return names | EXTERNAL | {"none"}


def _load():
    return json.loads(EVALS.read_text())


def test_size_and_schema():
    data = _load()
    assert 40 <= len(data) <= 60
    for e in data:
        assert set(e) == {"prompt", "expected", "why"}
        assert all(isinstance(v, str) and v.strip() for v in e.values())


def test_expected_skills_exist():
    known = _known()
    bad = [e["expected"] for e in _load() if e["expected"] not in known]
    assert not bad, f"unknown expected skills: {bad}"


def test_negatives_present():
    assert sum(e["expected"] == "none" for e in _load()) >= 8


def test_no_duplicate_prompts():
    prompts = [e["prompt"].strip().lower() for e in _load()]
    assert len(prompts) == len(set(prompts))


def test_public_hygiene():
    text = EVALS.read_text()
    for needle in ("/home/", "thr_", "mk-"):
        assert needle not in text
