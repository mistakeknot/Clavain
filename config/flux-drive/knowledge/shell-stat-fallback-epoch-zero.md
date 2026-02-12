---
lastConfirmed: 2026-02-12
provenance: independent
---
Shell `stat` calls with `|| echo 0` fallback silently convert errors into epoch 0, which compares as "very old" in any timestamp check. This creates false positives: a file that was deleted between discovery and stat appears maximally stale instead of unknown.

Fix: Use `|| echo ""` and check for empty string before numeric comparison. Empty = "unknown" (default to safe assumption), 0 = "epoch zero" (false signal).

Evidence: hooks/lib-discovery.sh staleness check — `stat -c %Y "$plan_path" || echo 0` made deleted files appear stale. Changed to `|| echo ""` with `-n` guard.
Verify: grep for `stat.*|| echo 0` in hooks/*.sh and scripts/*.sh.
