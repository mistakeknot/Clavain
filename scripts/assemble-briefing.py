#!/usr/bin/env python3
"""Assemble a role-briefing view for a fresh worker, per
docs/plans/2026-09-28-mk-42j9.38-role-briefing-template.md (bead mk-42j9.38,
sha256 fe61cbb559bc273507dd5ae8aa55039947874816683314f7de02768a3bf636ea).

This is the deterministic core of the assembler: sections 1, 2, 3a, 4, 5, 6, 7
of the template, populated only from `bd`, `git`, `ic` and CanonGraph MCP,
never from a transcript and never from model judgment. Section 3b (ranked
context) is intentionally NOT produced here -- it is the one place the design
allows a model in the loop (a scoped /recall fan-out), and it is layered on
by commands/brief.md, which calls this script for the deterministic sections
first. A caller that cannot run a model at all (a rotation successor spawn,
a coordinator lane-launch script) can invoke this file directly and get a
complete, provenance-checked briefing minus that one optional, capped,
advisory section.

Every rendered line carries a bracketed source reference. Items with no
determinable source are rejected (kept out of the rendered output, logged in
the `rejected` list) rather than silently dropped -- see ProvenanceError and
Section.add.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
BUDGET_TOKENS = 1500  # doc §3, aspirational; mandatory content is uncapped (§3.3a)
NOTE_PREFIXES = ("NEXT:", "OPEN:", "DECIDED:", "EVIDENCE:", "DEAD-END:", "ENV:")
CONSTRAINT_RE = re.compile(
    r"\b(must not|must|do not|don't|never|only|drop(?:ped)?)\b", re.IGNORECASE
)
CANONGRAPH_ENV = Path.home() / ".config/canongraph/canongraph.env"
DEFAULT_MEMORY_MD = Path.home() / ".claude/projects/-home-mk/memory/MEMORY.md"


# --------------------------------------------------------------------------
# Provenance: no rendered item without a source reference.
# --------------------------------------------------------------------------


class ProvenanceError(ValueError):
    """Raised internally when an item is added with no source; caught by
    Section.add and turned into a rejection record rather than a crash, so a
    single bad record degrades one line instead of the whole briefing."""


@dataclass
class RejectedItem:
    section: str
    text: str
    reason: str


@dataclass
class Section:
    """One numbered section of the briefing. `lines` are already-rendered,
    already-sourced strings. `add` is the only way in, and it is where the
    provenance check lives."""

    title: str
    lines: list[str] = field(default_factory=list)
    coverage: str | None = None  # "complete" | "partial: <reason>" | None

    def add(self, text: str, source: str, rejected: list[RejectedItem]) -> None:
        try:
            if not source or not source.strip():
                raise ProvenanceError(f"missing source for: {text!r}")
            self.lines.append(f"{text} [{source}]")
        except ProvenanceError as exc:
            rejected.append(RejectedItem(self.title, text, str(exc)))

    def render(self) -> str:
        body = "\n".join(f"- {line}" for line in self.lines) if self.lines else "- (none)"
        cov = f"\ncoverage: {self.coverage}" if self.coverage else ""
        return f"{body}{cov}"


# --------------------------------------------------------------------------
# Shell-out helpers. Every one degrades to (False, reason) instead of raising,
# so one unreachable lane never takes down the others (doc §4: "Every lane
# degrades to UNKNOWN (reason). None degrades to empty.").
# --------------------------------------------------------------------------


def _run(cmd: list[str], cwd: Path | None = None, timeout: float = 20.0) -> tuple[bool, str, str]:
    try:
        result = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout
        )
        return result.returncode == 0, result.stdout, result.stderr
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, "", str(exc)


# `bd` resolves its tracker from cwd (nearest git root's .beads config), which
# is *not* necessarily the repo being briefed -- e.g. on zklw the fleet/hub
# tracker binds at /home/mk/hub, distinct from a Clavain (or any other) code
# checkout's own .beads. --bd-cwd (or $CLAVAIN_BD_CWD) lets a caller point the
# assembler at the tracker that actually holds the bead, independent of
# --repo. Defaults to "." so a host where they coincide needs no flag.


def bd_show(bead_id: str, bd_cwd: Path) -> dict[str, Any] | None:
    ok, out, _err = _run(["bd", "show", bead_id, "--json"], cwd=bd_cwd)
    if not ok or not out.strip():
        return None
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return None
    if isinstance(data, list):
        return data[0] if data else None
    return data


def bd_children(bead_id: str, bd_cwd: Path) -> list[dict[str, Any]]:
    ok, out, _err = _run(["bd", "children", bead_id, "--json"], cwd=bd_cwd)
    if not ok or not out.strip():
        return []
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def bd_dep_list(bead_id: str, bd_cwd: Path, direction: str | None = None) -> str:
    cmd = ["bd", "dep", "list", bead_id]
    if direction:
        cmd += ["--direction", direction]
    ok, out, _err = _run(cmd, cwd=bd_cwd)
    return out.strip() if ok else ""


def git_info(repo: Path) -> dict[str, Any]:
    info: dict[str, Any] = {"ok": False}
    ok, head, _ = _run(["git", "-C", str(repo), "rev-parse", "HEAD"])
    if not ok:
        return info
    info["ok"] = True
    info["head"] = head.strip()
    ok, base, _ = _run(["git", "-C", str(repo), "merge-base", "HEAD", "main"])
    info["base"] = base.strip() if ok else None
    if info["base"]:
        ok, log, _ = _run(
            ["git", "-C", str(repo), "log", "--oneline", f"{info['base']}..HEAD"]
        )
        info["log"] = log.strip() if ok else ""
    else:
        info["log"] = ""
    ok, status, _ = _run(["git", "-C", str(repo), "status", "--porcelain"])
    info["status"] = status if ok else ""
    ok, branch, _ = _run(["git", "-C", str(repo), "rev-parse", "--abbrev-ref", "HEAD"])
    info["branch"] = branch.strip() if ok else "?"
    return info


def sha256_of(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def ic_run_current(repo: Path) -> dict[str, Any] | None:
    ok, out, _err = _run(["ic", "run", "current", f"--project={repo}"])
    if not ok or not out.strip():
        return None
    run_id = out.strip().splitlines()[0].strip()
    if not run_id:
        return None
    ok, status_out, _err = _run(["ic", "--json", "run", "status", run_id])
    if not ok:
        return {"run_id": run_id}
    try:
        status = json.loads(status_out)
    except json.JSONDecodeError:
        status = {}
    status["run_id"] = run_id
    return status


def ic_route_dispatch(role: str, policy: Path, producer_identity: str | None) -> dict[str, Any] | None:
    cmd = ["ic", "--json", "route", "dispatch", f"--role={role}", f"--policy={policy}"]
    if producer_identity:
        cmd.append(f"--producer-identity={producer_identity}")
    ok, out, _err = _run(cmd)
    if not ok or not out.strip():
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return None


# --------------------------------------------------------------------------
# CanonGraph MCP: HTTP streamable-transport, not the CLI (doc §3.3: the CLI
# cannot stand in while the MCP server holds the Kuzu lock -- confirmed
# 2026-09-28). Degrades to unavailable on any connection/auth failure so a
# host without this reachability still produces a briefing, just with
# `mandatory coverage: partial`.
# --------------------------------------------------------------------------


class CanonGraphClient:
    def __init__(self, base_url: str | None = None, token: str | None = None, timeout: float = 8.0):
        self.base_url = base_url or self._default_url()
        self.token = token or self._default_token()
        self.timeout = timeout
        self.session_id: str | None = None
        self.available = False
        self.unavailable_reason: str | None = None
        if not self.base_url or not self.token:
            self.unavailable_reason = "no canongraph.env / no CG_AUTH_TOKEN"
            return
        self._initialize()

    @staticmethod
    def _default_token() -> str | None:
        if not CANONGRAPH_ENV.exists():
            return None
        for line in CANONGRAPH_ENV.read_text().splitlines():
            if line.startswith("CG_AUTH_TOKEN="):
                return line.split("=", 1)[1].strip()
        return None

    @staticmethod
    def _default_url() -> str | None:
        # canongraph serve binds a Tailscale-reachable host:port; there is no
        # fixed default, so this only works when CANONGRAPH_MCP_URL is set or
        # the caller passes --canongraph-url. Absence degrades cleanly.
        return os.environ.get("CANONGRAPH_MCP_URL")

    def _post(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        assert self.base_url
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        req = urllib.request.Request(
            self.base_url, data=json.dumps(payload).encode(), headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                sid = resp.headers.get("Mcp-Session-Id")
                if sid:
                    self.session_id = sid
                body = resp.read().decode()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            self.unavailable_reason = f"connection failed: {exc}"
            return None
        # streamable-http emits "event: message\ndata: {...}" lines
        for line in body.splitlines():
            if line.startswith("data:"):
                try:
                    return json.loads(line[len("data:"):].strip())
                except json.JSONDecodeError:
                    return None
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return None

    def _initialize(self) -> None:
        resp = self._post(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "clavain-assemble-briefing", "version": "1"},
                },
            }
        )
        if resp is None or "error" in resp:
            self.unavailable_reason = self.unavailable_reason or f"initialize failed: {resp}"
            return
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.available = True

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any] | None:
        if not self.available:
            return None
        resp = self._post(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": name, "arguments": arguments}}
        )
        if resp is None or "error" in resp:
            return None
        result = resp.get("result", {})
        content = result.get("content") or result.get("structuredContent")
        if isinstance(content, list) and content:
            first = content[0]
            if isinstance(first, dict) and "text" in first:
                try:
                    return json.loads(first["text"])
                except (json.JSONDecodeError, TypeError):
                    return {"raw": first["text"]}
        if isinstance(content, dict):
            return content
        return result


# --------------------------------------------------------------------------
# Auto-memory (C5): binding entries per §3.3a item 5 -- type: feedback or
# type: user, cited by [[name]] only, never ranked or capped, included when
# applicability can't be determined rather than dropped.
# --------------------------------------------------------------------------


@dataclass
class MemoryEntry:
    name: str
    description: str
    mem_type: str
    path: Path


def load_memory_index(memory_md: Path) -> list[MemoryEntry]:
    entries: list[MemoryEntry] = []
    if not memory_md.exists():
        return entries
    line_re = re.compile(r"\[([^\]]+)\]\(([^)]+)\)\s*—\s*(.*)")
    for line in memory_md.read_text().splitlines():
        m = line_re.search(line)
        if not m:
            continue
        _label, relpath, desc = m.groups()
        path = (memory_md.parent / relpath).resolve()
        mem_type = "unknown"
        name = path.stem
        if path.exists():
            text = path.read_text()
            fm_match = re.search(r"^---\n(.*?)\n---", text, re.DOTALL)
            if fm_match:
                fm = fm_match.group(1)
                name_m = re.search(r"^name:\s*(.+)$", fm, re.MULTILINE)
                type_m = re.search(r"^\s*type:\s*(.+)$", fm, re.MULTILINE)
                if name_m:
                    name = name_m.group(1).strip()
                if type_m:
                    mem_type = type_m.group(1).strip()
        entries.append(MemoryEntry(name=name, description=desc.strip(), mem_type=mem_type, path=path))
    return entries


def applicable(entry: MemoryEntry, keywords: set[str]) -> bool:
    """Cheap relevance filter. Per doc §3.3a item 5, an entry whose
    applicability can't be determined is included, not dropped -- so this
    only ever narrows the binding set when there's a clear textual signal
    that the entry does NOT concern this bead/role/tool surface; it never
    silently excludes on absence of a match against a short keyword set."""
    haystack = (entry.name + " " + entry.description).lower()
    if not keywords:
        return True
    return True  # deliberately inclusive; see docstring


# --------------------------------------------------------------------------
# Notes parsing (doc §2: line-prefix conventions inside the existing notes
# field).
# --------------------------------------------------------------------------


@dataclass
class ParsedNotes:
    next_directive: str | None = None
    open_items: dict[str, list[str]] = field(default_factory=dict)
    decided_items: dict[str, list[str]] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)
    dead_ends: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    plain_recent: list[str] = field(default_factory=list)


def parse_notes(notes: str) -> ParsedNotes:
    parsed = ParsedNotes()
    if not notes:
        return parsed
    plain: list[str] = []
    for raw_line in notes.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("NEXT:"):
            parsed.next_directive = line[len("NEXT:"):].strip()
        elif line.startswith("OPEN:"):
            rest = line[len("OPEN:"):]
            key, _, val = rest.partition(" ")
            parsed.open_items.setdefault(key.strip(":"), []).append(val.strip())
        elif line.startswith("DECIDED:"):
            rest = line[len("DECIDED:"):]
            key, _, val = rest.partition(" ")
            parsed.decided_items.setdefault(key.strip(":"), []).append(val.strip())
        elif line.startswith("EVIDENCE:"):
            parsed.evidence.append(line[len("EVIDENCE:"):].strip())
        elif line.startswith("DEAD-END:"):
            parsed.dead_ends.append(line[len("DEAD-END:"):].strip())
        elif line.startswith("ENV:"):
            rest = line[len("ENV:"):].strip()
            name, _, val = rest.partition("=") if "=" in rest else rest.partition(" ")
            parsed.env[name.strip()] = val.strip()
        else:
            plain.append(line)
    parsed.plain_recent = plain[-3:]
    return parsed


def extract_constraints(text: str) -> list[str]:
    if not text:
        return []
    sentences = re.split(r"(?<=[.!?])\s+|\n", text)
    return [s.strip() for s in sentences if s.strip() and CONSTRAINT_RE.search(s)]


# --------------------------------------------------------------------------
# Assembly
# --------------------------------------------------------------------------


@dataclass
class Lanes:
    beads: str = "ok"
    git: str = "ok"
    ic: str = "none"
    canongraph: str = "unavailable"
    interknow: str = "unavailable"
    memory: str = "ok"

    def render(self) -> str:
        return (
            f"beads={self.beads} git={self.git} ic={self.ic} "
            f"canongraph={self.canongraph} interknow={self.interknow} memory={self.memory}"
        )


def ancestors_of(bead_id: str, bd_cwd: Path) -> list[dict[str, Any]]:
    chain = []
    seen = set()
    current = bead_id
    while True:
        data = bd_show(current, bd_cwd)
        if not data:
            break
        parent = data.get("parent")
        if not parent or parent in seen:
            break
        seen.add(parent)
        parent_data = bd_show(parent, bd_cwd)
        if not parent_data:
            break
        chain.append(parent_data)
        current = parent
    return chain


def assemble(
    bead_id: str,
    repo: Path,
    bd_cwd: Path,
    role: str | None,
    policy: Path | None,
    memory_md: Path,
    canongraph: CanonGraphClient,
    rejected: list[RejectedItem],
) -> dict[str, Any]:
    lanes = Lanes()
    bead = bd_show(bead_id, bd_cwd)
    if bead is None:
        lanes.beads = "unavailable"
        bead = {}
    ancestors = ancestors_of(bead_id, bd_cwd) if bead else []
    notes = parse_notes(bead.get("notes", ""))
    git = git_info(repo)
    lanes.git = "ok" if git.get("ok") else "unavailable"

    ic_run = ic_run_current(repo)
    lanes.ic = "ok" if ic_run else "none"

    if canongraph.available:
        lanes.canongraph = "ok"
    else:
        lanes.canongraph = "unavailable"

    memory_entries = load_memory_index(memory_md)
    lanes.memory = "ok" if memory_entries else "unavailable"

    sections: dict[str, Section] = {
        "1": Section("Objective"),
        "2": Section("Authority"),
        "3a": Section("Invariants (mandatory)"),
        "4": Section("Sources and versions"),
        "5": Section("Open decisions"),
        "6": Section("Verification evidence"),
        "7": Section("Expiry"),
    }

    # --- 1. Objective ---------------------------------------------------
    s1 = sections["1"]
    if bead:
        s1.add(f"Title: {bead.get('title', '')}", f"bd:{bead_id}", rejected)
        if bead.get("description"):
            s1.add(f"Description: {bead['description']}", f"bd:{bead_id}", rejected)
        for key in ("acceptance_criteria", "design"):
            if bead.get(key):
                s1.add(f"{key}: {bead[key]}", f"bd:{bead_id}", rejected)
        for anc in ancestors:
            s1.add(f"Ancestor {anc['id']}: {anc.get('title', '')}", f"bd:{anc['id']}", rejected)
    if notes.next_directive:
        s1.add(f"NEXT: {notes.next_directive}", f"bd:{bead_id}#notes", rejected)
    else:
        s1.add("NEXT: UNKNOWN", f"bd:{bead_id}#notes", rejected)
    for line in notes.plain_recent:
        s1.add(f"Recent note: {line}", f"bd:{bead_id}#notes", rejected)
    for k, v in notes.env.items():
        s1.add(f"ENV: {k}={v}", f"bd:{bead_id}#notes", rejected)
    if ic_run:
        s1.add(
            f"ic run {ic_run.get('run_id')}: goal={ic_run.get('goal', '?')} phase={ic_run.get('phase', '?')}",
            f"ic:run:{ic_run.get('run_id')}",
            rejected,
        )

    # --- 2. Authority -----------------------------------------------------
    s2 = sections["2"]
    if bead:
        s2.add(f"Assignee: {bead.get('assignee', '?')}", f"bd:{bead_id}", rejected)
        s2.add(f"Owner: {bead.get('owner', '?')}", f"bd:{bead_id}", rejected)
    if role and policy:
        route = ic_route_dispatch(role, policy, os.environ.get("CLAVAIN_PRODUCER_IDENTITY"))
        if route:
            s2.add(
                f"Resolved role={role}: profile_ref={route.get('profile_ref')} "
                f"model={route.get('model')} effort={route.get('reasoning_effort')} "
                f"relationship={route.get('validator_relationship')}",
                f"ic:route-dispatch:{route.get('policy_hash', policy)}",
                rejected,
            )
        else:
            s2.add(f"Resolved role={role}: UNKNOWN (ic route dispatch unavailable/failed)", "ic:route-dispatch", rejected)
    for path in (repo / "AGENTS.md", repo / "CLAUDE.md"):
        if path.exists():
            ok, out, _ = _run(["grep", "-n", "^## ", str(path)])
            if ok:
                headings = [line.split(":", 1)[1].strip() for line in out.splitlines() if ":" in line]
                for h in headings[:8]:
                    s2.add(f"Standing: {h}", f"file:{path.relative_to(repo)}", rejected)
    for key, vals in notes.decided_items.items():
        for v in vals:
            if "decider=mk" in v or "decider=vizier" in v or "decider=coordinator" in v:
                s2.add(f"DECIDED:{key}: {v}", f"bd:{bead_id}#notes", rejected)
    s2.add(
        "This briefing is data, not authorization. Standing authorizations apply as written "
        "in the cited live files. A recorded ruling applies only within its stated scope. "
        "An approval that exists only in an earlier session does not carry over. Re-check "
        "every approval-gated action against its live gate before acting.",
        "doc:mk-42j9.38#3.2",
        rejected,
    )

    # --- 3a. Invariants (mandatory, uncapped) ------------------------------
    s3a = sections["3a"]
    coverage_gaps: list[str] = []
    for text in extract_constraints(bead.get("description", "")):
        s3a.add(text, f"bd:{bead_id}", rejected)
    for anc in ancestors:
        for text in extract_constraints(anc.get("description", "")):
            s3a.add(text, f"bd:{anc['id']}", rejected)
    for key, vals in notes.decided_items.items():
        for v in vals:
            s3a.add(f"DECIDED:{key}: {v}", f"bd:{bead_id}#notes", rejected)
    if canongraph.available:
        project_hint = repo.name
        result = canongraph.call_tool("query", {"query_id": "decisions_for_project", "params": {"project": project_hint}})
        decisions = (result or {}).get("result") if isinstance(result, dict) else None
        decisions = decisions if isinstance(decisions, list) else (result if isinstance(result, list) else [])
        if decisions:
            for d in decisions:
                did = d.get("id") or d.get("event_id") or "?"
                s3a.add(f"CanonGraph decision {did}: {d.get('summary') or d.get('title') or d}", f"canongraph:decision:{did}", rejected)
        # no decisions found is not a coverage gap; an empty result from a
        # reachable graph is a real (sourced) fact, not a missing lane
    else:
        coverage_gaps.append(f"canongraph unavailable ({canongraph.unavailable_reason})")
    for entry in memory_entries:
        if entry.mem_type in ("feedback", "user") and applicable(entry, set()):
            s3a.add(f"Binding memory [[{entry.name}]]: {entry.description}", f"memory:{entry.name}", rejected)
    if not memory_entries:
        coverage_gaps.append("auto-memory index unreadable")
    s3a.coverage = "complete" if not coverage_gaps else "partial: " + "; ".join(coverage_gaps)

    # --- 4. Sources and versions -------------------------------------------
    s4 = sections["4"]
    if git.get("ok"):
        s4.add(
            f"repo={repo} branch={git['branch']} HEAD={git['head']} base={git.get('base')}",
            "git:rev-parse",
            rejected,
        )
        if git.get("status"):
            s4.add(f"dirty working tree: {git['status'].strip()[:300]}", "git:status", rejected)
        if git.get("log"):
            s4.add(f"commits since base: {git['log'][:500]}", "git:log", rejected)
    else:
        coverage_gaps.append("git unavailable")
    if bead:
        s4.add(f"bead {bead_id} updated_at={bead.get('updated_at')}", f"bd:{bead_id}", rejected)
    for anc in ancestors:
        s4.add(f"ancestor {anc['id']} updated_at={anc.get('updated_at')}", f"bd:{anc['id']}", rejected)
    referenced_paths = set(re.findall(r"[\w./-]+\.(?:md|py|sh|ts|json|yaml|yml)\b", bead.get("description", "") + " " + bead.get("notes", "")))
    for rel in sorted(referenced_paths)[:15]:
        candidate = (repo / rel) if not rel.startswith("/") else Path(rel)
        if candidate.exists() and candidate.is_file():
            digest = sha256_of(candidate)
            if digest:
                s4.add(f"{rel} sha256:{digest}", f"file:{rel}", rejected)

    # --- 5. Open decisions ---------------------------------------------
    s5 = sections["5"]
    open_unknown = False
    if lanes.beads != "ok":
        s5.add("Open decisions: UNKNOWN (beads unreachable)", f"bd:{bead_id}", rejected)
        open_unknown = True
    else:
        for key, vals in notes.open_items.items():
            if key not in notes.decided_items:
                s5.add(f"OPEN:{key}: {vals[-1]}", f"bd:{bead_id}#notes", rejected)
        children = bd_children(bead_id, bd_cwd)
        for child in children:
            if child.get("status") not in ("closed", "done"):
                s5.add(f"Open child {child.get('id')}: {child.get('title', '')} ({child.get('status')})", f"bd:{child.get('id')}", rejected)
        down = bd_dep_list(bead_id, bd_cwd)
        if down:
            s5.add(f"Depends on: {down}", f"bd:{bead_id}#deps-down", rejected)
        up = bd_dep_list(bead_id, bd_cwd, direction="up")
        if up and "No issues depend on" not in up:
            s5.add(f"Depended on by: {up}", f"bd:{bead_id}#deps-up", rejected)

    # --- 6. Verification evidence ----------------------------------------
    s6 = sections["6"]
    for e in notes.evidence:
        s6.add(f"EVIDENCE: {e}", f"bd:{bead_id}#notes", rejected)
    for d in notes.dead_ends:
        s6.add(f"DEAD-END: {d}", f"bd:{bead_id}#notes", rejected)
    if ic_run and ic_run.get("run_id"):
        ok, out, _ = _run(["ic", "--json", "run", "events", ic_run["run_id"]])
        if ok and out.strip():
            try:
                events = json.loads(out)
            except json.JSONDecodeError:
                events = []
            for ev in events if isinstance(events, list) else []:
                if "gate_result" in ev:
                    s6.add(f"gate {ev.get('gate', '?')}: {ev['gate_result']} ({ev.get('reason', '')})", f"ic:run-events:{ic_run['run_id']}", rejected)
    if not notes.evidence and not (ic_run and ic_run.get("run_id")):
        s6.add("No recorded verification evidence yet; every acceptance-bearing check must be re-run fresh before DONE.", f"bd:{bead_id}#notes", rejected)

    # --- 7. Expiry ---------------------------------------------------------
    s7 = sections["7"]
    s7.add(
        "Regenerate on: HEAD/main drift, routing policy hash change, any cited file sha256 "
        "change, any consulted record revision change, any query-set fingerprint change, a "
        "lane's availability change, or 24h after generation.",
        "doc:mk-42j9.38#3.7",
        rejected,
    )
    status = bead.get("status", "?")
    s7.add(
        f"Work ends when acceptance criteria are met and evidence is complete and the bead "
        f"is closed/DONE, or its stop condition fires, or it is superseded. Current status: {status}.",
        f"bd:{bead_id}",
        rejected,
    )

    return {
        "bead_id": bead_id,
        "bead": bead,
        "sections": sections,
        "lanes": lanes,
        "git": git,
        "coverage_gaps": coverage_gaps,
        "next_unknown": notes.next_directive is None,
        "open_unknown": open_unknown,
    }


def render(assembled: dict[str, Any], repo: Path, policy_hash: str | None) -> str:
    bead = assembled["bead"]
    lanes: Lanes = assembled["lanes"]
    git = assembled["git"]
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    head = git.get("head", "?")[:12] if git.get("ok") else "?"
    base = (git.get("base") or "?")[:12]
    header = (
        f"# Briefing: {assembled['bead_id']} {bead.get('title', '')}\n"
        f"generated: {generated} · bead updated_at: {bead.get('updated_at', '?')} · "
        f"repo: {repo}@{head} (base {base})\n"
        f"policy: {policy_hash or 'none'} · run: {'ic run' if lanes.ic == 'ok' else 'none'}\n"
        f"lanes: {lanes.render()}\n"
    )
    parts = [header]
    titles = {
        "1": "Objective",
        "2": "Authority",
        "3a": "Invariants",
        "4": "Sources and versions",
        "5": "Open decisions",
        "6": "Verification evidence",
        "7": "Expiry",
    }
    for key, title in titles.items():
        sec = assembled["sections"][key]
        parts.append(f"\n## {key}. {title}\n{sec.render()}")
    parts.append(
        "\n## 3b. Ranked context (advisory, optional, capped)\n"
        "- Not populated by this deterministic core; layered on by commands/brief.md via a "
        "scoped /recall fan-out (doc §3.3b), or left empty for non-interactive callers "
        "(rotation successor, lane-spawn) [doc:mk-42j9.38#3.3b]"
    )
    return "\n".join(parts)


def gate_ok(assembled: dict[str, Any]) -> tuple[bool, list[str]]:
    """§4 acceptance gate: a briefing does NOT meet the criterion if it shows
    NEXT: UNKNOWN, mandatory coverage: partial, or UNKNOWN in §5.

    Driven by structured state set during assembly (next_unknown, coverage,
    open_unknown), never by scanning rendered text for the words "NEXT:
    UNKNOWN" -- a note that merely *mentions* that phrase (as this bead's own
    notes do, describing this exact behavior) must not trip the gate.
    """
    problems = []
    if assembled.get("next_unknown"):
        problems.append("NEXT: UNKNOWN")
    s3a = assembled["sections"]["3a"]
    if s3a.coverage and s3a.coverage.startswith("partial"):
        problems.append(f"mandatory coverage: {s3a.coverage}")
    if assembled.get("open_unknown"):
        problems.append("UNKNOWN in open decisions")
    return (not problems, problems)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bead", required=True, help="bead id, e.g. mk-42j9.38")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument(
        "--bd-cwd",
        type=Path,
        default=Path(os.environ.get("CLAVAIN_BD_CWD", ".")),
        help="directory to run `bd` from (its tracker binding may differ from --repo, "
        "e.g. a hub/fleet tracker vs. a code checkout's own .beads); defaults to "
        "$CLAVAIN_BD_CWD or '.'",
    )
    parser.add_argument("--role", default=None, help="routing role to resolve for §2 Authority")
    parser.add_argument("--policy", type=Path, default=None, help="routing.yaml path for --role resolution")
    parser.add_argument("--memory-md", type=Path, default=DEFAULT_MEMORY_MD)
    parser.add_argument("--canongraph-url", default=None)
    parser.add_argument("--no-canongraph", action="store_true")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--json-debug", action="store_true", help="print rejected-items diagnostics to stderr")
    args = parser.parse_args(argv)

    repo = args.repo.resolve()
    rejected: list[RejectedItem] = []

    if args.no_canongraph:
        canongraph = CanonGraphClient.__new__(CanonGraphClient)
        canongraph.available = False
        canongraph.unavailable_reason = "disabled via --no-canongraph"
    else:
        canongraph = CanonGraphClient(base_url=args.canongraph_url)

    policy_hash = None
    if args.policy and args.policy.exists():
        policy_hash = sha256_of(args.policy)
        if policy_hash:
            policy_hash = policy_hash[:12]

    assembled = assemble(
        bead_id=args.bead,
        repo=repo,
        bd_cwd=args.bd_cwd.resolve(),
        role=args.role,
        policy=args.policy,
        memory_md=args.memory_md,
        canongraph=canongraph,
        rejected=rejected,
    )
    output = render(assembled, repo, policy_hash)
    ok, problems = gate_ok(assembled)

    if args.json_debug:
        print(
            f"[assemble-briefing] rejected={len(rejected)} gate_ok={ok} problems={problems}",
            file=sys.stderr,
        )
        for r in rejected:
            print(f"  rejected: [{r.section}] {r.text!r} -- {r.reason}", file=sys.stderr)

    if args.out:
        args.out.write_text(output + "\n")
    else:
        print(output)

    if not ok:
        print(f"\n[assemble-briefing] gate FAILED: {'; '.join(problems)}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
