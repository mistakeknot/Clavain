#!/usr/bin/env python3
"""Review-by-risk trial report (bead mk-h9541): baseline and end-of-trial, same definitions.

  review-trial-report.py --label baseline --since 2026-11-02 --until 2026-11-15 --out baseline.json
  review-trial-report.py --label trial    --since 2026-11-18 --until 2026-12-01 --out trial.json
  review-trial-report.py --compare baseline.json trial.json

Four measures, per policy class (skip / one-round / full, from review_policy.py) and overall:

  1. Review rounds per change. A change is one (repo, PR) from the cross-lab review
     receipts, else one bead. A round is one distinct (dispatch_id, attempt_id).
  2. Findings that changed code, per round. Receipts do not record which finding a
     fix answered, so this is a proxy: a round's actionable findings (severity not
     low/info) count as "changed code" when a later round of the same change ran on
     a different head_sha, i.e. the author pushed after that round. Rounds with no
     findings list on record are reported as `rounds_without_findings`.
  3. Review tokens as a share of tokens. `agent-cli outcomes --json --days N` gives
     tokens by role for closed beads; the share is cross-lab-review + plan-review
     (+ validation) over all roles it lists. N is the window length and counts back
     from today, so run each report on the window's last day (or save the output).
  4. Escapes: merged PRs (gh) in the window, counting only those whose 7 follow-up
     days are over (`merged_follow_up_incomplete` lists the rest; run the report
     again 7 days after the window ends, with --tokens-from to keep the first
     run's token share), followed within 7 days by a revert or
     hotfix PR touching one of the same paths, or by any PR whose title cites the
     PR number (`escape_rate`, the headline). `fix_same_path_rate` also counts any
     later fix(...) PR on a shared path and is an upper bound, not the headline. Needs `gh`;
     with --no-gh the measure is reported as unknown, never as zero.

Sources are read-only: the review receipt directory, agent-cli and gh.
"""
import argparse
import collections
import datetime
import glob
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import review_policy  # noqa: E402

REVIEW_ROLES = ("cross-lab-review", "plan-review", "validation")
FIX_RE = re.compile(r"^\s*(revert|hotfix|fix)\b|\bfollow-?up fix\b", re.IGNORECASE)
STRICT_RE = re.compile(r"^\s*(revert|hotfix)\b|\bregression\b|\bfollow-?up fix\b", re.IGNORECASE)
LOW = {"low", "info", "informational", "nit", "note", "minor", "p3", "p4"}


def day(text):
    return datetime.date.fromisoformat(text)


def receipts_dir():
    base = os.environ.get("CLAVAIN_REVIEW_RECEIPT_DIR") or os.path.expanduser("~/.local/state/clavain/reviews")
    return base


def load_receipts(since, until):
    rows = []
    for path in glob.glob(os.path.join(receipts_dir(), "*", "*.json")):
        try:
            row = json.loads(Path(path).read_text())
        except (OSError, ValueError):
            continue
        if not isinstance(row, dict) or row.get("kind") != "cross-lab-review-receipt":
            continue
        stamp = str(row.get("created_at") or "")[:10]
        try:
            when = day(stamp)
        except ValueError:
            continue
        if since <= when <= until:
            rows.append(row)
    return rows


def actionable(finding):
    sev = finding.get("severity") if isinstance(finding, dict) else None
    if not isinstance(sev, str) or not sev.strip():
        return True  # unlabelled counts, as in review_policy.is_high
    return re.split(r"[\s(/,:;-]", sev.strip(), 1)[0].lower() not in LOW


