#!/usr/bin/env python3
"""Probe an installed Hermes hook runtime in a fresh profile, without LLM calls."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--hermes-source', type=Path, required=True)
args = p.parse_args()
with tempfile.TemporaryDirectory(prefix='clavain-hermes-probe-') as home:
    os.environ['HERMES_HOME'] = home
    sys.path.insert(0, str(args.hermes_source.resolve()))
    from hermes_cli.plugins import PluginManifest, PluginContext, get_plugin_manager, get_pre_tool_call_block_message
    from tools.registry import registry
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location('clavain_adapter', root/'adapters/hermes/__init__.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    manager = get_plugin_manager()
    module.register(PluginContext(PluginManifest(name='clavain', version='1.0.0', path=str(root/'adapters/hermes')), manager))
    blocked = get_pre_tool_call_block_message('delegate_task', {}, session_id='isolated-probe')
    assert blocked and 'inherit' in blocked
    assert get_pre_tool_call_block_message('read_file', {}) is None
    context = manager.invoke_hook('pre_llm_call', model='unchanged-parent')
    assert 'frontier' in context[0]['context']
    assert registry.get_entry('clavain_dispatch', scope=manager.scope_key) is not None
    print(json.dumps(dict(host='hermes', native_hook_verified=True, delegation_blocked=True,
                         tool_registered=True, parent_model_changed=False, model_execution_verified=False)))
