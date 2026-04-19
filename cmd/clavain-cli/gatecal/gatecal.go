// Package gatecal manages the SQLite-backed gate threshold calibration store.
package gatecal

import (
	"context"
	"database/sql"
	"fmt"

	_ "modernc.org/sqlite"
)

// Store wraps a sqlite handle for gate.db.
type Store struct {
	db *sql.DB
}

// TierState is the persisted per-theme/per-check calibration state.
type TierState struct {
	Theme                            string
	CheckType                        string
	PhaseFrom                        string
	PhaseTo                          string
	Tier                             string
	FPR                              *float64
	FNR                              *float64
	WeightedN                        float64
	ConsecutiveWindowsAboveThreshold int
	Locked                           bool
	ChangeCount90d                   int
	LastChangedAt                    *int64
	FNRThreshold                     *float64
	OriginKey                        *string
	ThemeSource                      string
	UpdatedAt                        int64
}

// DrainResult summarizes one drain execution.
type DrainResult struct {
	SignalsProcessed int
	SinceIDBefore    int64
	SinceIDAfter     int64
	StateChanges     int
}

// Open initializes (or opens) gate.db at path and ensures schema exists.
func Open(path string) (*Store, error) {
	dsn := path + "?_busy_timeout=5000&_journal_mode=WAL"
	db, err := sql.Open("sqlite", dsn)
	if err != nil {
		return nil, fmt.Errorf("gatecal: open: %w", err)
	}

	s := &Store{db: db}
	if err := s.ensureSchema(context.Background()); err != nil {
		_ = db.Close()
		return nil, err
	}
	return s, nil
}

// DB exposes the underlying handle for tests and advanced callers.
func (s *Store) DB() *sql.DB { return s.db }

// Close releases the sqlite handle.
func (s *Store) Close() error { return s.db.Close() }

const schema = `
CREATE TABLE IF NOT EXISTS tier_state (
  theme TEXT NOT NULL,
  check_type TEXT NOT NULL,
  phase_from TEXT NOT NULL,
  phase_to TEXT NOT NULL,
  tier TEXT NOT NULL DEFAULT 'soft',
  fpr REAL,
  fnr REAL,
  weighted_n REAL NOT NULL DEFAULT 0,
  consecutive_windows_above_threshold INTEGER NOT NULL DEFAULT 0,
  locked INTEGER NOT NULL DEFAULT 0,
  change_count_90d INTEGER NOT NULL DEFAULT 0,
  last_changed_at INTEGER,
  fnr_threshold REAL,
  origin_key TEXT,
  theme_source TEXT NOT NULL,
  updated_at INTEGER NOT NULL,
  PRIMARY KEY (theme, check_type, phase_from, phase_to)
);

CREATE TABLE IF NOT EXISTS drain_log (
  rowid INTEGER PRIMARY KEY AUTOINCREMENT,
  drain_started INTEGER NOT NULL,
  drain_committed INTEGER,
  signals_processed INTEGER,
  since_id_before INTEGER,
  since_id_after INTEGER,
  state_changes INTEGER,
  invoker TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS signals_cache (
  event_id INTEGER PRIMARY KEY,
  run_id TEXT,
  check_type TEXT,
  phase_from TEXT,
  phase_to TEXT,
  signal TEXT,
  category TEXT,
  created_at INTEGER
);

CREATE INDEX IF NOT EXISTS idx_drain_log_committed ON drain_log(drain_committed);
CREATE INDEX IF NOT EXISTS idx_signals_cache_created ON signals_cache(created_at);
`

func (s *Store) ensureSchema(ctx context.Context) error {
	if _, err := s.db.ExecContext(ctx, schema); err != nil {
		return fmt.Errorf("gatecal: ensureSchema: %w", err)
	}
	return nil
}
