#!/usr/bin/env python3
"""Dry-run a plan's verify gauge against the plan's own emitted output.

WHY THIS EXISTS

Pilot 1 (shadow-work, 2026-07-27) ran the same three defects through two
independently authored plans, twice. Across two rounds and four executions:

  * every one of ~60 edits applied byte-exact, in both arms, with zero drift;
  * every single stop was a defect in the plan's OWN verify block.

Six such defects were observed, and five of them share one shape: the plan's
emitted text is simultaneously the artifact AND an input to a checker the same
author wrote, and nobody ever executed the one against the other. Reviewing a
gauge by reading it does not catch this - two frontier-tier authors, a
frontier-tier reviewer, and the harness itself all missed instances of it. The
check has to be mechanical.

So this linter does the only thing that reliably finds them: it applies the
plan's edits to a virtual copy of the tree, then runs the plan's own verify
commands against the result and compares with the plan's stated expectations.

WHAT IT CATCHES  (codes, and the pilot-1 defect each replays)

  GAUGE001  self-match         a verify grep expecting no output matches text
                               the same plan writes.
                               - round 2 arm A: edit emits `AppExit` into a doc
                                 comment; the same task greps for `AppExit`
                                 expecting nothing.
                               - harness: the frozen gauge contained the token
                                 `interp_fps` and lived under crates/, which a
                                 plan's `grep -rn interp_fps crates/` forbids.
  GAUGE002  unescaped-metachar a literal search run as a regex, so it over-
                               matches.
                               - round 1 arm B: `grep -c "r.displayed"` counted
                                 3 (the `.` matched `ring.displayed` twice)
                                 where the plan expected 1.
  GAUGE003  shell-quote        emitted text breaks the quoting of the file it
                               lands in.
                               - round 2 arm B: apostrophes in awk comments
                                 ("sink's", "ring's") closed the enclosing bash
                                 single-quote; `bash -n` died 4 lines later.
  GAUGE004  feature-gate       a `cargo test -p C` verify asserts on tests that
                               its own command cannot compile.
                               - round 1 arm A: the tests live in a module gated
                                 on a non-default feature; resolver=2 means a
                                 sibling crate's dependency does not unify it,
                                 so the required lines can never appear.
  GAUGE005  stale-artifact     a verify runs a built artifact that is only built
                               when absent, so a stale one is silently reused.
                               - the gauge's own v1 defect: a binary predating
                                 every edit reproduced the original defect
                                 signature and read as a genuine FAIL.

USAGE

    plan-gauge-lint.py PLAN.md [--contract auto|brief|exact] [--repo-root DIR]
                              [--extra-artifact PATH]...
    plan-gauge-lint.py --self-test        # replay all seven known defects

--repo-root turns the heuristics into a real dry-run: files named by the plan
are read, the plan's edits are applied in order, and the verify commands run
against that virtual post-edit tree. Without it the linter still works, using
only the plan's emitted blocks as the corpus, but it sees less.

Exit 0 = no blocking findings. Exit 1 = at least one. Exit 2 = usage/parse error.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

# --------------------------------------------------------------------------
# Plan model
# --------------------------------------------------------------------------

FENCE_RE = re.compile(r"^([ \t]*)(`{3,}|~{3,})[ \t]*([A-Za-z0-9_+.-]*)[ \t]*$")

# Markers that mean "the fence that follows is text this plan WRITES".
EMIT_MARKERS = (
    "new_string",
    "new:",
    "new",
    "replace with",
    "replacement",
    "replace it with",
    "after:",
    "to:",
    "becomes",
)
# Markers that mean "the fence that follows is text this plan MATCHES on".
OLD_MARKERS = (
    "old_string",
    "old:",
    "old",
    "before:",
    "from:",
    "find:",
    "current",
)
VERIFY_HINT = re.compile(r"\bverif|\bcheck\b|\bacceptance\b|\bgate\b", re.I)

# A path we can attribute an edit or a grep to.
PATH_RE = re.compile(r"[\w./-]*[\w-]+\.(?:rs|sh|toml|py|md|yaml|yml|json|ts|js|bats)\b")

# New-file grammar from the Pattern F contract: a prose line reading
#     Create `relative/path` with:
# followed by ONE fenced block holding the complete content of the new file.
# The path must contain a dot or a slash, so prose such as "Create fixtures
# with:" does not make "fixtures" a file; a leading list marker ("- ", "1. ")
# and a tail such as "with the following content:" are accepted.
CREATE_RE = re.compile(r"^\s*(?:(?:[-*]|\d+[.)])\s+)?create\s+`?([^`\s]*[./][^`\s]*)`?\s+with\b[^:]*:\s*$", re.I)

SHELL_LANGS = {"bash", "sh", "shell", "zsh", "console"}


@dataclass
class Block:
    lang: str
    body: str
    line: int          # 1-indexed line of the opening fence
    kind: str          # "emit" | "old" | "verify" | "create" | "unknown"
    target: str | None  # inferred path this block belongs to


@dataclass
class Expectation:
    """What the plan says the command should produce."""
    raw: str
    zero_output: bool = False       # "prints NOTHING", "no output", "exit 1"
    counts: list[int] = field(default_factory=list)  # "-> `0`", "→ `1`"


@dataclass
class Finding:
    code: str
    title: str
    line: int
    detail: str
    evidence: str = ""

    def render(self) -> str:
        out = [f"  {self.code}  line {self.line}: {self.title}", f"      {self.detail}"]
        if self.evidence:
            for ln in self.evidence.rstrip().splitlines():
                out.append(f"        | {ln}")
        return "\n".join(out)


def parse_blocks(text: str) -> list[Block]:
    """Split a plan into fenced blocks, classified by the prose that precedes them."""
    lines = text.splitlines()
    blocks: list[Block] = []
    i = 0
    # A plan names the file once per task and then emits several edits under it,
    # so the nearest path is usually far above the fence. Track it document-wide
    # rather than peeking a few lines up, or edits get attributed to nothing and
    # silently drop out of the virtual tree.
    current_path: str | None = None
    while i < len(lines):
        m = FENCE_RE.match(lines[i])
        if not m:
            cm = CREATE_RE.match(lines[i])
            if cm:
                current_path = cm.group(1)
                i += 1
                continue
            pm = PATH_RE.search(lines[i])
            if pm and not lines[i].lstrip().startswith(("|", ">")):
                current_path = pm.group(0)
            i += 1
            continue
        indent, fence, lang = m.group(1), m.group(2), m.group(3).lower()
        body: list[str] = []
        j = i + 1
        while j < len(lines):
            m2 = FENCE_RE.match(lines[j])
            if m2 and m2.group(2)[0] == fence[0] and len(m2.group(2)) >= len(fence) and not m2.group(3):
                break
            body.append(lines[j])
            j += 1
        kind, target = _classify(lines, i, lang, "\n".join(body))
        blocks.append(Block(lang=lang, body="\n".join(body), line=i + 1,
                            kind=kind, target=target or current_path))
        i = j + 1
    return blocks


def _preceding(lines: list[str], idx: int, n: int = 6) -> list[str]:
    """The nearest non-empty prose lines above a fence."""
    out = []
    k = idx - 1
    while k >= 0 and len(out) < n:
        s = lines[k].strip()
        if s:
            out.append(s)
        k -= 1
    return out


def _classify(lines: list[str], idx: int, lang: str, body: str) -> tuple[str, str | None]:
    ctx = _preceding(lines, idx)
    # The new-file grammar wins over every other marker: the fence directly
    # under a Create line is the complete file, not an edit and not a verify.
    for s in ctx[:2]:
        cm = CREATE_RE.match(s)
        if cm:
            return "create", cm.group(1)
    target = None
    for s in ctx:
        pm = PATH_RE.search(s)
        if pm:
            target = pm.group(0)
            break

    def _hits(markers) -> bool:
        # Only the two lines directly above a fence carry the edit marker; look
        # no further, or a distant "New:" claims an unrelated block.
        for s in ctx[:2]:
            low = s.lower().strip().rstrip(":").strip("*_` ")
            for mk in markers:
                mk = mk.rstrip(":")
                if low == mk or low.endswith(" " + mk) or low.startswith(mk + " "):
                    return True
        return False

    if _hits(EMIT_MARKERS):
        return "emit", target
    if _hits(OLD_MARKERS):
        return "old", target

    if lang in SHELL_LANGS:
        # A shell fence is a verify only when it reads like commands run from a
        # repo root. Plan B emits *awk body text* into a .sh file inside a bash
        # fence; misreading that as a command is exactly how the defect hides.
        if any(VERIFY_HINT.search(s) for s in ctx[:4]):
            return "verify", target
        first = [l for l in body.splitlines() if l.strip()][:3]
        if any(re.match(r"\s*(cd|cargo|grep|bash|wc|test|git|\./|rg|sed|awk\s+-|shasum)\b", l) for l in first):
            return "verify", target
        return "emit", target

    if lang in ("rust", "rs", "toml", "python", "py", "yaml", "yml", "json"):
        return "emit", target
    return "unknown", target


def parse_expectation(text: str, idx: int) -> Expectation:
    """Read the plan's stated expectation from the prose after a fence."""
    lines = text.splitlines()
    tail = []
    k = idx
    while k < len(lines) and len(tail) < 10:
        tail.append(lines[k])
        k += 1
    blob = "\n".join(tail)
    exp = Expectation(raw=blob.strip()[:400])
    if re.search(r"prints?\s+NOTHING|no output|produces? no output|empty output|exit(?:s)?\s*(?:code\s*)?1\b",
                 blob, re.I):
        exp.zero_output = True
    for m in re.finditer(r"(?:->|→|=>)\s*`?(\d+)`?", blob):
        exp.counts.append(int(m.group(1)))
    return exp


