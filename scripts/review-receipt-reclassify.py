#!/usr/bin/env python3
"""One-time reclassification notes for cross-lab review receipts (mk-tl0ou.3.4).

Reads receipts under the reviews directory (read-only) and writes a sibling
note per receipt that needs one, under a separate notes directory. A receipt is
never modified, moved or deleted. The notes only say which stored verdicts
should not be trusted at face value:

  approve  -> "approve-unrecognised"  (the old parser stored a non-accepted word)
  null     -> "null-verdict"          (no usable verdict was stored)
  BLOCK    -> "block-unverified"      (the source review text is not stored in
                                       the receipt, so BLOCK cannot be told
                                       apart from an unrecognised word that an
                                       older parser mapped to BLOCK)

PASS and PASS WITH NOTES receipts get no note. Neither does an UNKNOWN receipt
(the writer already records an unrecognised word as UNKNOWN), nor a BLOCK
receipt that carries a "verdict_raw" FAIL or BLOCK word: the writer stored the
word it read, so that BLOCK is verified (mk-0qjva). Idempotent: a note whose content
already matches is left alone. --check writes nothing and prints the counts.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from collections import Counter
from pathlib import Path

STATE = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "clavain"

REASONS = {
    "approve-unrecognised": "Stored verdict 'approve' is not an accepted review verdict word (accepted: PASS, PASS WITH NOTES, FAIL); it must not count as an approval or a block.",
    "null-verdict": "The receipt has no usable verdict value.",
    "block-unverified": "Stored verdict is BLOCK but the receipt holds no review text; an older parser also stored unrecognised verdict words as BLOCK, so a genuine FAIL cannot be confirmed from the receipt alone.",
}


# The stored word of a BLOCK the writer read itself: FAIL or BLOCK, alone or with
# an explanation after a separator (the shared classifier's FAIL class).
VERIFIED_BLOCK_RAW = re.compile(r"^(fail|block)($|[\s:;.,(])", re.IGNORECASE)


def classify(doc: object) -> str | None:
    if not isinstance(doc, dict):
        return "null-verdict"
    verdict = doc.get("verdict")
    if verdict is None or (isinstance(verdict, str) and not verdict.strip()):
        return "null-verdict"
    if not isinstance(verdict, str):
        return "null-verdict"
    word = verdict.strip().lower()
    if word == "approve":
        return "approve-unrecognised"
    if word == "block":
        raw = doc.get("verdict_raw")
        if isinstance(raw, str) and VERIFIED_BLOCK_RAW.match(raw.strip()):
            return None
        return "block-unverified"
    return None


class UnsafeDest(Exception):
    pass


def safe_dest_dir(out: Path, src: Path, rel_parent: Path, create: bool) -> Path:
    """Walk the destination directory component by component under `out`.

    Refuses any symlinked component and any destination whose real path falls
    inside the receipts tree. Creates missing directories only when asked.
    """
    cur = out
    if create:
        out.mkdir(parents=True, exist_ok=True)
    for part in rel_parent.parts:
        cur = cur / part
        if cur.is_symlink():
            raise UnsafeDest(f"symlinked output component: {cur}")
        if not cur.exists() and create:
            cur.mkdir()
    real = Path(os.path.realpath(cur))
    if real == src or src in real.parents:
        raise UnsafeDest(f"destination resolves inside the receipts tree: {cur}")
    return cur


def write_note(dest_dir: Path, name: str, text: str, src: Path) -> None:
    dest = dest_dir / name
    if dest.is_symlink():
        raise UnsafeDest(f"symlinked destination: {dest}")
    real = Path(os.path.realpath(dest))
    if src in real.parents:
        raise UnsafeDest(f"destination resolves inside the receipts tree: {dest}")
    tmp = dest_dir / f".note.{os.getpid()}.{name}"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(tmp, flags, 0o644)
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
        os.replace(tmp, dest)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--reviews-dir", type=Path, default=STATE / "reviews")
    ap.add_argument("--out-dir", type=Path, default=STATE / "reviews-reclass")
    ap.add_argument("--check", action="store_true", help="write nothing; print counts")
    args = ap.parse_args(argv)

    src = args.reviews_dir.resolve()
    if args.out_dir.is_symlink():
        print("error: --out-dir must not be a symlink", file=sys.stderr)
        return 2
    out = args.out_dir.resolve()
    if not src.is_dir():
        print(f"error: {src} is not a directory", file=sys.stderr)
        return 2
    if out == src or src in out.parents or out in src.parents:
        print("error: --out-dir must be separate from --reviews-dir", file=sys.stderr)
        return 2

    counts: Counter[str] = Counter()
    scanned = unreadable = 0
    for path in sorted(src.rglob("*.json")):
        if not path.is_file() or path.is_symlink():
            continue
        scanned += 1
        try:
            doc = json.loads(path.read_text())
        except (OSError, UnicodeError, ValueError):
            unreadable += 1
            continue
        reclass = classify(doc)
        if reclass is None:
            continue
        rel = path.relative_to(src)
        note = {
            "kind": "review-receipt-reclassification",
            "receipt": str(rel),
            "stored_verdict": doc.get("verdict") if isinstance(doc, dict) else None,
            "verdict_reclass": reclass,
            "reason": REASONS[reclass],
        }
        text = json.dumps(note, indent=2, sort_keys=True) + "\n"
        name = rel.name[: -len(".json")] + ".note.json"
        try:
            dest_dir = safe_dest_dir(out, src, rel.parent, create=False)
            dest = dest_dir / name
            if dest.is_symlink():
                raise UnsafeDest(f"symlinked destination: {dest}")
            if dest.exists() and dest.read_text() == text:
                counts[reclass + ":unchanged"] += 1
                continue
            if not args.check:
                dest_dir = safe_dest_dir(out, src, rel.parent, create=True)
                write_note(dest_dir, name, text, src)
        except UnsafeDest as exc:
            print(f"error: refusing unsafe output path: {exc}", file=sys.stderr)
            return 2
        counts[reclass] += 1

    mode = "check (nothing written)" if args.check else "applied"
    print(f"mode: {mode}")
    print(f"receipts scanned: {scanned}; unreadable: {unreadable}")
    for key in sorted(counts):
        print(f"{key}: {counts[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
