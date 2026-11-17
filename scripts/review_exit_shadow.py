#!/usr/bin/env python3
"""After-the-fact review observations. Output is never used by a gate."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

import yaml
from clavain_selector import records


def outcome(later):
    known = bool(later) and all(x['findings'] is not None for x in later)
    findings = sum(x['findings'] for x in later) if known else None
    empty = [x for x in later if x['findings'] == 0]
    found = any((x['findings'] or 0) > 0 for x in later)
    return dict(later_findings=findings, could_exit=False if found else (findings == 0 if known else None),
                estimated_claude_tokens_saved=sum(x['claude_tokens'] or 0 for x in empty),
                token_estimate_complete=all(x['claude_tokens'] is not None for x in empty))


def call_decide(request, root, project):
    proc = subprocess.run(['clavain-cli', 'decide', '--plugin-root', str(root),
                           '--project-root', str(project)], input=json.dumps(request),
                          text=True, capture_output=True, timeout=6, check=True)
    return json.loads(proc.stdout)


def observe(root, project, loop, native, findings, claude_tokens):
    if os.environ.get('CLAVAIN_SELECTOR', '').strip().lower() == 'off':
        return
    policy = yaml.safe_load((root / 'config/routing.yaml').read_text())
    if policy.get('decision_models', {}).get('review_exit', {}).get('mode') != 'shadow':
        return
    loop_hash = hashlib.sha256(loop.encode()).hexdigest()
    directory = project / '.clavain/decisions'
    # Existing record writer owns the secure append; no raw loop IDs are written.
    # Callbacks for a loop must be ordered by the caller.
    answer = call_decide(dict(question=dict(id='review_exit',
        text='Could this review round have exited early?', candidates=[
            dict(id='exit', description='Exit the review loop'),
            dict(id='continue', description='Continue reviewing')]),
        state=dict(findings=findings, loop_hash=loop_hash), native_choice=native,
        egress_allowed=False, sources=[]), root, project)
    if not answer.get('decision_id'):
        return
    observation = dict(schema='review-exit-observation-v1',
        decision_id=answer['decision_id'], loop_hash=loop_hash,
        observation_id=str(uuid.uuid4()), findings=findings, claude_tokens=claude_tokens,
        confidence=answer.get('confidence', 0), applied='native',
        native_agreement=answer.get('shadow_choice') == native,
        shadow_exit=answer.get('shadow_choice') == 'exit',
        token_estimate_method='review_artifact_utf8_bytes_div4_ceiling_claude_proxy',
        estimated_claude_tokens_saved=0)
    prior = [r for r in records.read_records(record_dir=directory)
             if r.get('schema') == observation['schema'] and r.get('loop_hash') == loop_hash]
    records.append_record(observation, record_dir=directory, project_root=project)
    for index, previous in enumerate(prior):
        records.append_record(dict(schema='review-exit-outcome-v1',
            decision_id=previous['decision_id'], through_observation=observation['observation_id'],
            loop_hash=loop_hash, **outcome(prior[index + 1:] + [observation])),
            record_dir=directory, project_root=project)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', type=Path, default=Path.cwd())
    parser.add_argument('--loop', required=True)
    parser.add_argument('--native', choices=['exit', 'continue'], required=True)
    parser.add_argument('--verdict-file', type=Path, action='append', default=[],
                        help='One verdict produced by this run; repeat for all run verdicts')
    parser.add_argument('--panel', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    policy = yaml.safe_load((root / 'config/routing.yaml').read_text())
    if (os.environ.get('CLAVAIN_SELECTOR', '').strip().lower() == 'off'
            or policy.get('decision_models', {}).get('review_exit', {}).get('mode') != 'shadow'):
        return
    findings = None
    tokens = None
    if args.verdict_file:
        # The controller supplies only artifacts produced in this invocation.
        # Read once, so the count and byte proxy describe the same snapshot.
        snapshots = [p.read_bytes() for p in dict.fromkeys(args.verdict_file)]
        rows = [json.loads(raw) for raw in snapshots]
        counts = [r.get('findings_count') for r in rows]
        if counts and all(type(n) is int and n >= 0 for n in counts):
            findings = sum(counts)
        if rows:
            tokens = (sum(map(len, snapshots)) + 3) // 4
    if args.panel:
        # The round's merged receipt is authoritative. PASS WITH NOTES, invalid
        # verdicts and failed CI remain unknown rather than claiming zero findings.
        receipt = (args.panel / 'receipt.md').read_text()
        if receipt.rstrip().endswith('VERDICT: PASS'):
            findings = 0
        files = list(args.panel.glob('prompt-*.txt')) + list(args.panel.glob('lens-*.md'))
        if files:
            tokens = (sum(len(p.read_bytes()) for p in files) + 3) // 4
    observe(root, args.project.resolve(),
            args.loop, args.native, findings, tokens)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        # Best effort, sanitized and fail-open, including missing CLI/config.
        pass
