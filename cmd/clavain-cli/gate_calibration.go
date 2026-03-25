package main

import (
	"encoding/json"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"strconv"
	"time"

	pkgphase "github.com/mistakeknot/intercore/pkg/phase"
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

const (
	halfLifeDays         = 30
	promotionFNRThresh   = 0.30
	promotionMinN        = 10.0
	cooldownDays         = 7
	velocityLimitChanges = 2
	velocityWindowDays   = 90
)

// cmdCalibrateGateTiers recalibrates gate tier assignments from signal data.
// Usage: calibrate-gate-tiers [--dry-run]
func cmdCalibrateGateTiers(args []string) error {
	dryRun := false
	for _, a := range args {
		if a == "--dry-run" {
			dryRun = true
		}
	}

	// Step 1: Load existing calibration file (for cursor + existing tiers)
	calPath := gateCalibrationFilePath()
	existing := loadGateCalibrationFile(calPath)
	sinceID := int64(0)
	if existing != nil {
		sinceID = existing.SinceID
	}

	// Step 2: Fetch new signals from intercore via subprocess
	var sr signalResult
	err := runICJSON(&sr, "gate", "signals", "--since-id="+strconv.FormatInt(sinceID, 10))
	if err != nil {
		return fmt.Errorf("calibrate-gate-tiers: fetch signals: %w", err)
	}

	if len(sr.Signals) == 0 && existing != nil {
		fmt.Fprintln(os.Stderr, "calibrate-gate-tiers: no new signals — calibration unchanged")
		return nil
	}

	// Step 3: Build weighted signal counts per key
	type signalCounts struct {
		weightedTP float64
		weightedFP float64
		weightedTN float64
		weightedFN float64
	}
	counts := map[string]*signalCounts{}

	now := time.Now().Unix()
	ln2 := math.Ln2

	for _, sig := range sr.Signals {
		key := pkgphase.GateCalibrationKey(sig.CheckType, sig.FromPhase, sig.ToPhase)
		sc, ok := counts[key]
		if !ok {
			sc = &signalCounts{}
			counts[key] = sc
		}

		ageDays := float64(now-sig.CreatedAt) / 86400.0
		weight := math.Exp(-ln2 * ageDays / halfLifeDays)

		switch sig.Signal {
		case "tp":
			sc.weightedTP += weight
		case "fp":
			sc.weightedFP += weight
		case "tn":
			sc.weightedTN += weight
		case "fn":
			sc.weightedFN += weight
		}
	}

	// Step 4: Merge with existing tiers and compute rates
	tiers := make(map[string]GateCalibrationEntry)
	if existing != nil {
		for k, v := range existing.Tiers {
			tiers[k] = v
		}
	}

	promoted := 0
	for key, sc := range counts {
		weightedN := sc.weightedTP + sc.weightedFP + sc.weightedTN + sc.weightedFN

		// Compute FPR and FNR
		var fpr, fnr float64
		if sc.weightedTP+sc.weightedFP > 0 {
			fpr = sc.weightedFP / (sc.weightedTP + sc.weightedFP)
		}
		if sc.weightedTN+sc.weightedFN > 0 {
			fnr = sc.weightedFN / (sc.weightedTN + sc.weightedFN)
		}

		entry, exists := tiers[key]
		if !exists {
			entry = GateCalibrationEntry{Tier: "soft"}
		}
		entry.FPR = fpr
		entry.FNR = fnr
		entry.WeightedN = weightedN
		entry.UpdatedAt = now

		// Skip locked entries
		if entry.Locked {
			tiers[key] = entry
			continue
		}

		// Promotion rule: soft→hard if FNR > threshold AND sufficient data
		if entry.Tier == "soft" && fnr > promotionFNRThresh && weightedN >= promotionMinN {
			// Check 7-day cooldown
			if entry.LastChangedAt > 0 {
				daysSinceChange := float64(now-entry.LastChangedAt) / 86400.0
				if daysSinceChange < cooldownDays {
					fmt.Fprintf(os.Stderr, "calibrate-gate-tiers: %s — promotion blocked (cooldown: %.0f days remaining)\n",
						key, float64(cooldownDays)-daysSinceChange)
					tiers[key] = entry
					continue
				}
			}

			// Check velocity limit (>2 changes in 90 days → lock)
			if entry.ChangeCount90d >= velocityLimitChanges {
				fmt.Fprintf(os.Stderr, "calibrate-gate-tiers: %s — velocity limit hit (%d changes in 90d), locking\n",
					key, entry.ChangeCount90d)
				entry.Locked = true
				tiers[key] = entry
				continue
			}

			// Promote
			entry.Tier = "hard"
			entry.LastChangedAt = now
			entry.ChangeCount90d++
			promoted++
			fmt.Fprintf(os.Stderr, "calibrate-gate-tiers: %s — promoted soft→hard (FNR=%.2f, n=%.1f)\n",
				key, fnr, weightedN)
		}

		tiers[key] = entry
	}

	// Emit interspect events (best-effort)
	if promoted > 0 {
		emitInterspectEvent("calibration_checkpoint", fmt.Sprintf("promoted %d gate(s)", promoted))
	}
	// Data starvation: warn if any key has weighted_n < 5
	for key, entry := range tiers {
		if entry.WeightedN < 5 && !entry.Locked {
			emitInterspectEvent("calibration_data_starvation", fmt.Sprintf("%s: n=%.1f", key, entry.WeightedN))
		}
	}

	// Step 5: Write calibration file (tmp+rename for atomicity)
	calFile := GateCalibrationFile{
		CreatedAt: now,
		SinceID:   sr.Cursor,
		Tiers:     tiers,
	}

	if dryRun {
		data, _ := json.MarshalIndent(calFile, "", "  ")
		fmt.Println(string(data))
		return nil
	}

	dir := filepath.Dir(calPath)
	if err := os.MkdirAll(dir, 0755); err != nil {
		return fmt.Errorf("calibrate-gate-tiers: mkdir: %w", err)
	}

	data, err := json.MarshalIndent(calFile, "", "  ")
	if err != nil {
		return fmt.Errorf("calibrate-gate-tiers: marshal: %w", err)
	}

	tmpPath := calPath + ".tmp"
	if err := os.WriteFile(tmpPath, data, 0644); err != nil {
		return fmt.Errorf("calibrate-gate-tiers: write: %w", err)
	}
	if err := os.Rename(tmpPath, calPath); err != nil {
		return fmt.Errorf("calibrate-gate-tiers: rename: %w", err)
	}

	fmt.Fprintf(os.Stderr, "calibrate-gate-tiers: %d key(s), %d promoted → %s\n",
		len(tiers), promoted, calPath)
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
