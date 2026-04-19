package gatecal

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

type v1Shape struct {
	CreatedAt int64                  `json:"created_at"`
	SinceID   int64                  `json:"since_id"`
	Tiers     map[string]v1EntryTest `json:"tiers"`
}

type v1EntryTest struct {
	Tier           string  `json:"tier"`
	Locked         bool    `json:"locked"`
	FPR            float64 `json:"fpr"`
	FNR            float64 `json:"fnr"`
	WeightedN      float64 `json:"weighted_n"`
	LastChangedAt  int64   `json:"last_changed_at,omitempty"`
	ChangeCount90d int     `json:"change_count_90d,omitempty"`
	UpdatedAt      int64   `json:"updated_at"`
}

func TestMigrateFromV1Inserts(t *testing.T) {
	dir := t.TempDir()
	v1Path := filepath.Join(dir, "gate-tier-calibration.json")
	v1 := v1Shape{
		CreatedAt: 1700000000,
		SinceID:   42,
		Tiers: map[string]v1EntryTest{
			"safety_secrets|brainstorm|design":  {Tier: "hard", FPR: 0.1, FNR: 0.4, WeightedN: 12, UpdatedAt: 1700000000},
			"quality_test_pass|design|planning": {Tier: "soft", FPR: 0.05, FNR: 0.2, WeightedN: 8, UpdatedAt: 1700000000},
			"random_check|x|y":                  {Tier: "soft", FPR: 0, FNR: 0, WeightedN: 0, UpdatedAt: 1700000000},
		},
	}
	data, _ := json.MarshalIndent(v1, "", "  ")
	if err := os.WriteFile(v1Path, data, 0o644); err != nil {
		t.Fatal(err)
	}

	s, err := Open(filepath.Join(dir, "gate.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer s.Close()

	if err := s.MigrateFromV1(context.Background(), v1Path); err != nil {
		t.Fatalf("MigrateFromV1: %v", err)
	}

	var n int
	err = s.DB().QueryRow(`SELECT COUNT(*) FROM tier_state WHERE theme='default' AND theme_source='migrated'`).Scan(&n)
	if err != nil {
		t.Fatal(err)
	}
	if n != 3 {
		t.Errorf("expected 3 migrated rows, got %d", n)
	}

	rows, err := s.DB().Query(`SELECT origin_key FROM tier_state ORDER BY origin_key`)
	if err != nil {
		t.Fatal(err)
	}
	defer rows.Close()

	got := []string{}
	for rows.Next() {
		var k string
		if err := rows.Scan(&k); err != nil {
			t.Fatalf("scan origin_key: %v", err)
		}
		got = append(got, k)
	}
	want := []string{
		"quality_test_pass|design|planning",
		"random_check|x|y",
		"safety_secrets|brainstorm|design",
	}
	for i := range want {
		if got[i] != want[i] {
			t.Errorf("origin_key[%d] = %q, want %q", i, got[i], want[i])
		}
	}

	if _, err := os.Stat(v1Path + ".v1.json.bak"); err != nil {
		t.Errorf("expected .v1.json.bak: %v", err)
	}
	if _, err := os.Stat(v1Path); !os.IsNotExist(err) {
		t.Errorf("expected v1 path removed, got %v", err)
	}
}

func TestMigrateFromV1Idempotent(t *testing.T) {
	dir := t.TempDir()
	v1Path := filepath.Join(dir, "gate-tier-calibration.json")
	v1 := v1Shape{Tiers: map[string]v1EntryTest{"a|b|c": {Tier: "soft"}}}
	data, _ := json.MarshalIndent(v1, "", "  ")
	_ = os.WriteFile(v1Path, data, 0o644)

	s, _ := Open(filepath.Join(dir, "gate.db"))
	defer s.Close()

	if err := s.MigrateFromV1(context.Background(), v1Path); err != nil {
		t.Fatal(err)
	}
	_ = os.WriteFile(v1Path, data, 0o644)
	if err := s.MigrateFromV1(context.Background(), v1Path); err != nil {
		t.Fatalf("second MigrateFromV1: %v", err)
	}

	var n int
	if err := s.DB().QueryRow(`SELECT COUNT(*) FROM tier_state`).Scan(&n); err != nil {
		t.Fatalf("count tier_state: %v", err)
	}
	if n != 1 {
		t.Errorf("expected idempotent (1 row), got %d", n)
	}
}

func TestMigrateFromV1NoFile(t *testing.T) {
	dir := t.TempDir()
	s, _ := Open(filepath.Join(dir, "gate.db"))
	defer s.Close()

	if err := s.MigrateFromV1(context.Background(), filepath.Join(dir, "nonexistent.json")); err != nil {
		t.Errorf("expected nil for missing v1 file, got %v", err)
	}
}
