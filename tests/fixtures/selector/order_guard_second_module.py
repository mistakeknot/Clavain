"""Negative fixture (revision 10): a copy of the eval.py-allowlisted line, in
a module that is not eval.py.

The order-guard checker allowlists exactly one qualified non-call binding --
`eval._REFERENCE_CANONICAL_ORDER = contract.canonical_order` at module scope,
literally in `eval.py` -- so the identical line here, in a different module,
must still be flagged. This file is parsed by `ast.parse` only -- it is
never imported or executed.
"""

from __future__ import annotations

import clavain_selector.contract as contract

eval._REFERENCE_CANONICAL_ORDER = contract.canonical_order
