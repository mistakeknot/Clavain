#!/usr/bin/env python3
"""Behavioural skill evals: one headless `claude -p` session per case, regex-graded.

Cases live in tests/skill-evals/cases.json; each names a fixture directory, a
prompt, and checks over the stream-json transcript, the fixture files after the
run, and the last assistant message.

Exit codes: 0 every case passed, 1 a case failed, 2 NOT RUN. A case that did
not run is never a pass: when any case did not run and none failed the exit is
2, and the summary names those cases.

Live sessions run with permission checks off, so they run ONLY inside an
isolated fresh CI guest, signalled by CLAVAIN_SKILL_EVAL_GUEST=1 set by the
guest recipe. Anywhere else a live run is refused (NOT RUN). An API key in the
environment is also refused: runs use subscription quota only. The session
sees only the skill copy under test (--plugin-dir) and project/local settings
(--setting-sources project,local), so a globally installed copy cannot answer.

--replay DIR grades recorded transcripts (DIR/<case id>.jsonl) with no session.
"""
import argparse, fnmatch, json, os, re, shutil, subprocess, sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = ROOT / "tests" / "skill-evals"
PASS, FAIL, NOT_RUN = "pass", "fail", "not-run"
CHECK_TYPES = {"tool_used", "trace", "files", "last_message"}


class NotRun(Exception):
    pass


def load_cases(path):
    cases = json.loads(Path(path).read_text())
    seen = set()
    for c in cases:
        for k in ("id", "skill", "fixture", "prompt", "checks"):
            if k not in c:
                raise ValueError(f"case missing {k}: {c.get('id')}")
        if c["id"] in seen:
            raise ValueError(f"duplicate case id {c['id']}")
        seen.add(c["id"])
        if not c["checks"]:
            raise ValueError(f"case {c['id']} has no checks")
        for ch in c["checks"]:
            if ch.get("type") not in CHECK_TYPES:
                raise ValueError(f"case {c['id']}: bad check type {ch.get('type')}")
    return cases


def parse_stream(text):
    """Return (events, tool_calls[(name, input_json)], last_message)."""
    events, calls, last = [], [], ""
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        events.append(ev)
        if ev.get("type") == "assistant":
            texts = []
            for blk in (ev.get("message") or {}).get("content") or []:
                if blk.get("type") == "tool_use":
                    calls.append((blk.get("name", ""), json.dumps(blk.get("input", {}))))
                elif blk.get("type") == "text":
                    texts.append(blk.get("text", ""))
            if texts:
                last = "\n".join(texts)
        elif ev.get("type") == "result" and isinstance(ev.get("result"), str):
            last = ev["result"]
    return events, calls, last


def run_check(ch, calls, raw, last, workdir):
    t = ch["type"]
    rx = re.compile(ch["regex"]) if ch.get("regex") else None
    want = ch.get("present", True)
    if t == "tool_used":
        irx = re.compile(ch["input"]) if ch.get("input") else None
        hit = any(n == ch["tool"] and (irx is None or irx.search(i)) for n, i in calls)
        return hit == want, f"tool {ch['tool']} used={hit}"
    if t == "trace":
        hit = bool(rx.search(raw))
        return hit == want, f"trace match={hit}"
    if t == "last_message":
        hit = bool(rx.search(last))
        return hit == want, f"last message match={hit}"
    # files: glob relative to workdir; present=false means no file may match
    files = [p for p in workdir.rglob("*") if p.is_file()
             and fnmatch.fnmatch(p.relative_to(workdir).as_posix(), ch["path"])]
    if not want:
        return not files, f"files {ch['path']} found={len(files)}"
    if not files:
        return False, f"no file matches {ch['path']}"
    if rx is None:
        return True, f"file {ch['path']} exists"
    ok = any(rx.search(p.read_text(errors="replace")) for p in files)
    return ok, f"file {ch['path']} regex match={ok}"