# --------------------------------------------------------------------------
# Edits and the virtual post-edit tree
# --------------------------------------------------------------------------

@dataclass
class Edit:
    target: str | None
    old: str
    new: str
    line: int
    create: bool = False   # from a Create block: new is the whole file, old is empty


def collect_edits(blocks: list[Block]) -> list[Edit]:
    """Pair each `old` fence with the `emit` fence that follows it."""
    edits: list[Edit] = []
    for i, b in enumerate(blocks):
        if b.kind == "create":
            edits.append(Edit(target=b.target, old="", new=b.body, line=b.line, create=True))
            continue
        if b.kind != "old":
            continue
        for nxt in blocks[i + 1: i + 3]:
            if nxt.kind == "emit":
                edits.append(Edit(target=b.target or nxt.target, old=b.body, new=nxt.body, line=nxt.line))
                break
    return edits


def _resolve_bare_targets(edits: list[Edit], repo_root: Path | None) -> None:
    """Prose says "in `sink.rs`" as often as it gives the full path. Left alone,
    a bare name becomes a second, empty virtual file and every check runs twice
    - once against the real assembled file and once against a fragment."""
    full = {e.target for e in edits if e.target and "/" in e.target}
    for e in edits:
        t = e.target
        if not t or "/" in t:
            continue
        cand = [f for f in full if f.endswith("/" + t)]
        if len(cand) == 1:
            e.target = cand[0]
            continue
        if repo_root:
            hits = [p for p in repo_root.rglob(t)
                    if p.is_file() and ".git" not in p.parts][:2]
            if len(hits) == 1:
                e.target = str(hits[0].relative_to(repo_root))


