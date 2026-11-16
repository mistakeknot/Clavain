#!/usr/bin/env python3
"""Review-by-risk trial policy (bead mk-h9541): decide how much review a change gets.

Reads `reasoning.review_policy` from config/routing.yaml. It only lowers the number
of review rounds or skips cross-lab review for low-risk changes; it never changes
which seat reviews, the frontier floors or reviewer independence.

Outside the trial window, or with enabled: false, or CLAVAIN_REVIEW_POLICY=off,
every change is `full` and the 3-fix-round + 1-confirm cap applies as before.

  review_policy.py decide [--prototype] [--config FILE] [--today YYYY-MM-DD] < paths
      prints JSON: {"class", "action", "max_rounds", "trial_active", "reason"}
      action: full | one-round | skip
"""
import argparse
import datetime
import json
import os
import re
import sys
from pathlib import Path

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config" / "routing.yaml"

# Keep-list. Every pattern is a place where a missed defect is expensive, so
# a match here always wins over the skip classes. Widening is safe; narrowing
# removes a surface from full review (tests/structural/test_review_policy.py).
KEEP_RE = re.compile("|".join([
    r"(^|/)(AGENTS|CLAUDE)\.md$",                                  # instruction files
    r"(^|/)SKILL(-compact)?\.md$",
    r"(^|/)(commands|agents)/[^/]+\.md$",
    r"(^|/)\.claude/",
    r"(^|/)\.codex/",
    r"(^|/)hooks?/", r"(^|/)hooks\.json$",                          # hooks
    r"settings[^/]*\.(json|ya?ml|toml)$", r"(^|/)permissions?[^/]*\.",
    r"(^|/)\.github/workflows/",                                    # CI workflows
    r"(^|/)(Makefile|Dockerfile)$", r"(^|/)(ci|\.ci)/",
    r"(^|/)(install|release|publish|deploy|bump|sign)[^/]*\.(sh|py|ts|js|ya?ml)$",
    r"(^|/)(scripts|bin)/[^/]*(release|publish|install|deploy|sign)[^/]*$",
    r"(^|/)plugin\.json$", r"(^|/)marketplace[^/]*\.json$",         # releases and publishes
    r"(^|/)config/routing[^/]*\.ya?ml$", r"(^|/)review[-_]policy",   # routing and this policy
    r"migrat", r"(^|/)schema[^/]*\.", r"\.sql$", r"(^|/)versions?/",  # migrations
    r"(^|/)saves?(/|[-_.])", r"save[-_]?(format|schema|game|data|file)", r"serializ",
    r"(^|/)(auth|oauth|authn|authz|login|signin|sign-in|session)[^/]*",  # sign-ins
    r"credential", r"secret", r"token", r"keychain", r"\.pem$", r"\.key$",
    r"billing", r"payment", r"stripe", r"invoice", r"checkout", r"spend", r"quota", r"budget",
]), re.IGNORECASE)

DOC_RE = re.compile(r"\.(md|mdx|txt|rst|adoc)$|(^|/)docs?/|(^|/)(README|CHANGELOG|LICENSE)[^/]*$", re.IGNORECASE)
TEST_RE = re.compile(r"(^|/)(tests?|__tests__|spec|e2e)/|\.(test|spec)\.[a-z]+$|(^|/)test_[^/]*\.py$|_test\.(go|py)$", re.IGNORECASE)


def load_policy(config=None):
    import yaml
    path = Path(config or os.environ.get("CLAVAIN_ROUTING_POLICY") or DEFAULT_CONFIG)
    with path.open() as stream:
        data = yaml.safe_load(stream) or {}
    policy = (data.get("reasoning") or {}).get("review_policy")
    return policy if isinstance(policy, dict) else None


def _day(value):
    if isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(str(value))


def trial_active(policy, today=None):
    """True only inside [first_day, last_day] with the trial enabled."""
    if not policy or policy.get("enabled") is not True:
        return False
    if os.environ.get("CLAVAIN_REVIEW_POLICY", "").lower() in ("off", "0", "false", "no"):
        return False
    try:
        first, last = _day(policy["first_day"]), _day(policy["last_day"])
    except (KeyError, ValueError, TypeError):
        return False  # an unreadable window is never an active trial
    today = today or _day(os.environ.get("CLAVAIN_REVIEW_POLICY_TODAY") or datetime.date.today())
    return first <= today <= last


def classify_paths(paths, prototype=False):
    """Return (class, reason). Classes: keep, routine, text-only, doc-only, test-only, one-shot-prototype."""
    paths = [p.strip() for p in paths if p and p.strip()]
    if not paths:
        return "keep", "no changed paths on record; unclassifiable changes keep full review"
    hit = [p for p in paths if KEEP_RE.search(p)]
    if hit:
        return "keep", f"keep-list path: {hit[0]}"
    if prototype:
        return "one-shot-prototype", "declared one-shot prototype with no keep-list path"
    if all(DOC_RE.search(p) for p in paths):
        return "doc-only", "every path is documentation"
    if all(TEST_RE.search(p) for p in paths):
        return "test-only", "every path is a test"
    if all(DOC_RE.search(p) or TEST_RE.search(p) for p in paths):
        return "text-only", "only docs and tests changed"
    return "routine", "code change outside the keep-list"


def decide(paths, policy, prototype=False, today=None):
    policy = policy or {}
    klass, why = classify_paths(paths, prototype)
    active = trial_active(policy, today)
    if not active:
        return dict(**{"class": klass}, action="full", max_rounds=3, trial_active=False,
                    reason="trial not active; full review and the 3+1 round cap")
    if klass == "keep":
        return dict(**{"class": klass}, action="full", max_rounds=3, trial_active=True, reason=why)
    if klass in (policy.get("skip_classes") or []):
        return dict(**{"class": klass}, action="skip", max_rounds=0, trial_active=True,
                    reason=why + "; author's check, tests and CI carry it")
    limit = int((policy.get("routine") or {}).get("max_rounds", 1))
    return dict(**{"class": klass}, action="one-round", max_rounds=limit, trial_active=True,
                reason=why + "; one round, a second only after a high-severity finding")


def is_high(severity, policy):
    """Unknown or missing severity counts as high: a missing label may only add a round."""
    levels = {str(x).lower() for x in (policy.get("routine") or {}).get("second_round_if_severity", [])}
    if not isinstance(severity, str) or not severity.strip():
        return True
    head = re.split(r"[\s(/,:;-]", severity.strip(), 1)[0].lower()
    if head in levels:
        return True
    return head not in {"p2", "p3", "p4", "medium", "low", "info", "informational", "nit", "note", "minor"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("decide")
    d.add_argument("--prototype", action="store_true", help="declare a one-shot prototype")
    d.add_argument("--config")
    d.add_argument("--today")
    args = parser.parse_args(argv)
    policy = load_policy(args.config)
    today = _day(args.today) if args.today else None
    print(json.dumps(decide(sys.stdin.read().splitlines(), policy, args.prototype, today), sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