def per_change(rows, policy):
    today = review_policy.today_pacific()
    classification_available = (today is not None and review_policy.valid_policy(policy)
                                and os.environ.get("CLAVAIN_REVIEW_POLICY", "").lower() not in ("off", "0", "false", "no"))
    if not classification_available:
        print("warning: policy classification unavailable (config, Pacific zone or policy override); classes unknown", file=sys.stderr)
    changes = collections.defaultdict(list)
    for row in rows:
        pr, bead = row.get("pr"), row.get("bead_id")
        if pr not in (None, "", "None"):
            key = f"{row.get('repo')}#{pr}"
        elif bead not in (None, "", "None"):
            key = f"bead:{bead}"
        else:
            continue
        changes[key].append(row)
    out = {}
    for key, items in changes.items():
        rounds = {}
        for row in sorted(items, key=lambda r: str(r.get("created_at"))):
            rounds.setdefault((row.get("dispatch_id"), row.get("attempt_id"), row.get("head_sha")), row)
        ordered = list(rounds.values())
        paths = sorted({p for r in ordered for p in (r.get("changed_paths") or []) if isinstance(p, str)})
        decision = review_policy.decide(paths, {**policy, "enabled": True, "merge_day": today.isoformat()}, today=today) if classification_available else None
        klass = decision["action"] if decision else "unknown"
        if not paths:
            klass = "no-paths"
        heads = [r.get("head_sha") for r in ordered]
        changed = with_findings = without = unknown_heads = 0
        for n, row in enumerate(ordered):
            found = row.get("findings")
            if not isinstance(found, list) or row.get("findings_source") == "unknown":
                without += 1
                continue
            with_findings += 1
            later = heads[n + 1:]
            if heads[n] is None or any(h is None for h in later):
                unknown_heads += 1  # missing head evidence cannot show that the author pushed
            elif any(h != heads[n] for h in later):
                changed += sum(1 for f in found if actionable(f))
        out[key] = dict(rounds=len(ordered), klass=klass, findings_changed_code=changed, rounds_unknown_heads=unknown_heads,
                        rounds_with_findings=with_findings, rounds_without_findings=without,
                        failed_rounds=sum(1 for r in ordered if r.get("verdict") in ("BLOCK", "FAIL")))
    return out


def summarize(changes):
    groups = collections.defaultdict(list)
    for item in changes.values():
        groups["all"].append(item)
        groups[item["klass"]].append(item)
    result = {}
    for name, items in sorted(groups.items()):
        rounds = sum(i["rounds"] for i in items)
        unknown_heads = sum(i["rounds_unknown_heads"] for i in items)
        known = sum(i["rounds_with_findings"] for i in items) - unknown_heads
        result[name] = dict(changes=len(items), rounds=rounds,
                            rounds_per_change=round(rounds / len(items), 3),
                            changes_with_2plus_rounds=sum(1 for i in items if i["rounds"] >= 2),
                            findings_changed_code=sum(i["findings_changed_code"] for i in items),
                            # Rate over rounds whose findings are on record; unknown stays unknown (None), never 0.
                            findings_changed_code_per_round=round(sum(i["findings_changed_code"] for i in items) / known, 3) if known else None,
                            rounds_with_findings=known, rounds_unknown_heads=unknown_heads,
                            rounds_without_findings=sum(i["rounds_without_findings"] for i in items))
    return result


def tokens(days):
    try:
        raw = subprocess.run(["agent-cli", "outcomes", "--json", "--days", str(days)], capture_output=True, text=True, timeout=120, check=True).stdout
        data = json.loads(raw)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    raw_roles = {k: v.get("tokens") if isinstance(v, dict) else None for k, v in (data.get("by_role") or {}).items()}
    roles = {k: v for k, v in raw_roles.items() if isinstance(v, (int, float)) and not isinstance(v, bool)}
    unknown_roles = sorted(k for k in raw_roles if k not in roles)
    # Runs whose usage agent-cli could not read (runs_no_usage) leave a role's tokens a lower bound.
    def count(role, key):
        value = (data.get("by_role") or {}).get(role, {})
        value = value.get(key) if isinstance(value, dict) else None
        return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None
    no_usage = {r: count(r, "runs_no_usage") for r in raw_roles}
    runs = {r: count(r, "runs") for r in raw_roles}
    partial = sorted(r for r, n in no_usage.items() if n is None or n > 0)
    total = sum(roles.values())
    present = [r for r in REVIEW_ROLES if r in roles]
    review = sum(roles[r] for r in present)
    # No review role listed, a role with unknown usage, or any run without usage data means the share is unknown.
    complete = bool(present) and not unknown_roles and not partial
    measured = round(review / total, 4) if total and present else None
    return dict(days=days, measure=data.get("measure"), by_role=roles, closed_beads=data.get("closed_beads"),
                roles_unknown_tokens=unknown_roles,
                roles_with_runs_no_usage=partial,
                runs_no_usage=sum(n for n in no_usage.values() if n), runs=sum(n for n in runs.values() if n),
                review_tokens=review if present else None, all_role_tokens=total,
                review_share=measured if complete else None,
                # Over the runs with usage data only: a lower bound, never the trial's headline number.
                review_share_measured_runs_only=measured,
                overhead_not_closed=(data.get("overhead_not_closed") or {}).get("tokens"))


def gh_json(args):
    out = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=120)
    if out.returncode:
        raise OSError(out.stderr[:200])
    return json.loads(out.stdout)


