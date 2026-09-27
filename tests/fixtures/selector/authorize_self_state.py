"""Negative fixture for the authorize-body AST allowlist checker.

Every function here is a *violation* of the rule that an adapter's
``authorize`` method (and ``authorize_by_policy`` itself) may only read its
own parameters, names bound locally within the function, the builtins
``any``/``dict``/``isinstance``/``len``, and ``contract.payload_sha256`` --
never any other module-level global, ``self`` attribute state, or a helper
call that could hide a side channel into the decision.
"""

from __future__ import annotations

_MODULE_GLOBAL_STATE = {"authorized": True}


def _sneaky_helper(chosen, validated, policy):
    return True


class SelfStateAdapter:
    def __init__(self):
        self._last = None

    def authorize_reads_self_attribute(self, chosen, validated, policy):
        # Violation: reads back adapter instance state via `self`.
        return self._last is not None

    def authorize_reads_getattr_self(self, chosen, validated, policy):
        # Violation: same self-state read, via getattr() instead of a
        # literal attribute access.
        return bool(getattr(self, "_last", None))

    def authorize_reads_module_global(self, chosen, validated, policy):
        # Violation: reads a module-level global set by parse_event/other
        # code, rather than only its own three parameters.
        return _MODULE_GLOBAL_STATE.get("authorized", False)

    def authorize_calls_helper(self, chosen, validated, policy):
        # Violation: delegates to a helper function instead of the one
        # allowed body shape `return authorize_by_policy(chosen, validated,
        # policy)`.
        return _sneaky_helper(chosen, validated, policy)


def authorize_by_policy_reads_module_global(chosen, validated, policy):
    # Violation: authorize_by_policy itself must not read any global besides
    # the `contract` module (and only via `contract.payload_sha256`).
    if _MODULE_GLOBAL_STATE.get("authorized"):
        return True
    return False
