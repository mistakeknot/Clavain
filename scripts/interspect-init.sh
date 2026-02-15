#!/usr/bin/env bash
# interspect-init.sh — Idempotent initialization for the Interspect evidence store.
#
# Creates:
#   ~/.clavain/interspect/interspect.db (SQLite, WAL mode)
#   ~/.clavain/interspect/overlays/     (git-tracked overlay directory)
#   ~/.clavain/interspect/reports/      (git-tracked analysis reports)
#
# Safe to run multiple times — uses CREATE TABLE IF NOT EXISTS.
# Called by session-start hook and /interspect commands.

set -euo pipefail

CLAVAIN_DIR="${CLAVAIN_DIR:-${HOME}/.clavain}"
INTERSPECT_DIR="${CLAVAIN_DIR}/interspect"
DB_FILE="${INTERSPECT_DIR}/interspect.db"

# ──── Directory structure ────

mkdir -p "${INTERSPECT_DIR}/overlays"
mkdir -p "${INTERSPECT_DIR}/reports"

# ──── SQLite schema ────

sqlite3 "${DB_FILE}" <<'SQL'
-- Enable WAL mode for concurrent read/serialized write safety.
-- This is persistent — only needs to be set once per database file,
-- but is idempotent if run again.
PRAGMA journal_mode = WAL;

-- Evidence table: captures overrides, false positives, corrections.
-- One row per event. Context is a JSON blob for flexible schema evolution.
CREATE TABLE IF NOT EXISTS evidence (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  ts              TEXT    NOT NULL,       -- ISO 8601 UTC
  session_id      TEXT    NOT NULL,
  seq             INTEGER NOT NULL,       -- monotonic within session
  source          TEXT    NOT NULL,       -- agent/skill name (e.g. "fd-safety")
  source_version  TEXT,                   -- commit SHA of source at event time
  event           TEXT    NOT NULL,       -- override, false_positive, correction, etc.
  override_reason TEXT,                   -- 'agent_wrong', 'deprioritized', 'already_fixed', NULL
  context         TEXT    NOT NULL,       -- JSON blob
  project         TEXT    NOT NULL,
  project_lang    TEXT,                   -- primary language (Go, Python, TypeScript, etc.)
  project_type    TEXT                    -- prototype, production, library, etc.
);

-- Sessions table: tracks Claude Code session lifecycle.
-- A NULL end_ts after 24 hours indicates a dark/abandoned session.
CREATE TABLE IF NOT EXISTS sessions (
  session_id TEXT PRIMARY KEY,
  start_ts   TEXT NOT NULL,
  end_ts     TEXT,                        -- NULL = still active or abandoned
  project    TEXT
);

-- Canary table: monitors post-modification metrics.
-- Each active overlay gets a canary that tracks baseline vs observed performance.
-- status: active → passed | reverted | expired_human_edit
CREATE TABLE IF NOT EXISTS canary (
  id                      INTEGER PRIMARY KEY AUTOINCREMENT,
  file                    TEXT    NOT NULL,
  commit_sha              TEXT    NOT NULL,
  group_id                TEXT,           -- links related modifications
  applied_at              TEXT    NOT NULL,
  window_uses             INTEGER NOT NULL DEFAULT 20,
  uses_so_far             INTEGER NOT NULL DEFAULT 0,
  window_expires_at       TEXT,           -- time-based fallback (14 days)
  baseline_override_rate  REAL,
  baseline_fp_rate        REAL,
  baseline_finding_density REAL,          -- findings per invocation
  baseline_window         TEXT,           -- JSON: time range, session IDs, N
  status                  TEXT    NOT NULL DEFAULT 'active',
  verdict_reason          TEXT
);

-- Modifications table: records all proposed/applied changes.
-- Grouped by group_id for related changes. tier is always 'persistent' in v1.
CREATE TABLE IF NOT EXISTS modifications (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  group_id         TEXT    NOT NULL,
  ts               TEXT    NOT NULL,
  tier             TEXT    NOT NULL DEFAULT 'persistent',
  mod_type         TEXT    NOT NULL,      -- context_injection, routing, prompt_tuning
  target_file      TEXT    NOT NULL,
  commit_sha       TEXT,
  confidence       REAL    NOT NULL,
  evidence_summary TEXT,                  -- human-readable
  status           TEXT    NOT NULL DEFAULT 'applied'  -- applied, reverted, superseded
);

-- ──── Indexes ────
-- Query patterns from the PRD: evidence by session, by source, by project;
-- canary by status; modifications by group and status.

CREATE INDEX IF NOT EXISTS idx_evidence_session
  ON evidence(session_id);

CREATE INDEX IF NOT EXISTS idx_evidence_source
  ON evidence(source);

CREATE INDEX IF NOT EXISTS idx_evidence_project
  ON evidence(project);

CREATE INDEX IF NOT EXISTS idx_evidence_event
  ON evidence(event);

CREATE INDEX IF NOT EXISTS idx_evidence_ts
  ON evidence(ts);

CREATE INDEX IF NOT EXISTS idx_sessions_project
  ON sessions(project);

CREATE INDEX IF NOT EXISTS idx_canary_status
  ON canary(status);

CREATE INDEX IF NOT EXISTS idx_canary_file
  ON canary(file);

CREATE INDEX IF NOT EXISTS idx_modifications_group
  ON modifications(group_id);

CREATE INDEX IF NOT EXISTS idx_modifications_status
  ON modifications(status);

CREATE INDEX IF NOT EXISTS idx_modifications_target
  ON modifications(target_file);
SQL

echo "Interspect initialized: ${DB_FILE}" >&2
