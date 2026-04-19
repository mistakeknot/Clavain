package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"time"

	"github.com/mistakeknot/clavain-cli/gatecal"
)

// ─── Gate Calibration Types ──────────────────────────────────────

// GateCalibrationFile is the on-disk format for gate-tier-calibration.json.
type GateCalibrationFile struct {
	CreatedAt int64                           `json:"created_at"`
	SinceID   int64                           `json:"since_id"` // cursor for incremental signal extraction
	Tiers     map[string]GateCalibrationEntry `json:"tiers"`    // keyed by GateCalibrationKey
}

// GateCalibrationEntry holds calibration data for one check×transition.
type GateCalibrationEntry struct {
	Tier           string  `json:"tier"`
	Locked         bool    `json:"locked"`
	FPR            float64 `json:"fpr"`
	FNR            float64 `json:"fnr"`
	WeightedN      float64 `json:"weighted_n"`
	LastChangedAt  int64   `json:"last_changed_at,omitempty"`  // unix timestamp of last tier change
	ChangeCount90d int     `json:"change_count_90d,omitempty"` // tier changes in last 90 days
	UpdatedAt      int64   `json:"updated_at"`
}

// signalResult matches the JSON output of `ic gate signals`.
type signalResult struct {
	Signals []gateSignal `json:"signals"`
	Cursor  int64        `json:"cursor"`
}

type gateSignal struct {
	EventID   int64  `json:"event_id"`
	RunID     string `json:"run_id"`
	CheckType string `json:"check_type"`
	FromPhase string `json:"from_phase"`
	ToPhase   string `json:"to_phase"`
	Signal    string `json:"signal_type"`
	CreatedAt int64  `json:"created_at"`
	Category  string `json:"category,omitempty"`
}

// ErrNoNewSignals is returned by calibrate-gate-tiers when no new signals were available.
var ErrNoNewSignals = errors.New("calibrate-gate-tiers: no new signals")

// cmdCalibrateGateTiers recalibrates gate tier assignments from signal data.
// Usage: calibrate-gate-tiers [--auto] [--dry-run]
func cmdCalibrateGateTiers(args []string) error {
	autoMode := false
	dryRun := false
	for _, a := range args {
		switch a {
		case "--auto":
			autoMode = true
		case "--dry-run":
			dryRun = true
		}
	}

	invoker := "manual"
	if autoMode {
		invoker = "auto"
	}

	calPath := gateCalibrationFilePath()
	dbPath := filepath.Join(filepath.Dir(calPath), "gate.db")

	s, err := gatecal.Open(dbPath)
	if err != nil {
		return fmt.Errorf("calibrate-gate-tiers: open gate.db: %w", err)
	}
	defer s.Close()

	ctx := context.Background()
	if err := s.MigrateFromV1(ctx, calPath); err != nil {
		return fmt.Errorf("calibrate-gate-tiers: migrate: %w", err)
	}

	sinceID := int64(0)
	if err := s.DB().QueryRowContext(ctx, `SELECT COALESCE(MAX(since_id_after), 0) FROM drain_log WHERE drain_committed IS NOT NULL`).Scan(&sinceID); err != nil {
		return fmt.Errorf("calibrate-gate-tiers: read cursor: %w", err)
	}

	var sr signalResult
	if err := runICJSON(&sr, "gate", "signals", "--since-id="+strconv.FormatInt(sinceID, 10)); err != nil {
		return fmt.Errorf("calibrate-gate-tiers: fetch signals: %w", err)
	}

	signals := make([]gatecal.GateSignal, 0, len(sr.Signals))
	for _, sig := range sr.Signals {
		signals = append(signals, gatecal.GateSignal{
			EventID:   sig.EventID,
			RunID:     sig.RunID,
			CheckType: sig.CheckType,
			FromPhase: sig.FromPhase,
			ToPhase:   sig.ToPhase,
			Signal:    sig.Signal,
			CreatedAt: sig.CreatedAt,
			Category:  sig.Category,
		})
	}

	now := time.Now().Unix()
	res, err := s.Drain(ctx, now, invoker, signals)
	if err != nil {
		return fmt.Errorf("calibrate-gate-tiers: drain: %w", err)
	}

	if !dryRun {
		if err := s.ExportV1JSON(ctx, calPath, res.SinceIDAfter); err != nil {
			return fmt.Errorf("calibrate-gate-tiers: export: %w", err)
		}
	}

	if res.StateChanges > 0 {
		emitInterspectEvent("calibration_checkpoint", fmt.Sprintf("state changes=%d", res.StateChanges))
	}

	fmt.Fprintf(os.Stderr, "calibrate-gate-tiers: signals=%d, state_changes=%d → %s\n",
		res.SignalsProcessed, res.StateChanges, calPath)
	if res.SignalsProcessed == 0 {
		return ErrNoNewSignals
	}
	return nil
}

// gateCalibrationFilePath returns the path to gate-tier-calibration.json.
// Walks up from CWD looking for .clavain/intercore.db — uses that parent dir.
func gateCalibrationFilePath() string {
	dir, err := os.Getwd()
	if err != nil {
		return filepath.Join(".", ".clavain", "gate-tier-calibration.json")
	}

	for {
		candidate := filepath.Join(dir, ".clavain", "intercore.db")
		if _, err := os.Stat(candidate); err == nil {
			return filepath.Join(dir, ".clavain", "gate-tier-calibration.json")
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			break
		}
		dir = parent
	}

	// Fallback: use CWD
	return filepath.Join(".", ".clavain", "gate-tier-calibration.json")
}

// loadGateCalibrationFile loads gate-tier-calibration.json from disk.
// Returns nil if missing or corrupt.
func loadGateCalibrationFile(path string) *GateCalibrationFile {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil
	}
	var f GateCalibrationFile
	if err := json.Unmarshal(data, &f); err != nil {
		fmt.Fprintf(os.Stderr, "calibrate-gate-tiers: warning: corrupt %s: %v\n", path, err)
		return nil
	}
	return &f
}

// emitInterspectEvent emits an interspect event (best-effort, fires and forgets).
func emitInterspectEvent(eventType, detail string) {
	// Use ic events add if available, otherwise skip
	_, _ = runIC("events", "add", "--type="+eventType, "--detail="+detail)
}
