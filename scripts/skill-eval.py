#!/usr/bin/env python3
"""Behavioural skill evals: one headless `claude -p` session per case, regex-graded.

Cases live in tests/skill-evals/cases.json; each names a fixture directory, a
prompt, and checks over the stream-json transcript, the fixture files after the
run, and the last assistant message.

Exit codes: 0 every case passed, 1 a case failed, 2 NOT RUN. A case that did
not run is never a pass: when any case did not run and none failed the exit is
2, and the summary names those cases.

Live sessions run with permission checks off. CLAVAIN_SKILL_EVAL_GUEST=1 is a
CALLER ASSERTION that the process already runs inside an isolated fresh CI guest;
this script verifies nothing about that and enforces no isolation. The per-run
temp directory is not filesystem isolation. Refusing when ANTHROPIC_API_KEY or
ANTHROPIC_AUTH_TOKEN is set is a best-effort check on two variables; it does not
establish that the run uses subscription quota only: the inherited environment
and project/local credential config remain available to the session. The skill
copy under test is mounted with --plugin-dir and --setting-sources project,local
limits settings, which stops a globally installed skill copy from answering.

A session only counts when claude exits 0 and the stream ends with a `result`
event whose is_error is false and subtype is "success"; otherwise the case is
NOT RUN and no check is graded.

Case files are trusted input: regexes have no timeout. Malformed cases (missing
fixture, bad regex, duplicate id) are NOT RUN results; the rest still run and
the JSON summary is still written.

--replay DIR grades recorded transcripts (DIR/<case id>.jsonl) with no session.
"""
import argparse, fnmatch, json, os, re, shutil, subprocess, sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = ROOT / "tests" / "skill-evals"
PASS, FAIL, NOT_RUN = "pass", "fail", "not-run"
CHECK_TYPES = {"tool_used", "tool_ok", "trace", "files", "last_message"}


class NotRun(Exception):
    pass


def load_cases(path):
    cases = json.loads(Path(path).read_text())
    if not isinstance(cases, list):
        raise ValueError("cases file must be a JSON list")
    return cases


def validate_case(c, seen):
    if not isinstance(c, dict):
        raise ValueError("case is not an object")
    for k in ("id", "skill", "fixture", "prompt", "checks"):
        if k not in c:
            raise ValueError(f"case missing {k}")
    if c["id"] in seen:
        raise ValueError(f"duplicate case id {c['id']}")
    seen.add(c["id"])
    if not c["checks"]:
        raise ValueError("case has no checks")
    if not (EVAL_DIR / "fixtures" / str(c["fixture"])).is_dir():
        raise ValueError(f"missing fixture {c['fixture']}")
    if not (ROOT / "skills" / str(c["skill"]) / "SKILL.md").is_file():
        raise ValueError(f"unknown skill {c['skill']}")
    for ch in c["checks"]:
        if ch.get("type") not in CHECK_TYPES:
            raise ValueError(f"bad check type {ch.get('type')}")
        for key in ("regex", "input", "output"):
            if ch.get(key):
                re.compile(ch[key])
        need = {"tool_used": "tool", "tool_ok": "tool", "trace": "regex",
                "last_message": "regex", "files": "path"}[ch["type"]]
        if not ch.get(need):
            raise ValueError(f"{ch['type']} check needs {need}")


def parse_stream(text):
    """Return (calls[(name, input_json, id)], results{id: (is_error, text)}, last_message, result_event)."""
    calls, results, last, final = [], {}, "", None
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if not isinstance(ev, dict):
            continue
        content = (ev.get("message") or {}).get("content")
        content = content if isinstance(content, list) else []
        if ev.get("type") == "assistant":
            texts = []
            for blk in content:
                if blk.get("type") == "tool_use":
                    calls.append((blk.get("name", ""), json.dumps(blk.get("input", {})), blk.get("id")))
                elif blk.get("type") == "text":
                    texts.append(blk.get("text", ""))
            if texts:
                last = "\n".join(texts)
        elif ev.get("type") == "user":
            for blk in content:
                if blk.get("type") == "tool_result":
                    c = blk.get("content", "")
                    if isinstance(c, list):
                        c = " ".join(b.get("text", "") for b in c if isinstance(b, dict))
                    results[blk.get("tool_use_id")] = (bool(blk.get("is_error")), str(c))
        elif ev.get("type") == "result":
            final = ev
            if isinstance(ev.get("result"), str):
                last = ev["result"]
    return calls, results, last, final


