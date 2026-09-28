"""Coordinator seat recipes run verbatim and carry the Seat block (mk-42j9.25).

The guidance gives two recipes a coordinator copies into a shell:

- the spawn recipe, which resolves `--role coordinator-seat` with
  `--seat-out` and passes "Seat: <json>" in the new thread's spawn prompt;
- the self-handoff recipe, which reads that JSON from `$seat_json` and passes
  it to `bb handoff --self --to <provider> --model <m> --effort <e>` together
  with "Seat: <json>" in `--instructions`, so every later generation has it.

Each recipe is executed here exactly as written (only the `…` placeholder is
dropped) against a fake `bb` and a fake route-spawn.
"""

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GUIDES = [
    "skills/dispatching-parallel-agents/SKILL.md",
    "skills/dispatching-parallel-agents/SKILL-compact.md",
    "docs/canon/reasoning-routing-operations.md",
]
SEAT = {
    # mk-h73i: coordinator-seat resolves the fleet default, unprofiled, for
    # every project. This dict is an opaque fixture value the fake
    # route-spawn.sh echoes back verbatim; the recipes never inspect it, so
    # any valid seat shape would do, but it should look like a seat a
    # coordinator would actually see today rather than the retired
    # per-project Opus override.
    "provider": "claude-code", "model": "claude-sonnet-5", "reasoning_level": "medium",
    "role": "coordinator-seat", "profile_ref": "coordinator-seat-sonnet",
    "policy_profile": None, "policy_hash": "a" * 64,
    "receipt": "/state/route-spawn/r.json",
}
FENCED = re.compile(r"^\s*```([\w-]*)\n(.*?)^\s*```", re.DOTALL | re.MULTILINE)
INLINE = re.compile(r"`([^`\n]+)`")

FAKE_BB = r"""#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
record = {"args": args}
if "--prompt-file" in args:
    path = args[args.index("--prompt-file") + 1]
    record["prompt_file"] = sys.stdin.read() if path == "-" else open(path).read()
with open(os.environ["FAKE_BB_LOG"], "a") as log:
    log.write(json.dumps(record) + "\n")
if os.environ.get("FAKE_BB_FAIL"):
    sys.exit(1)
"""

FAKE_ROUTE_SPAWN = r"""#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
with open(os.environ["FAKE_RS_LOG"], "a") as log:
    log.write(json.dumps(args) + "\n")
if os.environ.get("FAKE_RS_FAIL"):
    sys.exit(3)
seat = json.loads(os.environ["FAKE_SEAT"])
if "--seat-out" in args:
    with open(args[args.index("--seat-out") + 1], "w") as out:
        json.dump(seat, out)
print(seat["provider"], seat["model"], seat["reasoning_level"])
"""


def _snippets(text):
    for language, block in FENCED.findall(text):
        if language in ("", "bash", "sh"):
            yield block
    for span in INLINE.findall(FENCED.sub("", text)):
        yield span


def _recipe(rel, *markers):
    text = (ROOT / rel).read_text(encoding="utf-8")
    found = [s for s in _snippets(text) if all(m in s for m in markers)]
    assert found, f"{rel}: no copyable recipe containing {markers!r}"
    return found[0].replace("…", "")


def _harness(tmp_path):
    root = tmp_path / "clavain"
    (root / "scripts").mkdir(parents=True)
    route_spawn = root / "scripts/route-spawn.sh"
    route_spawn.write_text(FAKE_ROUTE_SPAWN)
    route_spawn.chmod(0o755)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "bb").write_text(FAKE_BB)
    (bindir / "bb").chmod(0o755)
    scratch = tmp_path / "tmpdir"
    scratch.mkdir()
    env = dict(os.environ)
    env.update({
        "PATH": f"{bindir}:{env['PATH']}",
        "CLAVAIN_SELECTED_ROOT": str(root),
        "TMPDIR": str(scratch),
        "FAKE_BB_LOG": str(tmp_path / "bb.log"),
        "FAKE_RS_LOG": str(tmp_path / "rs.log"),
        "FAKE_SEAT": json.dumps(SEAT),
        "project_slug": "clavain",
        "coordinator_id": "thr_parent",
    })
    return env, scratch


def _run(snippet, env, errexit=False, **extra):
    env = dict(env, **extra)
    shell = ["bash", "-ec" if errexit else "-c", snippet]
    return subprocess.run(shell, env=env, capture_output=True, text=True, timeout=30)


def _bb_calls(env):
    log = Path(env["FAKE_BB_LOG"])
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines()]


def _seat_in(call):
    """The JSON after "Seat: " in any argument or prompt file of a bb call."""
    haystacks = list(call["args"]) + [call.get("prompt_file") or ""]
    for text in haystacks:
        index = text.find("Seat: ")
        if index >= 0:
            seat, _ = json.JSONDecoder().raw_decode(text[index + len("Seat: "):])
            return seat
    return None


