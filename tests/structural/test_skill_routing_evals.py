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


def _load_script():
    import importlib.util
    spec = importlib.util.spec_from_file_location("evalscript", ROOT / "scripts" / "eval-skill-routing.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def test_public_hygiene():
    files = [EVALS, ROOT / "scripts" / "eval-skill-routing.py", Path(__file__)]
    needles = ("/ho" + "me/", "th" + "r_", "m" + "k-")
    for f in files:
        text = f.read_text()
        for needle in needles:
            assert needle not in text, f"{needle!r} in {f.name}"


def test_canon_namespace():
    c = _load_script().canon
    assert c("flux-drive") == c("interflux:flux-drive")
    assert c("unrelated:flux-drive") != c("interflux:flux-drive")
    assert c("anything:none") != c("none")
    assert c("/none") == "none"


def test_preflight():
    pf = _load_script().preflight
    hdr = "\t".join(["ID", "Label", "Email", "Provider", "Kind", "Enabled", "Priority", "5h"] + ["x"] * 7) + "\n"
    def row(kind, en, st, pct):
        return "\t".join(["i", "l", "e", "claude", kind, en, "1", pct, "-", "-", "-", "-", "-", "-", st]) + "\n"
    assert pf(hdr + row("oauth", "true", "ready", "0%"))[0]
    assert not pf(hdr + row("api_key", "true", "ready", "0%"))[0]
    assert not pf(hdr + row("oauth", "true", "ready", "100%"))[0]
    assert not pf(hdr + row("oauth", "false", "ready", "0%"))[0]
    assert not pf(hdr)[0]


def test_preflight_rejects_any_enabled_non_oauth():
    m = _load_script()
    hdr = "\t".join(["ID"] * 15) + "\n"
    def row(kind, en, pct="0%"):
        return "\t".join(["i", "l", "e", "claude", kind, en, "1", pct, "-", "-", "-", "-", "-", "-", "ready"]) + "\n"
    good = row("oauth", "true")
    assert m.preflight(hdr + good)[0]
    assert not m.preflight(hdr + good + row("api_key", "true"))[0]
    assert m.preflight(hdr + good + row("api_key", "false"))[0]


def test_positive_int():
    import argparse
    import pytest
    pi = _load_script().positive_int
    assert pi("3") == 3
    for bad in ("0", "-1"):
        with pytest.raises(argparse.ArgumentTypeError):
            pi(bad)


def test_clavain_prefix_alias():
    m = _load_script()
    own = m.own_names()
    assert "route" in own
    assert m.canon("clavain:route", own) == m.canon("route", own)
    assert m.canon("clavain:not-a-real-skill", own) != m.canon("not-a-real-skill", own)
    assert m.canon("unrelated:route", own) != "route"
    assert m.canon("anything:none", own) != "none"
    assert m.canon("clavain:none", own) != "none"
    assert m.canon("flux-drive", own) == "interflux:flux-drive"


def test_strict_and_normalized_both_computed():
    m = _load_script()
    own = m.own_names()
    assert m.score("clavain:route", "route", own) == (False, True)
    assert m.score("route", "route", own) == (True, True)
    assert m.score("clavain:not-a-real-skill", "not-a-real-skill", own) == (False, False)
