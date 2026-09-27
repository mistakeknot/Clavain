"""Per-integration mode resolution and the integration registry loader.

See the plan's "Flags and integration registry" section. This module reads
only what it is handed (an env mapping and an already-loaded registry dict);
it never reads `os.environ` or the filesystem itself, so callers control
exactly what "unset" means in a test.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Mapping

from clavain_selector.contract import AuthorizationPolicy, Point

GLOBAL_KILL_SWITCH = "CLAVAIN_SELECTOR"
_VALID_RAW_MODES = ("off", "shadow", "active")

EMPTY_REGISTRY: dict[str, Any] = {"schema_version": 1, "integrations": {}}

# Closed key set for one integration's registry entry.
_ALLOWED_ENTRY_KEYS = frozenset({
    "flag", "points", "active_allowed", "shadow_only", "floors", "fit_questions",
    "high_entropy", "deadline_ms", "session_budget", "authorize", "preparer",
    "hooks", "owner_bead",
})

_ALLOWED_AUTHORIZE_KEYS = frozenset({"allow_all", "allow_ids", "allow_id_prefixes", "deny_ids"})
_ALLOWED_HOOK_KEYS = frozenset({"host", "point"})
_ID_LIKE_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_VALID_POINT_VALUES = frozenset(p.value for p in Point)


@dataclass(frozen=True)
class RegistryError:
    """One structural problem found in the registry by `registry_errors`.

    `message` names keys only -- never a raw value from the file -- so it is
    always safe to log or surface directly.
    """

    integration: str
    key: str
    message: str


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


def _check_id_list(entry_integration: str, key: str, value: Any, errors: list[RegistryError]) -> None:
    if not isinstance(value, list):
        errors.append(RegistryError(entry_integration, key, f"{key} must be a list"))
        return
    seen: set[Any] = set()
    for item in value:
        if not isinstance(item, str) or not _ID_LIKE_PATTERN.match(item):
            errors.append(RegistryError(entry_integration, key, f"{key} entries must match the id/prefix pattern"))
            continue
        if item in seen:
            errors.append(RegistryError(entry_integration, key, f"{key} must not repeat a value"))
        seen.add(item)


def _check_authorize_block(integration: str, entry: Mapping[str, Any], errors: list[RegistryError]) -> None:
    block = entry.get("authorize")
    if block is None:
        return
    if not isinstance(block, Mapping):
        errors.append(RegistryError(integration, "authorize", "authorize must be an object"))
        return
    bad_keys = set(block.keys()) - _ALLOWED_AUTHORIZE_KEYS
    if bad_keys:
        errors.append(RegistryError(integration, "authorize", f"authorize has unknown key(s): {sorted(bad_keys)}"))
    allow_all = block.get("allow_all", False)
    if not isinstance(allow_all, bool):
        errors.append(RegistryError(integration, "authorize", "authorize.allow_all must be a bool"))
    for key in ("allow_ids", "allow_id_prefixes", "deny_ids"):
        if key in block:
            _check_id_list(integration, f"authorize.{key}", block[key], errors)
    if allow_all is True and not bool(entry.get("shadow_only", False)):
        errors.append(RegistryError(integration, "authorize", "authorize.allow_all is only legal when shadow_only is true"))


def _check_hooks_block(integration: str, entry: Mapping[str, Any], errors: list[RegistryError]) -> None:
    hooks = entry.get("hooks")
    if hooks is None:
        return
    if not isinstance(hooks, list):
        errors.append(RegistryError(integration, "hooks", "hooks must be a list"))
        return
    for hook in hooks:
        if not isinstance(hook, Mapping):
            errors.append(RegistryError(integration, "hooks", "each hooks entry must be an object"))
            continue
        bad_keys = set(hook.keys()) - _ALLOWED_HOOK_KEYS
        if bad_keys:
            errors.append(RegistryError(integration, "hooks", f"hooks entry has unknown key(s): {sorted(bad_keys)}"))
        if not isinstance(hook.get("host"), str) or not hook.get("host"):
            errors.append(RegistryError(integration, "hooks", "hooks entry.host must be a non-empty string"))
        if hook.get("point") not in _VALID_POINT_VALUES:
            errors.append(RegistryError(integration, "hooks", "hooks entry.point must be a known point"))


def registry_errors(data: Any) -> tuple[RegistryError, ...]:
    """Every structural problem in a loaded registry `dict`.

    Checks the closed per-entry key set, the `authorize` block's shape and
    the `allow_all`/`shadow_only` pairing rule, the `hooks` block's shape,
    and duplicate `{host, point}` hook pairs across integrations. An empty
    result means the registry is safe to use as-is.
    """
    errors: list[RegistryError] = []
    if not isinstance(data, Mapping):
        return (RegistryError("", "", "registry must be an object"),)
    integrations = data.get("integrations")
    if not isinstance(integrations, Mapping):
        return (RegistryError("", "integrations", "integrations must be an object"),)

    hook_owners: dict[tuple[str, Any], list[str]] = {}
    for integration, entry in integrations.items():
        if not isinstance(entry, Mapping):
            errors.append(RegistryError(str(integration), "", "integration entry must be an object"))
            continue
        bad_keys = set(entry.keys()) - _ALLOWED_ENTRY_KEYS
        if bad_keys:
            errors.append(RegistryError(integration, "", f"unknown key(s): {sorted(bad_keys)}"))
        _check_authorize_block(integration, entry, errors)
        _check_hooks_block(integration, entry, errors)
        for hook in entry.get("hooks") or []:
            if isinstance(hook, Mapping) and isinstance(hook.get("host"), str):
                hook_owners.setdefault((hook.get("host"), hook.get("point")), []).append(str(integration))

    for (host, point), owners in hook_owners.items():
        if len(owners) > 1:
            errors.append(RegistryError(",".join(sorted(owners)), "hooks", "duplicate {host, point} hook pair"))

    return tuple(errors)


def authorization_policy(registry: Mapping[str, Any], integration: str, point: "Point | str") -> AuthorizationPolicy:
    """The `AuthorizationPolicy` for one integration/point pair.

    A missing `authorize` block (or an unknown integration) denies
    everything: `allow_all=False`, empty `allow_ids`/`allow_id_prefixes`/
    `deny_ids`.
    """
    point_value = point if isinstance(point, Point) else Point(point)
    integrations = registry.get("integrations", {}) if isinstance(registry, Mapping) else {}
    entry = integrations.get(integration) or {}
    block = entry.get("authorize") or {}
    if not isinstance(block, Mapping):
        block = {}
    return AuthorizationPolicy(
        integration=integration,
        point=point_value,
        allow_all=bool(block.get("allow_all", False)),
        allow_ids=frozenset(block.get("allow_ids") or ()),
        allow_id_prefixes=tuple(block.get("allow_id_prefixes") or ()),
        deny_ids=frozenset(block.get("deny_ids") or ()),
    )


def hook_integration(registry: Mapping[str, Any], host: str, point: "Point | str") -> str | None:
    """The one integration whose `hooks` list contains `{host, point}`, or `None`.

    `None` both when no integration lists the pair and when more than one
    does (an ambiguous registry is never resolved silently; `registry_errors`
    reports the duplicate separately).
    """
    point_value = point.value if isinstance(point, Point) else str(point)
    integrations = registry.get("integrations", {}) if isinstance(registry, Mapping) else {}
    matches: list[str] = []
    for integration, entry in integrations.items():
        if not isinstance(entry, Mapping):
            continue
        for hook in entry.get("hooks") or []:
            if isinstance(hook, Mapping) and hook.get("host") == host and hook.get("point") == point_value:
                matches.append(integration)
                break
    if len(matches) == 1:
        return matches[0]
    return None


def load_registry(path: str | Path) -> dict[str, Any]:
    """Load `config/selector-integrations.json`, failing closed to an empty registry.

    Any I/O error, malformed JSON, or a structural problem reported by
    `registry_errors` (unknown key, malformed `authorize`/`hooks` block,
    duplicate hook pair, ...) resolves to an empty registry, so a corrupt or
    invalid config file turns every integration off rather than raising or
    silently ignoring the problem.
    """
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return dict(EMPTY_REGISTRY)
    if not isinstance(data, dict) or not isinstance(data.get("integrations"), dict):
        return dict(EMPTY_REGISTRY)
    if registry_errors(data):
        return dict(EMPTY_REGISTRY)
    return data
