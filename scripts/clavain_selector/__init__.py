"""Clavain shared selector layer (mk-42j9.7).

Stdlib-only Python package implementing the host-neutral, flag-gated
selection contract described in docs/plans/2026-09-25-jev-decision-layer.md.
Nothing in this package is registered by any host at import time: every
effect is gated behind an explicit per-integration flag resolved by
``clavain_selector.flags``.
"""

from __future__ import annotations
