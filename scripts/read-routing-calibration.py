#!/usr/bin/env python3
"""Strict, exact reader for B3 agent-model calibration artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


class CalibrationError(ValueError):
    pass


def _exact_number(raw: str) -> Decimal:
    try:
        approximate = float(raw)
        exact = Decimal(raw)
    except (InvalidOperation, OverflowError, ValueError) as exc:
        raise CalibrationError("invalid number") from exc
    if not math.isfinite(approximate):
        raise CalibrationError("numeric overflow")
    if approximate == 0 and exact != 0:
        raise CalibrationError("numeric underflow")
    return exact


def _reject_constant(raw: str) -> None:
    raise CalibrationError(f"non-finite number {raw}")


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CalibrationError(f"duplicate key {key!r}")
        result[key] = value
    return result


def _decode(data: bytes) -> Any:
    try:
        return json.loads(
            data,
            parse_int=_exact_number,
            parse_float=_exact_number,
            parse_constant=_reject_constant,
            object_pairs_hook=_strict_object,
        )
    except (CalibrationError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise CalibrationError(str(exc)) from exc


def _entry(value: Any, *, allow_phases: bool) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CalibrationError("calibration entry must be an object")
    if "recommended_model" in value and not isinstance(value["recommended_model"], str):
        raise CalibrationError("recommended_model must be a string")
    for field in ("confidence", "evidence_sessions"):
        if field in value and not isinstance(value[field], Decimal):
            raise CalibrationError(f"{field} must be a number")
    if "propagation_eligible" in value and not isinstance(value["propagation_eligible"], bool):
        raise CalibrationError("propagation_eligible must be a boolean")
    if "phases" in value:
        phases = value["phases"]
        if not allow_phases or not isinstance(phases, dict):
            raise CalibrationError("phases must be an object and cannot be nested")
        for phase in phases.values():
            _entry(phase, allow_phases=False)
    return value


def _eligible(entry: dict[str, Any], schema: int) -> bool:
    model = entry.get("recommended_model")
    confidence = entry.get("confidence")
    sessions = entry.get("evidence_sessions")
    if model not in {"haiku", "sonnet", "opus"}:
        return False
    if not isinstance(confidence, Decimal) or confidence < Decimal("0.7") or confidence > Decimal(1):
        return False
    if not isinstance(sessions, Decimal) or sessions != sessions.to_integral_value() or sessions < Decimal(3):
        return False
    return schema == 1 or entry.get("propagation_eligible") is True


def _phase_keys(phase: str, aliases_path: Path) -> list[str]:
    if not phase:
        return []
    keys = [phase]
    try:
        groups = aliases_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return keys
    for line in groups:
        group = line.split()
        if phase in group:
            keys.extend(candidate for candidate in group if candidate != phase)
            break
    return keys


def read(path: Path, agent: str, phase: str, aliases_path: Path) -> dict[str, Any] | None:
    if not agent or not agent.rsplit(":", 1)[-1]:
        return None
    data = path.read_bytes()
    root = _decode(data)
    if not isinstance(root, dict):
        raise CalibrationError("top level must be an object")
    schema_value = root.get("schema_version")
    if not isinstance(schema_value, Decimal) or schema_value != schema_value.to_integral_value():
        raise CalibrationError("schema_version must be an integral number")
    schema = int(schema_value)
    if schema not in {1, 2, 3}:
        raise CalibrationError(f"unsupported schema {schema}")
    raw_agents = root.get("agents", {})
    if not isinstance(raw_agents, dict):
        raise CalibrationError("agents must be an object")
    agents: dict[str, dict[str, Any]] = {}
    for name, raw_entry in raw_agents.items():
        agents[name] = _entry(raw_entry, allow_phases=True)

    selected = agents.get(agent.rsplit(":", 1)[-1])
    if selected is None:
        return None
    for key in _phase_keys(phase, aliases_path):
        phase_entry = selected.get("phases", {}).get(key)
        if phase_entry is not None and _eligible(phase_entry, schema):
            selected = phase_entry
            break
    else:
        if not _eligible(selected, schema):
            return None

    return {
        "model": selected["recommended_model"],
        "sha256": hashlib.sha256(data).hexdigest(),
        "schema_version": schema,
        "authoritative": schema in {2, 3},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("agent")
    parser.add_argument("phase")
    parser.add_argument("aliases", type=Path)
    args = parser.parse_args()
    try:
        result = read(args.path, args.agent, args.phase, args.aliases)
    except (CalibrationError, OSError) as exc:
        print(f"[routing-calibration] invalid artifact: {exc}", file=sys.stderr)
        return 2
    if result is not None:
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
