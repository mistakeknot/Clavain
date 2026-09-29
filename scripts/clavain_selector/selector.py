"""Ordered, fail-open selector orchestration (mk-42j9.7 Task 7)."""

from __future__ import annotations

import dataclasses
import inspect
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import clavain_selector.adapters.base as adapters_base
import clavain_selector.contract as contract
import clavain_selector.credentials as credentials
import clavain_selector.egress as egress
import clavain_selector.flags as flags
import clavain_selector.jev_client as jev_client
import clavain_selector.preparers as preparers
import clavain_selector.records as records
from clavain_selector.contract import FallbackReason, Point, Provenance, SessionRef


@dataclass(frozen=True)
class SelectionResult:
    """The decision, its durable record (if any), and the host-facing outcome."""

    record_dict: dict[str, Any] | None
    chosen_candidate: contract.Candidate | None
    fallback_reason: FallbackReason | None
    outcome: adapters_base.Outcome


@dataclass(frozen=True)
class _ModeDecision:
    mode: str
    flags: dict[str, Any]


class _PointMismatch(Exception):
    pass


class _ProvenanceModeError(Exception):
    pass


class _BindingMismatch(Exception):
    pass


def _resolve_mode(
    resolved: flags.ResolvedMode,
    provenance: Provenance,
    mode_override: str | None,
) -> _ModeDecision:
    """Apply the provenance cap after ordinary flag resolution.

    This remains a module seam so R12-1 tests can force a bad active result
    and independently prove the final PREPARER-only emission guard.
    """

    mode_flags = dict(resolved.flags)
    if mode_override == "eval":
        if provenance is Provenance.EXTERNAL:
            raise _ProvenanceModeError
        return _ModeDecision("eval", mode_flags)
    if provenance is Provenance.EVAL_CASE:
        raise _ProvenanceModeError
    if resolved.mode == "active" and provenance in (Provenance.OPERATOR, Provenance.EXTERNAL):
        mode_flags["active_denied"] = True
        return _ModeDecision("shadow", mode_flags)
    return _ModeDecision(resolved.mode, mode_flags)


def _mode_decision(value: object, inherited_flags: Mapping[str, Any]) -> _ModeDecision:
    if isinstance(value, _ModeDecision):
        return value
    if isinstance(value, str) and value in {"shadow", "eval", "active"}:
        return _ModeDecision(value, dict(inherited_flags))
    raise ValueError("mode resolver returned an invalid result")


def _native(reason: FallbackReason, *, mode: str = "shadow") -> adapters_base.Outcome:
    return adapters_base.Outcome(kind="native", mode=mode, fallback_reason=reason.value)


def _bare_internal() -> SelectionResult:
    return SelectionResult(None, None, FallbackReason.INTERNAL_ERROR, _native(FallbackReason.INTERNAL_ERROR))


def _entry(registry: Mapping[str, Any], integration: str) -> Mapping[str, Any]:
    integrations = registry.get("integrations", {}) if isinstance(registry, Mapping) else {}
    value = integrations.get(integration) if isinstance(integrations, Mapping) else None
    return value if isinstance(value, Mapping) else {}


def _fit_questions(entry: Mapping[str, Any]) -> bool:
    return bool(entry.get("fit_questions", True))


def _floors(entry: Mapping[str, Any]) -> jev_client.Floors:
    raw = entry.get("floors") if isinstance(entry.get("floors"), Mapping) else {}
    return jev_client.Floors(
        confidence=float(raw.get("confidence", 0.0)),
        fit=float(raw.get("fit", 0.0)),
    )


def _deadline_limit(entry: Mapping[str, Any], point: Point, env: Mapping[str, str]) -> int:
    configured: object = entry.get("deadline_ms", jev_client.MAX_DEADLINE_MS)
    if isinstance(configured, Mapping):
        configured = configured.get(point.value, jev_client.MAX_DEADLINE_MS)
    try:
        limit = int(configured)
    except (TypeError, ValueError):
        limit = jev_client.MAX_DEADLINE_MS
    raw_env = env.get("CLAVAIN_SELECTOR_DEADLINE_MS")
    if raw_env is not None:
        try:
            limit = min(limit, int(raw_env))
        except (TypeError, ValueError):
            pass
    return max(1, min(jev_client.MAX_DEADLINE_MS, limit))


