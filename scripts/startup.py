#!/usr/bin/env python3
"""Read-only startup rendering; explicit refresh and installation/ledger diagnosis."""
import argparse
import contextlib
import fcntl
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import shlex
import stat
import subprocess
import sys
import tempfile
import time
import uuid

SCHEMA = 1
INVENTORY_VERSION = 1
LIMIT = 10000
MAX_READ = 16 * 1024 * 1024
TTL = 3600
MARKER = '<!-- BEGIN CLAVAIN CODEX TOOL MAP -->'


def packed(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def read(path, limit=MAX_READ):
    with path.open('rb') as stream:
        value = stream.read(limit + 1)
    if len(value) > limit:
        raise ValueError('input exceeds read budget')
    return value


def obj(path):
    value = json.loads(read(path))
    if not isinstance(value, dict):
        raise ValueError('expected object')
    return value


def digest(path):
    try:
        return hashlib.sha256(read(path)).hexdigest()
    except (OSError, ValueError, RuntimeError):
        return None


def clip(value, count=240):
    value = str(value).replace('\x00', '')
    raw = value.encode('utf-8', errors='replace')
    return value if len(raw) <= count else raw[:count].decode('utf-8', errors='ignore') + '… [truncated; inspect source]'


def installation(source, manifest, repository=None):
    result = {'status':'unknown', 'selected_path':None, 'version':None, 'issues':[]}
    try:
        entries = obj(manifest)['plugins']['clavain@interagency-marketplace']
        if not isinstance(entries, list) or len(entries) != 1:
            raise ValueError('selected installation ambiguous')
        entry = entries[0]
        selected = Path(entry['installPath'])
        result.update(selected_path=str(selected), version=entry['version'])
        resolved = selected.resolve(strict=True)
        package = obj(resolved/'.claude-plugin/plugin.json')
        if package['version'] != entry['version']:
            result['issues'].append('selected package version mismatch')
        result['provenance'] = 'unknown'
        if repository is not None:
            commit = entry.get('gitCommitSha', '')
            if len(commit) != 40 or any(c not in '0123456789abcdef' for c in commit):
                result['issues'].append('missing or malformed source commit')
            else:
                expected = subprocess.run(['git', '-C', str(repository), 'show',
                                           commit+':.claude-plugin/plugin.json'],
                                          capture_output=True, timeout=5)
                if expected.returncode or json.loads(expected.stdout).get('version') != entry['version']:
                    result['issues'].append('recorded source commit and selected version disagree')
                else:
                    result['provenance'] = 'version-matched; full artifact verification still required'
        if resolved != source.resolve(strict=True):
            result['issues'].append('selected package and invoked hook source disagree')
        hooks = obj(resolved/'hooks/hooks.json')
        for groups in hooks.get('hooks', {}).values():
            for group in groups:
                for hook in group.get('hooks', []):
                    command = hook.get('command', '')
                    if '${CLAUDE_PLUGIN_ROOT}/' in command:
                        target = command.split('${CLAUDE_PLUGIN_ROOT}/', 1)[1].split()[0].strip('"\'')
                        if not (resolved/target).is_file():
                            result['issues'].append('missing hook target: '+target)
        result['status'] = 'error' if result['issues'] else 'ok'
    except (OSError, RuntimeError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
        result['issues'].append(type(error).__name__+': selected package unavailable or malformed')
    return result


def identity(args):
    source = args.source.resolve(strict=True)
    paths = ['.claude-plugin/plugin.json','hooks/hooks.json','hooks/session-start.sh',
             'scripts/startup.py','scripts/sync-agent-instructions.py','config/routing.yaml',
             'config/agent-instructions.md','config/host-adapters.json','config/codex-instructions.md']
    hashes = {p:digest(source/p) for p in paths}
    hashes.update({str(p.relative_to(source)):digest(p) for p in (source/'hooks').glob('*.sh')})
    project_instructions = {str(p/name):digest(p/name)
                            for p in [args.project.resolve(), *args.project.resolve().parents]
                            for name in ('AGENTS.md', 'CLAUDE.md') if (p/name).is_file()}
    skills = {str(p.relative_to(source)):digest(p) for p in sorted((source/'skills').glob('*/SKILL.md'))}
    return {'project_scope':str(args.project.resolve()), 'source':str(source), 'host':args.host,
            'selected_manifest_sha256':digest(args.installed_manifest),
            'instruction_surface_sha256':digest(args.instruction_file),
            'host_settings_sha256':digest(Path.home()/'.claude/settings.json') if args.host == 'claude' else digest(Path.home()/'.codex/config.toml'),
            'inventory_version':INVENTORY_VERSION, 'hashes':hashes, 'skills':skills,
            'project_instruction_candidates':project_instructions}


def snapshot_path(args):
    key = hashlib.sha256((str(args.project.resolve())+'\0'+args.host).encode()).hexdigest()[:24]
    return args.state_dir / ('snapshot-'+key+'.json')


def snapshot_status(args, current):
    try:
        snapshot = json.loads(read_private(args, snapshot_path(args)))
        if not isinstance(snapshot, dict):
            return 'unknown', None
        if snapshot.get('schema_version') != SCHEMA or not isinstance(snapshot.get('identity'), dict):
            return 'unknown', None
        created = snapshot['created_at']
        if type(created) not in (float, int) or not math.isfinite(created):
            return 'unknown', None
        age = time.time() - created
        if snapshot['identity'] != current or age < 0 or age > TTL:
            return 'stale', snapshot
        return 'fresh', snapshot
    except (OSError, ValueError, TypeError, KeyError):
        return 'unknown', None


def private_dir(args, create=True):
    if args.state_dir.is_symlink():
        raise ValueError('symlinked state directory refused')
    path = args.state_dir.resolve()
    project = args.project.resolve()
    if path == project or path.is_relative_to(project):
        raise ValueError('state writes inside project refused')
    # Reject a cache inside any worktree, including a different project.
    if any((p/'.git').exists() for p in [path, *path.parents]):
        raise ValueError('state writes inside worktree refused')
    if create:
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.stat().st_uid != os.getuid() or stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise ValueError('state directory must be private and owned by current user')
    return path


def read_private(args, path, tail=False):
    """Check private state without creating it; bound ledger reads from the end."""
    directory = private_dir(args, create=False)
    if path.parent.resolve() != directory:
        raise ValueError('state file outside private directory')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise ValueError('state must be a private regular file')
        start = max(0, info.st_size-MAX_READ) if tail else 0
        stream.seek(start)
        # A tail is a snapshot through the observed EOF; concurrent appends belong
        # to the next doctor call and must not create a spurious budget error.
        value = stream.read(info.st_size-start if tail else MAX_READ+1)
        if len(value) > MAX_READ:
            raise ValueError('input exceeds read budget')
        if tail:
            # Ignore only the partial first row when the byte window starts mid-file.
            if start:
                value = value.partition(b'\n')[2]
            return value.splitlines()[-100:]
        return value


def refresh(args, current):
    directory = private_dir(args)
    data = {'schema_version':SCHEMA, 'created_at':time.time(), 'identity':current,
            'installation':installation(args.source, args.installed_manifest, args.source_repo),
            'dependencies':{name:shutil.which(name) is not None for name in ('python3','ic','bd')},
            'acceptance':'unknown; requires fresh independent evidence'}
    if args.archive_ledger:
        data['ledger_archive'] = archive_ledger(args)
    if args.runtime_audit:
        started = time.monotonic()
        try:
            result = subprocess.run(['bash', str(args.runtime_audit), '--json'],
                                    cwd=args.project, capture_output=True, timeout=20)
            audit = json.loads(result.stdout)
            if not isinstance(audit, dict) or not isinstance(audit.get('findings'), list):
                raise ValueError('invalid runtime audit')
            data['runtime_audit'] = {'result':audit, 'exit_status':result.returncode,
                                     'duration_ms':(time.monotonic()-started)*1000}
        except (OSError, ValueError, subprocess.TimeoutExpired):
            data['runtime_audit'] = {'status':'unknown', 'exit_status':None}
    fd, name = tempfile.mkstemp(prefix='.snapshot-', dir=directory)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(packed(data)+'\n')
        os.replace(name, snapshot_path(args))
    finally:
        if os.path.exists(name):
            os.unlink(name)
    return data


def task_sections(args, payload):
    sections = []
    summary = []
    bead = payload.get('task_id') or os.environ.get('CLAVAIN_BEAD_ID')
    if bead:
        sections.append(('active-task','Active task: '+clip(bead)))
    # Read the existing export, never query a tracker that may migrate or auto-sync.
    # Export visibility is explicitly not live ownership or current acceptance.
    path = args.project/'.beads/issues.jsonl'
    if path.exists():
        try:
            active = []
            for line in read(path).splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError('invalid task row')
                if row.get('status') in ('in_progress','blocked') or (bead and row.get('id') == bead):
                    active.append(row)
            active.sort(key=lambda row: row.get('id') != bead)
            for row in active[:6]:
                summary.append('Task '+clip(row.get('id'),50)+' '+clip(row.get('status'),20)+
                               '; owner '+clip(row.get('assignee','unknown'),50))
                sections.append(('task', 'Task export (freshness unknown): '+packed({
                    k:clip(row.get(k,'unknown'), 180) for k in ('id','status','assignee','title','notes')})))
            if len(active) > 6:
                sections.append(('task-overflow',f'{len(active)-6} additional active tasks in .beads/issues.jsonl; inspect before choosing work.'))
        except (OSError, ValueError, TypeError):
            sections.append(('task-error','Task export unknown: malformed, unreadable, or oversized. Check tracker before work.'))
    path = args.project/'.clavain/scratch/inflight-agents.json'
    if path.exists():
        try:
            agents = obj(path).get('agents')
            if not isinstance(agents, list):
                raise ValueError('invalid agents')
            for agent in agents[:6]:
                if not isinstance(agent, dict):
                    raise ValueError('invalid agent')
                summary.append('In-flight owner '+clip(agent.get('id'),60)+' (liveness unknown)')
                sections.append(('ownership','In-flight agents (liveness unknown): '+clip(agent.get('id'))+' '+clip(agent.get('task'))))
            if len(agents) > 6:
                sections.append(('ownership-overflow','Additional owners in .clavain/scratch/inflight-agents.json; inspect before dispatch.'))
        except (OSError, ValueError, TypeError):
            sections.append(('ownership-error','In-flight ownership unknown: inspect manifest and live reservations before editing.'))
    if (args.project/'HANDOFF.md').exists():
        sections.append(('handoff','HANDOFF.md found; read when resuming its task.'))
    if (args.project/'.claude/clodex-toggle.flag').exists():
        sections.append(('mode','INTERSERVE MODE: ON; use governed role dispatch and retain independent review.'))
    return ([('state-summary','Current local state (verify freshness):\n'+'\n'.join(summary))] if summary else []) + sections


def drift_sections(args):
    path = args.project/'.interwatch/drift.json'
    if not path.exists():
        return []
    try:
        watch = obj(path).get('watchables', {})
        if not isinstance(watch, dict):
            raise ValueError('invalid watchables')
        rows = [(name, row) for name, row in watch.items() if isinstance(row,dict) and row.get('confidence') in ('Medium','High','Certain')]
        rows.sort(key=lambda item: float(item[1].get('score',0)), reverse=True)
        if rows:
            return [('drift','Drift detected (snapshot freshness unknown): '+', '.join(clip(name,60)+' ('+clip(row.get('path'),100)+')' for name,row in rows[:3]))]
    except (OSError,ValueError,TypeError):
        return [('drift-unknown','Document drift unknown: unreadable snapshot.')]
    return []


def contract(args):
    spec = importlib.util.spec_from_file_location('startup_contract', args.source/'scripts/sync-agent-instructions.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    body, metadata = module.render(args.source, args.host, portable_policy=True)
    try:
        existing = read(args.instruction_file).decode()
    except (OSError, ValueError, UnicodeError):
        existing = ''
    if body.strip() in existing:
        return '', metadata, 'current'
    explicit, explicit_meta = module.render(args.source, args.host, portable_policy=False)
    if explicit.strip() in existing:
        return '', explicit_meta, 'current'
    # An older managed block must be reconciled explicitly, not duplicated.
    if MARKER in existing:
        return '', metadata, 'stale; synchronize selected instruction block before governed dispatch'
    return body, metadata, 'injected'


def envelope(context):
    return packed({'hookSpecificOutput':{'hookEventName':'SessionStart','additionalContext':context}})+'\n'


def assemble(sections):
    kept, dropped = [], []
    for name, value in sections:
        candidate = '\n\n'.join(kept+[value])
        # Reserve space for a visible omitted-section warning.
        if len(envelope(candidate).encode()) <= LIMIT-250:
            kept.append(value)
        else:
            dropped.append(name)
    if dropped:
        kept.append('Some startup sections omitted by byte budget; full sources and private doctor diagnostics remain available. Fresh task/ownership checks are required.')
    output = envelope('\n\n'.join(kept))
    assert len(output.encode()) <= LIMIT
    return output, dropped


def finish_context(sections, freshness, instruction_status):
    """Derive the status from the actual final selection, including error paths."""
    priority = {'telemetry': 0, 'boundaries': 1, 'status': 2, 'contract': 3,
                'state-summary': 4, 'session-identity': 5, 'active-task': 6,
                'mode': 7, 'ownership-error': 7, 'task-error': 7, 'runtime-blocker': 7,
                'routing': 8, 'ownership': 9, 'task': 10}
    ordered = sorted(sections, key=lambda section: priority.get(section[0], 11))
    def with_status(status):
        text = f'Startup snapshot: {freshness}. Instruction contract: {status}. Run scripts/startup.py refresh or doctor explicitly for diagnostics.'
        return [(name, text if name == 'status' else value) for name, value in ordered]
    output, dropped = assemble(with_status(instruction_status))
    if 'contract' in dropped:
        instruction_status = 'unknown; NOT injected. Load the selected operating contract before governed work'
        # Remove the unfit body so a longer status cannot change the decision.
        ordered = [(name, value) for name, value in ordered if name != 'contract']
        output, dropped = assemble(with_status(instruction_status))
        dropped.append('contract')
    return output, dropped, instruction_status


def private_regular(fd):
    info = os.fstat(fd)
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) & 0o077 or info.st_nlink != 1):
        raise ValueError('ledger and lock must be private regular files with one link')


@contextlib.contextmanager
def ledger_lock(args, timeout=0.1):
    directory = private_dir(args)
    fd = os.open(directory/'hook-health.lock', os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_NONBLOCK, 0o600)
    try:
        private_regular(fd)
        deadline = time.monotonic()+timeout
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX|fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError('private ledger lock busy')
                time.sleep(min(0.01, max(0, deadline-time.monotonic())))
        yield directory
    finally:
        os.close(fd)


def archive_ledger(args):
    """Explicit maintenance only. The hash-bearing name survives interrupted refresh."""
    with ledger_lock(args, timeout=10) as directory:
        path = directory/'hook-health.jsonl'
        try:
            fd = os.open(path, os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        except FileNotFoundError:
            return {'status':'absent'}
        with os.fdopen(fd, 'rb') as stream:
            private_regular(stream.fileno())
            info = os.fstat(stream.fileno())
            sha = hashlib.sha256(); observed = 0
            while chunk := stream.read(1024*1024):
                sha.update(chunk); observed += len(chunk)
            os.fsync(stream.fileno())
            after = os.fstat(stream.fileno())
            if (observed != info.st_size or after.st_size != observed
                    or after.st_mtime_ns != info.st_mtime_ns
                    or path.stat().st_ino != info.st_ino):
                raise ValueError('ledger changed during archival; preserve it and finish legacy writers before retrying')
            name = 'hook-health-archive-'+sha.hexdigest()+'-'+uuid.uuid4().hex+'.jsonl'
            os.rename(path, directory/name)
        directory_fd = os.open(directory, os.O_RDONLY|os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return {'status':'archived','path':str(directory/name),'sha256':sha.hexdigest(),'size_bytes':observed}


def telemetry(args, record):
    # Open the active inode only after acquiring the archival lock. A maintenance
    # collision may lose telemetry coverage, never delay or fail host startup.
    with ledger_lock(args) as directory:
        fd = os.open(directory/'hook-health.jsonl', os.O_WRONLY|os.O_APPEND|os.O_CREAT|os.O_NOFOLLOW|os.O_NONBLOCK, 0o600)
        try:
            private_regular(fd)
            before = os.fstat(fd).st_size
            row = (packed(record)+'\n').encode()
            if os.write(fd, row) != len(row):
                os.ftruncate(fd, before)
                raise OSError('incomplete telemetry append')
        finally:
            os.close(fd)


def render(args, current, payload, started):
    freshness, snapshot = snapshot_status(args, current)
    body, meta, instruction_status = contract(args)
    sections = [('boundaries','Clavain startup is context only. Live reservations, task ownership, blockers, required review and acceptance prerequisites need fresh authoritative checks before action. Continue authorized work; publication needs its existing authority. Missing evidence is unknown.'),
                ('routing','Use clavain:using-clavain for substantive work, then task-relevant skills from the current catalog. Reuse valid context on resume; refresh only changed or missing evidence.'),
                ('status',f'Startup snapshot: {freshness}. Instruction contract: {instruction_status}. Run scripts/startup.py refresh or doctor explicitly for diagnostics.')]
    if body:
        sections.append(('contract',body))
    session = payload.get('session_id')
    if isinstance(session, str) and session:
        sections.insert(2, ('session-identity', 'Native session identity: '+clip(session,100)+
                               '. For child dispatch set DISPATCH_SESSION_ID='+shlex.quote(clip(session,128))+
                               '; use this explicit identity for task attribution. Startup does not write host environment files.'))
    # Limit individual fields, keep critical state before optional diagnostics.
    tasks = task_sections(args, payload)
    sections[2:2] = tasks[:1]
    sections.extend(tasks[1:])
    if snapshot:
        observed = snapshot.get('installation',{})
        sections.append(('installation',f'Installation at snapshot ({freshness}): {observed.get("status","unknown")}; this is not fresh host verification.'))
        audit = snapshot.get('runtime_audit', {})
        result = audit.get('result', {}) if isinstance(audit, dict) else {}
        for finding in result.get('findings', [])[:3]:
            if isinstance(finding, dict):
                sections.insert(2, ('runtime-blocker', f'Runtime evidence finding ({freshness} snapshot; recheck live): '+
                                  clip(finding.get('bead_id'))+' '+clip(finding.get('message'))+' '+clip(finding.get('action'))))
    sections.extend(drift_sections(args))
    sections.append(('diagnostics','Setup, repair, service startup, inventory refresh and cache maintenance are explicit operations. No passing-result caching or capability pruning.'))
    output, dropped, instruction_status = finish_context(sections, freshness, instruction_status)
    record = {'schema_version':SCHEMA,'event':'hook_health','hook':'clavain/SessionStart',
              'timestamp':time.time(),'host':args.host,'host_version':payload.get('host_version'),
              'session_id':payload.get('session_id'),'run_id':payload.get('run_id') or os.environ.get('IC_RUN_ID'),
              'task_id':payload.get('task_id') or os.environ.get('CLAVAIN_BEAD_ID'),
              'model':payload.get('model'),'effort':payload.get('reasoning_effort'),
              'identity_source':'hook_payload; unavailable fields are null',
              'instruction_hash':meta['contract_hash'],'instruction_status':instruction_status,
              'context_identity':current,'cache_freshness':freshness,
              'duration_ms':round((time.monotonic()-started)*1000,3),'exit_status':0,
              'status':'ok' if freshness == 'fresh' and instruction_status in ('current','injected') else 'unknown',
              'mutation_category':'private-telemetry-only','serialized_bytes':len(output.encode()),
              'injected_bytes':len(json.loads(output)['hookSpecificOutput']['additionalContext'].encode()),
              'dropped_sections':dropped,'independent_acceptance':None}
    if args.telemetry:
        try:
            telemetry(args, record)
        except (OSError, ValueError, RuntimeError):
            sections.insert(0,('telemetry','Startup telemetry unavailable; hook coverage is unknown.'))
            output, _, _ = finish_context(sections, freshness, instruction_status)
    return output


def main():
    started = time.monotonic()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=['render','refresh','doctor'])
    parser.add_argument('--source',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--project',type=Path,default=Path.cwd())
    parser.add_argument('--host',default='claude',choices=['claude','codex','kimi','gemini','hermes','opencode','cursor','vscode'])
    parser.add_argument('--state-dir',type=Path,default=Path(os.environ.get('CLAVAIN_STARTUP_STATE_DIR', str(Path('/var/tmp')/f'clavain-startup-{os.getuid()}'))),
                        help='Private state outside worktrees (including homes tracked by Git)')
    parser.add_argument('--installed-manifest',type=Path,default=Path.home()/'.claude/plugins/installed_plugins.json')
    parser.add_argument('--instruction-file',type=Path)
    parser.add_argument('--telemetry',action='store_true')
    parser.add_argument('--archive-ledger',action='store_true',help='Refresh only: retain the active ledger in a private hash-named archive')
    parser.add_argument('--runtime-audit',type=Path,help='Explicit refresh-only runtime audit script')
    parser.add_argument('--source-repo',type=Path,help='Doctor/refresh: verify recorded source version against this repository')
    args = parser.parse_args()
    if args.archive_ledger and args.operation != 'refresh':
        parser.error('--archive-ledger requires refresh')
    if args.instruction_file is None:
        if args.host not in ('claude', 'codex'):
            parser.error('--instruction-file is required for this host; select its actual native surface')
        args.instruction_file = Path.home()/('.codex/AGENTS.md' if args.host == 'codex' else '.claude/CLAUDE.md')
    try:
        current = identity(args)
        if args.operation == 'render':
            try:
                payload = json.loads(sys.stdin.read(65537) or '{}')
                if not isinstance(payload,dict):
                    raise ValueError('expected object')
            except (ValueError,UnicodeError):
                payload = {'source':'unknown'}
            print(render(args,current,payload,started),end='')
            return 0
        if args.operation == 'refresh':
            data = refresh(args,current)
        else:
            freshness, snapshot = snapshot_status(args,current)
            data = {'schema_version':SCHEMA,'installation':installation(args.source,args.installed_manifest,args.source_repo),
                    'cache_freshness':freshness,'identity':current,'recent_hook_issues':[],
                    'behaviorally_verified':False}
            try:
                rows = []
                for line in read_private(args, args.state_dir/'hook-health.jsonl', tail=True):
                    row = json.loads(line)
                    if row.get('context_identity') == current:
                        rows.append(row)
                # Current health is judged after the most recent refresh; old failures remain in the ledger.
                since = snapshot.get('created_at', 0) if snapshot else 0
                rows = [row for row in rows if row.get('timestamp', 0) >= since]
                for row in rows:
                    if row.get('status') != 'ok' or row.get('serialized_bytes',LIMIT+1)>LIMIT or row.get('duration_ms',1001)>1000:
                        data['recent_hook_issues'].append(row)
                data['ledger_status'] = 'observed' if rows else 'unknown'
                if not rows:
                    data['ledger_reason'] = 'No current host/source/configuration event after latest refresh.'
            except (OSError,ValueError,TypeError,AttributeError) as error:
                data['ledger_status'] = 'unknown'
                data['ledger_reason'] = type(error).__name__+': private ledger unavailable or invalid.'
        print(json.dumps(data,indent=2))
        return int(args.operation == 'doctor' and (data['installation']['status'] != 'ok' or data['cache_freshness'] != 'fresh' or data['recent_hook_issues'] or data.get('ledger_status') == 'unknown'))
    except (OSError,ValueError,RuntimeError,KeyError,TypeError) as error:
        if args.operation == 'render':
            print(envelope('Clavain startup unknown: '+type(error).__name__+'. Read the selected using-clavain skill and verify task, ownership, authority and acceptance prerequisites before action.'),end='')
            return 0
        print(json.dumps({'status':'error','error':str(error)}))
        return 1


if __name__ == '__main__':
    sys.dont_write_bytecode = True
    raise SystemExit(main())
