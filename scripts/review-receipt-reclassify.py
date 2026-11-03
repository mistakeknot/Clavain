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

PASS and PASS WITH NOTES receipts get no note. Idempotent: a note whose content
already matches is left alone. --check writes nothing and prints the counts.
"""

from __future__ import annotations

import argparse
import json
import os
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
        return "block-unverified"
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--reviews-dir", type=Path, default=STATE / "reviews")
    ap.add_argument("--out-dir", type=Path, default=STATE / "reviews-reclass")
    ap.add_argument("--check", action="store_true", help="write nothing; print counts")
    args = ap.parse_args(argv)

    src = args.reviews_dir.resolve()
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
        dest = out / rel.parent / (rel.name[: -len(".json")] + ".note.json")
        if dest.exists() and dest.read_text() == text:
            counts[reclass + ":unchanged"] += 1
            continue
        counts[reclass] += 1
        if args.check:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=dest.parent, prefix=".note.")
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
        os.replace(tmp, dest)

    mode = "check (nothing written)" if args.check else "applied"
    print(f"mode: {mode}")
    print(f"receipts scanned: {scanned}; unreadable: {unreadable}")
    for key in sorted(counts):
        print(f"{key}: {counts[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
