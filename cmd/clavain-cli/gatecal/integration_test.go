package gatecal

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestFullFlowMigrateDrainExport(t *testing.T) {
	dir := t.TempDir()
	clavainDir := filepath.Join(dir, ".clavain")
	if err := os.MkdirAll(clavainDir, 0o755); err != nil {
		t.Fatalf("MkdirAll: %v", err)
	}

	dbPath := filepath.Join(clavainDir, "gate.db")
	jsonPath := filepath.Join(clavainDir, "gate-tier-calibration.json")

	// Seed legacy v1 JSON with one entry to migrate.
	seed := v1File{
		CreatedAt: 1,
		SinceID:   0,
		Tiers: map[string]v1Entry{
			"perf_p99|design|plan": {
				Tier:      "soft",
				FPR:       0,
				FNR:       0,
				WeightedN: 0,
				UpdatedAt: 1,
			},
		},
	}
	seedBytes, err := json.MarshalIndent(seed, "", "  ")
	if err != nil {
		t.Fatalf("MarshalIndent seed: %v", err)
	}
	if err := os.WriteFile(jsonPath, seedBytes, 0o644); err != nil {
		t.Fatalf("WriteFile seed: %v", err)
	}

	s, err := Open(dbPath)
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer s.Close()

	if err := s.MigrateFromV1(context.Background(), jsonPath); err != nil {
		t.Fatalf("MigrateFromV1: %v", err)
	}

	if _, err := os.Stat(jsonPath + ".v1.json.bak"); err != nil {
		t.Fatalf("expected archive after migrate: %v", err)
	}

	now := time.Now().Unix()

	// Run three drains. safety_* should promote to hard after 3 stable windows;
	// quality_* should remain soft.
	for i := 0; i < 3; i++ {
		drainNow := now + int64(i)
		base := int64(100 + i*100)
		signals := make([]GateSignal, 0, 20)

		for j := int64(0); j < 6; j++ {
			signals = append(signals, GateSignal{
				EventID:   base + j,
				CheckType: "safety_secrets",
				FromPhase: "design",
				ToPhase:   "plan",
				Signal:    "tn",
				CreatedAt: drainNow,
			})
		}
		for j := int64(0); j < 4; j++ {
			signals = append(signals, GateSignal{
				EventID:   base + 6 + j,
				CheckType: "safety_secrets",
				FromPhase: "design",
				ToPhase:   "plan",
				Signal:    "fn",
				CreatedAt: drainNow,
			})
		}
		for j := int64(0); j < 10; j++ {
			signals = append(signals, GateSignal{
				EventID:   base + 50 + j,
				CheckType: "quality_test_pass",
				FromPhase: "design",
				ToPhase:   "plan",
				Signal:    "tn",
				CreatedAt: drainNow,
			})
		}

		res, err := s.Drain(context.Background(), drainNow, "auto", signals)
		if err != nil {
			t.Fatalf("Drain %d: %v", i+1, err)
		}
		if res.SignalsProcessed != len(signals) {
			t.Fatalf("Drain %d processed=%d want=%d", i+1, res.SignalsProcessed, len(signals))
		}
	}

	var safetyTier string
	if err := s.DB().QueryRow(
		`SELECT tier FROM tier_state WHERE check_type='safety_secrets' AND theme='safety' AND phase_from='design' AND phase_to='plan'`,
	).Scan(&safetyTier); err != nil {
		t.Fatalf("query safety tier: %v", err)
	}
	if safetyTier != "hard" {
		t.Fatalf("safety tier=%q want=hard", safetyTier)
	}

	var qualityTier string
	if err := s.DB().QueryRow(
		`SELECT tier FROM tier_state WHERE check_type='quality_test_pass' AND theme='quality' AND phase_from='design' AND phase_to='plan'`,
	).Scan(&qualityTier); err != nil {
		t.Fatalf("query quality tier: %v", err)
	}
	if qualityTier != "soft" {
		t.Fatalf("quality tier=%q want=soft", qualityTier)
	}

	var committed int
	if err := s.DB().QueryRow(
		`SELECT COUNT(*) FROM drain_log WHERE drain_committed IS NOT NULL AND invoker='auto'`,
	).Scan(&committed); err != nil {
		t.Fatalf("count committed drains: %v", err)
	}
	if committed != 3 {
		t.Fatalf("committed drains=%d want=3", committed)
	}

	var maxCursor int64
	if err := s.DB().QueryRow(`SELECT MAX(since_id_after) FROM drain_log`).Scan(&maxCursor); err != nil {
		t.Fatalf("max cursor: %v", err)
	}

	if err := s.ExportV1JSON(context.Background(), jsonPath, maxCursor); err != nil {
		t.Fatalf("ExportV1JSON: %v", err)
	}

	exportBytes, err := os.ReadFile(jsonPath)
	if err != nil {
		t.Fatalf("ReadFile export: %v", err)
	}

	var exported v1File
	if err := json.Unmarshal(exportBytes, &exported); err != nil {
		t.Fatalf("export JSON parse: %v", err)
	}

	safetyEntry, ok := exported.Tiers["safety_secrets|design|plan"]
	if !ok {
		t.Fatalf("missing exported safety key")
	}
	if safetyEntry.Tier != "hard" {
		t.Fatalf("exported safety tier=%q want=hard", safetyEntry.Tier)
	}

	qualityEntry, ok := exported.Tiers["quality_test_pass|design|plan"]
	if !ok {
		t.Fatalf("missing exported quality key")
	}
	if qualityEntry.Tier != "soft" {
		t.Fatalf("exported quality tier=%q want=soft", qualityEntry.Tier)
	}

	if _, err := os.Stat(jsonPath + ".v1.json.bak"); err != nil {
		t.Fatalf("expected archived v1 file to remain: %v", err)
	}
}
