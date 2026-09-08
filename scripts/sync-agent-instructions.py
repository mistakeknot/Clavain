#!/usr/bin/env python3
"""Narrow, host-neutral instruction synchronization. Never edits host settings."""
import argparse
import hashlib
import importlib.util
import json
import shlex
from pathlib import Path
import subprocess
import sys
import tempfile


def render(source, host, portable_policy=False, policy_source=None, expected_policy_hash=None):
    source = source.resolve(strict=True)
    hosts = json.loads((source/'config/host-adapters.json').read_text())
    adapter = hosts[host]
    policy = Path(policy_source).resolve(strict=True) if policy_source else source/'config/routing.yaml'
    policy_hash = hashlib.sha256(policy.read_bytes()).hexdigest()
    if expected_policy_hash and policy_hash != expected_policy_hash:
        raise ValueError('Reasoning policy changed after resolution; reclassify before dispatch')
    version = json.loads((source/'.claude-plugin/plugin.json').read_text()).get('version', 'unversioned')
    body = (source/'config/agent-instructions.md').read_text()
    host_text = (source/adapter['adapter']).read_text() if 'adapter' in adapter else adapter['instruction']
    selection = 'portable-managed-installation' if portable_policy else 'explicit-installation'
    policy_arg = ('"${CLAVAIN_ROUTING_POLICY:-$HOME/.agents/skills/clavain/../config/routing.yaml}"'
                  if portable_policy else shlex.quote(str(policy)))
    # Keep existing explicit-install hashes stable, but distinguish portable
    # selection and its executable expression in portable contract receipts.
    hash_input = body+host_text
    if portable_policy:
        hash_input += '\0'+selection+'\0'+policy_arg
    content_hash = hashlib.sha256(hash_input.encode()).hexdigest()
    receipt = f'Host: {host}; package: {version}; policy selection: {selection}; policy SHA256: {policy_hash}; contract SHA256: {content_hash}.'
    body = body.replace('{{INSTALLATION_RECEIPT}}', receipt).replace('{{POLICY_PATH}}', policy_arg).replace('{{HOST_ADAPTER}}', host_text.strip())
    metadata = dict(host=host, source=str(source), version=version, policy_hash=policy_hash,
                    contract_hash=content_hash, policy_selection=selection,
                    surface=adapter['surface'], routing='instructional',
                    governed_dispatch=adapter['dispatch'], behaviorally_verified=False,
                    parent_model_changed=False)
    return body, metadata


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--host', required=True)
    p.add_argument('--file', type=Path)
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--check', action='store_true')
    p.add_argument('--render', action='store_true')
    p.add_argument('--portable-policy', action='store_true',
                   help='Resolve the policy through each machine\'s managed skill link, with CLAVAIN_ROUTING_POLICY override')
    p.add_argument('--policy', type=Path, help='Explicit policy used by a governed dispatch receipt')
    p.add_argument('--expected-policy-hash', help='Reject policy drift from an immutable dispatch decision')
    args = p.parse_args()
    if args.policy and args.portable_policy:
        p.error('--policy and --portable-policy are mutually exclusive')
    body, metadata = render(args.source, args.host, args.portable_policy, args.policy, args.expected_policy_hash)
    if args.render:
        print(body, end='')
        return 0
    if not args.file:
        p.error('--file is required unless --render')
    helper = args.source.resolve()/'scripts/sync-codex-instructions.py'
    if args.check:
        spec = importlib.util.spec_from_file_location('narrow_sync', helper)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        old = args.file.read_bytes() if args.file.exists() else b''
        expected = module.replace_block(old, body.rstrip().encode(), args.host == 'kimi')
        metadata['current'] = old == expected
        # Report potential overrides without copying local personality or secrets.
        outside = old.split(module.START)[0] + (old.split(module.END)[-1] if module.END in old else b'')
        metadata['local_routing_override_review_required'] = any(x in outside.lower() for x in (b'--model', b'model:', b'--role', b'routing policy'))
        print(json.dumps(metadata, sort_keys=True))
        return 0 if metadata['current'] else 1
    with tempfile.TemporaryDirectory(prefix='clavain-contract-') as td:
        block = Path(td)/'block.md'
        block.write_text(body)
        cmd = [sys.executable, str(helper), '--file', str(args.file), '--block', str(block)]
        if args.host == 'kimi':
            cmd.append('--legacy-kimi')
        if args.dry_run:
            cmd.append('--dry-run')
        return subprocess.run(cmd).returncode


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        raise SystemExit(str(error))