def check_session(final, returncode):
    """Reject an unsuccessful session before any check is graded."""
    if returncode not in (None, 0):
        raise NotRun(f"claude exited {returncode}")
    if final is None:
        raise NotRun("no result event in transcript")
    if final.get("is_error") or final.get("subtype") != "success":
        raise NotRun(f"session ended in error (subtype={final.get('subtype')!r}, is_error={final.get('is_error')!r})")


def run_check(ch, calls, results, raw, last, workdir):
    t = ch["type"]
    rx = re.compile(ch["regex"]) if ch.get("regex") else None
    want = ch.get("present", True)
    if t == "tool_used":
        irx = re.compile(ch["input"]) if ch.get("input") else None
        hit = any(n == ch["tool"] and (irx is None or irx.search(i)) for n, i, _ in calls)
        return hit == want, f"tool {ch['tool']} used={hit}"
    if t == "tool_ok":
        # a matching call whose tool_result exists, is not an error, and (optionally) matches `output`
        irx = re.compile(ch["input"]) if ch.get("input") else None
        orx = re.compile(ch["output"]) if ch.get("output") else None
        hit = False
        for n, i, cid in calls:
            r = results.get(cid)
            if n == ch["tool"] and (irx is None or irx.search(i)) and r and not r[0] \
                    and (orx is None or orx.search(r[1])):
                hit = True
        return hit == want, f"tool {ch['tool']} succeeded={hit}"
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


def grade(case, raw, workdir, returncode=None):
    calls, tresults, last, final = parse_stream(raw)
    check_session(final, returncode)
    results = [(ch["type"],) + run_check(ch, calls, tresults, raw, last, workdir) for ch in case["checks"]]
    return all(ok for _, ok, _ in results), results


def guard_live(env):
    if env.get("CLAVAIN_SKILL_EVAL_GUEST") != "1":
        raise NotRun("live run refused: not inside an isolated CI guest (CLAVAIN_SKILL_EVAL_GUEST!=1)")
    for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        if env.get(k):
            raise NotRun(f"live run refused: {k} is set; refusing (best-effort check only)")
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
    return r.stdout, r.returncode


def run_case(case, replay=None, claude_args=()):
    start = time.time()
    status, detail = NOT_RUN, "not run"
    try:
        with tempfile.TemporaryDirectory(prefix="skill-eval-") as tmp:
            work = Path(tmp) / "work"
            shutil.copytree(EVAL_DIR / "fixtures" / case["fixture"], work)
            rc = None
            if replay:
                f = Path(replay) / f"{case['id']}.jsonl"
                if not f.is_file():
                    raise NotRun(f"no recorded transcript {f.name}")
                raw = f.read_text()
                rcf = Path(replay) / f"{case['id']}.rc"
                if rcf.is_file():
                    rc = int(rcf.read_text().strip())
                rf = Path(replay) / f"{case['id']}.files"
                if rf.is_dir():
                    shutil.copytree(rf, work, dirs_exist_ok=True)
            else:
                raw, rc = live_session(case, work, claude_args)
            ok, results = grade(case, raw, work, rc)
            status = PASS if ok else FAIL
            detail = [{"check": t, "ok": o, "note": n} for t, o, n in results]
    except NotRun as e:
        status, detail = NOT_RUN, str(e)
    except Exception as e:  # malformed case or unexpected error: never a pass
        status, detail = NOT_RUN, f"{type(e).__name__}: {e}"
    return {"id": str(case.get("id") if isinstance(case, dict) else "?"), "status": status,
            "detail": detail, "seconds": round(time.time() - start, 1)}


def run_all(cases, replay=None, only=None):
    results, seen = [], set()
    for c in cases:
        try:
            validate_case(c, seen)
        except Exception as e:
            cid = c.get("id", "?") if isinstance(c, dict) else "?"
            results.append({"id": str(cid), "status": NOT_RUN, "detail": f"invalid case: {e}", "seconds": 0.0})
            continue
        if only and c["id"] not in only:
            continue
        results.append(run_case(c, replay))
    return results


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
        unknown = set(a.case) - {c.get("id") for c in cases if isinstance(c, dict)}
        if unknown:
            print(f"unknown case id(s): {sorted(unknown)}", file=sys.stderr)
            return 2
    results = run_all(cases, a.replay, set(a.case) if a.case else None)
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
