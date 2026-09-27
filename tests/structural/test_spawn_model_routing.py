"""bb thread spawns resolve their model through route-spawn.sh (mk-42j9.25).

Guidance must never hardcode a frontier model on a `bb thread spawn` or
`bb handoff` line; the model comes from the policy via route-spawn.sh.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCAN_DIRS = ["skills", "commands", "hooks", "docs/canon"]
SPAWN_LINE = re.compile(r"bb\s+(thread\s+spawn|handoff)\b")
FRONTIER_LITERAL = re.compile(r"claude-(opus|fable)[\w.-]*|\b(opus|fable)\b", re.IGNORECASE)
MODEL_FLAG = re.compile(r"--model[= ]+(\S+)")


def _spawn_lines():
    for rel in SCAN_DIRS:
        base = ROOT / rel
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix not in {".md", ".sh", ".py", ".json", ".yaml", ".yml"}:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for number, line in _logical_lines(text):
                if SPAWN_LINE.search(line):
                    yield path.relative_to(ROOT), number, line


def _logical_lines(text):
    """Join backslash-continued lines so a --model on a later line is seen."""
    start, parts = None, []
    for number, line in enumerate(text.splitlines(), 1):
        if start is None:
            start = number
        if line.rstrip().endswith("\\"):
            parts.append(line.rstrip()[:-1])
            continue
        parts.append(line)
        yield start, " ".join(parts)
        start, parts = None, []
    if parts:
        yield start, " ".join(parts)


def test_no_hardcoded_frontier_model_on_spawn_lines():
    offenders = []
    for path, number, line in _spawn_lines():
        for value in MODEL_FLAG.findall(line):
            if FRONTIER_LITERAL.search(value):
                offenders.append(f"{path}:{number}: {line.strip()}")
    assert not offenders, (
        "bb spawn/handoff lines must take --model from scripts/route-spawn.sh, "
        "not a literal Opus or Fable id:\n" + "\n".join(offenders)
    )


def test_detector_catches_literal_models():
    for line in [
        "bb thread spawn --provider claude-code --model claude-opus-5-5 --reasoning-level medium",
        "bb handoff --replace --model opus",
        "bb thread spawn --model=claude-fable-5-1",
    ]:
        assert SPAWN_LINE.search(line)
        assert any(FRONTIER_LITERAL.search(v) for v in MODEL_FLAG.findall(line)), line
    continued = "bb thread spawn --provider claude-code \\\n  --model claude-opus-5-5 \\\n  --reasoning-level medium\n"
    [(_, joined)] = list(_logical_lines(continued))
    assert SPAWN_LINE.search(joined)
    assert any(FRONTIER_LITERAL.search(v) for v in MODEL_FLAG.findall(joined))
    assert not any(
        FRONTIER_LITERAL.search(v)
        for v in MODEL_FLAG.findall('bb thread spawn --provider "$P" --model "$M" --reasoning-level "$E"')
    )


def test_spawner_guidance_points_at_route_spawn():
    for rel in [
        "skills/dispatching-parallel-agents/SKILL.md",
        "skills/dispatching-parallel-agents/SKILL-compact.md",
        "docs/canon/reasoning-routing-operations.md",
    ]:
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "route-spawn.sh --role lane --lineage" in text or \
            'route-spawn.sh" --role lane --lineage' in text, f"{rel} must give the lane spawn recipe"
        # Coordinators run in other repositories: the path must be the selected
        # installation's, never relative to the caller's checkout.
        assert '"${CLAVAIN_SELECTED_ROOT:?}/scripts/route-spawn.sh"' in text, f"{rel} must use the selected root"
        assert not re.search(r"(?<![/\w])scripts/route-spawn\.sh", text), f"{rel} has a relative route-spawn path"
        assert "--role planning" not in text, f"{rel}: the frontier planning role is frontier-planning"
    ops = (ROOT / "docs/canon/reasoning-routing-operations.md").read_text(encoding="utf-8")
    assert "## Spawning bb threads" in ops
