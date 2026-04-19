package gatecal

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestExportV1JSONBasic(t *testing.T) {
	dir := t.TempDir()
	dbPath := filepath.Join(dir, "gate.db")
	jsonPath := filepath.Join(dir, "gate-tier-calibration.json")

	s, err := Open(dbPath)
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer s.Close()

	now := time.Now().Unix()

	_, err = s.Drain(context.Background(), now, "auto", []GateSignal{
		{EventID: 1, CheckType: "safety_secrets", FromPhase: "design", ToPhase: "plan", Signal: "tn", CreatedAt: now},
		{EventID: 2, CheckType: "safety_secrets", FromPhase: "design", ToPhase: "plan", Signal: "tn", CreatedAt: now},
	})
	if err != nil {
		t.Fatalf("Drain: %v", err)
	}

	_, err = s.DB().Exec(
		`INSERT INTO tier_state (theme, check_type, phase_from, phase_to, tier, weighted_n, theme_source, updated_at) VALUES ('compliance', 'safety_secrets', 'design', 'plan', 'hard', 12, 'labeled', ?)`,
		now,
	)
	if err != nil {
		t.Fatalf("seed hard tier: %v", err)
	}

	if err := s.ExportV1JSON(context.Background(), jsonPath, 1234); err != nil {
		t.Fatalf("ExportV1JSON: %v", err)
	}

	data, err := os.ReadFile(jsonPath)
	if err != nil {
		t.Fatalf("ReadFile: %v", err)
	}

	var got v1File
	if err := json.Unmarshal(data, &got); err != nil {
		t.Fatalf("export not v1 shape: %v", err)
	}

	if got.SinceID != 1234 {
		t.Errorf("since_id=%d want=1234", got.SinceID)
	}
	entry, ok := got.Tiers["safety_secrets|design|plan"]
	if !ok {
		t.Fatalf("missing key safety_secrets|design|plan")
	}
	if entry.Tier != "hard" {
		t.Errorf("worst-case tier failed: got=%q want=hard", entry.Tier)
	}
}

func TestExportV1JSONAtomicNoTmpResidue(t *testing.T) {
	dir := t.TempDir()
	jsonPath := filepath.Join(dir, "gate-tier-calibration.json")

	s, err := Open(filepath.Join(dir, "gate.db"))
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer s.Close()

	if err := s.ExportV1JSON(context.Background(), jsonPath, 0); err != nil {
		t.Fatalf("ExportV1JSON: %v", err)
	}

	if _, err := os.Stat(jsonPath + ".tmp"); !os.IsNotExist(err) {
		t.Errorf("expected no .tmp residue, got: %v", err)
	}
}