def build_virtual_tree(edits: list[Edit], repo_root: Path | None,
                       extra: list[Path]) -> tuple[dict[str, str], list[str]]:
    """Apply the plan's edits to a copy of the tree. Returns (files, notes)."""
    files: dict[str, str] = {}
    notes: list[str] = []
    _resolve_bare_targets(edits, repo_root)
    for e in edits:
        if not e.target:
            continue
        if e.create:
            files[e.target] = e.new if e.new.endswith("\n") else e.new + "\n"
            if repo_root and (repo_root / e.target).is_file():
                notes.append(f"{e.target}: Create target already exists in repo; the plan content replaces it in this dry run")
            continue
        if e.target not in files:
            if repo_root and (repo_root / e.target).is_file():
                files[e.target] = (repo_root / e.target).read_text(errors="replace")
            else:
                files[e.target] = ""
                notes.append(f"{e.target}: not found in repo; using emitted text only")
        cur = files[e.target]
        if e.old and e.old in cur:
            files[e.target] = cur.replace(e.old, e.new, 1)
        else:
            # Could not anchor the edit; append so the emitted text is still
            # visible to the checks. Better to over-include than to miss it.
            files[e.target] = cur + ("\n" if cur and not cur.endswith("\n") else "") + e.new + "\n"
            if e.old:
                notes.append(f"{e.target}: old_string did not match at line {e.line}; emitted text appended")
    for p in extra:
        try:
            files[str(p)] = p.read_text(errors="replace")
        except OSError as exc:
            notes.append(f"{p}: unreadable ({exc})")
    return files, notes


# --------------------------------------------------------------------------
# Command extraction
# --------------------------------------------------------------------------

@dataclass
class GrepCmd:
    pattern: str
    fixed: bool
    recursive: bool
    count: bool
    paths: list[str]
    raw: str
    line: int
    exp: Expectation


def _split_commands(body: str) -> list[str]:
    out = []
    for raw in body.splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        for part in re.split(r"\s*(?:\|\||&&|;)\s*", s):
            part = part.strip()
            if part:
                out.append(part)
    return out


def extract_greps(blocks: list[Block], text: str) -> list[GrepCmd]:
    greps: list[GrepCmd] = []
    for b in blocks:
        if b.kind != "verify":
            continue
        end_line = b.line + b.body.count("\n") + 2
        exp = parse_expectation(text, end_line)
        for cmd in _split_commands(b.body):
            head = cmd.split()[0] if cmd.split() else ""
            if head not in ("grep", "rg", "egrep", "fgrep"):
                continue
            try:
                argv = shlex.split(cmd)
            except ValueError:
                continue
            flags, pattern, paths = "", None, []
            it = iter(argv[1:])
            for tok in it:
                if tok.startswith("-") and len(tok) > 1 and not tok.startswith("--"):
                    if "e" in tok.lstrip("-"):
                        flags += tok.lstrip("-")
                        pattern = next(it, None)
                        continue
                    flags += tok.lstrip("-")
                elif tok.startswith("--"):
                    continue
                elif pattern is None:
                    pattern = tok
                else:
                    paths.append(tok)
            if not pattern:
                continue
            greps.append(GrepCmd(
                pattern=pattern,
                fixed=("F" in flags) or head == "fgrep",
                recursive=("r" in flags or "R" in flags),
                count=("c" in flags),
                paths=paths, raw=cmd, line=b.line, exp=exp,
            ))
    return greps


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------

METACHARS = set(".*[]^$+?(){}|\\")


def _basic_to_python(pat: str) -> str:
    """POSIX basic regex (grep default) -> Python. In BRE, + ? { } ( ) | are
    literal unless backslashed; . * [ ] ^ $ keep their meaning."""
    out, i = [], 0
    while i < len(pat):
        c = pat[i]
        if c == "\\" and i + 1 < len(pat):
            nxt = pat[i + 1]
            if nxt in "+?(){}|":
                out.append(nxt if nxt in "|" else re.escape(nxt) if nxt in "{}" else nxt)
                out.append("") if False else None
                out[-1] = {"+": "+", "?": "?", "(": "(", ")": ")", "{": "{", "}": "}", "|": "|"}[nxt]
            else:
                out.append(re.escape(nxt))
            i += 2
            continue
        if c in "+?(){}":
            out.append(re.escape(c))
        else:
            out.append(c)
        i += 1
    return "".join(out)


