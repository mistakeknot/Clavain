#!/usr/bin/env bash
# SessionEnd hook — recalibrates gate thresholds from accumulated `ic gate signals`.
# Exit 0 always: never block session exit on calibration failure.
set -u
timeout 10 clavain-cli calibrate-gate-tiers --auto 2>&1 | head -20 || true
exit 0
