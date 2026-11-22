#!/usr/bin/env python3
"""Review-by-risk trial policy: decide how much review a change gets.

Reads `reasoning.review_policy` from config/routing.yaml. It only lowers the number
of review rounds or skips cross-lab review for low-risk changes; it never changes
which seat reviews, the frontier floors or reviewer independence.

The window is in Pacific time (America/Los_Angeles). Outside the trial window, or with enabled: false, or CLAVAIN_REVIEW_POLICY=off,
every change is `full` and the 3-fix-round + 1-confirm cap applies as before.

  review_policy.py decide [--prototype] [--config FILE] < paths
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

try:
    import zoneinfo
except ImportError:  # pragma: no cover
    zoneinfo = None

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
    r"(^|/)config/", r"(^|/)units/", r"(^|/)schemas?/",             # configuration, units and schemas
    r"(^|/)(test_)?review[-_](policy|round_limit)",                    # gate and its regression tests
    r"dispatch|routing|gate",
    r"instruction", r"contract",                                    # managed operating contract and instruction text
    r"(^|/)docs/canon/",                                            # canon: routing and reasoning rules
    r"(^|/)policies/",                                              # fleet instruction and approval files
    r"(^|/)[^/]*(standing[-_]approvals?|approvals?[-_](index|root|archive)|instruction[-_]files?)[^/]*$",
    r"(^|/)(review-by-risk|batch-lane|handoff-scripts|ops-hygiene|decision-cards|one-shot-lane|vizier-[^/]*|coordinator-[^/]*)\.md$",
    r"(^|/)scripts/(dispatch|lib-routing|route|review|lib-review|orchestrate|lib-gates|gate)[^/]*",  # dispatch, routing, review gates
    r"(^|/)(dispatch|routing|review-round|review_round)[^/]*\.(sh|py)$",
    r"migrat", r"(^|/)schema[^/]*\.", r"\.sql$", r"(^|/)versions?/",  # migrations
    r"(^|/)saves?(/|[-_.])", r"save[-_]?(format|schema|game|data|file)", r"serializ",
    r"(^|/)(auth|oauth|authn|authz|login|signin|sign-in|session)[^/]*",  # sign-ins
    r"credential", r"secret", r"token", r"keychain", r"\.pem$", r"\.key$",
    r"(^|/)scripts/(lib-|clavain_selector/|clavain-select|authz|capacity|pool|provider|burn|codex-|clodex|bb-|check-instruction|sync-|startup|native-readiness|token|verify-config|gates/)",  # service budgets, approvals, fleet and instruction sync
    r"(^|/)\.[^/]+/", r"(^|/)bin/", r"(^|/)server/", r"(^|/)systemd/", r"\.(service|timer|socket|plist)$",  # hidden config dirs, executables, services
    r"sudoers", r"cron", r"(^|/)[^/]*ssh", r"converge", r"allow", r"denylist", r"autoMode",       # permission and host-control writers
    r"jev", r"egress", r"fleet", r"approv", r"entitle", r"selector",
    r"billing", r"payment", r"stripe", r"invoice", r"checkout", r"spend", r"quota", r"budget",
]), re.IGNORECASE)

# Allow-list (rework): reduced review is for paths a named safe class names, and
# only when no keep-list pattern matches either. A path no class names keeps full review, so a
# surface nobody listed is never reviewed less by accident.
#   docs: prose under a docs/ directory, or a root README/CHANGELOG/LICENSE
#   tests and harnesses always keep full review
#   routine: explicit presentation files; unknown source files retain full review
DOC_RE = re.compile(r"(^|/)docs?/.*\.(md|mdx|rst|adoc|txt)$|^(README|CHANGELOG|LICENSE)(\.(md|rst|txt|adoc))?$", re.IGNORECASE)
TEST_RE = re.compile(r"(^|/)(tests?|__tests__|e2e)/[^/]+(/[^/]+)*\.[a-z0-9]+$|\.(test|spec)\.[a-z]+$|(^|/)test_[^/]*\.py$|_test\.(go|py)$", re.IGNORECASE)
# Design choice: begin with two named presentation files, never a source-directory wildcard.
ROUTINE_RE = re.compile(r"^(styles/theme\.css|ui/spacing\.css)$")



def load_policy(config=None):
    import yaml
    path = Path(config or os.environ.get("CLAVAIN_ROUTING_POLICY") or DEFAULT_CONFIG)
    with path.open() as stream:
        data = yaml.safe_load(stream) or {}
    policy = (data.get("reasoning") or {}).get("review_policy")
    return policy if isinstance(policy, dict) else None


def _day(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ValueError("merge_day must be a YYYY-MM-DD string")
    return datetime.date.fromisoformat(value)


SKIP_CLASSES = {"text-only", "doc-only", "test-only", "one-shot-prototype"}
KEEP_CATEGORIES = {"spend", "credentials", "sign-ins", "payments", "save-formats-and-migrations",
                   "releases-and-publishes", "instruction-files", "hooks", "ci-workflows"}


def valid_policy(policy):
    """True only for a complete, well-formed block. Anything else is not an active trial (full review)."""
    if not isinstance(policy, dict):
        return False
    routine = policy.get("routine")
    if not isinstance(routine, dict):
        return False
    limit = routine.get("max_rounds")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit != 1:
        return False  # the trial is defined as exactly one routine round
    levels = routine.get("second_round_if_severity")
    if not isinstance(levels, list) or not levels or not all(isinstance(x, str) and x.strip() for x in levels):
        return False
    skips = policy.get("skip_classes")
    if not isinstance(skips, list) or not skips or not set(skips) <= SKIP_CLASSES:
        return False
    keep = policy.get("keep_list")
    if not isinstance(keep, list) or not all(isinstance(x, str) for x in keep) or set(keep) != KEEP_CATEGORIES or len(keep) != len(KEEP_CATEGORIES):
        return False  # every keep-list category must be named, nothing else
    if policy.get("enabled") not in (True, False):
        return False
    for key in ("trial", "bead"):
        if not isinstance(policy.get(key), str) or not policy[key].strip():
            return False
    for key in ("merge_day",):
        if key not in policy:
            return False
    return True


def today_pacific():
    """Today's date in America/Los_Angeles, the zone the window is stated in. None if the zone is unreadable."""
    try:
        return datetime.datetime.now(zoneinfo.ZoneInfo("America/Los_Angeles")).date()
    except Exception:  # missing tz data: never guess, the trial is then not active
        return None