def _count_matches(pattern: str, text: str, fixed: bool, extended: bool = False) -> int:
    if fixed:
        return sum(1 for line in text.splitlines() if pattern in line)
    py = pattern if extended else _basic_to_python(pattern)
    try:
        rx = re.compile(py)
    except re.error:
        return -1
    return sum(1 for line in text.splitlines() if rx.search(line))


def _scope(files: dict[str, str], g: GrepCmd) -> dict[str, str]:
    """Which virtual files this grep would actually read."""
    if not g.paths:
        return files
    sel = {}
    for p in g.paths:
        p = p.rstrip("/")
        for name, content in files.items():
            if name == p or name.endswith("/" + p) or p.endswith(name):
                sel[name] = content
            elif g.recursive and (name.startswith(p + "/") or ("/" + p + "/") in name):
                sel[name] = content
    return sel


def check_self_match(files: dict[str, str], greps: list[GrepCmd]) -> list[Finding]:
    """GAUGE001 - a verify that forbids text the plan itself writes."""
    out = []
    for g in greps:
        expects_zero = g.exp.zero_output or (g.exp.counts and g.exp.counts[0] == 0 and g.count)
        if not expects_zero:
            continue
        scope = _scope(files, g)
        for name, content in scope.items():
            n = _count_matches(g.pattern, content, g.fixed)
            if n > 0:
                hits = [l.strip() for l in content.splitlines()
                        if (g.pattern in l if g.fixed else re.search(_basic_to_python(g.pattern), l))]
                out.append(Finding(
                    code="GAUGE001",
                    title="verify expects no output, but the plan's own emitted text matches",
                    line=g.line,
                    detail=(f"`{g.raw}` is stated to produce nothing, yet after this plan's edits "
                            f"{name} contains {n} match(es). Applying the plan faithfully guarantees "
                            f"this verify fails."),
                    evidence="\n".join(hits[:3]),
                ))
    return out


def check_unescaped_metachar(files: dict[str, str], greps: list[GrepCmd]) -> list[Finding]:
    """GAUGE002 - a literal search run as a regex, so it over-matches."""
    out = []
    for g in greps:
        if g.fixed:
            continue
        pat = g.pattern
        # Backslash-escaped metachars mean the author knew. Ignore anchors and
        # alternation, which are almost always deliberate.
        stripped = re.sub(r"\\.", "", pat)
        risky = [c for c in stripped if c in METACHARS and c not in "^$|\\"]
        if not risky:
            continue
        # A '.' between identifier characters reads as a field access typed
        # literally - the exact shape of the round-1 defect.
        literalish = re.search(r"\w\.\w", stripped) or "()" in stripped
        if not literalish:
            continue
        for name, content in _scope(files, g).items():
            n_rx = _count_matches(pat, content, fixed=False)
            n_fx = _count_matches(pat, content, fixed=True)
            if n_rx != n_fx:
                expected = g.exp.counts[0] if g.exp.counts else None
                extra = ""
                if expected is not None:
                    extra = (f" The plan expects {expected}; as a regex this returns {n_rx}, "
                             f"as a fixed string {n_fx}.")
                out.append(Finding(
                    code="GAUGE002",
                    title="literal pattern searched as a regex, and it over-matches",
                    line=g.line,
                    detail=(f"`{g.raw}` has unescaped {sorted(set(risky))} in a pattern that reads "
                            f"literally. Against {name} the regex matches {n_rx} line(s) but the "
                            f"literal string matches {n_fx}.{extra} Use `grep -F`, or escape."),
                    evidence="",
                ))
    return out


SINGLE_QUOTED_OPEN = re.compile(r"(?<!\\)'")


def check_shell_quote(files: dict[str, str], edits: list[Edit],
                      notes: list[str]) -> list[Finding]:
    """GAUGE003 - emitted text that breaks the quoting of the file it lands in."""
    out = []
    # Authoritative: syntax-check any shell file the plan touched, post-edit.
    for name, content in files.items():
        if not name.endswith(".sh"):
            continue
        if not content.strip():
            continue
        with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as fh:
            fh.write(content)
            tmp = fh.name
        try:
            r = subprocess.run(["bash", "-n", tmp], capture_output=True, text=True)
            if r.returncode != 0:
                msg = r.stderr.replace(tmp, name).strip()
                out.append(Finding(
                    code="GAUGE003",
                    title="the plan's edits leave a shell script that will not parse",
                    line=0,
                    detail=f"After applying this plan's edits, `bash -n {name}` fails.",
                    evidence=msg,
                ))
        finally:
            os.unlink(tmp)

    # Heuristic, for when the file could not be assembled: an apostrophe inside
    # a comment in emitted shell text. Harmless in isolation, fatal the moment
    # it lands inside a single-quoted region such as `awk '...'`.
    assembled = {f for f in files if f.endswith(".sh")}
    for e in edits:
        if not e.target or not e.target.endswith(".sh"):
            continue
        if e.target in assembled and files.get(e.target, "").strip():
            continue
        for ln in e.new.splitlines():
            s = ln.strip()
            if s.startswith("#") and SINGLE_QUOTED_OPEN.search(s):
                out.append(Finding(
                    code="GAUGE003",
                    title="emitted shell comment contains an apostrophe",
                    line=e.line,
                    detail=(f"This text is written into {e.target}. An apostrophe inside a comment "
                            f"is fatal if the comment lands within a single-quoted region (an "
                            f"`awk '...'` body, for instance): it closes the quote and the rest is "
                            f"parsed as shell."),
                    evidence=s,
                ))
                break
    return out


