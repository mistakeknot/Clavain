#!/usr/bin/env python3
"""Assemble a deterministic review packet from a fixed INPUT.json contract.

WHY THIS EXISTS

mk-42j9.34: ad-hoc, hand-assembled review inputs vary in size and shape
between callers, which makes cost and finding-rate comparisons meaningless
and lets evidence gaps slip through unnoticed (a plan reviewed with no
tests attached looks the same as one where tests genuinely weren't run).
This builder replaces hand-assembly with one deterministic path: same
INPUT.json plus the same referenced sources always produces the same
packet bytes, missing required evidence always fails assembly instead of
silently omitting a section, and `UNRUN` is rendered as visible evidence of
missing verification rather than mapped to a passing test.

This script is Step 1 of the plan (docs/plans/plan-clavain-42j9-34.md):
the deterministic interface and the fixed section contract. Step 2 adds
transcript-input rejection and a stricter, allowlisted producer-receipt
projection sourced from `ic route`. Step 3 adds bounded excerpt context and
immutable packet reuse under `.clavain/reviews/packets/`. This script never
runs tests, calls a model, or queries a live tracker/session log — every
input is a file already on disk.

USAGE

    build-review-packet.py --input INPUT.json --output-dir DIR
    build-review-packet.py --verify PACKET.md

Exit codes: 0 success; 2 invalid/incomplete input; 1 I/O or tool failure
(e.g. `git` missing, unreadable file that passed the initial checks).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1

REQUIRED_KEYS = {"schema_version", "kind", "bead_ids"}
KNOWN_KEYS = {
    "schema_version",
    "kind",
    "bead_ids",
    "beads_file",
    "criteria_files",
    "producer_receipt",
    "plan_file",
    "changes",
    "excerpts",
    "excerpts_not_applicable",
    "tests",
    "tests_not_run",
    "prior_findings",
    "asks",
    "previous_packet",
    "max_bytes",
}

SECTION_ORDER = [
    "Review contract",
    "Acceptance criteria",
    "Producer receipt",
    "Scope",
    "Diff or plan",
    "Touched-file excerpts",
    "Test output",
    "Prior-review disposition",
    "Focused review asks",
    "Attached",
    "Requested output",
]

PREAMBLE_PATH = Path(__file__).resolve().parent / "review-packet-preamble.md"

DEFAULT_MAX_BYTES = 49152


class InputError(ValueError):
    """Invalid or incomplete INPUT.json -> exit 2."""


class ToolError(RuntimeError):
    """I/O or subprocess failure on an otherwise-valid input -> exit 1."""


# ---------------------------------------------------------------------------
# Loading and validation
# ---------------------------------------------------------------------------


def load_input(path: str) -> dict[str, Any]:
    """Load INPUT.json and resolve every relative path against its directory.

    Returns the raw spec dict with an added `_base_dir` (Path) key used by
    every downstream resolver. Raises InputError for anything that isn't
    readable, parseable JSON.
    """
    input_path = Path(path)
    if not input_path.is_file():
        raise InputError(f"input file not found: {path}")
    try:
        text = input_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise InputError(f"cannot read input file {path}: {exc}") from exc
    try:
        spec = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InputError(f"input file is not valid JSON: {exc}") from exc
    if not isinstance(spec, dict):
        raise InputError("input file must contain a JSON object")
    spec["_base_dir"] = input_path.resolve().parent
    return spec


def _resolve(base_dir: Path, rel: str) -> Path:
    p = Path(rel)
    return p if p.is_absolute() else (base_dir / p)


def validate_input(spec: dict[str, Any]) -> None:
    """Raise InputError for any schema, contract, or evidence violation."""
    base_dir: Path = spec["_base_dir"]
    keys = set(spec.keys()) - {"_base_dir"}

    unknown = keys - KNOWN_KEYS
    if unknown:
        raise InputError(f"unknown input keys: {sorted(unknown)}")
    missing = REQUIRED_KEYS - keys
    if missing:
        raise InputError(f"missing required keys: {sorted(missing)}")

    if spec.get("schema_version") != SCHEMA_VERSION:
        raise InputError(
            f"unsupported schema_version {spec.get('schema_version')!r}; "
            f"only {SCHEMA_VERSION} is known"
        )

    kind = spec.get("kind")
    if kind not in ("plan", "diff"):
        raise InputError(f"kind must be 'plan' or 'diff', got {kind!r}")

    bead_ids = spec.get("bead_ids")
    if not isinstance(bead_ids, list) or not bead_ids:
        raise InputError("bead_ids must be a nonempty array")
    if any(not isinstance(b, str) or not b for b in bead_ids):
        raise InputError("bead_ids entries must be nonempty strings")
    if len(set(bead_ids)) != len(bead_ids):
        raise InputError("bead_ids contains duplicates")

    has_beads_file = bool(spec.get("beads_file"))
    has_criteria_files = bool(spec.get("criteria_files"))
    if not has_beads_file and not has_criteria_files:
        raise InputError(
            "at least one of beads_file or criteria_files is required to "
            "supply acceptance criteria"
        )

    if kind == "plan":
        if not spec.get("plan_file"):
            raise InputError("plan_file is required when kind is 'plan'")
        has_excerpts = bool(spec.get("excerpts"))
        has_na = bool(spec.get("excerpts_not_applicable"))
        if has_excerpts == has_na:
            raise InputError(
                "exactly one of excerpts or excerpts_not_applicable is "
                "required for kind:plan"
            )
    else:  # diff
        changes = spec.get("changes")
        if not isinstance(changes, list) or not changes:
            raise InputError("changes must be a nonempty array when kind is 'diff'")

    changes = spec.get("changes")
    if changes is not None:
        if not isinstance(changes, list):
            raise InputError("changes must be an array")
        for entry in changes:
            if not isinstance(entry, dict) or not all(
                entry.get(k) for k in ("repo", "base", "head")
            ):
                raise InputError(
                    "each changes entry needs nonempty repo, base, and head"
                )

    tests = spec.get("tests")
    tests_not_run = spec.get("tests_not_run")
    if bool(tests) and bool(tests_not_run):
        raise InputError("tests and tests_not_run are mutually exclusive")
    if not tests and not tests_not_run:
        raise InputError("one of tests or tests_not_run is required")
    if tests is not None:
        if not isinstance(tests, list):
            raise InputError("tests must be an array")
        for entry in tests:
            if not isinstance(entry, dict) or not all(
                k in entry for k in ("label", "command", "exit_code", "scope", "path")
            ):
                raise InputError(
                    "each tests entry needs label, command, exit_code, scope, path"
                )

    max_bytes = spec.get("max_bytes", DEFAULT_MAX_BYTES)
    if not isinstance(max_bytes, int) or max_bytes <= 0:
        raise InputError("max_bytes must be a positive integer")

    if not spec.get("producer_receipt"):
        raise InputError("producer_receipt is required")
    receipt_path = _resolve(base_dir, spec["producer_receipt"])
    if not receipt_path.is_file():
        raise InputError(f"producer_receipt not found: {receipt_path}")

    _load_and_validate_beads(spec)
    _load_producer_receipt_for_spec(spec)  # validated for side effect (raises InputError)


def _load_and_validate_beads(spec: dict[str, Any]) -> list[dict[str, Any]]:
    base_dir: Path = spec["_base_dir"]
    bead_ids = spec["bead_ids"]
    beads_by_id: dict[str, dict[str, Any]] = {}

    if spec.get("beads_file"):
        beads_path = _resolve(base_dir, spec["beads_file"])
        if not beads_path.is_file():
            raise InputError(f"beads_file not found: {beads_path}")
        try:
            raw = json.loads(beads_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise InputError(f"beads_file is not valid JSON: {exc}") from exc
        if not isinstance(raw, list):
            raise InputError("beads_file must contain a JSON array")
        for entry in raw:
            bid = entry.get("id") if isinstance(entry, dict) else None
            if bid in bead_ids:
                beads_by_id[bid] = {
                    "id": bid,
                    "title": entry.get("title", ""),
                    "acceptance_criteria": entry.get("acceptance_criteria", ""),
                }

    for entry in spec.get("criteria_files") or []:
        bid = entry.get("bead_id")
        crit_path = _resolve(base_dir, entry.get("path", ""))
        if not crit_path.is_file():
            raise InputError(f"criteria_files path not found: {crit_path}")
        if bid in beads_by_id and beads_by_id[bid].get("acceptance_criteria"):
            raise InputError(
                f"bead {bid} has criteria from both beads_file and "
                "criteria_files; exactly one source per bead is required"
            )
        seal_path = crit_path.with_suffix(crit_path.suffix + ".seal")
        if seal_path.is_file():
            try:
                subprocess.run(
                    ["clavain-cli", "verify-seal", str(crit_path)],
                    check=True,
                    capture_output=True,
                )
            except (OSError, subprocess.CalledProcessError) as exc:
                raise InputError(
                    f"criteria seal verification failed for {crit_path}: {exc}"
                ) from exc
        crit_text = crit_path.read_text(encoding="utf-8")
        reject_transcript_input(str(crit_path), crit_text)
        beads_by_id[bid] = {
            "id": bid,
            "title": beads_by_id.get(bid, {}).get("title", ""),
            "acceptance_criteria": crit_text,
        }

    missing = [b for b in bead_ids if b not in beads_by_id]
    if missing:
        raise InputError(f"no criteria source found for bead_ids: {missing}")
    empty = [
        b for b in bead_ids if not (beads_by_id[b].get("acceptance_criteria") or "").strip()
    ]
    if empty:
        raise InputError(f"acceptance_criteria is empty for bead_ids: {empty}")

    return [beads_by_id[b] for b in bead_ids]


def load_producer_receipt(path: str) -> dict[str, Any]:
    """Load and independently re-verify one completed native dispatch receipt.

    The file at `path` is expected to be the shape `ic --json route list
    --dispatch=<id>`'s `context_json` produces for one attempt (see
    scripts/collect-zaka.sh, which writes this exact shape). Loading it is
    not admission by itself: this function re-queries `ic route list` for
    the declared `dispatch_id`, requires an explicit `attempt_id` match
    (never the first/latest record), and requires the matched record to
    agree with the supplied file. It also cross-checks the executed model
    against `ic route identity` so a caller cannot claim an identity the
    resolver would not recognize. This is the review's producer -- the
    model that actually ran -- never a nested `producer_model` describing
    an earlier reviewed artifact's author, and never the requested profile.
    """
    receipt_path = Path(path)
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise InputError(f"cannot read producer_receipt {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise InputError(f"producer_receipt is not valid JSON: {exc}") from exc
    if not isinstance(receipt, dict):
        raise InputError("producer_receipt must be a JSON object")

    if receipt.get("state") != "completed" or receipt.get("terminal") is not True:
        raise InputError("producer_receipt is not a completed, terminal dispatch result")
    result = receipt.get("result")
    if not isinstance(result, dict) or result.get("exit_code") != 0:
        raise InputError("producer_receipt result.exit_code must be 0")

    dispatch_id = receipt.get("dispatch_id")
    attempt_id = receipt.get("attempt_id")
    if not dispatch_id or not attempt_id:
        raise InputError("producer_receipt is missing dispatch_id or attempt_id")

    route = receipt.get("resolved_route") or {}
    profile = receipt.get("resolved_profile") or {}
    inner_profile = profile.get("profile") or {}
    execution = receipt.get("execution") or {}
    if not route.get("policy_hash"):
        raise InputError("producer_receipt is missing resolved_route.policy_hash")
    if not inner_profile.get("backend") or not inner_profile.get("model"):
        raise InputError("producer_receipt is missing resolved_profile.profile.{backend,model}")
    if not execution.get("backend") or not execution.get("model"):
        raise InputError("producer_receipt is missing execution.{backend,model}")

    # Re-derive the authoritative record from `ic route list` -- never trust
    # a caller-supplied hash of its own claim. Selecting by attempt_id (not
    # "first" or "last") is what makes this an explicit selection rather
    # than an arbitrary one.
    try:
        proc = subprocess.run(
            ["ic", "--json", "route", "list", f"--dispatch={dispatch_id}", "--limit=10000"],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise ToolError("ic executable not found") from exc
    except subprocess.CalledProcessError as exc:
        raise ToolError(f"ic route list failed: {exc.stderr.strip()}") from exc
    try:
        records = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ToolError(f"ic route list did not return valid JSON: {exc}") from exc

    matches = []
    for record in records or []:
        try:
            ctx = json.loads(record["context_json"])
        except (KeyError, TypeError, json.JSONDecodeError):
            continue
        if ctx.get("terminal") is True and ctx.get("attempt_id") == attempt_id:
            matches.append(ctx)
    if not matches:
        raise InputError(
            f"no terminal ic route record matches dispatch_id={dispatch_id} "
            f"attempt_id={attempt_id}"
        )
    if len(matches) > 1:
        raise InputError(
            f"ambiguous ic route record: {len(matches)} terminal matches for "
            f"dispatch_id={dispatch_id} attempt_id={attempt_id}"
        )
    authoritative = matches[0]
    auth_route = authoritative.get("resolved_route") or {}
    auth_profile = authoritative.get("resolved_profile") or {}
    auth_inner_profile = auth_profile.get("profile") or {}
    auth_execution = authoritative.get("execution") or {}
    # Cross-check every claim this packet will actually render, not only the
    # fields most convenient to check -- every field named here appears in
    # _render_producer_receipt(), so a caller who forged any one of them
    # (e.g. resolved_profile.profile.model_identity, execution.backend,
    # resolved_route.classification_reasons) could otherwise misattribute
    # the packet without the checked fields ever disagreeing.
    if (
        authoritative.get("state") != receipt.get("state")
        or authoritative.get("result", {}).get("exit_code") != result.get("exit_code")
        or auth_route.get("policy_hash") != route.get("policy_hash")
        or auth_route.get("classification_reasons") != route.get("classification_reasons")
        or auth_route.get("review_requirement") != route.get("review_requirement")
        or auth_route.get("policy_profile") != route.get("policy_profile")
        or auth_execution.get("model") != execution.get("model")
        or auth_execution.get("backend") != execution.get("backend")
        or auth_execution.get("reasoning_effort") != execution.get("reasoning_effort")
        or authoritative.get("bead_id") != receipt.get("bead_id")
        or authoritative.get("checkout") != receipt.get("checkout")
        or auth_profile.get("profile_ref") != profile.get("profile_ref")
        or auth_inner_profile.get("backend") != inner_profile.get("backend")
        or auth_inner_profile.get("model") != inner_profile.get("model")
        or auth_inner_profile.get("model_identity") != inner_profile.get("model_identity")
        or auth_inner_profile.get("reasoning_effort") != inner_profile.get("reasoning_effort")
    ):
        raise InputError(
            "producer_receipt disagrees with the authoritative ic route record "
            f"for dispatch_id={dispatch_id} attempt_id={attempt_id}"
        )

    # Canonical identity check: never duplicate alias normalization here.
    try:
        proc = subprocess.run(
            ["ic", "--json", "route", "identity", f"--model={execution['model']}"],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise ToolError("ic executable not found") from exc
    except subprocess.CalledProcessError as exc:
        raise ToolError(f"ic route identity failed: {exc.stderr.strip()}") from exc
    try:
        identity = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ToolError(f"ic route identity did not return valid JSON: {exc}") from exc
    canonical = identity.get("canonical_identity")
    declared = inner_profile.get("model_identity")
    if not canonical or (declared and declared != canonical):
        raise InputError(
            f"producer identity disagreement: declared model_identity={declared!r}, "
            f"ic route identity resolved {canonical!r}"
        )

    return receipt


def _load_producer_receipt_for_spec(spec: dict[str, Any]) -> dict[str, Any]:
    base_dir: Path = spec["_base_dir"]
    receipt_path = _resolve(base_dir, spec["producer_receipt"])
    if not receipt_path.is_file():
        raise InputError(f"producer_receipt not found: {receipt_path}")
    return load_producer_receipt(str(receipt_path))


# ---------------------------------------------------------------------------
# Transcript-input rejection (Step 2)
# ---------------------------------------------------------------------------

_AUTHOR_SESSION_DIR_NAMES = {
    (".claude", "projects"),
    (".codex", "sessions"),
}

_ANCHORED_MARKER_PAIRS = [
    (r"(?m)^\s*(Human|User)\s*:\s", r"(?m)^\s*Assistant\s*:\s"),
    (r"(?m)^\s*#{1,6}\s*(Human|User)\b", r"(?m)^\s*#{1,6}\s*Assistant\b"),
    (r"(?m)^\s*\*\*(Human|User)\s*:?\*\*", r"(?m)^\s*\*\*Assistant\s*:?\*\*"),
    (r"<\|im_start\|>\s*(user|human)", r"<\|im_start\|>\s*assistant"),
]

_MESSAGE_ROLE_VALUES = {"user", "assistant", "system", "human"}
_CODEX_ITEM_TYPES = {"message", "reasoning"}


def _json_object_looks_like_message(obj: Any) -> bool:
    return (
        isinstance(obj, dict)
        and isinstance(obj.get("role"), str)
        and obj.get("role").lower() in _MESSAGE_ROLE_VALUES
        and "content" in obj
    )


def _line_looks_like_session_event(obj: dict[str, Any]) -> bool:
    # Claude session JSONL: {"type": "user"|"assistant", "message": {...}}
    if obj.get("type") in ("user", "assistant") and isinstance(obj.get("message"), dict):
        return True
    # Codex response_item JSONL: {"type": "response_item", "item": {"type": "message"|"reasoning", ...}}
    if obj.get("type") == "response_item" and isinstance(obj.get("item"), dict):
        if obj["item"].get("type") in _CODEX_ITEM_TYPES:
            return True
    # Raw provider event/usage log, regardless of filename.
    if "total_cost_usd" in obj or "event_log" in obj:
        return True
    return False


def _detect_transcript_rule(content: str) -> str | None:
    stripped = content.strip()
    if not stripped:
        return None

    # Whole-file JSON: messages-array export.
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, list) and parsed and all(
        _json_object_looks_like_message(item) for item in parsed
    ):
        return "messages-array export"

    # JSONL: Claude/Codex session events or raw provider events.
    lines = [ln for ln in stripped.splitlines() if ln.strip()]
    if lines:
        parsed_lines = []
        for ln in lines:
            try:
                parsed_lines.append(json.loads(ln))
            except json.JSONDecodeError:
                parsed_lines = None
                break
        if parsed_lines and any(
            isinstance(obj, dict) and _line_looks_like_session_event(obj)
            for obj in parsed_lines
        ):
            return "session/provider event JSONL"

    # Anchored, paired conversation markers (plain text or Markdown).
    for human_pat, assistant_pat in _ANCHORED_MARKER_PAIRS:
        if re.search(human_pat, content) and re.search(assistant_pat, content):
            return "anchored conversation markers"

    return None


def reject_transcript_input(path: str, content: str) -> None:
    """Raise InputError if `content` (read from `path`) is transcript-shaped.

    Reject rather than strip: stripping can turn failing evidence into
    apparent success. Diagnostics name the source and the matched rule
    without echoing the rejected text. This cannot prove arbitrary unmarked
    prose was never copied from a conversation -- it only catches the
    realistic accident of attaching a provider JSONL, a session export, or
    an anchored conversation fixture as if it were ordinary evidence.
    """
    p = Path(path)
    try:
        resolved = p.resolve()
    except OSError:
        resolved = p
    parts = resolved.parts
    for i in range(len(parts) - 1):
        if (parts[i], parts[i + 1]) in _AUTHOR_SESSION_DIR_NAMES:
            raise InputError(
                f"{path}: rejected as input from a known author session directory"
            )

    rule = _detect_transcript_rule(content)
    if rule:
        raise InputError(f"{path}: rejected as transcript-shaped input ({rule})")


# ---------------------------------------------------------------------------
# Evidence collection
# ---------------------------------------------------------------------------


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _verify_refs(repo: str, base: str, head: str) -> None:
    for ref in (base, head):
        try:
            subprocess.run(
                ["git", "-C", repo, "rev-parse", "--verify", f"{ref}^{{commit}}"],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            raise InputError(
                f"ref {ref!r} does not resolve to a commit in {repo}: "
                f"{exc.stderr.strip()}"
            ) from exc


def _reject_binary_or_submodule(repo: str, base: str, head: str) -> None:
    """Fail explicitly on any binary or submodule (gitlink) change.

    A text-only packet must never be passed off as complete evidence for
    these -- v1 has no evidence contract for them at all.
    """
    try:
        raw = subprocess.run(
            ["git", "-C", repo, "diff", "--raw", "-z", "--no-renames", base, head, "--"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except FileNotFoundError as exc:
        raise ToolError("git executable not found") from exc
    except subprocess.CalledProcessError as exc:
        raise ToolError(f"git diff --raw failed for {repo}: {exc.stderr.strip()}") from exc

    fields = raw.split("\0")
    i = 0
    while i < len(fields) and fields[i]:
        meta = fields[i]
        # ":<old-mode> <new-mode> <old-sha> <new-sha> <status>"
        parts = meta.split(" ")
        old_mode, new_mode = parts[0].lstrip(":"), parts[1]
        path = fields[i + 1]
        i += 2
        if old_mode == "160000" or new_mode == "160000":
            raise InputError(
                f"{path}: submodule (gitlink) changes are not a supported "
                "evidence type; require an explicit separately reviewed "
                "evidence contract before extending v1 to them"
            )

    try:
        numstat = subprocess.run(
            ["git", "-C", repo, "diff", "--numstat", "-z", "--no-renames", base, head, "--"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except FileNotFoundError as exc:
        raise ToolError("git executable not found") from exc
    except subprocess.CalledProcessError as exc:
        raise ToolError(f"git diff --numstat failed for {repo}: {exc.stderr.strip()}") from exc
    for line in numstat.split("\0"):
        if not line:
            continue
        cols = line.split("\t", 2)
        if len(cols) == 3 and cols[0] == "-" and cols[1] == "-":
            raise InputError(
                f"{cols[2]}: binary changes are not a supported evidence "
                "type; require an explicit separately reviewed evidence "
                "contract before extending v1 to them"
            )


def _git_diff(repo: str, base: str, head: str) -> str:
    _verify_refs(repo, base, head)
    _reject_binary_or_submodule(repo, base, head)
    try:
        proc = subprocess.run(
            [
                "git", "-C", repo, "diff", "--no-ext-diff", "--no-textconv",
                "--no-color", "--no-renames", "--unified=0", base, head, "--",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise ToolError("git executable not found") from exc
    except subprocess.CalledProcessError as exc:
        raise ToolError(f"git diff failed for {repo}: {exc.stderr.strip()}") from exc
    return proc.stdout


_HUNK_HEADER_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_EXCERPT_CONTEXT_LINES = 8
_MAX_PLAN_EXCERPT_LINES = 80


def _parse_diff_paths(repo: str, base: str, head: str) -> list[tuple[str, str, str]]:
    """Return (status, old_path, new_path) for every entry in the scope."""
    try:
        raw = subprocess.run(
            ["git", "-C", repo, "diff", "--raw", "-z", "--no-renames", base, head, "--"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except FileNotFoundError as exc:
        raise ToolError("git executable not found") from exc
    except subprocess.CalledProcessError as exc:
        raise ToolError(f"git diff --raw failed for {repo}: {exc.stderr.strip()}") from exc

    fields = raw.split("\0")
    entries = []
    i = 0
    while i < len(fields) and fields[i]:
        meta = fields[i]
        status = meta.split(" ")[-1]
        path = fields[i + 1]
        i += 2
        if status[0] in ("R", "C"):
            new_path = fields[i]
            i += 1
            entries.append((status, path, new_path))
        elif status[0] == "A":
            entries.append((status, "", path))
        elif status[0] == "D":
            entries.append((status, path, ""))
        else:
            entries.append((status, path, path))
    return entries


def _show_file_lines(repo: str, ref: str, path: str) -> list[str] | None:
    try:
        content = subprocess.run(
            ["git", "-C", repo, "show", f"{ref}:{path}"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    return content.splitlines()


def collect_excerpts_for_diff_scope(repo: str, base: str, head: str) -> str:
    """Bind bounded, 8-line context excerpts around every zero-context hunk.

    A wholly new/deleted file is fully present in the raw diff already; this
    labels that fact rather than repeating its contents. Ranges are merged
    per (side, path) and sorted so the same scope always renders identically.
    """
    entries = _parse_diff_paths(repo, base, head)
    parts = []
    for status, old_path, new_path in entries:
        if status[0] == "A":
            parts.append(f"`{new_path}` @ `{head}`: new file, fully present in the diff above.")
            continue
        if status[0] == "D":
            parts.append(f"`{old_path}` @ `{base}`: deleted file, fully present in the diff above.")
            continue

        path = new_path or old_path
        try:
            file_diff = subprocess.run(
                [
                    "git", "-C", repo, "diff", "--no-ext-diff", "--no-textconv",
                    "--no-color", "--no-renames", "--unified=0", base, head, "--", path,
                ],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
        except FileNotFoundError as exc:
            raise ToolError("git executable not found") from exc
        except subprocess.CalledProcessError as exc:
            raise ToolError(f"git diff failed for {repo}:{path}: {exc.stderr.strip()}") from exc

        head_lines = _show_file_lines(repo, head, path)
        ranges: list[tuple[int, int]] = []
        for line in file_diff.splitlines():
            m = _HUNK_HEADER_RE.match(line)
            if not m:
                continue
            new_start = int(m.group(3))
            new_count = int(m.group(4) or "1")
            lo = max(1, new_start - _EXCERPT_CONTEXT_LINES)
            hi = new_start + max(new_count, 1) - 1 + _EXCERPT_CONTEXT_LINES
            ranges.append((lo, hi))
        if not ranges or head_lines is None:
            continue
        ranges.sort()
        merged: list[list[int]] = []
        for lo, hi in ranges:
            if merged and lo <= merged[-1][1] + 1:
                merged[-1][1] = max(merged[-1][1], hi)
            else:
                merged.append([lo, hi])
        for lo, hi in merged:
            hi = min(hi, len(head_lines))
            snippet = "\n".join(head_lines[lo - 1 : hi])
            parts.append(
                f"`{path}` lines {lo}-{hi} @ `{head}`:\n\n```\n{snippet}\n```"
            )
    return "\n\n".join(parts) if parts else "None supplied"


def collect_changes(spec: dict[str, Any]) -> list[dict[str, str]]:
    result = []
    for entry in spec.get("changes") or []:
        diff_text = _git_diff(entry["repo"], entry["base"], entry["head"])
        result.append(
            {
                "repo": entry["repo"],
                "base": entry["base"],
                "head": entry["head"],
                "diff": diff_text,
            }
        )
    return result


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _render_review_contract() -> str:
    return PREAMBLE_PATH.read_text(encoding="utf-8").strip()


def _render_acceptance_criteria(beads: list[dict[str, Any]]) -> str:
    parts = []
    for bead in beads:
        title = bead.get("title") or bead["id"]
        parts.append(f"### {bead['id']}: {title}\n\n{bead['acceptance_criteria'].strip()}")
    return "\n\n".join(parts)


def _render_producer_receipt(receipt: dict[str, Any]) -> str:
    profile = receipt.get("resolved_profile", {}) or {}
    execution = receipt.get("execution", {}) or {}
    route = receipt.get("resolved_route", {}) or {}
    lines = [
        f"- bead_id: `{receipt.get('bead_id', '')}`",
        f"- checkout: `{receipt.get('checkout', '')}`",
        f"- state: `{receipt.get('state', '')}` (terminal: {receipt.get('terminal', '')})",
        f"- resolved_profile.profile_ref: `{profile.get('profile_ref', '')}`",
    ]
    inner = profile.get("profile", {}) or {}
    if inner:
        lines.append(
            "- resolved_profile.profile: backend=`{backend}` model=`{model}` "
            "model_identity=`{model_identity}` reasoning_effort=`{reasoning_effort}`".format(
                backend=inner.get("backend", ""),
                model=inner.get("model", ""),
                model_identity=inner.get("model_identity", ""),
                reasoning_effort=inner.get("reasoning_effort", ""),
            )
        )
    if execution:
        lines.append(
            "- execution: backend=`{backend}` model=`{model}` "
            "reasoning_effort=`{reasoning_effort}`".format(
                backend=execution.get("backend", ""),
                model=execution.get("model", ""),
                reasoning_effort=execution.get("reasoning_effort", ""),
            )
        )
    if route:
        lines.append(
            "- resolved_route: policy_hash=`{policy_hash}` "
            "classification_reasons={reasons} review_requirement=`{req}` "
            "policy_profile=`{profile}`".format(
                policy_hash=route.get("policy_hash", ""),
                reasons=json.dumps(route.get("classification_reasons", [])),
                req=route.get("review_requirement", ""),
                profile=route.get("policy_profile", ""),
            )
        )
    return "\n".join(lines)


def _render_scope(spec: dict[str, Any], beads: list[dict[str, Any]]) -> str:
    lines = [f"- kind: `{spec['kind']}`", f"- bead_ids: {json.dumps(spec['bead_ids'])}"]
    for entry in spec.get("changes") or []:
        lines.append(f"- repo `{entry['repo']}`: `{entry['base']}` -> `{entry['head']}`")
    return "\n".join(lines)


def _render_diff_or_plan(spec: dict[str, Any], changes: list[dict[str, str]]) -> str:
    parts = []
    if spec["kind"] == "plan":
        plan_path = _resolve(spec["_base_dir"], spec["plan_file"])
        plan_text = plan_path.read_text(encoding="utf-8")
        reject_transcript_input(str(plan_path), plan_text)
        parts.append(f"#### Plan: `{spec['plan_file']}`\n\n```markdown\n{plan_text}\n```")
    for change in changes:
        parts.append(
            f"#### Diff: `{change['repo']}` {change['base']} -> {change['head']}\n\n"
            f"```diff\n{change['diff']}```"
        )
    return "\n\n".join(parts) if parts else "None supplied"


def _render_touched_excerpts(spec: dict[str, Any], changes: list[dict[str, str]]) -> str:
    if spec["kind"] == "plan":
        if spec.get("excerpts_not_applicable"):
            return f"Not applicable: {spec['excerpts_not_applicable']}"
        parts = []
        for rng in spec.get("excerpts") or []:
            repo, ref, path = rng["repo"], rng["ref"], rng["path"]
            try:
                content = subprocess.run(
                    ["git", "-C", repo, "show", f"{ref}:{path}"],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout
            except (OSError, subprocess.CalledProcessError) as exc:
                raise InputError(
                    f"excerpt {repo}:{ref}:{path} could not be read: {exc}"
                ) from exc
            reject_transcript_input(f"{repo}:{ref}:{path}", content)
            lines = content.splitlines()
            start, end = rng["start_line"], rng["end_line"]
            if end - start + 1 > _MAX_PLAN_EXCERPT_LINES:
                raise InputError(
                    f"excerpt {repo}:{path} lines {start}-{end} exceeds the "
                    f"{_MAX_PLAN_EXCERPT_LINES}-line limit for plan excerpt ranges"
                )
            if start < 1 or end < start or end > len(lines):
                raise InputError(
                    f"excerpt {repo}:{path} lines {start}-{end} is out of range "
                    f"for {ref} ({len(lines)} lines)"
                )
            snippet = "\n".join(lines[start - 1 : end])
            parts.append(
                f"`{repo}:{path}` lines {start}-{end} @ `{ref}`:\n\n```\n{snippet}\n```"
            )
        return "\n\n".join(parts)
    # kind: diff -- bounded, merged, 8-line-context excerpts per zero-context
    # hunk (whole new/deleted files are labeled, not repeated: they're
    # already fully present in the diff above).
    if not changes:
        return "None supplied"
    parts = [
        collect_excerpts_for_diff_scope(c["repo"], c["base"], c["head"]) for c in changes
    ]
    return "\n\n".join(p for p in parts if p and p != "None supplied") or "None supplied"


def _render_test_output(spec: dict[str, Any]) -> str:
    if spec.get("tests_not_run"):
        return f"UNRUN: {spec['tests_not_run']}"
    parts = []
    for t in spec.get("tests") or []:
        output_text = "None supplied"
        if t.get("path") and t["path"] != "-":
            out_path = _resolve(spec["_base_dir"], t["path"])
            if not out_path.is_file():
                # A test entry that names an output file is asserting that
                # file is the evidence for its exit_code -- silently
                # rendering "None supplied" would let required test evidence
                # go missing without assembly ever failing.
                raise InputError(
                    f"test {t['label']!r} names output path {out_path} but it "
                    "does not exist"
                )
            output_text = out_path.read_text(encoding="utf-8")
            reject_transcript_input(str(out_path), output_text)
        parts.append(
            f"- **{t['label']}** (`{t['command']}`, scope `{t['scope']}`, "
            f"exit_code {t['exit_code']}):\n\n```\n{output_text}\n```"
        )
    return "\n\n".join(parts) if parts else "None supplied"


def _render_prior_findings(
    spec: dict[str, Any], previous_manifest: dict[str, Any] | None = None
) -> str:
    findings = spec.get("prior_findings")
    lines: list[str] = []
    if previous_manifest is not None:
        lines.append(
            "**This is a delta re-review**, not a full review: it binds to and "
            f"continues parent packet `{previous_manifest['packet_id']}`. Every "
            "scope and finding disposition already reviewed there carries "
            "forward unchanged; only the fix delta since that head is new "
            "evidence here."
        )
        lines.append("")
    if not findings:
        lines.append("None supplied")
        return "\n".join(lines)
    lines.append("| id | severity | disposition | evidence |")
    lines.append("|---|---|---|---|")
    for f in findings:
        lines.append(
            f"| {f.get('id','')} | {f.get('severity','')} | "
            f"{f.get('disposition','')} | {f.get('evidence','')} |"
        )
    return "\n".join(lines)


def _render_asks(spec: dict[str, Any]) -> str:
    asks = spec.get("asks")
    if not asks:
        return "None supplied"
    return "\n".join(f"- {a}" for a in asks)


def _render_attached(spec: dict[str, Any], sources: list[dict[str, str]]) -> str:
    lines = [f"- {s['role']}: `{s['path']}` (sha256 `{s['sha256']}`)" for s in sources]
    return "\n".join(lines) if lines else "None supplied"


def _render_requested_output() -> str:
    return (
        "State `VERDICT: PASS`, `VERDICT: FAIL`, or `VERDICT: UNRUN` (only when "
        "required verification could not be run -- UNRUN never means PASS). "
        "List findings with severity, location, and evidence drawn only from "
        "this packet. This deliverable gets one fix round followed by one "
        "delta re-review; do not invent a further round. Preserve any "
        "role-specific conformance table as additional output alongside the "
        "verdict."
    )


# ---------------------------------------------------------------------------
# Packet assembly
# ---------------------------------------------------------------------------


def _collect_sources(spec: dict[str, Any]) -> list[dict[str, str]]:
    base_dir: Path = spec["_base_dir"]
    sources = []
    for role, key in (("plan_file", "plan_file"), ("producer_receipt", "producer_receipt"), ("beads_file", "beads_file")):
        if spec.get(key):
            p = _resolve(base_dir, spec[key])
            sources.append({"role": role, "path": str(p), "sha256": _sha256_file(p)})
    for entry in spec.get("criteria_files") or []:
        p = _resolve(base_dir, entry["path"])
        sources.append(
            {"role": f"criteria_files:{entry['bead_id']}", "path": str(p), "sha256": _sha256_file(p)}
        )
    return sources


def _identity_payload(
    spec: dict[str, Any],
    beads: list[dict[str, Any]],
    changes: list[dict[str, str]],
    previous_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The subset of evidence that determines packet identity.

    Excludes anything about *where* the packet is written (output_dir) or
    *when*/*by whom* it will be reviewed -- those never affect what a
    reviewer is shown, only where the bytes land.

    Includes a content hash for every input whose *bytes*, not just its
    metadata, can change what gets rendered: the preamble text, each test's
    output file, and the producer receipt itself. Test/receipt *metadata*
    (label, command, exit_code, the receipt's parsed fields) is already
    covered by "tests" and by the producer-receipt cross-check in
    load_producer_receipt(), but only a content hash catches a same-metadata,
    different-bytes swap of the underlying evidence file.
    """
    base_dir: Path = spec["_base_dir"]
    test_output_sha256 = {}
    for t in spec.get("tests") or []:
        if t.get("path") and t["path"] != "-":
            out_path = _resolve(base_dir, t["path"])
            if out_path.is_file():
                test_output_sha256[t["label"]] = _sha256_file(out_path)
    return {
        "schema_version": spec["schema_version"],
        "kind": spec["kind"],
        "bead_ids": spec["bead_ids"],
        "beads": beads,
        "changes": changes,
        "tests": spec.get("tests"),
        "test_output_sha256": test_output_sha256,
        "tests_not_run": spec.get("tests_not_run"),
        "prior_findings": spec.get("prior_findings"),
        "asks": spec.get("asks"),
        "excerpts_not_applicable": spec.get("excerpts_not_applicable"),
        "plan_file_sha256": (
            _sha256_file(_resolve(base_dir, spec["plan_file"]))
            if spec.get("plan_file")
            else None
        ),
        "producer_receipt_sha256": (
            _sha256_file(_resolve(base_dir, spec["producer_receipt"]))
            if spec.get("producer_receipt")
            else None
        ),
        "preamble_sha256": _sha256_bytes(PREAMBLE_PATH.read_bytes()),
        "max_bytes": spec.get("max_bytes", DEFAULT_MAX_BYTES),
        "previous_packet_id": (
            previous_manifest["packet_id"] if previous_manifest is not None else None
        ),
    }


