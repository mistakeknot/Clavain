#!/usr/bin/env python3
"""Offline scoring for tests/evals/skill-routing.json.

Asks ONE headless `claude -p` session per batch which skill it would load for
each prompt, given only skill names and descriptions. Runs through the bb
account pooler, which is meant to use subscription quota; this script reads no API key itself, but see the spend boundary below. A prompt with no parseable
answer is counted "not run", never a pass.

Usage: eval-skill-routing.py [--limit N] [--batch-size N] [--model M] [--dry-run]
Default --limit is 10 prompts; the cap is deliberate (quota).

Spend boundary: `bb pool exec` has no subscription-only flag, and the pool's own
fallback policy (extra usage, API-key accounts) cannot be enforced from this
script. The only guard here is a preflight that refuses to run unless
`bb pool account list` shows at least one enabled, ready subscription (oauth)
account with headroom. It does not stop the pool from choosing another account.
"""
import argparse, json, os, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVALS = ROOT / "tests" / "evals" / "skill-routing.json"

# Skills that live outside this repo but are part of the overlap clusters.
EXTERNAL = {
    "interflux:flux-drive": "Multi-agent review of documents, code or diffs: triage, dispatch specialist agents, synthesize findings.",
}


# Only these aliases are normalized; everything else must match exactly.
ALIASES = {"flux-drive": "interflux:flux-drive"}


def canon(name: str, own=None) -> str:
    """Canonical identity. `own` (this repo's bare skill/command names) enables the
    explicit rule that "clavain:<name>" equals bare <name> for names in that set only."""
    name = name.strip().lstrip("/")
    if own and name.startswith("clavain:") and name[len("clavain:"):] in own:
        name = name[len("clavain:"):]
    return ALIASES.get(name, name)  # "none" is accepted only as the bare token


def own_names() -> set:
    return {p.parent.name for p in (ROOT / "skills").glob("*/SKILL.md")} | {
        p.stem for p in (ROOT / "commands").glob("*.md")}


def score(got: str, exp: str, own) -> tuple:
    """Return (strict_match, normalized_match)."""
    return canon(got) == canon(exp), canon(got, own) == canon(exp, own)


def preflight(text: str = None) -> tuple:
    """Return (ok, message) from `bb pool account list` output."""
    if text is None:
        r = subprocess.run(["bb", "pool", "account", "list"], capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            return False, "bb pool account list failed: " + r.stderr[-200:]
        text = r.stdout
    rows = [l.split("\t") for l in text.splitlines()[1:] if l.strip()]
    for c in rows:
        if len(c) >= 15 and c[3] == "claude" and c[5] == "true" and c[4] != "oauth":
            return False, "an enabled non-oauth claude account is in the pool; refusing to run"
    for c in rows:
        if len(c) >= 15 and c[3] == "claude" and c[4] == "oauth" and c[5] == "true" and c[14].strip() == "ready":
            pct = c[7].strip().rstrip("%")
            if pct.isdigit() and int(pct) < 100:
                return True, ""
    return False, "no enabled, ready subscription (oauth) claude account with 5h headroom; refusing to run"


def positive_int(v):
    n = int(v)
    if n <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return n


def description(path: Path) -> str:
    m = re.search(r'^description:\s*(.+)$', path.read_text(errors="replace"), re.M)
    return m.group(1).strip().strip('"') if m else ""


def catalog() -> dict:
    cat = {}
    for p in sorted((ROOT / "skills").glob("*/SKILL.md")):
        cat[p.parent.name] = description(p)
    for p in sorted((ROOT / "commands").glob("*.md")):
        cat.setdefault(p.stem, description(p))
    cat.update(EXTERNAL)
    return cat


def build_prompt(cat, items):
    lines = ["You route user requests to skills. Available skills (name: description):", ""]
    lines += [f"- {n}: {d[:220]}" for n, d in cat.items()]
    lines += ["", 'For each numbered request below, name the ONE skill you would load, or "none" if no skill applies.',
              'Reply with ONLY a JSON object mapping the request number (string) to the skill name. No prose.', ""]
    lines += [f"{n}. {it['prompt']}" for n, (_, it) in enumerate(items, 1)]
    return "\n".join(lines)


INPUT_DIR = Path.home() / ".local/state/bb-account-pool/exec-input"


def ask(prompt, model):
    # The pool host allows only: --print --output-format text --max-turns 1 --model,
    # and reads stdin files only from INPUT_DIR (direct children).
    f = INPUT_DIR / f"skill-routing-{os.getpid()}.txt"
    f.write_text(prompt)
    try:
        cmd = ["bb", "pool", "exec", "--stdin-file", str(f), "--", "claude", "--print",
               "--output-format", "text", "--max-turns", "1", "--model", model or "sonnet"]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    finally:
        f.unlink(missing_ok=True)
    if r.returncode != 0:
        return None, None, r.stderr[-300:]
    if os.environ.get("EVAL_RAW_OUT"):
        Path(os.environ["EVAL_RAW_OUT"]).write_text(r.stdout)
    m = re.search(r"\{.*\}", r.stdout, re.S)
    try:
        return json.loads(m.group(0)), None, ""
    except (AttributeError, json.JSONDecodeError):
        return None, None, "unparseable reply"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=positive_int, default=10)
    ap.add_argument("--batch-size", type=positive_int, default=10)
    ap.add_argument("--model", default=None)
    ap.add_argument("--dry-run", action="store_true", help="print the first batch prompt and exit")
    a = ap.parse_args()
    if not a.dry_run:
        ok, msg = preflight()
        if not ok:
            print(f"preflight: {msg}", file=sys.stderr); return 2
    allitems = list(enumerate(json.loads(EVALS.read_text())))
    step = max(1, len(allitems) // a.limit)  # evenly spaced sample across clusters
    items = allitems[::step][: a.limit]
    cat = catalog()
    if a.dry_run:
        print(build_prompt(cat, items[: a.batch_size])); return 0
    passed = failed = not_run = strict_passed = 0
    own = own_names()
    misses, usages = [], []
    for s in range(0, len(items), a.batch_size):
        batch = items[s : s + a.batch_size]
        ans, usage, err = ask(build_prompt(cat, batch), a.model)
        usages.append(usage)
        if err:
            print(f"batch error: {err}", file=sys.stderr)
        for bi, (i, it) in enumerate(batch, 1):
            got = (ans or {}).get(str(bi))
            if not isinstance(got, str) or not got.strip():
                not_run += 1; continue
            got = got.strip().lstrip("/")
            exp = it["expected"]
            strict, norm = score(got, exp, own)
            strict_passed += strict
            if norm:
                passed += 1
            else:
                failed += 1; misses.append((it["prompt"], exp, got))
    ran = passed + failed
    print(f"prompts={len(items)} ran={ran} not_run={not_run} pass={passed} fail={failed} "
          f"strict_pass={strict_passed} normalized_pass={passed}")
    if ran:
        print(f"strict_accuracy_of_all={strict_passed/len(items):.0%}  "
              f"normalized_accuracy_of_ran={passed/ran:.0%}  normalized_accuracy_of_all={passed/len(items):.0%}")
    for p, e, g in misses:
        print(f"MISS expected={e} got={g} :: {p}")
    print("usage:", json.dumps(usages))
    return 0


if __name__ == "__main__":
    sys.exit(main())