CARGO_TEST_RE = re.compile(r"\bcargo\s+test\b([^\n|]*)")


def check_feature_gate(blocks: list[Block], text: str, files: dict[str, str],
                       repo_root: Path | None) -> list[Finding]:
    """GAUGE004 - a cargo test verify that cannot compile the tests it asserts on."""
    out = []
    lines = text.splitlines()
    for b in blocks:
        if b.kind != "verify":
            continue
        for m in CARGO_TEST_RE.finditer(b.body):
            args = m.group(1)
            if "--features" in args or "--all-features" in args:
                continue
            pm = re.search(r"-p\s+([\w-]+)", args)
            if not pm:
                continue
            crate = pm.group(1)
            end_line = b.line + b.body.count("\n") + 2
            tail = "\n".join(lines[end_line: end_line + 12])
            # Which module paths does the expectation name?
            mods = set(re.findall(r"\b([a-z_][a-z0-9_]*)::(?:[a-z_][a-z0-9_]*::)*tests::", tail))
            if not mods:
                continue
            gated = _gated_modules(crate, repo_root, files)
            hit = sorted(mods & set(gated))
            if hit:
                feats = ", ".join(sorted({gated[h] for h in hit}))
                out.append(Finding(
                    code="GAUGE004",
                    title="cargo test verify cannot compile the tests it asserts on",
                    line=b.line,
                    detail=(f"`cargo test -p {crate}` carries no --features, but the expected output "
                            f"names tests under module(s) {hit}, which are gated on non-default "
                            f"feature(s): {feats}. Those test lines can never appear in any run of "
                            f"this command. Add `--features {feats}`."),
                    evidence="",
                ))
    return out


def _gated_modules(crate: str, repo_root: Path | None, files: dict[str, str]) -> dict[str, str]:
    """Map module name -> feature that gates it, for a crate's lib.rs."""
    gated: dict[str, str] = {}
    sources: list[str] = []
    if repo_root:
        for lib in list(repo_root.glob(f"**/{crate}/src/lib.rs"))[:4]:
            try:
                sources.append(lib.read_text(errors="replace"))
            except OSError:
                pass
    for name, content in files.items():
        if name.endswith("lib.rs"):
            sources.append(content)
    for src in sources:
        for m in re.finditer(
            r'#\[cfg\((?P<cfg>[^\]]*feature\s*=\s*"(?P<feat>[\w-]+)"[^\]]*)\)\]\s*(?:pub\s+)?mod\s+(?P<mod>\w+)',
            src,
        ):
            gated[m.group("mod")] = m.group("feat")
    return gated


BIN_INVOKE_RE = re.compile(r'(\$\{?BIN\}?|\./target/(?:release|debug)/[\w-]+)')
GUARDED_BUILD_RE = re.compile(r'if\s*\[+\s*!\s*-[xf]\s+"?\$?\{?\w+', re.I)


def _strip_guarded_regions(body: str) -> str:
    """Drop every `if [ ! -x ... ]` ... `fi` region, so what remains is the code
    that runs unconditionally."""
    out, depth = [], 0
    for ln in body.splitlines():
        if depth == 0 and GUARDED_BUILD_RE.search(ln):
            depth = 1
            continue
        if depth:
            if re.match(r"\s*(if|case)\b", ln):
                depth += 1
            elif re.match(r"\s*(fi|esac)\b", ln):
                depth -= 1
            continue
        out.append(ln)
    return "\n".join(out)


def check_stale_artifact(blocks: list[Block], files: dict[str, str]) -> list[Finding]:
    """GAUGE005 - a verify that runs a built artifact only built when absent."""
    out = []
    bodies = [(b.line, b.body) for b in blocks if b.kind in ("verify", "emit", "create")]
    bodies += [(0, c) for n, c in files.items() if n.endswith(".sh")]
    for line, body in bodies:
        if not BIN_INVOKE_RE.search(body):
            continue
        if "cargo build" not in body:
            continue
        guarded = GUARDED_BUILD_RE.search(body)
        if not guarded:
            continue
        # Excise the guarded region, then ask whether any build survives. The
        # build inside the guard is indented, so "is there a cargo build at low
        # indentation" is not a test - it answers yes for the defect itself.
        if "cargo build" in _strip_guarded_regions(body):
            continue
        out.append(Finding(
            code="GAUGE005",
            title="verify runs a built artifact that is only built when missing",
            line=line,
            detail=("The build is guarded by an existence test, so a stale artifact left by an "
                    "earlier run is silently reused. This fails in the dangerous direction: an "
                    "artifact predating the fix reproduces the original defect and reads as a "
                    "genuine failure. Build unconditionally; it is incremental and cheap."),
            evidence=guarded.group(0),
        ))
    return out


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------