def _load_previous_packet_manifest(spec: dict[str, Any]) -> dict[str, Any] | None:
    prev = spec.get("previous_packet")
    if not prev:
        return None
    p = _resolve(spec["_base_dir"], prev)
    if not p.is_file():
        raise InputError(f"previous_packet manifest not found: {p}")
    # A bare, unverified manifest.json is just a JSON file a caller supplied
    # -- it could claim any packet_id/head it likes. Route it through
    # verify_packet() against the packet.md sitting next to it so the parent
    # bundle's own packet_sha256 and source hashes have to check out before
    # its "reviewed head" is trusted for delta binding.
    try:
        manifest = verify_packet(str(p.parent / "packet.md"))
    except ToolError as exc:
        raise InputError(f"previous_packet failed verification: {exc}") from exc
    return manifest


def _bind_delta_to_parent(
    spec: dict[str, Any],
    beads: list[dict[str, Any]],
    changes: list[dict[str, str]],
    previous_manifest: dict[str, Any],
) -> None:
    """A delta re-review's base must equal its parent's reviewed head, and its
    bead scope/acceptance criteria must be unchanged from the parent's.

    This is what makes a delta unable to masquerade as a full review of an
    unrelated or expanded scope: it can only ever continue exactly the scope
    the parent packet already covered. Without the bead/criteria check, a
    caller could keep the same commit range while attaching a new or reworded
    bead -- the rendered disposition text claims "every scope ... already
    reviewed there carries forward unchanged," which is only true if the
    bead scope actually did not change.
    """
    if spec["kind"] != "diff":
        raise InputError("previous_packet is only supported for kind:diff re-review")
    prev_changes = previous_manifest.get("changes") or []
    if len(prev_changes) != len(changes):
        raise InputError(
            "previous_packet scope count does not match this packet's changes"
        )
    for prev, cur in zip(prev_changes, changes):
        if prev.get("repo") != cur["repo"] or prev.get("head") != cur["base"]:
            raise InputError(
                f"delta base for {cur['repo']} must equal previous_packet's "
                f"reviewed head ({prev.get('head')!r}), got base={cur['base']!r}"
            )
    prev_bead_ids = (previous_manifest.get("inputs") or {}).get("bead_ids")
    if prev_bead_ids != spec["bead_ids"]:
        raise InputError(
            "previous_packet bead_ids do not match this packet's bead_ids -- "
            "a changed bead scope requires a fresh full review, not a delta"
        )
    if previous_manifest.get("beads") != beads:
        raise InputError(
            "previous_packet acceptance criteria do not match this packet's "
            "beads -- a changed criterion requires a fresh full review, not "
            "a delta"
        )