def _flag(args, name):
    assert name in args, f"bb call lacks {name}: {args}"
    return args[args.index(name) + 1]


@pytest.mark.parametrize("rel", GUIDES)
def test_coordinator_spawn_recipe_runs_verbatim(rel, tmp_path):
    snippet = _recipe(rel, "--role coordinator-seat", "bb thread spawn")
    env, scratch = _harness(tmp_path)
    result = _run(snippet, env)
    assert result.returncode == 0, result.stderr
    [call] = _bb_calls(env)
    assert call["args"][:2] == ["thread", "spawn"], call
    assert _flag(call["args"], "--provider") == "claude-code"
    assert _flag(call["args"], "--model") == "claude-sonnet-5"
    assert _flag(call["args"], "--reasoning-level") == "medium"
    assert _seat_in(call) == SEAT, f"{rel}: the spawn prompt must carry the Seat block"
    assert not any(scratch.iterdir()), f"{rel}: the mktemp seat file must be removed after a spawn"

    failed_env, failed_scratch = _harness(tmp_path / "failed")
    result = _run(snippet, failed_env, FAKE_RS_FAIL="1")
    assert _bb_calls(failed_env) == [], f"{rel}: no spawn when routing fails"
    assert not any(failed_scratch.iterdir()), f"{rel}: the mktemp seat file must be removed when routing fails"


@pytest.mark.parametrize("rel", GUIDES)
def test_coordinator_spawn_recipe_cleans_up_when_spawn_fails_under_errexit(rel, tmp_path):
    snippet = _recipe(rel, "--role coordinator-seat", "bb thread spawn")
    env, scratch = _harness(tmp_path)
    _run(snippet, env, errexit=True, FAKE_BB_FAIL="1")
    assert len(_bb_calls(env)) == 1, f"{rel}: the spawn must have been attempted"
    assert not any(scratch.iterdir()), f"{rel}: the mktemp seat file must be removed when bb fails under set -e"


@pytest.mark.parametrize("rel", GUIDES)
def test_self_handoff_carries_the_seat_to_every_generation(rel, tmp_path):
    spawn = _recipe(rel, "--role coordinator-seat", "bb thread spawn")
    handoff = _recipe(rel, "bb handoff --self", "$seat_json")
    env, _ = _harness(tmp_path)
    assert _run(spawn, env).returncode == 0
    # Generation 1 reads its Seat from the spawn prompt; each handoff must pass
    # the same Seat on, so generations 2 and 3 have it too.
    seat = _seat_in(_bb_calls(env)[-1])
    for generation in (1, 2, 3):
        result = _run(handoff, env, seat_json=json.dumps(seat))
        assert result.returncode == 0, f"{rel} generation {generation}: {result.stderr}"
        call = _bb_calls(env)[-1]
        assert call["args"][:2] == ["handoff", "--self"], call
        assert _flag(call["args"], "--to") == "claude-code"
        assert _flag(call["args"], "--model") == "claude-sonnet-5"
        assert _flag(call["args"], "--effort") == "medium"
        seat = _seat_in(call)
        assert seat == SEAT, f"{rel} generation {generation}: the handoff must carry the Seat block forward"


@pytest.mark.parametrize("rel", GUIDES)
def test_self_handoff_without_a_seat_does_not_guess(rel, tmp_path):
    handoff = _recipe(rel, "bb handoff --self", "$seat_json")
    env, _ = _harness(tmp_path)
    _run(handoff, env, seat_json="")
    assert _bb_calls(env) == [], f"{rel}: no handoff without a Seat block"


@pytest.mark.parametrize("field", ["provider", "model", "reasoning_level"])
@pytest.mark.parametrize("value", ["", None, "missing"])
@pytest.mark.parametrize("rel", GUIDES)
def test_self_handoff_refuses_an_incomplete_seat(rel, field, value, tmp_path):
    handoff = _recipe(rel, "bb handoff --self", "$seat_json")
    env, _ = _harness(tmp_path)
    seat = dict(SEAT)
    if value == "missing":
        del seat[field]
    else:
        seat[field] = value
    _run(handoff, env, seat_json=json.dumps(seat))
    assert _bb_calls(env) == [], f"{rel}: no handoff when the Seat {field} is {value!r}"


@pytest.mark.parametrize("rel", GUIDES)
def test_handoff_lines_use_deployed_bb_flags(rel):
    text = (ROOT / rel).read_text(encoding="utf-8")
    for snippet in _snippets(text):
        for line in snippet.splitlines():
            if re.search(r"\bbb\s+handoff\b", line) and "handoff coordinator" not in line:
                assert "--reasoning-level" not in line and "--provider" not in line, \
                    f"{rel}: bb handoff takes --to and --effort, not --provider or --reasoning-level: {line.strip()}"