BRIEF_REQUIRED_SECTIONS = (
    "objective",
    "scope",
    "constraints",
    "authority",
    "acceptance criteria",
    "verification",
    "deliverables",
)
HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.M)
DECLARED_CONTRACT_RE = re.compile(r"^\s*Contract:\s*(brief|exact)\s*$", re.I | re.M)


def resolve_contract(plan_text: str, requested: str) -> str:
    """Resolve the planning contract without changing legacy exact plans."""
    if requested != "auto":
        return requested
    declared = DECLARED_CONTRACT_RE.search(plan_text)
    return declared.group(1).lower() if declared else "exact"


def _brief_sections(plan_text: str) -> dict[str, tuple[str, int]]:
    """Return normalized heading -> (body, heading line)."""
    matches = list(HEADING_RE.finditer(plan_text))
    sections: dict[str, tuple[str, int]] = {}
    for index, match in enumerate(matches):
        name = re.sub(r"\s+", " ", match.group(1).strip().lower())
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(plan_text)
        line = plan_text.count("\n", 0, match.start()) + 1
        sections[name] = (plan_text[start:end].strip(), line)
    return sections


def lint_brief(plan_text: str) -> tuple[list[Finding], list[str]]:
    """Validate an outcome brief without demanding implementation mechanics.

    A brief is checked before implementation exists, so its verification
    commands are syntax-checked but deliberately not executed. The executor
    owns the implementation and test loop; the validator replays these checks
    against the resulting checkout.
    """
    sections = _brief_sections(plan_text)
    findings: list[Finding] = []
    for required in BRIEF_REQUIRED_SECTIONS:
        body, line = sections.get(required, ("", 1))
        if not body:
            findings.append(Finding(
                code="BRIEF001",
                title=f"missing or empty {required} section",
                line=line,
                detail=(
                    "A brief must state objective, scope, constraints, authority, "
                    "acceptance criteria, verification, and deliverables."
                ),
            ))

    verification, verify_line = sections.get("verification", ("", 1))
    if verification:
        shell_blocks = [
            b for b in parse_blocks("## Verification\n" + verification)
            if b.lang in SHELL_LANGS
        ]
        if not shell_blocks:
            findings.append(Finding(
                code="BRIEF002",
                title="verification has no shell replay",
                line=verify_line,
                detail="Put the acceptance replay in a fenced bash/sh block.",
            ))
        else:
            for block in shell_blocks:
                check = subprocess.run(
                    ["bash", "-n"], input=block.body, text=True,
                    capture_output=True,
                )
                if check.returncode:
                    findings.append(Finding(
                        code="BRIEF003",
                        title="verification shell does not parse",
                        line=verify_line + block.line,
                        detail="The brief's verification must be runnable after implementation.",
                        evidence=check.stderr.strip(),
                    ))

    deliverables, deliverables_line = sections.get("deliverables", ("", 1))
    if deliverables:
        required_packet = {
            "diff or commit": r"\b(diff|commit)\b",
            "checks run": r"\b(check|test|verification)s?\b",
            "failures": r"\bfail(?:ure|ures|ed)?\b",
            "unresolved questions": r"\bunresolved\b",
        }
        missing = [label for label, pattern in required_packet.items()
                   if not re.search(pattern, deliverables, re.I)]
        if missing:
            findings.append(Finding(
                code="BRIEF004",
                title="incomplete result packet",
                line=deliverables_line,
                detail="Deliverables must include: " + ", ".join(missing) + ".",
            ))

    return findings, ["contract=brief; verification syntax-checked, not executed"]

def lint(plan_text: str, repo_root: Path | None = None,
         extra: list[Path] | None = None) -> tuple[list[Finding], list[str]]:
    blocks = parse_blocks(plan_text)
    edits = collect_edits(blocks)
    files, notes = build_virtual_tree(edits, repo_root, extra or [])
    greps = extract_greps(blocks, plan_text)

    findings: list[Finding] = []
    findings += check_self_match(files, greps)
    findings += check_unescaped_metachar(files, greps)
    findings += check_shell_quote(files, edits, notes)
    findings += check_feature_gate(blocks, plan_text, files, repo_root)
    findings += check_stale_artifact(blocks, files)

    # Stable, de-duplicated ordering.
    seen, uniq = set(), []
    for f in sorted(findings, key=lambda f: (f.code, f.line)):
        key = (f.code, f.line, f.detail[:80])
        if key not in seen:
            seen.add(key)
            uniq.append(f)
    return uniq, notes


def lint_contract(plan_text: str, contract: str, repo_root: Path | None = None,
                  extra: list[Path] | None = None) -> tuple[list[Finding], list[str]]:
    if contract == "brief":
        return lint_brief(plan_text)
    findings, notes = lint(plan_text, repo_root, extra)
    return findings, ["contract=exact; virtual post-edit gauge replay"] + notes


def _report(findings: list[Finding], notes: list[str], label: str, quiet: bool) -> None:
    if quiet:
        return
    print(f"=== plan-gauge-lint: {label} ===")
    for n in notes:
        print(f"  note: {n}")
    if not findings:
        print("  no gauge defects found")
        return
    for f in findings:
        print(f.render())
    codes = sorted({f.code for f in findings})
    print(f"\n  {len(findings)} finding(s): {', '.join(codes)}")


