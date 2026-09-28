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
    _load_producer_receipt_dict(spec)  # validated for side effect (raises InputError)


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
        beads_by_id[bid] = {
            "id": bid,
            "title": beads_by_id.get(bid, {}).get("title", ""),
            "acceptance_criteria": crit_path.read_text(encoding="utf-8"),
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


def _load_producer_receipt_dict(spec: dict[str, Any]) -> dict[str, Any]:
    base_dir: Path = spec["_base_dir"]
    receipt_path = _resolve(base_dir, spec["producer_receipt"])
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InputError(f"producer_receipt is not valid JSON: {exc}") from exc
    if not isinstance(receipt, dict):
        raise InputError("producer_receipt must be a JSON object")
    # Full admission (native-dispatch lookup via `ic route list`, allowlisted
    # field projection, canonical identity comparison) is Step 2's
    # load_producer_receipt(). Step 1 only requires a genuinely terminal,
    # successful receipt to exist before it will build anything.
    if receipt.get("state") != "completed" or receipt.get("terminal") is not True:
        raise InputError(
            "producer_receipt is not a completed, terminal dispatch result"
        )
    result = receipt.get("result")
    if not isinstance(result, dict) or result.get("exit_code") != 0:
        raise InputError("producer_receipt result.exit_code must be 0")
    return receipt


# ---------------------------------------------------------------------------
# Evidence collection
# ---------------------------------------------------------------------------


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _git_diff(repo: str, base: str, head: str) -> str:
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
    try:
        proc = subprocess.run(
            [
                "git", "-C", repo, "diff", "--no-ext-diff", "--no-textconv",
                "--no-color", "--no-renames", "--unified=3", base, head, "--",
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
            lines = content.splitlines()
            start, end = rng["start_line"], rng["end_line"]
            snippet = "\n".join(lines[start - 1 : end])
            parts.append(
                f"`{repo}:{path}` lines {start}-{end} @ `{ref}`:\n\n```\n{snippet}\n```"
            )
        return "\n\n".join(parts)
    # kind: diff -- Step 3 binds bounded, merged, 8-line-context excerpts per
    # hunk; Step 1 surfaces the same diffs collected above as a placeholder.
    if not changes:
        return "None supplied"
    return "Derived automatically from the diff above (see Diff or plan)."


def _render_test_output(spec: dict[str, Any]) -> str:
    if spec.get("tests_not_run"):
        return f"UNRUN: {spec['tests_not_run']}"
    parts = []
    for t in spec.get("tests") or []:
        output_text = "None supplied"
        if t.get("path") and t["path"] != "-":
            out_path = _resolve(spec["_base_dir"], t["path"])
            if out_path.is_file():
                output_text = out_path.read_text(encoding="utf-8")
        parts.append(
            f"- **{t['label']}** (`{t['command']}`, scope `{t['scope']}`, "
            f"exit_code {t['exit_code']}):\n\n```\n{output_text}\n```"
        )
    return "\n\n".join(parts) if parts else "None supplied"


def _render_prior_findings(spec: dict[str, Any]) -> str:
    findings = spec.get("prior_findings")
    if not findings:
        return "None supplied"
    lines = ["| id | severity | disposition | evidence |", "|---|---|---|---|"]
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


def _identity_payload(spec: dict[str, Any], beads: list[dict[str, Any]], changes: list[dict[str, str]]) -> dict[str, Any]:
    """The subset of evidence that determines packet identity.

    Excludes anything about *where* the packet is written (output_dir) or
    *when*/*by whom* it will be reviewed -- those never affect what a
    reviewer is shown, only where the bytes land.
    """
    return {
        "schema_version": spec["schema_version"],
        "kind": spec["kind"],
        "bead_ids": spec["bead_ids"],
        "beads": beads,
        "changes": changes,
        "tests": spec.get("tests"),
        "tests_not_run": spec.get("tests_not_run"),
        "prior_findings": spec.get("prior_findings"),
        "asks": spec.get("asks"),
        "excerpts_not_applicable": spec.get("excerpts_not_applicable"),
        "plan_file_sha256": (
            _sha256_file(_resolve(spec["_base_dir"], spec["plan_file"]))
            if spec.get("plan_file")
            else None
        ),
    }


def build_packet(spec: dict[str, Any], output_dir: str) -> Path:
    validate_input(spec)
    beads = _load_and_validate_beads(spec)
    receipt = _load_producer_receipt_dict(spec)
    changes = collect_changes(spec)
    sources = _collect_sources(spec)

    sections = {
        "Review contract": _render_review_contract(),
        "Acceptance criteria": _render_acceptance_criteria(beads),
        "Producer receipt": _render_producer_receipt(receipt),
        "Scope": _render_scope(spec, beads),
        "Diff or plan": _render_diff_or_plan(spec, changes),
        "Touched-file excerpts": _render_touched_excerpts(spec, changes),
        "Test output": _render_test_output(spec),
        "Prior-review disposition": _render_prior_findings(spec),
        "Focused review asks": _render_asks(spec),
        "Attached": _render_attached(spec, sources),
        "Requested output": _render_requested_output(),
    }

    body = "\n\n".join(f"## {name}\n\n{sections[name]}" for name in SECTION_ORDER)
    packet_bytes = (body.rstrip() + "\n").encode("utf-8")

    max_bytes = spec.get("max_bytes", DEFAULT_MAX_BYTES)
    if len(packet_bytes) > max_bytes:
        raise InputError(
            f"packet is {len(packet_bytes)} bytes, exceeds max_bytes={max_bytes}"
        )

    identity = _identity_payload(spec, beads, changes)
    packet_id = _sha256_bytes(
        json.dumps(identity, sort_keys=True, default=str).encode("utf-8")
    )

    dest_dir = Path(output_dir) / packet_id
    dest_packet = dest_dir / "packet.md"
    dest_manifest = dest_dir / "manifest.json"

    if dest_packet.is_file():
        # Idempotent: identical input identity already published. Step 3
        # hardens this against a corrupted existing bundle; Step 1 trusts an
        # existing file at the content-addressed path.
        return dest_packet

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_packet.write_bytes(packet_bytes)
    manifest = {
        "packet_id": packet_id,
        "packet_sha256": _sha256_bytes(packet_bytes),
        "sources": sources,
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

    for source in manifest.get("sources", []):
        source_path = Path(source["path"])
        if source_path.is_file():
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