def grade(case, raw, workdir):
    _, calls, last = parse_stream(raw)
    if not calls and not last:
        raise NotRun("session produced no parseable transcript")
    results = [(ch["type"],) + run_check(ch, calls, raw, last, workdir) for ch in case["checks"]]
    return all(ok for _, ok, _ in results), results


def guard_live(env):
    if env.get("CLAVAIN_SKILL_EVAL_GUEST") != "1":
        raise NotRun("live run refused: not inside an isolated CI guest (CLAVAIN_SKILL_EVAL_GUEST!=1)")
    for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        if env.get(k):
            raise NotRun(f"live run refused: {k} is set; subscription quota only")
    if not shutil.which("claude"):
        raise NotRun("claude CLI not found")


def live_session(case, workdir, claude_args=()):
    guard_live(os.environ)
    skill_src = ROOT / "skills" / case["skill"]
    plugin = Path(tempfile.mkdtemp(prefix="skill-eval-plugin-"))
    (plugin / ".claude-plugin").mkdir()
    (plugin / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": "clavain", "version": "0.0.0-eval"}))
    shutil.copytree(skill_src, plugin / "skills" / case["skill"])
    cmd = ["claude", "-p", case["prompt"], "--output-format", "stream-json", "--verbose",
           "--setting-sources", "project,local", "--plugin-dir", str(plugin),
           "--permission-mode", "bypassPermissions",
           "--max-turns", str(case.get("max_turns", 10)), *claude_args]
    try:
        r = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True, timeout=case.get("timeout", 900))
    except subprocess.TimeoutExpired:
        raise NotRun("session timed out")
    finally:
        shutil.rmtree(plugin, ignore_errors=True)
    if r.returncode != 0 and not r.stdout.strip():
        raise NotRun(f"claude exited {r.returncode}: {r.stderr[-200:]}")
    return r.stdout


def run_case(case, replay=None, claude_args=()):
    start = time.time()
    with tempfile.TemporaryDirectory(prefix="skill-eval-") as tmp:
        work = Path(tmp) / "work"
        shutil.copytree(EVAL_DIR / "fixtures" / case["fixture"], work)
        try:
            if replay:
                f = Path(replay) / f"{case['id']}.jsonl"
                if not f.is_file():
                    raise NotRun(f"no recorded transcript {f.name}")
                raw = f.read_text()
                rf = Path(replay) / f"{case['id']}.files"
                if rf.is_dir():
                    shutil.copytree(rf, work, dirs_exist_ok=True)
            else:
                raw = live_session(case, work, claude_args)
            ok, results = grade(case, raw, work)
            status = PASS if ok else FAIL
            detail = [{"check": t, "ok": o, "note": n} for t, o, n in results]
        except NotRun as e:
            status, detail = NOT_RUN, str(e)
    return {"id": case["id"], "status": status, "detail": detail, "seconds": round(time.time() - start, 1)}


def exit_code(results):
    st = [r["status"] for r in results]
    if FAIL in st:
        return 1
    if NOT_RUN in st or not st:
        return 2
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--cases", default=str(EVAL_DIR / "cases.json"))
    ap.add_argument("--case", action="append", help="run only this case id (repeatable)")
    ap.add_argument("--replay", help="grade recorded transcripts from DIR instead of running sessions")
    ap.add_argument("--out", help="write JSON results here")
    a = ap.parse_args(argv)
    cases = load_cases(a.cases)
    if a.case:
        unknown = set(a.case) - {c["id"] for c in cases}
        if unknown:
            print(f"unknown case id(s): {sorted(unknown)}", file=sys.stderr)
            return 2
        cases = [c for c in cases if c["id"] in a.case]
    results = [run_case(c, a.replay) for c in cases]
    for r in results:
        print(f"{r['status'].upper():8} {r['id']} ({r['seconds']}s)")
        if r["status"] != PASS:
            print(f"         {r['detail']}")
    code = exit_code(results)
    print({0: "ALL PASSED", 1: "FAILED", 2: "NOT RUN (this is not a pass)"}[code])
    if a.out:
        Path(a.out).write_text(json.dumps(results, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
