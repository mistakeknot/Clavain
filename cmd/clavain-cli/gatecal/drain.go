package gatecal

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"math"
	"strings"
	"time"
)

// GateSignal is the per-event record returned by `ic gate signals`.
type GateSignal struct {
	EventID   int64  `json:"event_id"`
	RunID     string `json:"run_id"`
	CheckType string `json:"check_type"`
	FromPhase string `json:"from_phase"`
	ToPhase   string `json:"to_phase"`
	Signal    string `json:"signal_type"`
	CreatedAt int64  `json:"created_at"`
	Category  string `json:"category,omitempty"`
}

// Algorithm constants ported from v1 gate calibration.
const (
	HalfLifeDays          = 30
	DefaultFNRThreshold   = 0.30
	PromotionMinN         = 10.0
	ZeroFNRSafetyMinN     = 20.0
	CooldownDays          = 7
	VelocityLimitChanges  = 2
	StableWindowsRequired = 3
)

// Drain ingests signals and updates tier_state in one SQLite transaction.
func (s *Store) Drain(ctx context.Context, now int64, invoker string, signals []GateSignal) (DrainResult, error) {
	var lastErr error
	for i := 0; i < 3; i++ {
		res, err := s.drainOnce(ctx, now, invoker, signals)
		if err == nil {
			return res, nil
		}
		if !isSQLiteBusy(err) {
			return res, err
		}
		lastErr = err
		time.Sleep(time.Duration(i+1) * 150 * time.Millisecond)
	}
	return DrainResult{}, lastErr
}

