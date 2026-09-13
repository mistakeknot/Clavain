"""Hermes native adapter. No personality, provider, or credential mutations."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def before_tool(tool_name, args, **kwargs):
    if tool_name == 'delegate_task':
        return {'action': 'block', 'message': 'Use clavain_dispatch with an explicit role and decision context. Native delegation cannot preserve the Clavain contract and may inherit the parent model.'}


def inject_context(**kwargs):
    try:
        result = subprocess.run([sys.executable, str(ROOT/'scripts/sync-agent-instructions.py'), '--source', str(ROOT), '--host', 'hermes', '--render'], capture_output=True, text=True, timeout=5, check=True)
        return {'context': result.stdout}
    except (OSError, subprocess.SubprocessError):
        return {'context': 'Clavain reasoning contract unavailable. Governed delegation is blocked until the selected installation is repaired. Configuration does not change the running parent model.'}


def observe(**kwargs):
    # Existing host telemetry owns session/model and child outcome storage.
    # Never copy prompts, results, personalities or credentials to another store.
    return None


def governed_dispatch(args, **kwargs):
    required = ('role', 'context_file', 'prompt_file', 'project', 'output')
    if any(not isinstance(args.get(k), str) or not args[k] for k in required):
        return json.dumps({'error': 'role, context_file, prompt_file, project and output are required'})
    env = dict(os.environ, CLAVAIN_ROUTING_POLICY=str(ROOT/'config/routing.yaml'), CLAVAIN_DECISION_CONTEXT=str(Path(args['context_file']).resolve()))
    if args.get('policy_profile'):
        env['CLAVAIN_POLICY_PROFILE'] = args['policy_profile']
    cmd = ['bash', str(ROOT/'scripts/dispatch.sh'), '--role', args['role'], '--prompt-file', args['prompt_file'], '-C', args['project'], '-o', args['output']]
    if args.get('producer_identity'):
        cmd += ['--producer-identity', args['producer_identity']]
    # dispatch.sh owns timeout, fallback, output and routing/calibration receipts.
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    return json.dumps({'exit_code': result.returncode, 'output': args['output'], 'diagnostic': result.stderr[-4000:], 'routing': 'dispatch-enforced', 'parent_model_changed': False})


def register(ctx):
    ctx.register_hook('pre_tool_call', before_tool)
    ctx.register_hook('pre_llm_call', inject_context)
    ctx.register_hook('on_session_start', observe)
    ctx.register_hook('subagent_stop', observe)
    ctx.register_tool(name='clavain_dispatch', toolset='clavain', handler=governed_dispatch, schema={
        'name': 'clavain_dispatch',
        'description': 'Delegate governed work using Clavain role selection with model, effort, independence and policy receipts.',
        'parameters': {'type': 'object', 'properties': {k: {'type': 'string'} for k in ('role', 'context_file', 'prompt_file', 'project', 'output', 'producer_identity', 'policy_profile')}, 'required': ['role', 'context_file', 'prompt_file', 'project', 'output']}})