# --------------------------------------------------------------------------
# Self-test: replay the seven known defects (six from pilot 1, one from pattern F)
# --------------------------------------------------------------------------

def _fixtures() -> list[dict]:
    return [
        {
            "id": "R1-A",
            "name": "round 1 arm A - cargo test cannot compile the tests it asserts on",
            "expect": "GAUGE004",
            "files": {
                "crates/bevy_metalfx/src/lib.rs":
                    '#[cfg(all(target_os = "macos", feature = "frame-interpolation"))]\n'
                    'pub mod present;\n',
            },
            "plan": """
## Task 2 - sink.rs cumulative counter

### Verify Task 2

```bash
cargo test -p bevy_metalfx 2>&1 | tail -25
```

Expected output must contain ALL of:
- `test present::sink::tests::displayed_is_cumulative_not_ring_occupancy ... ok`
- every `test result:` line reads `ok.` with `0 failed`
""",
        },
        {
            "id": "R1-B",
            "name": "round 1 arm B - unescaped dot over-matches ring.displayed",
            "expect": "GAUGE002",
            "files": {"crates/bevy_metalfx/src/present/sink.rs": "struct Ring { next: usize }\n"},
            "plan": """
## Task 2

In `crates/bevy_metalfx/src/present/sink.rs`:

old_string:
```rust
struct Ring { next: usize }
```

new_string:
```rust
struct Ring {
    /// Record one presented frame - any frame the owned layer displayed, real
    /// or interpolated; the callback cannot tell them apart.
    next: usize,
    /// Separates "no drawable was free" (`dropped`) from "encoded and never
    /// displayed" (`encoded` high, `displayed` zero).
    displayed: u64,
}
impl PresentSink {
    fn counts(&self) -> (u64, u64) { (r.encoded, r.displayed) }
}
```

### Verify Task 2

```bash
grep -c "r.displayed" crates/bevy_metalfx/src/present/sink.rs
```

Expected: `grep -c "r.displayed"` -> `1`.
""",
        },
        {
            "id": "R2-A",
            "name": "round 2 arm A - edit emits AppExit, same task's grep forbids it",
            "expect": "GAUGE001",
            "files": {"crates/sw-renderer/src/main.rs": "fn debug_scene() {}\n"},
            "plan": """
## Task 4 - bench-mode hard exit

In `crates/sw-renderer/src/main.rs`:

old_string:
```rust
fn debug_scene() {}
```

new_string:
```rust
/// Flush stdio and terminate the bench process once results are on disk.
///
/// `AppExit` is not reliable here: with `--dual-present`, teardown wedges
/// inside winit and the process never dies.
fn bench_exit() -> ! {
    std::process::exit(0);
}

fn debug_scene() {}
```

### Verify Task 4

```bash
grep -n "MessageWriter\\|AppExit" crates/sw-renderer/src/main.rs
```

Expected: the `grep` prints NOTHING (exit code 1).
""",
        },
        {
            "id": "R2-B",
            "name": "round 2 arm B - apostrophes close the enclosing bash single-quote",
            "expect": "GAUGE003",
            "files": {
                "crates/sw-renderer/scripts/validate-dual-present.sh":
                    "#!/usr/bin/env bash\n"
                    "awk -v be=\"$BASE\" 'BEGIN {\n"
                    "  print \"  PASS  render rate held\"\n"
                    "}'\n",
            },
            "plan": """
## Task 5 - the validation script

In `crates/sw-renderer/scripts/validate-dual-present.sh`:

Old:
```bash
  print "  PASS  render rate held"
```

New:
```bash
  print "  PASS  render rate held"

  # 5. The presented rate is a measurement, not a sum. One presented-handler is
  #    attached to every drawable, so the sink's rate must equal presents per
  #    rendered frame x render rate.
  if (bsrc != "owned_layer") {
    print "  SKIP  presented rate unmeasured"
  } else {
    print "  PASS  presented rate is the measured total"
  }

  # 6. present_displayed is a counter, not a 480-deep ring gauge. It used to
  #    be the ring's occupancy, which saturates at RING_CAPACITY.
  if (dd + 0 <= 480) {
    print "  SKIP  displayed counter untested"
  }
```

### Verify Task 5

```bash
bash -n crates/sw-renderer/scripts/validate-dual-present.sh && echo SYNTAX_OK
```

Expected: `SYNTAX_OK`.
""",
        },
        {
            "id": "HARNESS",
            "name": "harness - the frozen gauge itself carried a token the plan forbids",
            "expect": "GAUGE001",
            "files": {
                "crates/sw-renderer/src/main.rs": "let total = 1.0;\n",
                # The frozen gauge, which lives under crates/ and is present at
                # verify time even though no plan edit produced it.
                "crates/sw-renderer/scripts/gate1-gauge.sh":
                    "#!/usr/bin/env bash\n"
                    "# D1  presented_fps was synthesised as `mean_fps + p.interp_fps`.\n"
                    "echo gauge\n",
            },
            "extra_artifacts": ["crates/sw-renderer/scripts/gate1-gauge.sh"],
            "plan": """
## Task 7 - guardrails

In `crates/sw-renderer/src/main.rs`:

old_string:
```rust
let total = 1.0;
```

new_string:
```rust
let total = p.presented_fps;
```

### Verify Task 7

```bash
grep -rn "interp_fps" crates/
```

Expected: produces no output (exit 1).
""",
        },
        {
            "id": "GAUGE-V1",
            "name": "gauge v1 - release binary reused when present, so a stale one is measured",
            "expect": "GAUGE005",
            "files": {},
            "plan": """
## Task 6 - end-to-end validation

The harness script:

```bash
BIN=./target/release/sw-renderer
if [ ! -x "$BIN" ]; then
  cargo build -p sw-renderer --release || exit 1
fi
"$BIN" --bench-quick --dual-present
```

Expected: exits 0.
""",
        },
        {
            "id": "PF-C",
            "name": "pattern F - a new-file plan whose verify forbids text the created file contains",
            "expect": "GAUGE001",
            "files": {},
            "plan": """
## Task 1

Create `scripts/hello.sh` with:
```bash
#!/usr/bin/env bash
echo "TODO: replace me"
```

### Verify Task 1

```bash
grep -c "TODO" scripts/hello.sh
```

Expected: prints NOTHING (exit 1).
""",
        },
    ]