def _fingerprint(
    adapter: adapters_base.HostAdapter,
    paths: Sequence[str],
    phase: adapters_base.FingerprintPhase,
) -> str:
    """Call the host fingerprint API, retaining compatibility with old fakes."""

    method = adapter.fingerprint
    try:
        parameters = inspect.signature(method).parameters.values()
        supports_phase = any(
            item.name == "phase" or item.kind is inspect.Parameter.VAR_KEYWORD
            for item in parameters
        )
    except (TypeError, ValueError):
        supports_phase = True
    path_values = tuple(Path(path) for path in paths)
    if supports_phase:
        return method(path_values, phase=phase)
    return method(path_values)


def _external_scope_rule(prepared: preparers.PreparedSet, paths: Sequence[str]) -> str | None:
    if prepared.provenance is not Provenance.EXTERNAL:
        return None
    for raw_path in paths:
        rule = egress._source_rule(Path(raw_path), prepared.project_root)
        if rule is not None:
            return rule
    return None


def _admission_request(
    request: contract.SelectionRequest,
    prepared: preparers.PreparedSet,
) -> contract.SelectionRequest:
    """Include declared read sets in source checks without changing wire bytes."""

    read_paths = [Path(path) for _, paths in prepared.read_set_paths for path in paths]
    sources = tuple(dict.fromkeys((*request.sources, *read_paths)))
    if sources == request.sources:
        return request
    return dataclasses.replace(request, sources=sources)


def _write_record_error(record: Mapping[str, Any]) -> None:
    try:
        line = {
            "kind": "record_unwritable",
            "point": record.get("point", "unknown"),
            "integration": record.get("integration", "unknown"),
        }
        print(json.dumps(line, sort_keys=True, separators=(",", ":")), file=sys.stderr)
    except Exception:
        pass


