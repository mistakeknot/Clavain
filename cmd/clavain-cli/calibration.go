package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	_ "modernc.org/sqlite"
)

// ─── Calibrated Thresholds Types ──────────────────────────────────

// CalibratedThresholds is the on-disk format for calibrated-thresholds.json.
type CalibratedThresholds struct {
	CalibratedAt string                    `json:"calibrated_at"`
	WindowDays   int                       `json:"window_days"`
	Agents       map[string]AgentThreshold `json:"agents"`
}

// AgentThreshold holds the calibrated confidence threshold for one agent.
type AgentThreshold struct {
	ConfidenceThreshold float64 `json:"confidence_threshold"`
	ImprovementRate     float64 `json:"improvement_rate"`
	SampleCount         int     `json:"sample_count"`
}

// ─── Canary Outcome Recording ─────────────────────────────────────

// cmdInterspectRecordCanary records a canary outcome into interspect.db.
// Usage: interspect-record-canary --agent=<name> --override=<id> --metric=<m>
//
//	--baseline=<val> --measured=<val> --outcome=<improved|degraded|neutral>
func cmdInterspectRecordCanary(args []string) error {
	var agent, overrideID, metric, outcome string
	var baseline, measured float64
	var appliedAt int64

	for _, a := range args {
		switch {
		case strings.HasPrefix(a, "--agent="):
			agent = strings.TrimPrefix(a, "--agent=")
		case strings.HasPrefix(a, "--override="):
			overrideID = strings.TrimPrefix(a, "--override=")
		case strings.HasPrefix(a, "--metric="):
			metric = strings.TrimPrefix(a, "--metric=")
		case strings.HasPrefix(a, "--baseline="):
			v, err := strconv.ParseFloat(strings.TrimPrefix(a, "--baseline="), 64)
			if err != nil {
				return fmt.Errorf("interspect-record-canary: invalid --baseline: %w", err)
			}
			baseline = v
		case strings.HasPrefix(a, "--measured="):
			v, err := strconv.ParseFloat(strings.TrimPrefix(a, "--measured="), 64)
			if err != nil {
				return fmt.Errorf("interspect-record-canary: invalid --measured: %w", err)
			}
			measured = v
		case strings.HasPrefix(a, "--outcome="):
			outcome = strings.TrimPrefix(a, "--outcome=")
		case strings.HasPrefix(a, "--applied-at="):
			v, err := strconv.ParseInt(strings.TrimPrefix(a, "--applied-at="), 10, 64)
			if err != nil {
				return fmt.Errorf("interspect-record-canary: invalid --applied-at: %w", err)
			}
			appliedAt = v
		}
	}

	// Validate required fields
	if agent == "" || overrideID == "" || metric == "" || outcome == "" {
		return fmt.Errorf("usage: interspect-record-canary --agent=<name> --override=<id> --metric=<metric> --baseline=<val> --measured=<val> --outcome=<improved|degraded|neutral>")
	}
	switch outcome {
	case "improved", "degraded", "neutral":
		// valid
	default:
		return fmt.Errorf("interspect-record-canary: --outcome must be improved, degraded, or neutral (got %q)", outcome)
	}

	if appliedAt == 0 {
		appliedAt = time.Now().Unix()
	}

	db, err := openInterspectDB()
	if err != nil {
		// Fallback: write to pending JSONL
		return appendCanaryPending(agent, overrideID, metric, baseline, measured, outcome, appliedAt)
	}
	defer db.Close()

	// Ensure table exists
	if err := ensureCanaryOutcomesTable(db); err != nil {
		return appendCanaryPending(agent, overrideID, metric, baseline, measured, outcome, appliedAt)
	}

	now := time.Now().Unix()
	_, err = db.ExecContext(context.Background(),
		`INSERT INTO canary_outcomes (agent_name, override_id, applied_at, measured_at, metric, baseline_value, override_value, outcome)
		 VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
		agent, overrideID, appliedAt, now, metric, baseline, measured, outcome,
	)
	if err != nil {
		// SQLite busy — fallback
		return appendCanaryPending(agent, overrideID, metric, baseline, measured, outcome, appliedAt)
	}

	fmt.Fprintf(os.Stderr, "interspect: recorded canary outcome for %s (%s)\n", agent, outcome)
	return nil
}

// ─── Threshold Calibration ────────────────────────────────────────

// cmdInterspectCalibrateThresholds recalibrates confidence thresholds from canary outcomes.
// Usage: interspect-calibrate-thresholds [--window-days=30]
func cmdInterspectCalibrateThresholds(args []string) error {
	windowDays := 30
	for _, a := range args {
		if strings.HasPrefix(a, "--window-days=") {
			v, err := strconv.Atoi(strings.TrimPrefix(a, "--window-days="))
			if err != nil {
				return fmt.Errorf("interspect-calibrate-thresholds: invalid --window-days: %w", err)
			}
			windowDays = v
		}
	}

	db, err := openInterspectDB()
	if err != nil {
		return fmt.Errorf("interspect-calibrate-thresholds: %w", err)
	}
	defer db.Close()

	// Ensure table exists
	if err := ensureCanaryOutcomesTable(db); err != nil {
		return fmt.Errorf("interspect-calibrate-thresholds: %w", err)
	}

	// Step 1: Drain any pending records
	drainCanaryPending(db)

	// Step 2: Read outcomes from the window
	cutoff := time.Now().Add(-time.Duration(windowDays) * 24 * time.Hour).Unix()
	rows, err := db.QueryContext(context.Background(),
		`SELECT agent_name, outcome FROM canary_outcomes WHERE measured_at >= ?`, cutoff)
	if err != nil {
		return fmt.Errorf("interspect-calibrate-thresholds: query: %w", err)
	}
	defer rows.Close()

	type agentStats struct {
		improved int
		total    int
	}
	stats := map[string]*agentStats{}
	for rows.Next() {
		var agent, outcome string
		if err := rows.Scan(&agent, &outcome); err != nil {
			continue
		}
		s, ok := stats[agent]
		if !ok {
			s = &agentStats{}
			stats[agent] = s
		}
		s.total++
		if outcome == "improved" {
			s.improved++
		}
	}

	if len(stats) == 0 {
		fmt.Fprintln(os.Stderr, "interspect: no canary outcomes in window — skipping calibration")
		return nil
	}

	// Step 3: Load existing thresholds (to preserve values for agents without new data)
	existing := loadCalibratedThresholds()

	// Step 4: Compute new thresholds
	agents := map[string]AgentThreshold{}

	// Carry forward existing entries first
	if existing != nil {
		for k, v := range existing.Agents {
			agents[k] = v
		}
	}

	for agent, s := range stats {
		improvementRate := float64(s.improved) / float64(s.total)

		// Get current threshold (default 0.7)
		currentThreshold := 0.7
		if existing != nil {
			if at, ok := existing.Agents[agent]; ok {
				currentThreshold = at.ConfidenceThreshold
			}
		}

		newThreshold := currentThreshold
		if improvementRate > 0.6 {
			// Canary overrides are working well — lower threshold to apply more
			newThreshold = currentThreshold - 0.1
		} else if improvementRate < 0.3 {
			// Canary overrides are not working — raise threshold to be more selective
			newThreshold = currentThreshold + 0.1
		}
		// Clamp to [0.3, 0.95]
		newThreshold = math.Max(0.3, math.Min(0.95, newThreshold))

		agents[agent] = AgentThreshold{
			ConfidenceThreshold: newThreshold,
			ImprovementRate:     improvementRate,
			SampleCount:         s.total,
		}
	}

	// Step 5: Write calibrated-thresholds.json
	ct := CalibratedThresholds{
		CalibratedAt: time.Now().UTC().Format(time.RFC3339),
		WindowDays:   windowDays,
		Agents:       agents,
	}

	outPath := calibratedThresholdsPath()
	dir := filepath.Dir(outPath)
	if err := os.MkdirAll(dir, 0755); err != nil {
		return fmt.Errorf("interspect-calibrate-thresholds: mkdir: %w", err)
	}

	data, err := json.MarshalIndent(ct, "", "  ")
	if err != nil {
		return fmt.Errorf("interspect-calibrate-thresholds: marshal: %w", err)
	}

	tmpPath := outPath + ".tmp"
	if err := os.WriteFile(tmpPath, data, 0644); err != nil {
		return fmt.Errorf("interspect-calibrate-thresholds: write: %w", err)
	}
	if err := os.Rename(tmpPath, outPath); err != nil {
		return fmt.Errorf("interspect-calibrate-thresholds: rename: %w", err)
	}

	fmt.Fprintf(os.Stderr, "interspect: calibrated thresholds for %d agent(s) → %s\n", len(agents), outPath)
	return nil
}

// ─── DB Helpers ───────────────────────────────────────────────────

// openInterspectDB opens the interspect.db with busy_timeout for safe concurrent access.
func openInterspectDB() (*sql.DB, error) {
	dbPath := interspectDBPath()
	if _, err := os.Stat(dbPath); err != nil {
		return nil, fmt.Errorf("interspect.db not found at %s", dbPath)
	}

	db, err := sql.Open("sqlite", dbPath+"?_busy_timeout=5000")
	if err != nil {
		return nil, fmt.Errorf("open interspect.db: %w", err)
	}
	db.SetMaxOpenConns(1)
	return db, nil
}

// interspectDBPath returns the path to interspect.db.
func interspectDBPath() string {
	clavainDir := os.Getenv("CLAVAIN_DIR")
	if clavainDir == "" {
		clavainDir = filepath.Join(os.Getenv("HOME"), ".clavain")
	}
	return filepath.Join(clavainDir, "interspect", "interspect.db")
}

// calibratedThresholdsPath returns the path to calibrated-thresholds.json.
func calibratedThresholdsPath() string {
	clavainDir := os.Getenv("CLAVAIN_DIR")
	if clavainDir == "" {
		clavainDir = filepath.Join(os.Getenv("HOME"), ".clavain")
	}
	return filepath.Join(clavainDir, "interspect", "calibrated-thresholds.json")
}

// ensureCanaryOutcomesTable creates the canary_outcomes table if it doesn't exist.
func ensureCanaryOutcomesTable(db *sql.DB) error {
	_, err := db.ExecContext(context.Background(), `
		CREATE TABLE IF NOT EXISTS canary_outcomes (
			id INTEGER PRIMARY KEY,
			agent_name TEXT NOT NULL,
			override_id TEXT NOT NULL,
			applied_at INTEGER NOT NULL,
			measured_at INTEGER NOT NULL,
			metric TEXT NOT NULL,
			baseline_value REAL,
			override_value REAL,
			outcome TEXT NOT NULL
		);
		CREATE INDEX IF NOT EXISTS idx_canary_outcomes_agent ON canary_outcomes(agent_name);
		CREATE INDEX IF NOT EXISTS idx_canary_outcomes_measured ON canary_outcomes(measured_at);
	`)
	return err
}

// loadCalibratedThresholds loads calibrated-thresholds.json from disk.
// Returns nil if missing or corrupt (same pattern as loadInterspectCalibration).
func loadCalibratedThresholds() *CalibratedThresholds {
	path := calibratedThresholdsPath()
	data, err := os.ReadFile(path)
	if err != nil {
		return nil // File missing — expected
	}
	var ct CalibratedThresholds
	if err := json.Unmarshal(data, &ct); err != nil {
		fmt.Fprintf(os.Stderr, "interspect: warning: corrupt %s: %v\n", path, err)
		return nil
	}
	return &ct
}

// ─── Pending JSONL Fallback ───────────────────────────────────────

func canaryPendingPath() string {
	clavainDir := os.Getenv("CLAVAIN_DIR")
	if clavainDir == "" {
		clavainDir = filepath.Join(os.Getenv("HOME"), ".clavain")
	}
	return filepath.Join(clavainDir, "interspect", "canary-pending.jsonl")
}

type canaryPendingRecord struct {
	AgentName  string  `json:"agent_name"`
	OverrideID string  `json:"override_id"`
	Metric     string  `json:"metric"`
	Baseline   float64 `json:"baseline_value"`
	Measured   float64 `json:"override_value"`
	Outcome    string  `json:"outcome"`
	AppliedAt  int64   `json:"applied_at"`
	MeasuredAt int64   `json:"measured_at"`
}

func appendCanaryPending(agent, overrideID, metric string, baseline, measured float64, outcome string, appliedAt int64) error {
	rec := canaryPendingRecord{
		AgentName:  agent,
		OverrideID: overrideID,
		Metric:     metric,
		Baseline:   baseline,
		Measured:   measured,
		Outcome:    outcome,
		AppliedAt:  appliedAt,
		MeasuredAt: time.Now().Unix(),
	}
	data, err := json.Marshal(rec)
	if err != nil {
		return fmt.Errorf("interspect-record-canary: marshal pending: %w", err)
	}

	path := canaryPendingPath()
	if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil {
		return fmt.Errorf("interspect-record-canary: mkdir: %w", err)
	}

	f, err := os.OpenFile(path, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err != nil {
		return fmt.Errorf("interspect-record-canary: open pending: %w", err)
	}
	defer f.Close()

	_, err = f.Write(append(data, '\n'))
	if err != nil {
		return fmt.Errorf("interspect-record-canary: write pending: %w", err)
	}

	fmt.Fprintf(os.Stderr, "interspect: wrote canary outcome to pending JSONL (DB unavailable)\n")
	return nil
}

// drainCanaryPending reads canary-pending.jsonl and inserts rows into the DB.
// Removes the file after successful drain. Fails silently on errors.
func drainCanaryPending(db *sql.DB) {
	path := canaryPendingPath()
	data, err := os.ReadFile(path)
	if err != nil {
		return // No pending file — normal
	}

	lines := strings.Split(strings.TrimSpace(string(data)), "\n")
	inserted := 0
	for _, line := range lines {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		var rec canaryPendingRecord
		if err := json.Unmarshal([]byte(line), &rec); err != nil {
			continue
		}
		_, err := db.ExecContext(context.Background(),
			`INSERT INTO canary_outcomes (agent_name, override_id, applied_at, measured_at, metric, baseline_value, override_value, outcome)
			 VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
			rec.AgentName, rec.OverrideID, rec.AppliedAt, rec.MeasuredAt, rec.Metric, rec.Baseline, rec.Measured, rec.Outcome,
		)
		if err == nil {
			inserted++
		}
	}

	if inserted > 0 {
		fmt.Fprintf(os.Stderr, "interspect: drained %d pending canary record(s)\n", inserted)
	}

	// Remove pending file after drain
	os.Remove(path)
}