def build_packet(spec: dict[str, Any], output_dir: str) -> Path:
    validate_input(spec)
    beads = _load_and_validate_beads(spec)
    receipt = _load_producer_receipt_for_spec(spec)
    changes = collect_changes(spec)
    sources = _collect_sources(spec)
    previous_manifest = _load_previous_packet_manifest(spec)
    if previous_manifest is not None:
        _bind_delta_to_parent(spec, beads, changes, previous_manifest)

    sections = {
        "Review contract": _render_review_contract(),
        "Acceptance criteria": _render_acceptance_criteria(beads),
        "Producer receipt": _render_producer_receipt(receipt),
        "Scope": _render_scope(spec, beads),
        "Diff or plan": _render_diff_or_plan(spec, changes),
        "Touched-file excerpts": _render_touched_excerpts(spec, changes),
        "Test output": _render_test_output(spec),
        "Prior-review disposition": _render_prior_findings(spec, previous_manifest),
        "Focused review asks": _render_asks(spec),
        "Attached": _render_attached(spec, sources),
        "Requested output": _render_requested_output(),
    }

    body = "\n\n".join(f"## {name}\n\n{sections[name]}" for name in SECTION_ORDER)
    packet_bytes = (body.rstrip() + "\n").encode("utf-8")

    max_bytes = spec.get("max_bytes", DEFAULT_MAX_BYTES)
    if len(packet_bytes) > max_bytes:
        # Never truncate to hit a cost target -- print a per-section byte
        # breakdown so the operator can see exactly where to trim duplicated
        # context (or decide to raise max_bytes) without guessing.
        section_sizes = {
            name: len((f"## {name}\n\n{sections[name]}").encode("utf-8"))
            for name in SECTION_ORDER
        }
        breakdown = "\n".join(
            f"  {name}: {size} bytes"
            for name, size in sorted(section_sizes.items(), key=lambda kv: -kv[1])
        )
        raise InputError(
            f"packet is {len(packet_bytes)} bytes, exceeds max_bytes={max_bytes}\n"
            f"per-section byte counts:\n{breakdown}"
        )

    identity = _identity_payload(spec, beads, changes, previous_manifest)
    packet_id = _sha256_bytes(
        json.dumps(identity, sort_keys=True, default=str).encode("utf-8")
    )

    # A delta packet is addressed distinctly from a full review of the same
    # content -- both to avoid colliding with an unrelated full review that
    # happens to hash the same, and so the printed path itself is legible as
    # a delta bound to its parent (never mistakable for an independent full
    # review of the combined scope).
    if previous_manifest is not None:
        dest_dir = Path(output_dir) / f"delta-{previous_manifest['packet_id']}-{packet_id}"
    else:
        dest_dir = Path(output_dir) / packet_id
    dest_packet = dest_dir / "packet.md"
    dest_manifest = dest_dir / "manifest.json"

    if dest_packet.is_file():
        # Idempotent: identical input identity already published, and the
        # existing bundle at this content-addressed path re-verifies clean.
        # A corrupted or tampered bundle sitting at this path must fail
        # loudly instead of being silently rebuilt/overwritten -- that would
        # erase the evidence that tampering happened.
        cached_manifest = verify_packet(str(dest_packet))
        # Defense in depth beyond the identity payload: if the freshly
        # assembled bytes for this call disagree with what's cached at this
        # content-addressed path, the identity payload missed some rendered
        # input (a packet_id collision on different evidence) -- fail loudly
        # rather than silently serving stale evidence under a "clean" cache
        # hit.
        if cached_manifest.get("packet_sha256") != _sha256_bytes(packet_bytes):
            raise ToolError(
                f"packet_id {packet_id} is cached at {dest_packet} with "
                "different rendered bytes than this call just produced -- "
                "the identity payload does not capture everything that "
                "changed"
            )
        return dest_packet

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_packet.write_bytes(packet_bytes)
    profile = (receipt.get("resolved_profile") or {}).get("profile") or {}
    execution = receipt.get("execution") or {}
    manifest = {
        "packet_id": packet_id,
        "packet_sha256": _sha256_bytes(packet_bytes),
        "packet_bytes": len(packet_bytes),
        "sources": sources,
        # "attachments" duplicates "sources" under the plan's field name;
        # verify_packet keeps reading "sources" so existing bundles stay
        # verifiable.
        "attachments": sources,
        "inputs": {
            "schema_version": spec["schema_version"],
            "kind": spec["kind"],
            "bead_ids": spec["bead_ids"],
        },
        # Retained (not just bead_ids) so a delta re-review can detect a
        # reworded/expanded acceptance criterion even when bead_ids is
        # unchanged -- see _bind_delta_to_parent().
        "beads": beads,
        "producer_identity": {
            "profile_ref": (receipt.get("resolved_profile") or {}).get("profile_ref"),
            "backend": profile.get("backend") or execution.get("backend"),
            "model": profile.get("model") or execution.get("model"),
            "model_identity": profile.get("model_identity"),
            "reasoning_effort": profile.get("reasoning_effort") or execution.get("reasoning_effort"),
            "attempt_id": receipt.get("attempt_id"),
        },
        "changes": changes,
        "previous_packet_id": (
            previous_manifest["packet_id"] if previous_manifest is not None else None
        ),
    }
    dest_manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return dest_packet


