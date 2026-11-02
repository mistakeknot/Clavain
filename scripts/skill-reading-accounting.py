#!/usr/bin/env python3
"""Reading accounting for progressive disclosure of skills.

Parses existing Claude Code session transcripts (JSONL, read-only, local only)
and, for each invocation of a Clavain skill, attributes the reads of that
skill's references/ files and SKILL*.md files: Read tool calls and Bash reads
(cat/head/tail/sed/less/grep/rg/ls/wc, globs, grep -r).

Per skill it reports:
  invocations                 Skill tool calls naming the skill
  reference_bytes_per_inv     bytes of reference files read (result size) / invocations
  full_open_share             share of invocations that opened every reference file
  compact_reads               reads of SKILL-compact.md (and share of invocations)
  unattributed_calls          reads of a skill path that could not be tied to
                              a specific file and invocation, as a share of
                              all reads of skill paths

Stop rule: if more than --max-unattributed (default 0.30) of skill-path reads
cannot be attributed, the report says STOP and the exit status is 3.

Only counts and paths relative to the skill directory are emitted; transcript
text is never printed. Run niced; it is single threaded.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shlex
import sys
from collections import defaultdict

# .../skills/<skill>/<rest>
SKILL_PATH_RE = re.compile(r"skills/([A-Za-z0-9._-]+)/((?:references/[^\s'\"|;&<>)]*)|(?:SKILL[A-Za-z0-9._-]*\.md))")
# a bare skills/<skill>/references directory or glob target
SKILL_DIR_RE = re.compile(r"skills/([A-Za-z0-9._-]+)(?:/references)?/?[*\s'\"]|skills/([A-Za-z0-9._-]+)/?$")
READ_CMDS = {"cat", "head", "tail", "sed", "less", "more", "grep", "egrep", "rg", "ls", "wc", "awk", "bat", "nl"}
GLOB_CHARS = set("*?[")


def skill_files(skills_dir):
    """Map skill -> {'refs': {relpath: size}, 'compact': bool} from a checkout."""
    out = {}
    for d in sorted(glob.glob(os.path.join(skills_dir, "*"))):
        if not os.path.isdir(d):
            continue
        name = os.path.basename(d)
        refs = {}
        for root, _, files in os.walk(os.path.join(d, "references")):
            for f in files:
                p = os.path.join(root, f)
                refs[os.path.relpath(p, d)] = os.path.getsize(p)
        out[name] = {"refs": refs, "compact": os.path.exists(os.path.join(d, "SKILL-compact.md"))}
    return out


def split_commands(cmd):
    """Split a shell command into simple commands (best effort)."""
    parts = re.split(r"\|\||&&|;|\||\n", cmd)
    return [p.strip() for p in parts if p.strip()]


def classify_bash(cmd):
    """Return list of (kind, token) for each skill path a read command touches.

    kind: 'path' (concrete file), 'glob' (glob/recursive/dir listing)."""
    hits = []
    for sub in split_commands(cmd):
        try:
            toks = shlex.split(sub)
        except ValueError:
            toks = sub.split()
        if not toks:
            continue
        i = 0
        while i < len(toks) and (re.match(r"^\w+=", toks[i]) or toks[i] in ("sudo", "nice", "time")):
            i += 1
        if i >= len(toks) or os.path.basename(toks[i]) not in READ_CMDS:
            continue
        recursive = any(t in ("-r", "-R", "-rn", "-rl", "-rI", "--recursive") or (t.startswith("-") and not t.startswith("--") and "r" in t[1:] and toks[i] in ("grep", "egrep")) for t in toks[i + 1:])
        for t in toks[i + 1:]:
            if t.startswith("-"):
                continue
            if "skills/" not in t:
                continue
            m = SKILL_PATH_RE.search(t)
            if m and not (GLOB_CHARS & set(t)):
                hits.append(("path", m.group(1), m.group(2)))
                continue
            m2 = re.search(r"skills/([A-Za-z0-9._-]+)", t)
            if m2:
                hits.append(("glob" if (GLOB_CHARS & set(t)) or recursive or toks[i] == "ls" else "dir", m2.group(1), t))
    return hits


def iter_events(path):
    with open(path, errors="replace") as fh:
        for line in fh:
            if "tool_use" not in line and "tool_result" not in line:
                continue
            try:
                yield json.loads(line)
            except ValueError:
                continue


def result_size(ev, block):
    """Bytes of output a tool_result delivered."""
    tur = ev.get("toolUseResult")
    if isinstance(tur, dict):
        f = tur.get("file")
        if isinstance(f, dict) and isinstance(f.get("content"), str):
            return len(f["content"].encode("utf-8", "replace"))
        if isinstance(tur.get("stdout"), str):
            return len(tur["stdout"].encode("utf-8", "replace"))
    c = block.get("content")
    if isinstance(c, str):
        return len(c.encode("utf-8", "replace"))
    if isinstance(c, list):
        return sum(len(x.get("text", "").encode("utf-8", "replace")) for x in c if isinstance(x, dict))
    return 0


def new_stats():
    return {"invocations": 0, "ref_bytes": 0, "full_open_invocations": 0,
            "compact_reads": 0, "compact_invocations": 0, "skill_md_reads": 0,
            "reads": 0, "unattributed": 0, "why": defaultdict(int), "ref_reads": 0, "per_ref": defaultdict(int)}


def process_session(path, inv, skills):
    """Accumulate into inv (skill -> stats). Returns list of per-invocation dicts."""
    active = {}   # skill -> current invocation dict
    pending = {}  # tool_use_id -> list of (skill|None, rel|None, kind)
    done = []

    def start(skill):
        rec = {"skill": skill, "refs": set(), "ref_bytes": 0, "compact": False}
        active[skill] = rec
        done.append(rec)
        return rec

    for ev in iter_events(path):
        content = ev.get("message", {}).get("content")
        if not isinstance(content, list):
            continue
        for b in content:
            if not isinstance(b, dict):
                continue
            t = b.get("type")
            if t == "tool_use":
                name, inp, tid = b.get("name"), b.get("input") or {}, b.get("id")
                if name == "Skill":
                    sk = str(inp.get("skill", ""))
                    if sk.startswith("clavain:"):
                        sk = sk.split(":", 1)[1]
                        if sk in skills:
                            start(sk)
                    continue
                items = []
                if name == "Read":
                    fp = str(inp.get("file_path", ""))
                    m = SKILL_PATH_RE.search(fp)
                    if m:
                        items.append(("path", m.group(1), m.group(2)))
                elif name in ("Grep", "Glob"):
                    s = " ".join(str(inp.get(k, "")) for k in ("path", "pattern", "glob"))
                    m = re.search(r"skills/([A-Za-z0-9._-]+)", s)
                    if m:
                        items.append(("glob", m.group(1), s))
                elif name == "Bash":
                    items = classify_bash(str(inp.get("command", "")))
                if items:
                    pending[tid] = items
            elif t == "tool_result":
                tid = b.get("tool_use_id")
                items = pending.pop(tid, None)
                if not items:
                    continue
                size = result_size(ev, b)
                share = size // max(len(items), 1)
                for kind, sk, rel in items:
                    if sk not in skills:
                        continue  # not a Clavain skill; not counted at all
                    st = inv[sk]
                    st["reads"] += 1
                    rec = active.get(sk)
                    if kind != "path" or rec is None or b.get("is_error"):
                        st["unattributed"] += 1
                        why = ("not_a_concrete_file" if kind != "path"
                               else "no_prior_invocation" if rec is None else "tool_error")
                        st["why"][why] += 1
                        continue
                    if rel.startswith("references/"):
                        key = rel
                        rec["refs"].add(key)
                        rec["ref_bytes"] += share
                        st["ref_bytes"] += share
                        st["ref_reads"] += 1
                        st["per_ref"][key] += share
                    elif rel == "SKILL-compact.md":
                        rec["compact"] = True
                        st["compact_reads"] += 1
                    else:
                        st["skill_md_reads"] += 1
    return done


def main(argv=None):
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--transcripts", default=os.path.expanduser("~/.claude/projects"),
                    help="directory holding <project>/*.jsonl session files")
    ap.add_argument("--skills-dir", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "skills"),
                    help="Clavain skills/ directory (source of reference inventory)")
    ap.add_argument("--max-unattributed", type=float, default=0.30)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="max session files (0 = all)")
    args = ap.parse_args(argv)

    skills = skill_files(args.skills_dir)
    inv = {s: new_stats() for s in skills}
    files = sorted(glob.glob(os.path.join(args.transcripts, "*", "*.jsonl")) +
                   glob.glob(os.path.join(args.transcripts, "*.jsonl")))
    if args.limit:
        files = files[:args.limit]
    sessions = 0
    for f in files:
        try:
            recs = process_session(f, inv, skills)
        except OSError:
            continue
        sessions += 1
        for r in recs:
            st = inv[r["skill"]]
            st["invocations"] += 1
            refs = skills[r["skill"]]["refs"]
            if refs and set(refs) <= r["refs"]:
                st["full_open_invocations"] += 1
            if r["compact"]:
                st["compact_invocations"] += 1

    total_reads = sum(s["reads"] for s in inv.values())
    total_un = sum(s["unattributed"] for s in inv.values())
    un_share = (total_un / total_reads) if total_reads else 0.0
    stop = total_reads > 0 and un_share > args.max_unattributed
    out = {"sessions": sessions, "skill_path_reads": total_reads,
           "unattributed_calls": total_un, "unattributed_share": round(un_share, 4),
           "stop": stop, "skills": {}}
    for name, st in sorted(inv.items()):
        n = st["invocations"]
        nrefs = len(skills[name]["refs"])
        out["skills"][name] = {
            "invocations": n,
            "reference_files": nrefs,
            "reference_bytes_total": st["ref_bytes"],
            "reference_bytes_per_invocation": round(st["ref_bytes"] / n, 1) if n else None,
            "full_open_share": round(st["full_open_invocations"] / n, 3) if n and nrefs else None,
            "has_compact": skills[name]["compact"],
            "compact_reads": st["compact_reads"],
            "compact_invocation_share": round(st["compact_invocations"] / n, 3) if n else None,
            "skill_md_reads": st["skill_md_reads"],
            "skill_path_reads": st["reads"],
            "unattributed_calls": st["unattributed"],
            "unattributed_share": round(st["unattributed"] / st["reads"], 3) if st["reads"] else None,
            "unattributed_reasons": dict(st["why"]),
            "per_reference_bytes": dict(sorted(st["per_ref"].items())),
        }
    if args.json:
        json.dump(out, sys.stdout, indent=2)
        print()
    else:
        print(f"sessions={sessions} skill_path_reads={total_reads} unattributed={total_un} ({un_share:.1%})")
        print(f"{'skill':32} {'inv':>5} {'refs':>4} {'B/inv':>9} {'full%':>6} {'compact':>7} {'unattr':>6}")
        for name, s in out["skills"].items():
            if not (s["invocations"] or s["skill_path_reads"]):
                continue
            bpi = "-" if s["reference_bytes_per_invocation"] is None else f"{s['reference_bytes_per_invocation']:.0f}"
            fo = "-" if s["full_open_share"] is None else f"{s['full_open_share']:.0%}"
            ua = "-" if s["unattributed_share"] is None else f"{s['unattributed_share']:.0%}"
            print(f"{name:32} {s['invocations']:>5} {s['reference_files']:>4} {bpi:>9} {fo:>6} {s['compact_reads']:>7} {ua:>6}")
        if stop:
            print(f"STOP: {un_share:.1%} of skill-path reads are unattributed (limit {args.max_unattributed:.0%}); "
                  "the numbers above are not reliable.")
    return 3 if stop else 0


if __name__ == "__main__":
    sys.exit(main())
