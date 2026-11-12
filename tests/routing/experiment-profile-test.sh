#!/usr/bin/env bash
# Real resolver only: these checks never launch an engine.
set -euo pipefail
cd "$(dirname "$0")/../.."
python3 - <<'PY'
import copy, hashlib, json, pathlib, subprocess, tempfile, yaml
root = pathlib.Path.cwd()
policy = root / 'config/routing.yaml'
cfg = yaml.safe_load(policy.read_text())
registry = json.loads((root / 'config/experiment-profiles.json').read_text())
profiles = cfg['reasoning']['profiles']
tiers = cfg['dispatch']['tiers']
assert set(registry) == {p for p in profiles if p.startswith('experiment-')}
experiment_tiers = {e['tier'] for e in registry.values()}
assert len(experiment_tiers) == len(registry)
for name, e in registry.items():
    assert profiles[name] == {'scope': e['bead'], 'roles': {e['role']: e['tier']}}
    t = tiers[e['tier']]
    assert t['fallbacks'] == []
    for key, field in [('backend','backend'), ('model','model'), ('reasoning_effort','effort'), ('service_tier','service_tier')]:
        assert t[key] == e['assert'][field]
for name, t in tiers.items():
    assert not experiment_tiers.intersection(t.get('fallbacks', []))
assert not experiment_tiers.intersection(cfg['dispatch']['roles'].values())
assert not experiment_tiers.intersection(cfg['dispatch']['fallback'].values())
for name,p in profiles.items():
    if name not in registry:
        assert not experiment_tiers.intersection(p.get('roles', {}).values())
assert {n for n,t in tiers.items() if t.get('model')=='claude-fable-5-2'} == {'one-shot-fable','exp-mk-d0h1j.1-fable-high'}
# Pin the launcher boundary's consumers. A new consumer needs its own guard.
callers = {p.name for p in (root/'scripts').glob('*') if p.is_file() and p.suffix in {'.sh','.py'} and
           p.name not in {'tier-fallback-chain.py','lib-routing.sh'} and
           ('tier-fallback-chain.py' in p.read_text() or 'routing_resolve_dispatch_tier' in p.read_text())}
assert callers == {'dispatch.sh'}, callers
with tempfile.TemporaryDirectory() as tmp:
    tmp = pathlib.Path(tmp)
    old = tmp/'main.yaml'
    old.write_bytes(subprocess.check_output(['git','show','origin/main:config/routing.yaml']))
    context = tmp/'context.json'
    def resolve(role, path=policy, profile=None, reasons=(), scope=None, producer=None, ok=True, error="unsupported_adapter"):
        context.write_text(json.dumps({'reasons':list(reasons),'rationale':'routing fixture', **({'scope':scope} if scope else {})}))
        args=['ic','--json','route','dispatch',f'--policy={path}',f'--role={role}',f'--context-file={context}']
        if profile: args.append(f'--policy-profile={profile}')
        if producer is None and role in {'plan-review','validation','cross-lab-review'}:
            producer = 'gpt-6.1-sol' if role=='plan-review' or (profile and 'fable-high' in profile) else 'opus'
        if producer: args.append(f'--producer-identity={producer}')
        result=subprocess.run(args, text=True, capture_output=True)
        if not ok:
            assert result.returncode != 0 and error in result.stdout+result.stderr, result
            return
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)
    # Exclude exactly these transport-dependent fields; compare all others.
    excluded_keys = {'policy_hash','policy_source'}
    for role in cfg['dispatch']['roles']:
        before=resolve(role,old); after=resolve(role)
        assert {k:v for k,v in before.items() if k not in excluded_keys} == {k:v for k,v in after.items() if k not in excluded_keys}, role
        assert after['policy_hash']==hashlib.sha256(policy.read_bytes()).hexdigest()
    scout=resolve('scout',reasons=['difficult-verification'])
    assert scout['profile']['reasoning_effort']=='high'
    for name,e in registry.items():
        r=resolve('cross-lab-review',profile=name,reasons=['difficult-verification'],scope=e['bead'])
        assert r['profile_ref']==e['tier'] and r['profile']['reasoning_effort']==e['assert']['effort']
        assert r['effort_floors_exempted']==['difficult-verification'] and r['fallback_chain']==[]
        resolve('cross-lab-review',profile=name,reasons=['difficult-verification'],scope='mk-other',ok=False,error='requires scope')
        reasons=['difficult-verification','foundational-invariants']
        if e['assert']['backend']=='codex':
            assert resolve('cross-lab-review',profile=name,reasons=reasons,scope=e['bead'])['profile']['reasoning_effort']=='high'
        else:
            # With no fallback the resolver emits only the aggregate refusal.
            resolve('cross-lab-review',profile=name,reasons=reasons,scope=e['bead'],ok=False,error='no eligible model')
            # A resolver-only fixture makes the excluded Fable reason visible;
            # production experiment tiers still have no fallback at all.
            fixture=copy.deepcopy(cfg)
            fixture['dispatch']['tiers'][e['tier']]['fallbacks']=['crosslab-sol']
            diagnostic=tmp/'diagnostic.yaml'
            diagnostic.write_text(yaml.safe_dump(fixture))
            diagnostic_route=resolve('cross-lab-review',path=diagnostic,profile=name,reasons=reasons,scope=e['bead'])
            assert any(x['profile_ref']==e['tier'] and x['reason']=='unsupported_adapter' for x in diagnostic_route['excluded']), diagnostic_route['excluded']
    for producer in ['opus','anthropic/claude-opus-5-5']:
        r=resolve('cross-lab-review',profile='experiment-mk-d0h1j.1-sol-medium',reasons=['difficult-verification'],scope='mk-d0h1j.1',producer=producer)
        assert r['producer_model']=='claude-opus-5-5' and r['producer_identity']==producer
print('PASS: experiment registry, reachability, default semantic golden, floors and canonical producers')
PY
