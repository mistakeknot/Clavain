"""Per-integration mode resolution and the integration registry loader.

See the plan's "Flags and integration registry" section. This module reads
only what it is handed (an env mapping and an already-loaded registry dict);
it never reads `os.environ` or the filesystem itself, so callers control
exactly what "unset" means in a test.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Mapping

GLOBAL_KILL_SWITCH = "CLAVAIN_SELECTOR"
_VALID_RAW_MODES = ("off", "shadow", "active")

EMPTY_REGISTRY: dict[str, Any] = {"schema_version": 1, "integrations": {}}


@dataclass(frozen=True)
class ResolvedMode:
    """The result of resolving one integration's flag against the registry."""

    mode: str  # "off" | "shadow" | "active"
    active_denied: bool = False
    unknown_value: str | None = None
    flags: dict[str, Any] = field(default_factory=dict)


def _flag_name(integration: str, registry: Mapping[str, Any]) -> str:
    entry = registry.get("integrations", {}).get(integration) or {}
    flag = entry.get("flag")
    if isinstance(flag, str) and flag:
        return flag
    return f"CLAVAIN_SELECTOR_{integration.upper()}"


def resolve_mode(integration: str, env: Mapping[str, str], registry: Mapping[str, Any]) -> ResolvedMode:
    """Resolve the effective mode for `integration`.

    - The global kill switch (`CLAVAIN_SELECTOR=off`, case-insensitive) forces
      every integration off, unconditionally.
    - An integration absent from the registry resolves to off.
    - Any flag value other than off/shadow/active (case-insensitive) resolves
      to off.
    - `active` resolves to `shadow` (with `flags.active_denied: true`) unless
      the registry entry has `active_allowed: true` and `shadow_only` is not
      true.
    """
    kill = str(env.get(GLOBAL_KILL_SWITCH, "")).strip().lower()
    if kill == "off":
        return ResolvedMode("off")

    integrations = registry.get("integrations", {}) if isinstance(registry, Mapping) else {}
    entry = integrations.get(integration)
    if entry is None:
        return ResolvedMode("off")

    flag_name = _flag_name(integration, registry)
    raw_value = env.get(flag_name)
    raw = str(raw_value).strip().lower() if raw_value is not None else "off"
    unknown_value = None
    if raw not in _VALID_RAW_MODES:
        unknown_value = raw_value
        raw = "off"

    if raw == "active":
        active_allowed = bool(entry.get("active_allowed", False))
        shadow_only = bool(entry.get("shadow_only", False))
        if active_allowed and not shadow_only:
            return ResolvedMode("active")
        return ResolvedMode("shadow", active_denied=True, flags={"active_denied": True})

    return ResolvedMode(raw, unknown_value=unknown_value)


def load_registry(path: str | Path) -> dict[str, Any]:
    """Load `config/selector-integrations.json`, failing closed to an empty registry.

    Any I/O error or malformed JSON (including a JSON value that is not an
    object with an `integrations` object) resolves to an empty registry, so a
    corrupt config file turns every integration off rather than raising.
    """
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return dict(EMPTY_REGISTRY)
    if not isinstance(data, dict) or not isinstance(data.get("integrations"), dict):
        return dict(EMPTY_REGISTRY)
    return data
