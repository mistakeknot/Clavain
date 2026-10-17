#!/usr/bin/env python3
"""Wayfind: a decision map kept in beads, for efforts whose route is not yet visible.

Adapted from the wayfinder skill in mattpocock/skills (MIT License,
Copyright (c) 2026 Matt Pocock). This file is the mechanism only: label and
body conventions plus four subcommands built from `bd`. The loop that uses it
is commands/wayfind.md.

A map is a beads epic labelled wayfinder:map. Each child is one decision
ticket carrying exactly one type label. The map body has five sections; the
Destination and Out of scope sections are the targets, and a hash of them is
stored in the body so `lint` can tell when they changed without a cited source.

    wayfind chart   create a map, add tickets to it, or retarget it
    wayfind ready   list the frontier, or claim one ticket from it
    wayfind resolve record a ticket's answer, close it, update the map
    wayfind lint    check the map's rules and report whether it converges

Exit codes: 0 ok, 1 rule violation (the request is well formed but a map rule
refuses it, or lint found a broken rule), 2 usage, malformed spec or bd failure,
3 divergence alarm. A refused request changes nothing.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

MAP_LABEL = "wayfinder:map"
TYPES = ("grilling", "prototype", "research", "task", "revisit")
TYPE_LABELS = {f"wayfinder:{t}": t for t in TYPES}
# Tickets that resolve only on the owner's answer. A revisit reverses an owner decision, so it is one.
HITL_TYPES = frozenset({"grilling", "prototype", "revisit"})
INVALIDATED_LABEL = "wayfinder:invalidated"
SUPERSEDED_LABEL = "wayfinder:superseded"

SECTIONS = ("Destination", "Out of scope", "Notes", "Decisions so far", "Not yet specified")
TARGET_SECTIONS = ("Destination", "Out of scope")
MAP_MARKER = "<!-- wayfind:map v1 -->"
TARGETS_RE = re.compile(r"<!-- wayfind:targets sha256=([0-9a-f]{64}) source=(.*?) -->")

DEFAULT_CAP = 7          # design choice: open tickets per map before chart refuses
DEFAULT_MAX_AGE_DAYS = 14  # design choice: no resolution for this long is stale
SUMMARY_WIDTH = 120

EXIT_OK, EXIT_RULE, EXIT_USAGE, EXIT_ALARM = 0, 1, 2, 3


class WayfindError(Exception):
    """Usage, spec or bd failure."""
    exit_code = EXIT_USAGE


class RuleError(WayfindError):
    """A well-formed request that a map rule refuses."""
    exit_code = EXIT_RULE


# ---------------------------------------------------------------------------
# bd
# ---------------------------------------------------------------------------


class Bd:
    """Thin wrapper over the bd CLI. Every write goes through bd itself."""

    def __init__(self, binary: str | None = None, directory: str | None = None, actor: str | None = None):
        self.binary = binary or os.environ.get("WAYFIND_BD", "bd")
        self.directory = directory
        self.actor = actor

    def run(self, *args: str, stdin: str | None = None) -> str:
        cmd = [self.binary]
        if self.directory:
            cmd += ["-C", self.directory]
        if self.actor:
            cmd += ["--actor", self.actor]
        cmd += list(args)
        try:
            proc = subprocess.run(cmd, input=stdin, capture_output=True, text=True, timeout=120)
        except FileNotFoundError as exc:
            raise WayfindError(f"bd not found: {self.binary}") from exc
        except subprocess.TimeoutExpired as exc:
            raise WayfindError(f"bd {' '.join(args[:2])} timed out") from exc
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout).strip().splitlines()
            raise WayfindError(f"bd {' '.join(args[:2])} failed: {detail[-1] if detail else proc.returncode}")
        return proc.stdout

    def json(self, *args: str):
        out = self.run(*args, "--json")
        try:
            return json.loads(out) if out.strip() else []
        except json.JSONDecodeError as exc:
            raise WayfindError(f"bd {' '.join(args[:2])} returned non-JSON output") from exc

    def show(self, issue_id: str) -> dict:
        data = self.json("show", issue_id)
        if isinstance(data, list):
            if not data:
                raise WayfindError(f"{issue_id}: not found")
            data = data[0]
        return data

    def children(self, map_id: str) -> list[dict]:
        return self.json("list", "--parent", map_id, "--all", "--limit", "0")

    def ready_ids(self, map_id: str) -> list[str]:
        return [i["id"] for i in self.json("ready", "--parent", map_id, "--unassigned", "--limit", "0")]

    def create(self, title: str, description: str, labels: list[str], *, parent: str | None = None,
               issue_type: str = "task", blocked_by: list[str] | None = None) -> str:
        """Create one issue, labels and blocking links included, in a single bd call."""
        args = ["create", "--title", title, "-t", issue_type, "--body-file", "-"]
        if labels:
            args += ["-l", ",".join(labels)]
        if parent:
            # bd copies the parent's labels onto children; a ticket must not look like a map.
            args += ["--parent", parent, "--no-inherit-labels"]
        if blocked_by:
            # A bare id makes the new issue blocked by it ("blocks:<id>" means the reverse).
            args += ["--deps", ",".join(blocked_by)]
        out = self.run(*args, "--json", stdin=description)
        try:
            return json.loads(out)["id"]
        except (json.JSONDecodeError, KeyError) as exc:
            raise WayfindError("bd create returned no id") from exc

    def set_description(self, issue_id: str, body: str) -> None:
        self.run("update", issue_id, "--body-file", "-", stdin=body)

    def add_label(self, issue_id: str, label: str) -> None:
        self.run("update", issue_id, "--add-label", label)

    def remove_label(self, issue_id: str, label: str) -> None:
        self.run("update", issue_id, "--remove-label", label)

    def comments(self, issue_id: str) -> list[dict]:
        return self.json("comments", issue_id) or []

    def comment(self, issue_id: str, text: str) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as fh:
            fh.write(text)
            path = fh.name
        try:
            self.run("comments", "add", issue_id, "-f", path)
        finally:
            os.unlink(path)

    def close(self, issue_id: str, reason: str) -> None:
        self.run("close", issue_id, "--reason", reason)

    def claim(self, issue_id: str) -> None:
        self.run("update", issue_id, "--claim")

    def release(self, issue_id: str) -> None:
        self.run("update", issue_id, "--status", "open", "--assignee", "")

    def whoami(self) -> str:
        """The name bd records as assignee on --claim: --actor, $BEADS_ACTOR, git user.name, $USER."""
        if self.actor:
            return self.actor
        if os.environ.get("BEADS_ACTOR"):
            return os.environ["BEADS_ACTOR"]
        cmd = ["git"] + (["-C", self.directory] if self.directory else []) + ["config", "user.name"]
        try:
            name = subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            name = ""
        return name or os.environ.get("USER", "")


# ---------------------------------------------------------------------------
# Map body
# ---------------------------------------------------------------------------


def targets_digest(sections: dict[str, str]) -> str:
    # An empty target renders as the placeholder, so both must hash alike.
    joined = "\n---\n".join("" if is_placeholder(sections.get(name, "")) else sections[name].strip()
                            for name in TARGET_SECTIONS)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def parse_body(body: str) -> dict[str, str]:
    """Split a map body into its `## ` sections. Unknown headings are kept."""
    sections: dict[str, str] = {}
    current = None
    lines: list[str] = []
    for line in (body or "").splitlines():
        heading = re.match(r"^## (.+?)\s*$", line)
        if heading:
            if current is not None:
                sections[current] = "\n".join(lines).strip()
            current, lines = heading.group(1), []
        elif current is not None and not TARGETS_RE.search(line) and line.strip() != MAP_MARKER:
            lines.append(line)
    if current is not None:
        sections[current] = "\n".join(lines).strip()
    return sections


def targets_marker(body: str) -> tuple[str, str] | None:
    match = TARGETS_RE.search(body or "")
    return (match.group(1), match.group(2)) if match else None


def render_body(sections: dict[str, str], source: str) -> str:
    out = [MAP_MARKER]
    for name in SECTIONS:
        out += [f"## {name}", sections.get(name, "").strip() or "_(none)_", ""]
    for name, text in sections.items():
        if name not in SECTIONS:
            out += [f"## {name}", text.strip(), ""]
    clean_source = " ".join(source.split()).replace("-->", "")
    out.append(f"<!-- wayfind:targets sha256={targets_digest(sections)} source={clean_source} -->")
    return "\n".join(out) + "\n"


def check_targets(map_id: str, body: str, sections: dict[str, str]) -> None:
    """Refuse to rewrite a map whose targets changed without a cited source."""
    marker = targets_marker(body)
    if marker is None:
        raise RuleError(f"{map_id}: no targets marker; set the targets with wayfind chart --map ... --source ...")
    if marker[0] != targets_digest(sections):
        raise RuleError(f"{map_id}: Destination or Out of scope changed without a cited source; "
                        "restore them, or record the owner's change with wayfind chart --map ... --source ...")


def bullets(text: str) -> list[str]:
    return [m.group(1).strip() for m in re.finditer(r"^\s*[-*] (.+)$", text or "", re.MULTILINE)]


def set_bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def decision_lines(sections: dict[str, str]) -> list[str]:
    text = sections.get("Decisions so far", "")
    return [] if is_placeholder(text) else bullets(text)


def decision_for(lines: list[str], ticket_id: str) -> str | None:
    return next((ln for ln in lines if ln.startswith(f"{ticket_id} ")), None)


def is_placeholder(text: str) -> bool:
    return (text or "").strip() in ("", "_(none)_")


def one_line(text: str) -> str:
    first = next((ln.strip() for ln in (text or "").splitlines() if ln.strip()), "")
    return first if len(first) <= SUMMARY_WIDTH else first[: SUMMARY_WIDTH - 1] + "…"


# ---------------------------------------------------------------------------
# Map state
# ---------------------------------------------------------------------------


def ticket_type(issue: dict) -> str | None:
    found = [TYPE_LABELS[label] for label in issue.get("labels") or [] if label in TYPE_LABELS]
    return found[0] if len(found) == 1 else None


def type_labels(issue: dict) -> list[str]:
    return [label for label in issue.get("labels") or [] if label in TYPE_LABELS]


def load_map(bd: Bd, map_id: str) -> dict:
    issue = bd.show(map_id)
    if MAP_LABEL not in (issue.get("labels") or []):
        raise WayfindError(f"{map_id} is not a map (no {MAP_LABEL} label)")
    return issue


def map_tickets(bd: Bd, map_id: str) -> list[dict]:
    return [c for c in bd.children(map_id) if c.get("id") != map_id]


def parse_time(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# chart
# ---------------------------------------------------------------------------


def read_text(value: str | None, path: str | None) -> str | None:
    if path:
        return Path(path).read_text(encoding="utf-8")
    return value


SPEC_KEYS = frozenset({"tickets", "fog", "graduate", "notes"})
TICKET_KEYS = frozenset({"key", "type", "title", "question", "blocked_by"})


def _strings(value, what: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
        raise WayfindError(f"{what} must be a list of non-empty strings")
    return [v.strip() for v in value]


def load_spec(path: str | None) -> dict:
    """Read and shape-check a ticket spec. Nothing is written until the whole spec passes."""
    if not path:
        return {"tickets": [], "fog": [], "graduate": [], "notes": ""}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, list):
        data = {"tickets": data}
    if not isinstance(data, dict):
        raise WayfindError("ticket spec must be a JSON object or list")
    unknown = sorted(set(data) - SPEC_KEYS)
    if unknown:
        raise WayfindError(f"ticket spec: unknown key(s) {', '.join(unknown)}")
    raw = data.get("tickets") or []
    if not isinstance(raw, list):
        raise WayfindError("ticket spec: tickets must be a list")
    tickets, keys = [], set()
    for i, ticket in enumerate(raw):
        if not isinstance(ticket, dict):
            raise WayfindError(f"ticket {i}: must be an object")
        unknown = sorted(set(ticket) - TICKET_KEYS)
        if unknown:
            raise WayfindError(f"ticket {i}: unknown key(s) {', '.join(unknown)}")
        if ticket.get("type") not in TYPES:
            raise WayfindError(f"ticket {i}: type must be one of {', '.join(TYPES)}")
        for field in ("title", "question"):
            if field in ticket and not isinstance(ticket[field], str):
                raise WayfindError(f"ticket {i}: {field} must be a string")
        if not (ticket.get("title") or "").strip():
            raise WayfindError(f"ticket {i}: title is required")
        key = ticket.get("key", i)
        if not isinstance(key, (str, int)) or isinstance(key, bool) or not str(key).strip():
            raise WayfindError(f"ticket {i}: key must be a non-empty string or an integer")
        key = str(key).strip()
        if key in keys:
            raise WayfindError(f"ticket {i}: duplicate key {key!r}")
        keys.add(key)
        blocked = ticket.get("blocked_by")
        if isinstance(blocked, list):
            # Integer blockers name the index keys of earlier tickets.
            blocked = [str(b) if isinstance(b, int) and not isinstance(b, bool) else b for b in blocked]
        tickets.append({**ticket, "key": key, "blocked_by": _strings(blocked, f"ticket {i}: blocked_by")})
    notes = data.get("notes") or ""
    if not isinstance(notes, str):
        raise WayfindError("ticket spec: notes must be a string")
    return {"tickets": tickets, "fog": _strings(data.get("fog"), "fog"),
            "graduate": _strings(data.get("graduate"), "graduate"), "notes": notes}


def creation_order(tickets: list[dict], existing_ids: set[str]) -> list[dict]:
    """Order new tickets so each one's blockers exist before it. Refuses unknown blockers and cycles.

    A blocked_by entry names a spec key or an existing ticket of this map.
    """
    keys = {t["key"] for t in tickets}
    for t in tickets:
        if t["key"] in existing_ids:
            raise WayfindError(f"ticket key {t['key']!r} is also an existing ticket id; rename the key")
        for blocker in t["blocked_by"]:
            if blocker not in keys and blocker not in existing_ids:
                raise WayfindError(f"ticket {t['key']!r}: blocker {blocker!r} is neither a spec key "
                                   "nor a ticket of this map")
    ordered, placed = [], set()
    pending = list(tickets)
    while pending:
        ready = [t for t in pending if all(b in placed or b not in keys for b in t["blocked_by"])]
        if not ready:
            raise WayfindError("blocked_by forms a cycle among: " + ", ".join(t["key"] for t in pending))
        for t in ready:
            ordered.append(t)
            placed.add(t["key"])
        pending = [t for t in pending if t["key"] not in placed]
    return ordered


def ticket_body(ticket: dict, map_id: str) -> str:
    parts = [f"Map: {map_id}", f"Type: {ticket['type']}", ""]
    parts.append((ticket.get("question") or ticket["title"]).strip())
    if ticket.get("type") in HITL_TYPES:
        parts += ["", "Resolves only on the owner's answer: a live reply while the owner is present, "
                      "or a card pick. An agent's choice is a recommendation, never the resolution."]
    if ticket.get("type") == "revisit":
        parts += ["Resolve it with --supersedes naming the closed decision it replaces."]
    return "\n".join(parts) + "\n"


def cmd_chart(bd: Bd, args) -> int:
    # Every check runs before the first write, so a refused or malformed request changes nothing.
    spec = load_spec(args.tickets)
    destination = read_text(args.destination, args.destination_file)
    out_of_scope = read_text(args.out_of_scope, args.out_of_scope_file)
    retarget = destination is not None or out_of_scope is not None

    if args.map:
        issue = load_map(bd, args.map)
        map_id = args.map
        body = issue.get("description") or ""
        sections = parse_body(body)
        marker = targets_marker(body)
        source = marker[1] if marker else ""
        if not retarget:
            check_targets(map_id, body, sections)
        if retarget:
            if not args.source:
                raise RuleError("changing Destination or Out of scope needs --source (the owner's card pick or a ruling)")
            if destination is not None:
                sections["Destination"] = destination.strip()
            if out_of_scope is not None:
                sections["Out of scope"] = out_of_scope.strip()
            source = args.source
        existing = map_tickets(bd, map_id)
    else:
        if not args.title or destination is None:
            raise WayfindError("a new map needs --title and --destination (or --destination-file)")
        if not args.source:
            raise RuleError("a new map needs --source: where the owner set the Destination")
        sections = {"Destination": destination.strip(), "Out of scope": (out_of_scope or "").strip(),
                    "Notes": "", "Decisions so far": "", "Not yet specified": ""}
        source = args.source
        map_id = None
        existing = []

    fog = [] if is_placeholder(sections.get("Not yet specified", "")) else bullets(sections["Not yet specified"])
    for item in spec["graduate"]:
        if item not in fog:
            raise WayfindError(f"cannot graduate {item!r}: not in Not yet specified")
        fog.remove(item)
    fog += [item for item in spec["fog"] if item not in fog]
    sections["Not yet specified"] = set_bullets(fog)
    if spec["notes"].strip():
        notes = "" if is_placeholder(sections.get("Notes", "")) else sections["Notes"]
        sections["Notes"] = (notes + "\n" + spec["notes"].strip()).strip()

    tickets = creation_order(spec["tickets"], {t["id"] for t in existing})
    open_now = [t for t in existing if t.get("status") != "closed"]
    if len(open_now) + len(tickets) > args.cap and not args.allow_over_cap:
        raise RuleError(
            f"{len(open_now)} open + {len(tickets)} new tickets exceeds the cap of {args.cap}; "
            "keep the rest as fog, or pass --allow-over-cap")

    if args.dry_run:
        print(json.dumps({"map": map_id, "create_map": map_id is None, "retarget": retarget and bool(map_id),
                          "tickets": [{"key": t["key"], "type": t["type"], "title": t["title"],
                                       "blocked_by": t["blocked_by"]} for t in tickets],
                          "fog": fog}, indent=2))
        return EXIT_OK

    if map_id is None:
        map_id = bd.create(f"[map] {args.title}", render_body(sections, source), [MAP_LABEL], issue_type="epic")

    # Tickets first, each created whole (labels and blockers in one bd call), the map body last.
    # A failure part way leaves the body as it was, so graduated fog is never lost and the map
    # cannot read as cleared while tickets are missing.
    created: dict[str, str] = {}
    try:
        for ticket in tickets:
            blockers = [created[b] if b in created else b for b in ticket["blocked_by"]]
            created[ticket["key"]] = bd.create(ticket["title"], ticket_body(ticket, map_id),
                                               [f"wayfinder:{ticket['type']}"], parent=map_id,
                                               blocked_by=blockers)
    except WayfindError as exc:
        done = ", ".join(f"{k}={v}" for k, v in created.items()) or "none"
        raise WayfindError(f"{exc}. Map {map_id}: created {done}; the map body is unchanged. Rerun with "
                           "only the tickets not yet created, keeping fog and graduate as they were") from exc

    if args.map:
        bd.set_description(map_id, render_body(sections, source))
        if retarget:
            bd.comment(map_id, f"Targets changed. Source: {source}")

    print(json.dumps({"map": map_id, "tickets": created, "fog": len(fog)}) if args.json
          else f"map {map_id}: {len(created)} ticket(s) created, {len(fog)} fog item(s)")
    return EXIT_OK


# ---------------------------------------------------------------------------
# ready
# ---------------------------------------------------------------------------


def frontier(bd: Bd, map_id: str) -> tuple[list[dict], list[dict], list[dict]]:
    """Return (unclaimed frontier, HITL tickets in flight, all in-progress tickets)."""
    tickets = map_tickets(bd, map_id)
    by_id = {t["id"]: t for t in tickets}
    in_progress = [t for t in tickets if t.get("status") == "in_progress"]
    in_flight = [t for t in in_progress if ticket_type(t) in HITL_TYPES]
    ready = [by_id[i] for i in bd.ready_ids(map_id) if i in by_id and ticket_type(by_id[i])]
    if in_flight:
        # One HITL ticket per map at a time: parallel grilling repeats questions.
        ready = [t for t in ready if ticket_type(t) not in HITL_TYPES]
    return ready, in_flight, in_progress


def claim_one(bd: Bd, map_id: str, ready: list[dict]) -> tuple[dict | None, str | None]:
    """Claim the first frontier ticket. Returns (claimed, held_reason).

    Two agents can both see no HITL ticket in flight and both claim one. After a HITL
    claim, re-read the map: if another HITL ticket is now in flight with a smaller id,
    release ours. Both agents apply the same rule, so exactly one keeps its claim.
    """
    if not ready:
        return None, None
    ticket = ready[0]
    try:
        bd.claim(ticket["id"])
    except WayfindError as exc:
        if "already claimed" not in str(exc):
            raise
        return None, f"{ticket['id']} was claimed by someone else first; rerun ready"
    if ticket_type(ticket) not in HITL_TYPES:
        return ticket, None
    _, in_flight, _ = frontier(bd, map_id)
    rivals = sorted(t["id"] for t in in_flight if t["id"] != ticket["id"])
    if rivals and rivals[0] < ticket["id"]:
        bd.release(ticket["id"])
        return None, f"{rivals[0]} was claimed at the same time; {ticket['id']} released"
    return ticket, None


def cmd_ready(bd: Bd, args) -> int:
    load_map(bd, args.map)
    ready, in_flight, in_progress = frontier(bd, args.map)
    me = bd.whoami()
    mine = [t for t in in_progress if me and t.get("assignee") == me]
    claimed, resumed, held = None, False, None
    if args.claim:
        if mine:
            # Finish what you hold before taking more; a crashed session resumes here.
            claimed, resumed = mine[0], True
        else:
            claimed, held = claim_one(bd, args.map, ready)
    if args.json:
        print(json.dumps({"map": args.map,
                          "frontier": [{"id": t["id"], "type": ticket_type(t), "title": t.get("title")} for t in ready],
                          "hitl_in_flight": [t["id"] for t in in_flight],
                          "in_progress": [{"id": t["id"], "type": ticket_type(t), "assignee": t.get("assignee")}
                                          for t in in_progress],
                          "claimed": claimed["id"] if claimed else None,
                          "resumed": resumed,
                          "held": held}))
        return EXIT_OK
    for t in in_progress:
        owner = "yours" if t in mine else (t.get("assignee") or "unassigned")
        print(f"in progress: {t['id']} ({ticket_type(t)}, {owner})")
    if in_flight:
        print("held: other HITL tickets wait until the one in flight resolves")
    if not ready:
        print("frontier empty")
    for t in ready:
        print(f"{t['id']}\t{ticket_type(t)}\t{t.get('title', '')}")
    if held:
        print(f"held: {held}")
    if claimed:
        print(f"{'resumed' if resumed else 'claimed'} {claimed['id']}")
    return EXIT_OK


# ---------------------------------------------------------------------------
# resolve
# ---------------------------------------------------------------------------


def check_supersedes(bd: Bd, old_id: str, ticket_id: str, map_id: str, lines: list[str]) -> dict:
    """The replaced decision must be a resolved ticket of the same map, not already replaced by another."""
    if old_id == ticket_id:
        raise RuleError(f"{ticket_id} cannot supersede itself")
    old = bd.show(old_id)
    if old.get("parent") != map_id:
        raise RuleError(f"{old_id} is not a ticket of map {map_id}")
    if old.get("status") != "closed" or INVALIDATED_LABEL in (old.get("labels") or []):
        raise RuleError(f"{old_id} is not a resolved decision; only a closed, resolved ticket can be superseded")
    entry = decision_for(lines, old_id) or ""
    match = re.search(r"\(superseded by (\S+)\)", entry)
    if match and match.group(1) != ticket_id:
        raise RuleError(f"{old_id} was already superseded by {match.group(1)}; supersede that one instead")
    return old


def cmd_resolve(bd: Bd, args) -> int:
    # All checks first; then each write is skipped when already done, so a retry with the
    # same arguments after a failure part way finishes the job instead of being refused.
    ticket = bd.show(args.ticket)
    kind = ticket_type(ticket)
    if kind is None:
        raise RuleError(f"{args.ticket} has no single wayfinder type label")
    map_id = ticket.get("parent")
    if not map_id:
        raise RuleError(f"{args.ticket} has no parent map")
    map_issue = load_map(bd, map_id)
    answer = read_text(args.answer, args.answer_file)
    if not answer or not answer.strip():
        raise WayfindError("resolve needs --answer or --answer-file")
    if args.invalidated and args.supersedes:
        raise WayfindError("--invalidated and --supersedes do not combine: an invalidated ticket decides nothing")
    if args.supersedes and kind != "revisit":
        raise RuleError("--supersedes is for revisit tickets")
    if kind == "revisit" and not args.invalidated and not args.supersedes:
        raise RuleError("a revisit ticket resolves with --supersedes naming the decision it replaces")
    if kind in HITL_TYPES and not args.invalidated and not args.source:
        raise RuleError(f"a {kind} ticket resolves only on the owner's answer: pass --source naming it")

    body = map_issue.get("description") or ""
    sections = parse_body(body)
    check_targets(map_id, body, sections)
    marker = targets_marker(body)
    lines = decision_lines(sections)
    entry = f"{args.ticket} {ticket.get('title', '')}: {args.summary or one_line(answer)}"
    reason = ("wayfind: invalidated" if args.invalidated
              else f"wayfind: resolved (source: {args.source})" if args.source else "wayfind: resolved")

    closed = ticket.get("status") == "closed"
    if closed:
        previous = ticket.get("close_reason") or ""
        if not previous.startswith("wayfind:"):
            raise RuleError(f"{args.ticket} was closed outside wayfind; reopen it (bd reopen) and resolve it here, "
                            "or open a revisit ticket")
        if previous.startswith("wayfind: invalidated") != bool(args.invalidated):
            raise RuleError(f"{args.ticket} is already closed as '{previous}'; open a revisit ticket to change it")
        recorded = decision_for(lines, args.ticket)
        if recorded is not None and not recorded.startswith(entry):
            raise RuleError(f"{args.ticket} is already resolved with a different answer; "
                            "open a revisit ticket instead of editing it")
    else:
        blockers = [d.get("id") for d in ticket.get("dependencies") or []
                    if d.get("dependency_type") == "blocks" and d.get("status") != "closed"]
        if blockers:
            raise RuleError(f"{args.ticket} is still blocked by {', '.join(blockers)}")
    old = check_supersedes(bd, args.supersedes, args.ticket, map_id, lines) if args.supersedes else None

    source = f"\n\nSource: {args.source}" if args.source else ""
    note = f"{'Invalidated' if args.invalidated else 'Resolution'}:\n{answer.strip()}{source}"
    steps = 0
    if not closed:
        if not any((c.get("text") or "").strip() == note.strip() for c in bd.comments(args.ticket)):
            bd.comment(args.ticket, note)
        if args.invalidated and INVALIDATED_LABEL not in (ticket.get("labels") or []):
            bd.add_label(args.ticket, INVALIDATED_LABEL)
        bd.close(args.ticket, reason)
        steps += 1
    if old is not None and SUPERSEDED_LABEL not in (old.get("labels") or []):
        bd.comment(old["id"], f"Superseded by {args.ticket}.")
        bd.add_label(old["id"], SUPERSEDED_LABEL)
        steps += 1

    new_lines = list(lines)
    if old is not None:
        new_lines = [f"{ln} (superseded by {args.ticket})" if ln.startswith(f"{old['id']} ")
                     and "(superseded by " not in ln else ln for ln in new_lines]
    if not args.invalidated and decision_for(new_lines, args.ticket) is None:
        new_lines.append(entry)
    if new_lines != lines:
        sections["Decisions so far"] = set_bullets(new_lines)
        # Write targets back exactly as found; resolve never changes them.
        bd.set_description(map_id, render_body(sections, marker[1] if marker else ""))
        steps += 1

    verb = "invalidated" if args.invalidated else "resolved"
    if not steps:
        print(f"{args.ticket} already {verb}; nothing to do")
    else:
        print(f"{args.ticket} {verb}{' (finished an earlier partial run)' if closed else ''}; map {map_id} updated")
    return EXIT_OK


# ---------------------------------------------------------------------------
# lint
# ---------------------------------------------------------------------------


def evaluate(bd: Bd, map_id: str, cap: int, max_age_days: int, now: dt.datetime | None = None) -> dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    issue = bd.show(map_id)
    errors: list[str] = []
    warnings: list[str] = []
    alarms: list[str] = []

    if MAP_LABEL not in (issue.get("labels") or []):
        errors.append(f"{map_id}: missing {MAP_LABEL} label")
    body = issue.get("description") or ""
    sections = parse_body(body)
    for name in SECTIONS:
        if name not in sections:
            errors.append(f"{map_id}: missing section '## {name}'")
    marker = targets_marker(body)
    if marker is None:
        errors.append(f"{map_id}: no targets marker; Destination has no recorded source")
    elif marker[0] != targets_digest(sections):
        errors.append(f"{map_id}: Destination or Out of scope changed without a cited source "
                      "(use wayfind chart --map ... --source ...)")

    tickets = map_tickets(bd, map_id)
    by_id = {t["id"]: t for t in tickets}
    open_tickets = [t for t in tickets if t.get("status") != "closed"]
    closed = [t for t in tickets if t.get("status") == "closed"]
    invalidated = [t for t in closed if INVALIDATED_LABEL in (t.get("labels") or [])]
    resolved = [t for t in closed if t not in invalidated]
    in_flight = [t for t in open_tickets if t.get("status") == "in_progress" and ticket_type(t) in HITL_TYPES]
    lines = decision_lines(sections)

    for t in tickets:
        labels = type_labels(t)
        if len(labels) != 1:
            errors.append(f"{t['id']}: needs exactly one type label, has {labels or 'none'}")
        if MAP_LABEL in (t.get("labels") or []):
            warnings.append(f"{t['id']}: carries {MAP_LABEL}; only the map should")
    for t in resolved:
        if ticket_type(t) in HITL_TYPES and "source:" not in (t.get("close_reason") or ""):
            errors.append(f"{t['id']}: {ticket_type(t)} ticket closed without the owner's answer as its source")
        if decision_for(lines, t["id"]) is None:
            errors.append(f"{t['id']}: closed but missing from Decisions so far; finish it by rerunning "
                          f"wayfind resolve {t['id']} with the same arguments")
        if ticket_type(t) == "revisit" and not any(f"(superseded by {t['id']})" in ln for ln in lines):
            errors.append(f"{t['id']}: revisit resolved without superseding a decision")
        if SUPERSEDED_LABEL in (t.get("labels") or []) and "(superseded by " not in (decision_for(lines, t["id"]) or ""):
            errors.append(f"{t['id']}: labelled superseded but Decisions so far does not say by what; "
                          "rerun the revisit's wayfind resolve")
    for ln in lines:
        ticket_id = ln.split(" ", 1)[0]
        if ticket_id in by_id and by_id[ticket_id] not in resolved:
            errors.append(f"{ticket_id}: listed in Decisions so far but not resolved")
    if len(in_flight) > 1:
        errors.append(f"{len(in_flight)} HITL tickets in flight ({', '.join(t['id'] for t in in_flight)}); "
                      "run them one at a time")
    if len(open_tickets) > cap:
        warnings.append(f"{len(open_tickets)} open tickets, above the cap of {cap}; return the far ones to fog")

    fog_text = sections.get("Not yet specified", "")
    fog = 0 if is_placeholder(fog_text) else len(bullets(fog_text))
    created = parse_time(issue.get("created_at"))
    closed_times = [ts for ts in (parse_time(t.get("closed_at")) for t in closed) if ts is not None]
    last_closed = max(closed_times, default=None)
    last_activity = last_closed or created
    age_days = (now - created).days if created else None
    idle_days = (now - last_activity).days if last_activity else None

    # Divergence alarms only. Routine progress is never reported.
    if len(invalidated) >= 2 and len(invalidated) > len(resolved):
        alarms.append(f"diverging: {len(invalidated)} tickets invalidated against {len(resolved)} resolved; "
                      "the route keeps changing under the map, so revisit the Destination with the owner")
    if open_tickets and idle_days is not None and idle_days >= max_age_days:
        alarms.append(f"stale: no ticket resolved for {idle_days} days with {len(open_tickets)} open")

    cleared = not open_tickets and fog == 0 and bool(resolved) and not errors
    return {
        "map": map_id,
        "fog": fog,
        "open": len(open_tickets),
        "resolved": len(resolved),
        "invalidated": len(invalidated),
        "invalidated_ratio": round(len(invalidated) / len(resolved), 2) if resolved else None,
        "age_days": age_days,
        "idle_days": idle_days,
        "hitl_in_flight": [t["id"] for t in in_flight],
        "cleared": cleared,
        "errors": errors,
        "warnings": warnings,
        "alarms": alarms,
    }


def cmd_lint(bd: Bd, args) -> int:
    report = evaluate(bd, args.map, args.cap, args.max_age_days)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        ratio = report["invalidated_ratio"]
        print(f"wayfind {report['map']}: fog={report['fog']} open={report['open']} resolved={report['resolved']} "
              f"invalidated={report['invalidated']} ratio={'-' if ratio is None else ratio} "
              f"age={report['age_days']}d idle={report['idle_days']}d")
        for kind in ("errors", "warnings", "alarms"):
            for line in report[kind]:
                print(f"{kind[:-1].upper()}: {line}")
        if report["cleared"]:
            print("cleared: no open tickets and no fog; hand the map to /clavain:strategy")
    if report["errors"]:
        return EXIT_RULE
    if report["alarms"]:
        return EXIT_ALARM
    return EXIT_OK


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wayfind", description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("-C", dest="directory", help="run bd in this directory")
    parser.add_argument("--actor", help="name bd records as the claimant (default: as bd resolves it)")
    sub = parser.add_subparsers(dest="command", required=True)

    chart = sub.add_parser("chart", help="create a map, add tickets, or retarget a map")
    chart.add_argument("--map", help="existing map id; omit to create a new map")
    chart.add_argument("--title", help="short destination title for a new map")
    chart.add_argument("--destination")
    chart.add_argument("--destination-file")
    chart.add_argument("--out-of-scope")
    chart.add_argument("--out-of-scope-file")
    chart.add_argument("--source", help="where the owner set or changed the targets: a card pick, a ruling, a live turn")
    chart.add_argument("--tickets", help="JSON spec: {tickets:[{key,type,title,question,blocked_by}], fog:[], graduate:[], notes}")
    chart.add_argument("--cap", type=int, default=DEFAULT_CAP)
    chart.add_argument("--allow-over-cap", action="store_true")
    chart.add_argument("--dry-run", action="store_true")
    chart.add_argument("--json", action="store_true")

    ready = sub.add_parser("ready", help="list the frontier, or claim one ticket")
    ready.add_argument("map")
    ready.add_argument("--claim", action="store_true",
                       help="claim one frontier ticket, or resume the one you already hold")
    ready.add_argument("--json", action="store_true")

    resolve = sub.add_parser("resolve", help="record an answer, close the ticket, update the map")
    resolve.add_argument("ticket")
    resolve.add_argument("--answer")
    resolve.add_argument("--answer-file")
    resolve.add_argument("--summary", help="one-line entry for Decisions so far")
    resolve.add_argument("--source", help="the owner's answer: a card pick, a ruling, a live turn (required for HITL)")
    resolve.add_argument("--invalidated", action="store_true", help="the question no longer applies")
    resolve.add_argument("--supersedes", help="for a revisit ticket (required): the decision it replaces")

    lint = sub.add_parser("lint", help="check the map's rules and convergence")
    lint.add_argument("map")
    lint.add_argument("--cap", type=int, default=DEFAULT_CAP)
    lint.add_argument("--max-age-days", type=int, default=DEFAULT_MAX_AGE_DAYS)
    lint.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    bd = Bd(directory=args.directory, actor=args.actor)
    handlers = {"chart": cmd_chart, "ready": cmd_ready, "resolve": cmd_resolve, "lint": cmd_lint}
    try:
        return handlers[args.command](bd, args)
    except WayfindError as exc:
        print(f"wayfind: {exc}", file=sys.stderr)
        return exc.exit_code
    except (OSError, json.JSONDecodeError) as exc:
        print(f"wayfind: {exc}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
