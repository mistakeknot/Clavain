#!/usr/bin/env python3
"""Merge an operator routing overlay over the neutral routing policy."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / "config" / "routing.yaml"
DEFAULT_CONFIG = Path("~/.config/aleph-orchestration/operator.toml")

OPEN_MAPS = frozenset({
    ("subagents", "overrides"),
    ("subagents", "phases"),
    ("reasoning", "profiles"),
    ("reasoning", "project_profiles"),
    ("reasoning", "project_aliases"),
    ("dispatch", "model_aliases"),
    ("dispatch", "roles"),
    ("dispatch", "tiers"),
    ("dispatch", "effort_floors"),
    ("dispatch", "effort_floor_exemptions"),
    ("dispatch", "fallback"),
    ("executor_routing", "classes"),
})


class OverlayError(Exception):
    pass


def _where(path):
    return ".".join(path) if path else "<top level>"


def _kind(value):
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "mapping"
    return type(value).__name__


def _check_free(value, path):
    if value is None:
        raise OverlayError(f"{_where(path)}: null is not allowed")
    if isinstance(value, dict):
        for key, item in value.items():
            _check_free(item, path + (str(key),))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _check_free(item, path + (str(index),))


def merge(base, overlay, path=()):
    if overlay is None:
        raise OverlayError(f"{_where(path)}: null is not allowed")
    if _kind(base) != _kind(overlay):
        raise OverlayError(f"{_where(path)}: expected {_kind(base)}, found {_kind(overlay)}")
    if isinstance(base, list):
        _check_free(overlay, path)
        return list(overlay)
    if not isinstance(base, dict):
        return overlay
    open_map = path in OPEN_MAPS
    merged = dict(base)
    for key, value in overlay.items():
        if not isinstance(key, str):
            raise OverlayError(f"{_where(path)}: key {key!r} is not a string")
        here = path + (key,)
        if key in base:
            merged[key] = merge(base[key], value, here)
        elif open_map:
            _check_free(value, here)
            merged[key] = value
        else:
            raise OverlayError(f"{_where(here)}: unknown key")
    return merged


def load_yaml(path, what):
    try:
        text = Path(path).read_bytes()
    except OSError as exc:
        raise OverlayError(f"{what} {path}: {exc.strerror or exc}") from exc
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise OverlayError(f"{what} {path}: malformed YAML: {exc}") from exc
    return text, data


def build(base_path, overlay_path):
    base_bytes, base = load_yaml(base_path, "policy")
    if not isinstance(base, dict):
        raise OverlayError(f"policy {base_path}: top level is not a mapping")
    overlay_bytes, overlay = load_yaml(overlay_path, "overlay")
    if overlay is None:
        raise OverlayError(f"overlay {overlay_path}: empty or null document (write {{}} for no overrides)")
    if not isinstance(overlay, dict):
        raise OverlayError(f"overlay {overlay_path}: top level is not a mapping")
    merged = merge(base, overlay)
    text = yaml.safe_dump(merged, sort_keys=False, default_flow_style=False, allow_unicode=True, width=10000)
    digest = hashlib.sha256(base_bytes + b"\0" + overlay_bytes).hexdigest()
    return text, digest


def cache_dir():
    explicit = os.environ.get("CLAVAIN_ROUTING_CACHE_DIR")
    if explicit:
        return Path(explicit).expanduser()
    root = os.environ.get("XDG_CACHE_HOME") or str(Path("~/.cache").expanduser())
    return Path(root) / "clavain" / "routing-policy"


def write_resolved(text, digest, out=None):
    if out is None:
        directory = cache_dir()
        target = directory / f"routing.{digest}.yaml"
        if target.exists() and target.read_text() == text:
            return target
    else:
        target = Path(out)
        directory = target.parent
    try:
        directory.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=directory, prefix=".routing-", suffix=".tmp")
        with os.fdopen(fd, "w") as handle:
            handle.write(text)
        os.replace(tmp, target)
    except OSError as exc:
        raise OverlayError(f"cannot write resolved policy {target}: {exc.strerror or exc}") from exc
    return target


def operator_overlay_path(config):
    orch = os.environ.get("CLAVAIN_ORCH_BIN") or shutil.which("orch")
    if not orch:
        raise OverlayError(f"operator config {config} exists but the orch tool is not on PATH (set CLAVAIN_ORCH_BIN)")
    try:
        proc = subprocess.run([orch, "snapshot", "--json", "--config", str(config)],
                              capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise OverlayError(f"orch snapshot failed for {config}: {exc}") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip().splitlines()
        raise OverlayError(f"orch snapshot failed for {config}: {detail[-1] if detail else 'exit ' + str(proc.returncode)}")
    try:
        operator = json.loads(json.loads(proc.stdout)["operator.json"])
        raw = operator.get("seats", {}).get("routing_overlay", "")
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise OverlayError(f"orch snapshot for {config} is not usable: {exc}") from exc
    if not isinstance(raw, str):
        raise OverlayError("operator config seats.routing_overlay is not a string")
    if not raw:
        return None
    expanded = Path(raw).expanduser()
    if not expanded.is_absolute():
        raise OverlayError(f"operator config seats.routing_overlay {raw!r} is not an absolute path")
    return expanded


def overlay_path():
    explicit = os.environ.get("CLAVAIN_ROUTING_OVERLAY")
    if explicit is not None:
        if not explicit:
            return None
        path = Path(explicit).expanduser()
        if not path.is_file():
            raise OverlayError(f"CLAVAIN_ROUTING_OVERLAY {explicit} is not a file")
        return path
    configured = os.environ.get("ALEPH_ORCH_CONFIG")
    if configured:
        config = Path(configured).expanduser()
        if not config.is_file():
            raise OverlayError(f"ALEPH_ORCH_CONFIG {configured} is not a file")
    else:
        config = DEFAULT_CONFIG.expanduser()
        if not config.is_file():
            return None
    path = operator_overlay_path(config)
    if path is None:
        return None
    if not path.is_file():
        raise OverlayError(f"routing overlay {path} named by {config} does not exist")
    return path


def effective(base_path=BASE, overlay=None, out=None):
    chosen = Path(overlay) if overlay else overlay_path()
    if chosen is None:
        return Path(base_path), None
    text, digest = build(base_path, chosen)
    return write_resolved(text, digest, out), chosen


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["path", "policy", "resolve", "check"])
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument("--overlay", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "check":
            chosen = args.overlay or overlay_path()
            if chosen is None:
                print("no overlay configured; neutral defaults apply")
                return 0
            _, digest = build(args.base, chosen)
            print(f"ok overlay={chosen} sha256={hashlib.sha256(Path(chosen).read_bytes()).hexdigest()} resolved={digest}")
            return 0
        resolved, chosen = effective(args.base, args.overlay, args.out)
    except OverlayError as exc:
        print(f"routing overlay: {exc}", file=sys.stderr)
        return 1
    if chosen is None and args.command == "path":
        return 0
    print(resolved)
    return 0


if __name__ == "__main__":
    sys.exit(main())
