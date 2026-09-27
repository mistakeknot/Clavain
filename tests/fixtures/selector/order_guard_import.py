"""Negative fixture for test_order_guard_module_calls (mk-42j9.7 Task R6a).

Every pattern below must be flagged by the order-guard AST checker: importing
`require_canonical`/`canonical_order` by name, or referencing either as a
non-call `contract.X` attribute (assignment, default value, positional arg to
`functools.partial`, or via `getattr`). This file is parsed by `ast.parse`
only -- it is never imported or executed.
"""

from __future__ import annotations

import functools

from clavain_selector.contract import require_canonical

import clavain_selector.contract as contract

g = contract.require_canonical


def f(x, _g=contract.canonical_order):
    return x


functools.partial(contract.require_canonical)

getattr(contract, "require_canonical")
