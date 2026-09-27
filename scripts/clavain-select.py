#!/usr/bin/env python3
"""Command-line selector interface (mk-42j9.7 Task 7/8).

Provides the `hook` subcommand for the selector-hook.sh wrapper. Task 7 only
implements `hook`; Task 8 adds other subcommands.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import clavain_selector.adapters.base as adapters_base
import clavain_selector.adapters.claude_code as claude_code_adapter
import clavain_selector.adapters.stubs as stub_adapters
import clavain_selector.contract as contract
import clavain_selector.flags as flags
import clavain_selector.preparers as preparers
import clavain_selector.selector as selector
from clavain_selector.contract import Point, SessionRef


def _load_registry() -> dict:
    """Load the integration registry."""
    override = os.environ.get("CLAVAIN_SELECTOR_REGISTRY")
    registry_path = (
        Path(override).expanduser()
        if override
        else Path(__file__).resolve().parent.parent / "config" / "selector-integrations.json"
    )
    return flags.load_registry(registry_path)


def _get_host_adapter(host: str) -> adapters_base.HostAdapter:
    """Get the appropriate host adapter by name."""
    adapter_types = {
        "claude-code": claude_code_adapter.ClaudeCodeAdapter,
        "codex": stub_adapters.CodexAdapter,
        "hermes": stub_adapters.HermesAdapter,
        "kimi": stub_adapters.KimiAdapter,
        "pi": stub_adapters.PiAdapter,
        "bb": stub_adapters.BbAdapter,
    }
    adapter_type = adapter_types.get(host)
    if adapter_type is None:
        raise ValueError("unknown host adapter")
    return adapter_type()


def main_hook(args) -> int:
    """Handle the `hook` subcommand.

    Resolves the integration via flags.hook_integration(registry, host, point).
    If unique match: prepare candidates and run selection in shadow mode.
    If zero or multiple matches: exit 0 with empty output, no record, no socket.
    """
    point_str = args.point
    host = args.host

    try:
        point = Point(point_str)
    except ValueError:
        # Invalid point
        return 0

    # The global kill switch is resolved before anything else is loaded.
    env = dict(os.environ)
    if str(env.get(flags.GLOBAL_KILL_SWITCH, "")).strip().lower() == "off":
        return 0

    # Load registry and resolve integration
    registry = _load_registry()
    integration = flags.hook_integration(registry, host, point)

    if integration is None:
        # No unique match
        return 0

    # Flag off is inert: stdin is never read and the preparer never runs.
    if flags.resolve_mode(integration, env, registry).mode == "off":
        return 0

    # Get project root
    project_root = Path(os.environ.get("CLAUDE_PROJECT_DIR", "."))
    try:
        project_root = project_root.resolve()
    except Exception:
        return 0

    # Get adapter and parse stdin
    try:
        adapter = _get_host_adapter(host)
    except Exception:
        return 0

    try:
        raw_stdin = sys.stdin.buffer.read()
        event = adapter.parse_event(point, raw_stdin)
    except Exception:
        return 0

    # Prepare candidates
    try:
        prepared = preparers.prepare(registry, integration, point, event, project_root)
    except preparers.NotPrepared:
        return 0

    # Run selection under the registry/flag-resolved mode.
    try:
        session = SessionRef(host_session_id=event.session_id or "unknown")
        now = int(time.time() * 1000)

        result = selector.select(
            prepared,
            session=session,
            adapter=adapter,
            env=env,
            now=now,
            registry=registry,
            event=event,
        )

        # Native fallbacks emit no bytes. Shadow rendering is empty for the
        # reference adapter; active rendering returns the bound host effect.
        if result.outcome.kind in ("shadow", "emitted"):
            output = adapter.render(point, result.outcome, event)
            sys.stdout.buffer.write(output)
    except Exception:
        pass

    return 0


def main() -> int:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Clavain selector CLI")
    subparsers = parser.add_subparsers(dest="subcommand", help="Subcommand")

    # Hook subcommand
    hook_parser = subparsers.add_parser("hook", help="Hook integration point")
    hook_parser.add_argument("--point", required=True, help="Integration point (e.g., pre_tool)")
    hook_parser.add_argument("--host", required=True, help="Host name (e.g., claude-code)")
    hook_parser.set_defaults(func=main_hook)

    args = parser.parse_args()

    if not hasattr(args, "func"):
        parser.print_help()
        return 1

    try:
        return args.func(args)
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