def self_test(verbose: bool) -> int:
    fixtures = _fixtures()
    failures = 0
    print("=== plan-gauge-lint --self-test: replaying the seven known gauge defects (six from pilot 1, one from pattern F) ===\n")
    rows = []
    for fx in fixtures:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for rel, content in fx["files"].items():
                p = root / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content)
            extra = [root / e for e in fx.get("extra_artifacts", [])]
            findings, notes = lint(fx["plan"], repo_root=root, extra=extra)
            codes = {f.code for f in findings}
            want = fx["expect"]
            ok = want in codes
            rows.append((fx["id"], want, sorted(codes), ok))
            if not ok:
                failures += 1
            if verbose or not ok:
                print(f"--- {fx['id']}: {fx['name']}")
                _report(findings, notes, fx["id"], quiet=False)
                print()

    print(f"{'fixture':<10} {'expect':<10} {'got':<28} result")
    for fid, want, got, ok in rows:
        print(f"{fid:<10} {want:<10} {','.join(got) or '-':<28} {'PASS' if ok else 'FAIL'}")
    caught = len(rows) - failures
    print(f"\n  caught {caught}/{len(rows)} known defects")

    # A linter that flags everything is worthless. Confirm a clean plan is clean.
    clean_plan = """
## Task 1

In `src/lib.rs`:

old_string:
```rust
fn a() {}
```

new_string:
```rust
fn a() { let x = 1; }
```

### Verify Task 1

```bash
cargo test -p mycrate --features full 2>&1 | tail -5
grep -cF "let x = 1" src/lib.rs
```

Expected: `grep -cF "let x = 1" src/lib.rs` -> `1`.
"""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "src").mkdir(parents=True, exist_ok=True)
        (root / "src/lib.rs").write_text("fn a() {}\n")
        cf, _ = lint(clean_plan, repo_root=root)
    if cf:
        print("\n  FALSE POSITIVE on the clean control plan:")
        for f in cf:
            print(f.render())
        failures += 1
    else:
        print("  clean control plan: no findings (no false positives)")

    print()
    if failures:
        print(f"SELF-TEST FAILED ({failures} problem(s))")
        return 1
    print("SELF-TEST PASSED")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        prog="plan-gauge-lint.py",
        description="Dry-run a plan's verify gauge against the plan's own emitted output.",
    )
    ap.add_argument("plan", nargs="?", help="path to the plan markdown")
    ap.add_argument("--repo-root", type=Path, default=None,
                    help="repo the plan edits; enables the real post-edit dry run")
    ap.add_argument("--extra-artifact", type=Path, action="append", default=[],
                    help="a file present at verify time but not produced by the plan "
                         "(e.g. a frozen gauge). Repeatable.")
    ap.add_argument("--contract", choices=("auto", "brief", "exact"), default="auto",
                    help="planning contract; auto reads `Contract: brief|exact` and "
                         "otherwise preserves the legacy exact-plan gauge")
    ap.add_argument("--self-test", action="store_true",
                    help="replay the seven known gauge defects and exit")
    ap.add_argument("--json", action="store_true", help="machine-readable findings")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test(args.verbose)

    if not args.plan:
        ap.error("a plan path is required (or --self-test)")
    path = Path(args.plan)
    if not path.is_file():
        print(f"no such plan: {path}", file=sys.stderr)
        return 2

    plan_text = path.read_text(errors="replace")
    contract = resolve_contract(plan_text, args.contract)
    findings, notes = lint_contract(plan_text, contract, args.repo_root, args.extra_artifact)
    if args.json:
        print(json.dumps({
            "plan": str(path),
            "contract": contract,
            "notes": notes,
            "findings": [
                {"code": f.code, "title": f.title, "line": f.line,
                 "detail": f.detail, "evidence": f.evidence}
                for f in findings
            ],
        }, indent=2))
    else:
        _report(findings, notes, str(path), quiet=False)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