def select(
    prepared: preparers.PreparedSet,
    *,
    session: SessionRef,
    adapter: adapters_base.HostAdapter,
    env: Mapping[str, str],
    now: int,
    registry: Mapping[str, Any],
    mode_override: str | None = None,
    deadline: jev_client.Deadline | None = None,
    event: adapters_base.HostEvent | None = None,
) -> SelectionResult:
    """Run the fourteen fallback rows in order and fail closed to native."""

    if mode_override not in (None, "eval"):
        raise ValueError("mode_override must be None or 'eval'")

    # Row 1 precedes every other check, record write and filesystem read. An
    # unverified integration can only make this inert, never enable it:
    # verification below rejects a set whose integration was tampered with.
    try:
        resolved = flags.resolve_mode(getattr(prepared, "integration"), env, registry)
    except Exception:
        return _bare_internal()
    if resolved.mode == "off":
        return SelectionResult(None, None, FallbackReason.FLAG_OFF, _native(FallbackReason.FLAG_OFF))

    # Row 12's clock: the caller's `now`, advanced on the monotonic clock
    # `jev_client.Deadline` already measures with.
    started_ns = time.monotonic_ns()

    try:
        preparers.verify(prepared)
        request = preparers.request_from(prepared, session=session)
    except Exception:
        return _bare_internal()
    point_mismatch = event is not None and event.point != prepared.point

    integration = prepared.integration
    point = prepared.point
    entry = _entry(registry, integration)
    fit_questions = _fit_questions(entry)
    effective_mode = "shadow"
    mode_flags: dict[str, Any] = {}
    egress_verdict = "not_run"
    selector_fields: dict[str, Any] = {}
    result_fields: dict[str, Any] = {}

    def build_record(
        reason: FallbackReason | None,
        *,
        applied: str = "native",
        detail: str = "",
        validation: Mapping[str, Any] | None = None,
        egress_rule_ids: Sequence[str] = (),
    ) -> dict[str, Any]:
        raw_flag = entry.get("flag")
        record_flags = dict(mode_flags)
        record_flags["fit_questions"] = fit_questions
        if isinstance(raw_flag, str) and str(env.get(raw_flag, "")).lower() in {"off", "shadow", "active"}:
            record_flags[raw_flag] = str(env[raw_flag]).lower()
        return records.build_record(
            request=request,
            fit_questions=fit_questions,
            host={"name": getattr(adapter, "name", "unknown")},
            adapter_version=str(getattr(adapter, "version", "unknown")),
            mode=effective_mode,
            egress_verdict=egress_verdict,
            applied=applied,
            fallback_reason=reason.value if reason is not None else None,
            provenance=prepared.provenance,
            preparer=prepared.preparer,
            egress_rule_ids=egress_rule_ids,
            fallback_detail=detail,
            selector=selector_fields,
            result=result_fields,
            validation=validation,
            flags=record_flags,
        )

    def fallback(
        reason: FallbackReason,
        *,
        detail: str = "",
        validation: Mapping[str, Any] | None = None,
        egress_rule_ids: Sequence[str] = (),
        chosen: contract.Candidate | None = None,
        shadow_outcome: bool = False,
    ) -> SelectionResult:
        try:
            record = build_record(
                reason,
                detail=detail,
                validation=validation,
                egress_rule_ids=egress_rule_ids,
            )
        except Exception:
            return _bare_internal()
        try:
            records.append_record(record)
        except Exception:
            _write_record_error(record)
        if shadow_outcome:
            outcome = adapters_base.Outcome(
                kind="shadow",
                mode=effective_mode,
                candidate=chosen,
                fallback_reason=reason.value,
            )
        else:
            outcome = _native(reason, mode=effective_mode)
        return SelectionResult(record, chosen, reason, outcome)

    if point_mismatch:
        return fallback(FallbackReason.INTERNAL_ERROR, detail=_PointMismatch.__name__)

    try:
        mode_flags.update(resolved.flags)
        try:
            effective = _mode_decision(
                _resolve_mode(resolved, prepared.provenance, mode_override),
                resolved.flags,
            )
        except _ProvenanceModeError as exc:
            return fallback(FallbackReason.INTERNAL_ERROR, detail=type(exc).__name__)
        effective_mode = effective.mode
        mode_flags.update(effective.flags)

        # Row 2 precedes creation of the trusted ValidatedCandidates value.
        invalid = contract.validate_request(request)
        if invalid is not None:
            return fallback(invalid)
        validated = preparers.validated(prepared, request)

        # Row 3 / A3: the registry must explicitly serve this point.
        raw_points = entry.get("points", ())
        if not isinstance(raw_points, (list, tuple, set, frozenset)):
            return fallback(FallbackReason.POINT_UNREACHABLE)
        registry_points = {value.value if isinstance(value, Point) else str(value) for value in raw_points}
        if point.value not in registry_points:
            return fallback(FallbackReason.POINT_UNREACHABLE)
        capability = adapter.capabilities().get(point)
        if capability is None and point is not Point.LIBRARY:
            return fallback(FallbackReason.POINT_UNREACHABLE)
        if capability is not None:
            unreachable = adapters_base.gate_mode(capability, effective_mode)
            if unreachable is not None:
                return fallback(unreachable)

        # Row 4 / R12-3: external conditions are explicitly unverified.
        if prepared.provenance is Provenance.EXTERNAL and any(
            candidate.preconditions for candidate in prepared.candidates
        ):
            return fallback(
                FallbackReason.STALE_BEFORE_SELECT,
                validation={"stage": "pre_eligibility", "reject_reason": "unmet_precondition"},
            )

        phase4 = adapters_base.FingerprintPhase()
        fingerprints4: dict[str, str] = {}
        for candidate, (candidate_id, paths) in zip(prepared.candidates, prepared.read_set_paths):
            if candidate.id != candidate_id:
                raise preparers.NotPrepared
            rule = _external_scope_rule(prepared, paths)
            if rule is not None:
                egress_verdict = "refused"
                return fallback(FallbackReason.EGRESS_REFUSED, egress_rule_ids=(rule,))
            if paths:
                try:
                    fingerprints4[candidate.id] = _fingerprint(adapter, paths, phase4)
                except adapters_base.FingerprintUnavailable:
                    return fallback(
                        FallbackReason.STALE_BEFORE_SELECT,
                        detail="fingerprint_unavailable",
                        validation={"stage": "pre_eligibility", "reject_reason": None},
                    )
        pre_context = contract.ValidationContext(
            now_ms=now,
            current_revision=prepared.task_revision,
            current_read_set_fingerprints=fingerprints4,
            authorized=False,
        )
        stale = contract.pre_eligibility(prepared.candidates, pre_context)
        if stale is not None:
            return fallback(stale, validation={"stage": "pre_eligibility", "reject_reason": None})

        # Row 5: scan the request and every declared source/read-set path.
        admitted = egress.admit(
            _admission_request(request, prepared),
            high_entropy=bool(entry.get("high_entropy", False)),
        )
        if isinstance(admitted, egress.Refusal):
            egress_verdict = "refused"
            return fallback(FallbackReason.EGRESS_REFUSED, egress_rule_ids=admitted.rule_ids)
        egress_verdict = "admitted"

        # Rows 6-8.
        budget = jev_client.Budget(
            session.host_session_id,
            integration,
            limit=int(entry.get("session_budget", jev_client.BUDGET_LIMIT)),
        )
        if budget.consume() is not None:
            return fallback(FallbackReason.BUDGET_EXHAUSTED)

        breaker = jev_client.Breaker()
        if breaker.check() is not None:
            return fallback(FallbackReason.CIRCUIT_OPEN)

        try:
            credential = credentials.load()
        except credentials.CredentialUnavailable:
            return fallback(FallbackReason.CREDENTIAL_UNAVAILABLE)

        # The loaded-key literal can only be checked after row 8. Re-admit
        # immediately before constructing a call; no socket exists yet.
        admitted_with_key = egress.admit(
            _admission_request(request, prepared),
            key_literal=credential.reveal(),
            high_entropy=bool(entry.get("high_entropy", False)),
        )
        if isinstance(admitted_with_key, egress.Refusal):
            egress_verdict = "refused"
            return fallback(FallbackReason.EGRESS_REFUSED, egress_rule_ids=admitted_with_key.rule_ids)
        admitted = admitted_with_key

        # Rows 9-10: one deadline, one call, one breaker observation.
        configured_deadline = jev_client.Deadline.start(_deadline_limit(entry, point, env))
        effective_deadline = configured_deadline
        if deadline is not None and deadline.remaining_ms() < configured_deadline.remaining_ms():
            effective_deadline = deadline
        if effective_deadline.remaining_ms() <= 0:
            timed_out = jev_client.JevFailure(
                reason=FallbackReason.TIMEOUT,
                detail=jev_client.FailureDetail.DEADLINE,
                attempts=0,
                http_status=None,
                latency_ms=0,
            )
            breaker.record(timed_out)
            fields = jev_client.to_record_fields(timed_out, timed_out)
            selector_fields.update(fields["selector"])
            result_fields.update(fields["result"])
            return fallback(FallbackReason.TIMEOUT, detail=timed_out.detail.value)

        call = jev_client.JevCall.build(admitted, fit_questions=fit_questions, deadline=effective_deadline)
        client_result = jev_client.JevClient(credential).call(call)
        breaker.record(client_result)
        if isinstance(client_result, jev_client.JevFailure):
            fields = jev_client.to_record_fields(client_result, client_result)
            selector_fields.update(fields["selector"])
            result_fields.update(fields["result"])
            return fallback(client_result.reason, detail=client_result.detail.value)

        floors = _floors(entry)
        decision = jev_client.apply_floors(client_result.response, floors, call.battery)
        fields = jev_client.to_record_fields(decision, client_result)
        selector_fields.update(fields["selector"])
        selector_fields["floors"] = dataclasses.asdict(floors)
        result_fields.update(fields["result"])
        if isinstance(decision, jev_client.Abstention):
            return fallback(decision.reason)

        # Row 12: re-fingerprint the chosen candidate, authorize exactly once
        # with the three typed positional arguments, then revalidate.
        chosen = next(
            (candidate for candidate in prepared.candidates if candidate.id == decision.candidate_id),
            None,
        )
        if chosen is None:
            return fallback(
                FallbackReason.INVALID_ID,
                validation={"stage": "host_revalidation", "reject_reason": "invalid_id"},
            )
        chosen_paths = dict(prepared.read_set_paths).get(chosen.id, ())
        rule = _external_scope_rule(prepared, chosen_paths)
        if rule is not None:
            egress_verdict = "refused"
            return fallback(FallbackReason.EGRESS_REFUSED, egress_rule_ids=(rule,))
        fingerprints12: dict[str, str] = {}
        if chosen_paths:
            try:
                fingerprints12[chosen.id] = _fingerprint(
                    adapter,
                    chosen_paths,
                    adapters_base.FingerprintPhase(),
                )
            except adapters_base.FingerprintUnavailable:
                return fallback(
                    FallbackReason.STALE_READ_SET,
                    detail="fingerprint_unavailable",
                    validation={"stage": "host_revalidation", "reject_reason": "stale_read_set"},
                )

        policy = flags.authorization_policy(registry, integration, point)
        authorized = adapter.authorize(chosen, validated, policy)
        authorized = bool(authorized and adapters_base.launch_argv_ok(chosen, validated))
        elapsed_ms = max(0, (time.monotonic_ns() - started_ns) // 1_000_000)
        validation_context = contract.ValidationContext(
            now_ms=now + elapsed_ms,
            current_revision=prepared.task_revision,
            current_read_set_fingerprints=fingerprints12,
            authorized=authorized,
        )
        rejected = contract.revalidate(
            prepared.candidates,
            chosen.id,
            validation_context,
            # No host-owned verifier exists for declared preconditions, so any
            # precondition on the chosen candidate is unverifiable, hence unmet.
            preconditions_met=not chosen.preconditions,
        )
        if rejected is not None:
            reason = FallbackReason(rejected.value)
            return fallback(
                reason,
                validation={"stage": "host_revalidation", "reject_reason": rejected.value},
            )

        # Row 13 and R12-1: independently enforce PREPARER immediately before
        # constructing any emitted outcome.
        if effective_mode != "active":
            return fallback(
                FallbackReason.SHADOW_MODE,
                chosen=chosen,
                shadow_outcome=True,
                validation={"stage": "host_revalidation", "reject_reason": None},
            )
        if prepared.provenance is not Provenance.PREPARER:
            return fallback(
                FallbackReason.SHADOW_MODE,
                chosen=chosen,
                validation={"stage": "host_revalidation", "reject_reason": None},
            )
        # A1: a host effect is bound to the host event it answers. Only the
        # library point, which has no host event, may emit without one.
        if (event is None and point is not Point.LIBRARY) or (
            event is not None and event.point != point
        ):
            return fallback(
                FallbackReason.INTERNAL_ERROR,
                detail=_PointMismatch.__name__,
                validation={"stage": "host_revalidation", "reject_reason": None},
            )

        outcome = adapters_base.emitted_outcome(chosen, validated, mode="active")
        if outcome.binding_sha256 != dict(validated.bindings).get(chosen.id):
            raise _BindingMismatch
        emitted_record = build_record(
            None,
            applied="emitted",
            validation={"stage": "host_revalidation", "reject_reason": None},
        )
        try:
            records.append_record(emitted_record)
        except Exception:
            unwritable = build_record(
                FallbackReason.RECORD_UNWRITABLE,
                validation={"stage": "host_revalidation", "reject_reason": None},
            )
            _write_record_error(unwritable)
            return SelectionResult(
                unwritable,
                chosen,
                FallbackReason.RECORD_UNWRITABLE,
                _native(FallbackReason.RECORD_UNWRITABLE, mode="active"),
            )
        return SelectionResult(emitted_record, chosen, None, outcome)
    except Exception as exc:
        # Unexpected failures expose only the exception type, never the message.
        return fallback(FallbackReason.INTERNAL_ERROR, detail=type(exc).__name__)