def escapes(repos, since, until):
    """Merged PRs in the window followed within 7 days by a revert or a fix touching the same paths."""
    merged_total = merged_strict = merged_loose = incomplete = 0
    today = datetime.date.today()
    detail, unreadable = [], []
    horizon = until + datetime.timedelta(days=7)
    for repo in repos:
        try:
            prs = gh_json(["pr", "list", "--repo", repo, "--state", "merged", "--limit", "300",
                           "--search", f"merged:{since.isoformat()}..{horizon.isoformat()}",
                           "--json", "number,title,mergedAt,files"])
        except (OSError, ValueError, subprocess.SubprocessError):
            unreadable.append(repo)
            continue
        prs = [p for p in prs if p.get("mergedAt")]
        for pr in prs:
            merged = datetime.datetime.fromisoformat(pr["mergedAt"].replace("Z", "+00:00"))
            if not since <= merged.date() <= until:
                continue
            if merged.date() + datetime.timedelta(days=7) > today:
                incomplete += 1  # its 7 follow-up days are not over: unknown, not "no escape"
                continue
            merged_total += 1
            mine = {f["path"] for f in pr.get("files") or []}
            hit = None
            for other in prs:
                later = datetime.datetime.fromisoformat(other["mergedAt"].replace("Z", "+00:00"))
                if other["number"] == pr["number"] or not (merged < later <= merged + datetime.timedelta(days=7)):
                    continue
                title = other.get("title") or ""
                same = bool(mine & {f["path"] for f in other.get("files") or []})
                strict = bool(re.search(rf"#{pr['number']}\b", title)) or (bool(STRICT_RE.search(title)) and same)
                if strict:
                    hit = "strict"
                    detail.append(f"{repo}#{pr['number']} -> #{other['number']}")
                    break
                if same and FIX_RE.search(title):
                    hit = hit or "loose"
            merged_strict += hit == "strict"
            merged_loose += hit in ("strict", "loose")
    if len(unreadable) == len(repos):
        return None
    rate = lambda n: round(n / merged_total, 4) if merged_total else None  # noqa: E731
    return dict(merged=merged_total, merged_follow_up_incomplete=incomplete, repos_unreadable=unreadable,
                escaped=merged_strict, escape_rate=rate(merged_strict),
                fix_same_path=merged_loose, fix_same_path_rate=rate(merged_loose), examples=detail[:20])


def build(args):
    policy = review_policy.load_policy()
    rows = load_receipts(args.since, args.until)
    changes = per_change(rows, policy)
    repos = args.repos or [r for r, _ in collections.Counter(x.get("repo") for x in rows if x.get("repo")).most_common(args.max_repos)]
    return dict(label=args.label, since=args.since.isoformat(), until=args.until.isoformat(),
                receipts=len(rows), summary=summarize(changes),
                tokens=(json.loads(args.tokens_from.read_text()).get("tokens") if args.tokens_from else tokens((args.until - args.since).days + 1)),
                escapes=None if args.no_gh else escapes(repos, args.since, args.until), repos=repos,
                generated=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"))


def compare(a, b):
    for name in ("all", "full", "one-round", "skip"):
        x, y = a["summary"].get(name), b["summary"].get(name)
        if x and y:
            print(f"{name:10} rounds/change {x['rounds_per_change']} -> {y['rounds_per_change']}  "
                  f"changed-code findings/round {x['findings_changed_code_per_round']} -> {y['findings_changed_code_per_round']}  "
                  f"changes {x['changes']} -> {y['changes']}")
    ta, tb = a.get("tokens"), b.get("tokens")
    print("review token share", ta and ta["review_share"], "->", tb and tb["review_share"])
    ea, eb = a.get("escapes"), b.get("escapes")
    print("escape rate", ea and ea["escape_rate"], "->", eb and eb["escape_rate"])


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--label", default="report")
    parser.add_argument("--since", type=day)
    parser.add_argument("--until", type=day)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--repos", nargs="*")
    parser.add_argument("--max-repos", type=int, default=8)
    parser.add_argument("--no-gh", action="store_true")
    parser.add_argument("--tokens-from", type=Path, help="reuse the token share from an earlier report (the token window counts back from the day it runs)")
    parser.add_argument("--compare", nargs=2, type=Path)
    args = parser.parse_args()
    if args.compare:
        compare(*(json.loads(p.read_text()) for p in args.compare))
        return 0
    if not (args.since and args.until):
        parser.error("--since and --until are required")
    report = build(args)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.out:
        args.out.write_text(text + "\n")
    print(text if not args.out else f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