func (s *Store) drainOnce(ctx context.Context, now int64, invoker string, signals []GateSignal) (DrainResult, error) {
	res := DrainResult{}

	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return res, fmt.Errorf("gatecal.drain: begin: %w", err)
	}
	defer tx.Rollback()

	var prevCursor sql.NullInt64
	err = tx.QueryRowContext(ctx, `SELECT MAX(since_id_after) FROM drain_log WHERE drain_committed IS NOT NULL`).Scan(&prevCursor)
	if err != nil && !errors.Is(err, sql.ErrNoRows) {
		return res, fmt.Errorf("gatecal.drain: read cursor: %w", err)
	}
	if prevCursor.Valid {
		res.SinceIDBefore = prevCursor.Int64
	}

	logRes, err := tx.ExecContext(ctx,
		`INSERT INTO drain_log (drain_started, since_id_before, invoker) VALUES (?, ?, ?)`,
		now, res.SinceIDBefore, invoker,
	)
	if err != nil {
		return res, fmt.Errorf("gatecal.drain: open drain_log: %w", err)
	}
	logRowID, _ := logRes.LastInsertId()

	if len(signals) == 0 {
		res.SinceIDAfter = res.SinceIDBefore
		_, err = tx.ExecContext(ctx,
			`UPDATE drain_log SET drain_committed=?, signals_processed=0, since_id_after=?, state_changes=0 WHERE rowid=?`,
			now, res.SinceIDAfter, logRowID,
		)
		if err != nil {
			return res, fmt.Errorf("gatecal.drain: close empty log: %w", err)
		}
		if err := tx.Commit(); err != nil {
			return res, fmt.Errorf("gatecal.drain: commit empty: %w", err)
		}
		return res, nil
	}

	for _, sig := range signals {
		_, _ = tx.ExecContext(ctx,
			`INSERT OR IGNORE INTO signals_cache (event_id, run_id, check_type, phase_from, phase_to, signal, category, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
			sig.EventID, sig.RunID, sig.CheckType, sig.FromPhase, sig.ToPhase, sig.Signal, sig.Category, sig.CreatedAt,
		)
	}

	type groupKey struct{ theme, ct, pf, pt string }
	type weights struct {
		wTP, wFP, wTN, wFN float64
		maxEventID         int64
	}
	groups := map[groupKey]*weights{}
	maxEventID := res.SinceIDBefore

	for _, sig := range signals {
		theme, _ := DeriveTheme(sig.CheckType, nil)
		k := groupKey{theme: theme, ct: sig.CheckType, pf: sig.FromPhase, pt: sig.ToPhase}
		w, ok := groups[k]
		if !ok {
			w = &weights{}
			groups[k] = w
		}

		ageDays := float64(now-sig.CreatedAt) / 86400.0
		weight := math.Exp(-math.Ln2 * ageDays / HalfLifeDays)
		switch sig.Signal {
		case "tp":
			w.wTP += weight
		case "fp":
			w.wFP += weight
		case "tn":
			w.wTN += weight
		case "fn":
			w.wFN += weight
		}

		if sig.EventID > w.maxEventID {
			w.maxEventID = sig.EventID
		}
		if sig.EventID > maxEventID {
			maxEventID = sig.EventID
		}
	}

	for k, w := range groups {
		row, err := loadTierStateForUpdate(ctx, tx, k.theme, k.ct, k.pf, k.pt)
		if err != nil {
			return res, err
		}

		if row.LastChangedAt > 0 {
			adjusted := &weights{}
			for _, sig := range signals {
				if sig.CheckType != k.ct || sig.FromPhase != k.pf || sig.ToPhase != k.pt {
					continue
				}
				theme, _ := DeriveTheme(sig.CheckType, nil)
				if theme != k.theme || sig.CreatedAt <= row.LastChangedAt {
					continue
				}
				ageDays := float64(now-sig.CreatedAt) / 86400.0
				weight := math.Exp(-math.Ln2 * ageDays / HalfLifeDays)
				switch sig.Signal {
				case "tp":
					adjusted.wTP += weight
				case "fp":
					adjusted.wFP += weight
				case "tn":
					adjusted.wTN += weight
				case "fn":
					adjusted.wFN += weight
				}
				if sig.EventID > adjusted.maxEventID {
					adjusted.maxEventID = sig.EventID
				}
			}
			w = adjusted
		}

		weightedN := w.wTP + w.wFP + w.wTN + w.wFN
		fpr := 0.0
		fnr := 0.0
		if w.wTP+w.wFP > 0 {
			fpr = w.wFP / (w.wTP + w.wFP)
		}
		if w.wTN+w.wFN > 0 {
			fnr = w.wFN / (w.wTN + w.wFN)
		}

		row.WeightedN = weightedN
		row.FPR = fpr
		row.FNR = fnr

		if !row.Locked && row.Tier == "soft" && weightedN > 0 {
			threshold := DefaultFNRThreshold
			if row.FNRThreshold.Valid {
				threshold = row.FNRThreshold.Float64
			}
			above := fnr > threshold &&
				weightedN >= PromotionMinN &&
				!(fnr == 0 && weightedN < ZeroFNRSafetyMinN)
			cooldownOK := row.LastChangedAt == 0 || (now-row.LastChangedAt) >= CooldownDays*86400
			velocityOK := row.ChangeCount90d <= VelocityLimitChanges-1

			if above && cooldownOK && velocityOK {
				row.ConsecutiveWindows++
				if row.ConsecutiveWindows >= StableWindowsRequired {
					row.Tier = "hard"
					row.LastChangedAt = now
					row.ChangeCount90d++
					row.ConsecutiveWindows = 0
					res.StateChanges++
				}
			} else if !above {
				row.ConsecutiveWindows = 0
			}

			if row.ChangeCount90d >= VelocityLimitChanges {
				if !row.Locked {
					row.Locked = true
					res.StateChanges++
				}
			}
		}

		row.UpdatedAt = now
		if err := upsertTierState(ctx, tx, row); err != nil {
			return res, err
		}
	}

	res.SignalsProcessed = len(signals)
	res.SinceIDAfter = maxEventID

	_, err = tx.ExecContext(ctx,
		`UPDATE drain_log SET drain_committed=?, signals_processed=?, since_id_after=?, state_changes=? WHERE rowid=?`,
		now, res.SignalsProcessed, res.SinceIDAfter, res.StateChanges, logRowID,
	)
	if err != nil {
		return res, fmt.Errorf("gatecal.drain: close drain_log: %w", err)
	}
	if err := tx.Commit(); err != nil {
		return res, fmt.Errorf("gatecal.drain: commit: %w", err)
	}
	return res, nil
}

// tierStateRow is the mutable row view for tier_state.
type tierStateRow struct {
	Theme              string
	CheckType          string
	PhaseFrom          string
	PhaseTo            string
	Tier               string
	FPR                float64
	FNR                float64
	WeightedN          float64
	ConsecutiveWindows int
	Locked             bool
	ChangeCount90d     int
	LastChangedAt      int64
	FNRThreshold       sql.NullFloat64
	OriginKey          sql.NullString
	ThemeSource        string
	UpdatedAt          int64
}

func loadTierStateForUpdate(ctx context.Context, tx *sql.Tx, theme, ct, pf, pt string) (*tierStateRow, error) {
	row := &tierStateRow{
		Theme:       theme,
		CheckType:   ct,
		PhaseFrom:   pf,
		PhaseTo:     pt,
		Tier:        "soft",
		ThemeSource: deriveSourceFor(theme, ct),
	}
	var locked int
	err := tx.QueryRowContext(ctx,
		`SELECT tier, fpr, fnr, weighted_n, consecutive_windows_above_threshold, locked, change_count_90d, last_changed_at, fnr_threshold, origin_key, theme_source, updated_at FROM tier_state WHERE theme=? AND check_type=? AND phase_from=? AND phase_to=?`,
		theme, ct, pf, pt,
	).Scan(
		&row.Tier,
		&nullableFloat64{Dest: &row.FPR},
		&nullableFloat64{Dest: &row.FNR},
		&row.WeightedN,
		&row.ConsecutiveWindows,
		&locked,
		&row.ChangeCount90d,
		&nullableInt{Dest: &row.LastChangedAt},
		&row.FNRThreshold,
		&row.OriginKey,
		&row.ThemeSource,
		&row.UpdatedAt,
	)
	if err == sql.ErrNoRows {
		return row, nil
	}
	if err != nil {
		return nil, fmt.Errorf("gatecal.drain: load tier_state: %w", err)
	}
	row.Locked = locked != 0
	return row, nil
}

func upsertTierState(ctx context.Context, tx *sql.Tx, r *tierStateRow) error {
	locked := 0
	if r.Locked {
		locked = 1
	}
	var lastChanged sql.NullInt64
	if r.LastChangedAt > 0 {
		lastChanged = sql.NullInt64{Int64: r.LastChangedAt, Valid: true}
	}
	_, err := tx.ExecContext(ctx, `
INSERT INTO tier_state (theme, check_type, phase_from, phase_to, tier, fpr, fnr, weighted_n, consecutive_windows_above_threshold, locked, change_count_90d, last_changed_at, fnr_threshold, origin_key, theme_source, updated_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(theme, check_type, phase_from, phase_to) DO UPDATE SET
  tier=excluded.tier,
  fpr=excluded.fpr,
  fnr=excluded.fnr,
  weighted_n=excluded.weighted_n,
  consecutive_windows_above_threshold=excluded.consecutive_windows_above_threshold,
  locked=excluded.locked,
  change_count_90d=excluded.change_count_90d,
  last_changed_at=excluded.last_changed_at,
  fnr_threshold=excluded.fnr_threshold,
  theme_source=excluded.theme_source,
  updated_at=excluded.updated_at`,
		r.Theme,
		r.CheckType,
		r.PhaseFrom,
		r.PhaseTo,
		r.Tier,
		r.FPR,
		r.FNR,
		r.WeightedN,
		r.ConsecutiveWindows,
		locked,
		r.ChangeCount90d,
		lastChanged,
		r.FNRThreshold,
		r.OriginKey,
		r.ThemeSource,
		r.UpdatedAt,
	)
	if err != nil {
		return fmt.Errorf("gatecal.drain: upsert tier_state: %w", err)
	}
	return nil
}

func deriveSourceFor(theme, ct string) string {
	if theme == "default" {
		return "default"
	}
	for prefix, mapped := range knownPrefixes {
		if strings.HasPrefix(ct, prefix) && mapped == theme {
			return "inferred"
		}
	}
	return "labeled"
}

// nullableInt scans possibly NULL INTEGER into an int64 (zero on NULL).
type nullableInt struct{ Dest *int64 }

func (n *nullableInt) Scan(value interface{}) error {
	if value == nil {
		*n.Dest = 0
		return nil
	}
	switch v := value.(type) {
	case int64:
		*n.Dest = v
	case int:
		*n.Dest = int64(v)
	default:
		return fmt.Errorf("nullableInt: unexpected type %T", v)
	}
	return nil
}

// nullableFloat64 scans possibly NULL REAL into a float64 (zero on NULL).
type nullableFloat64 struct{ Dest *float64 }

func (n *nullableFloat64) Scan(value interface{}) error {
	if value == nil {
		*n.Dest = 0
		return nil
	}
	switch v := value.(type) {
	case float64:
		*n.Dest = v
	case int64:
		*n.Dest = float64(v)
	case int:
		*n.Dest = float64(v)
	default:
		return fmt.Errorf("nullableFloat64: unexpected type %T", v)
	}
	return nil
}

func isSQLiteBusy(err error) bool {
	if err == nil {
		return false
	}
	return strings.Contains(strings.ToLower(err.Error()), "sqlite_busy") ||
		strings.Contains(strings.ToLower(err.Error()), "database is locked")
}
