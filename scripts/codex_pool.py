#!/usr/bin/env python3
"""Scope one pooled Codex process and reconcile its JSON turns with hub evidence.

Pass raw events through for the existing budget supervisor. The terminal pool
record has a distinct type so its normalized counts never double count turns.
"""
import argparse
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import time

from pool_receipt import FIELDS, PoolAttempt


def run(args):
    def identity(model):
        proc = subprocess.run(['ic', '--json', 'route', 'identity', '--policy='+args.policy,
                               '--model='+model], capture_output=True, text=True, timeout=10)
        if proc.returncode:
            raise ValueError('pool model identity unavailable')
        return json.loads(proc.stdout)['model_identity']

    requested = identity(args.model)
    pool = PoolAttempt(args.attempt, args.receipt, 'codex')  # Admission before launch.
    total = dict.fromkeys(FIELDS, 0)
    started = done = 0
    error = ''
    cancelled = [False]
    signal.signal(signal.SIGTERM, lambda *_: cancelled.__setitem__(0, True))
    signal.signal(signal.SIGINT, lambda *_: cancelled.__setitem__(0, True))
    budget_hit = False
    child = None
    ref = None

    def consume(line):
        nonlocal started, done, budget_hit
        event = json.loads(line)
        if not isinstance(event, dict):
            raise ValueError('invalid Codex event')
        kind = event.get('type')
        if kind == 'turn.started':
            if started != done:
                raise ValueError('overlapping Codex turns')
            started += 1
        elif kind == 'turn.completed':
            if started != done + 1:
                raise ValueError('unbound Codex turn')
            usage = event['usage']
            values = [usage[k] for k in ('input_tokens', 'cached_input_tokens', 'output_tokens')]
            if any(type(v) is not int or not 0 <= v <= 2**53 for v in values):
                raise ValueError('invalid Codex usage')
            inp, cached, out = values
            if cached > inp:
                raise ValueError('Codex cache exceeds input')
            total['input_tokens'] += inp - cached
            total['cache_read_input_tokens'] += cached
            total['output_tokens'] += out
            done += 1
            budget_hit = bool(args.budget and sum(total.values()) >= args.budget)
        elif kind in ('turn.failed', 'error'):
            raise ValueError('Codex provider failed')

    try:
        command = args.command[1:] if args.command[:1] == ['--'] else args.command
        child = subprocess.Popen(command, stdin=sys.stdin, stdout=subprocess.PIPE, env=pool.child_env())
        pending = b''
        stopping_at = None
        with selectors.DefaultSelector() as sel:
            sel.register(child.stdout, selectors.EVENT_READ)
            while sel.get_map():
                if (cancelled[0] or error or budget_hit) and stopping_at is None:
                    stopping_at = time.monotonic()
                    if child.poll() is None:
                        child.send_signal(signal.SIGINT)
                if stopping_at is not None and child.poll() is None:
                    elapsed = time.monotonic() - stopping_at
                    if elapsed >= 7: child.kill()
                    elif elapsed >= 5: child.terminate()
                for key, _ in sel.select(.1):
                    data = os.read(key.fd, 65536)
                    if not data:
                        sel.unregister(key.fileobj)
                        break
                    sys.stdout.buffer.write(data)
                    sys.stdout.buffer.flush()
                    pending += data
                    while b'\n' in pending:
                        line, pending = pending.split(b'\n', 1)
                        try:
                            if len(line) > 8 << 20:
                                raise ValueError('oversized Codex event')
                            consume(line)
                        except (ValueError, KeyError, TypeError):
                            error = 'invalid or incomplete Codex accounting'
                    if len(pending) > 8 << 20:
                        raise ValueError('oversized Codex event')
        child.stdout.close()
        rc = child.wait(timeout=8)
        if pending:
            # Keep the terminal record separate even after a truncated raw line.
            print(flush=True)
            error = 'truncated Codex stream'
    except (OSError, ValueError, subprocess.SubprocessError):
        error = 'Codex accounting transport failed'
        if child is not None and child.poll() is None:
            child.kill()
            child.wait()
        rc = child.returncode if child is not None else 127
    try:
        ref = pool.finish(total)
        data = json.loads(Path(ref['path']).read_text())
        for request in data['requests']:
            if request['kind'] == 'inference':
                for hop in request['hops']:
                    if identity(hop['model']) != requested:
                        raise ValueError('pool model differs from routed model')
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        error = 'pool request accounting unavailable or unreconciled'
    success = not (error or rc or cancelled[0] or budget_hit) and 0 < started == done
    record = dict(type='pool.accounting', terminal=True, complete=success,
                  status='success' if success else 'accounting_error', backend_exit=rc, **total)
    if ref is not None:
        record['pool_receipt'] = ref
    print(json.dumps(record), flush=True)
    if not success:
        print('Codex pool accounting unavailable or invalid', file=sys.stderr)
    return (128 - rc if rc < 0 else rc) or (0 if success else 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', required=True)
    parser.add_argument('--receipt', required=True)
    parser.add_argument('--model', required=True)
    parser.add_argument('--policy', required=True)
    parser.add_argument('--budget', type=int, default=0)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.budget < 0 or not args.command:
        parser.error('command and nonnegative budget required')
    try:
        return run(args)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        print('Codex pool accounting unavailable before launch', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