def verify_packet(path: str) -> dict[str, Any]:
    packet_path = Path(path)
    if not packet_path.is_file():
        raise ToolError(f"packet not found: {path}")
    manifest_path = packet_path.parent / "manifest.json"
    if not manifest_path.is_file():
        raise ToolError(f"manifest not found alongside packet: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ToolError(f"manifest is not valid JSON: {exc}") from exc

    actual_sha = _sha256_file(packet_path)
    if actual_sha != manifest.get("packet_sha256"):
        raise ToolError("packet.md does not match manifest.packet_sha256 (tampered or stale)")

    if "sources" not in manifest:
        raise ToolError(f"manifest is missing the sources field: {manifest_path}")

    for source in manifest["sources"]:
        source_path = Path(source["path"])
        if not source_path.is_file():
            raise ToolError(f"source {source_path} recorded in manifest no longer exists")
        if _sha256_file(source_path) != source["sha256"]:
            raise ToolError(f"source {source_path} no longer matches recorded sha256")

    return manifest


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", help="path to INPUT.json")
    parser.add_argument("--output-dir", help="directory to publish the packet under")
    parser.add_argument("--verify", metavar="PACKET.md", help="verify an existing packet")
    args = parser.parse_args(argv)

    if args.verify:
        if args.input or args.output_dir:
            print("error: --verify cannot be combined with --input/--output-dir", file=sys.stderr)
            return 2
        try:
            verify_packet(args.verify)
        except ToolError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(str(Path(args.verify).resolve()))
        return 0

    if not args.input or not args.output_dir:
        print("error: --input and --output-dir are required (or use --verify)", file=sys.stderr)
        return 2

    try:
        spec = load_input(args.input)
        packet_path = build_packet(spec, args.output_dir)
    except InputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except ToolError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(str(packet_path.resolve()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