def trial_active(policy, today=None):
    """True only from merge_day through merge_day + 13 days inclusive with the trial enabled and the block complete."""
    if not valid_policy(policy) or policy.get("enabled") is not True:
        return False
    if os.environ.get("CLAVAIN_REVIEW_POLICY", "").lower() in ("off", "0", "false", "no"):
        return False
    try:
        first = _day(policy["merge_day"])
        last = first + datetime.timedelta(days=13)
    except (KeyError, ValueError, TypeError):
        return False  # an unreadable window is never an active trial
    today = today or today_pacific()
    if today is None:
        return False
    return first <= today <= last


def ambiguous(path):
    """A path git would never print for a plain file: do not guess, keep full review."""
    return ("\\" in path or path.startswith("/") or "\x00" in path or path.startswith('"')
            or any(part in ("", ".", "..") for part in path.split("/"))
            or any(ord(c) < 32 or ord(c) == 127 for c in path) or path != path.strip())


def classify_paths(paths, prototype=False):
    """Return (class, reason). Classes: keep, routine, doc-only.

    A change is reduced only when every path is a named safe path and none is on the keep-list."""
    if not isinstance(paths, (list, tuple)):
        return "keep", "path list is not a list; unclassifiable changes keep full review"
    if any(not isinstance(p, str) for p in paths):
        return "keep", "non-string path entry; unclassifiable changes keep full review"
    paths = [p for p in paths if p != ""]
    if not paths:
        return "keep", "no changed paths on record; unclassifiable changes keep full review"
    odd = [p for p in paths if ambiguous(p)]
    if odd:
        return "keep", f"ambiguous path (backslash, absolute, dot segment or control character): {odd[0]!r}; unclassifiable changes keep full review"
    # Test and harness changes can disable verification; path names cannot prove
    # that they are independent of the review gate. Keep them all in full review.
    hit = [p for p in paths if KEEP_RE.search(p) or TEST_RE.search(p)]
    if hit:
        return "keep", f"keep-list path: {hit[0]}"
    named = lambda p: bool(DOC_RE.search(p) or ROUTINE_RE.search(p))
    # Legacy --prototype is accepted for compatibility but grants no reduction.
    unnamed = [p for p in paths if not named(p)]
    if unnamed:
        return "keep", f"path no safe class names: {unnamed[0]}; full review"
    if all(DOC_RE.search(p) for p in paths):
        return "doc-only", "every path is documentation"
    return "routine", "every path is documentation or an explicitly listed presentation file"


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
    return dict(**{"class": klass}, action="one-round", max_rounds=1, trial_active=True,
                reason=why + "; one round, a second only after a high-severity finding")


def is_high(severity, policy):
    """Unknown or missing severity counts as high: a missing label may only add a round."""
    if not valid_policy(policy):
        return True
    levels = {x.lower() for x in policy["routine"]["second_round_if_severity"]}
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
    d.add_argument("--prototype", action="store_true", help="legacy compatibility flag; does not change review classification")
    d.add_argument("--config")
    args = parser.parse_args(argv)
    policy = load_policy(args.config)
    # Split only on "\n": str.splitlines() also splits on VT, FS and other separators a path may hold.
    raw = sys.stdin.buffer.read().decode("utf-8", "surrogateescape")
    print(json.dumps(decide(raw.split("\n"), policy, args.prototype), sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
