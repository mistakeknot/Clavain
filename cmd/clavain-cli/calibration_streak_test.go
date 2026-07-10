package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"
)

var calibrationTestTime = time.Date(2026, 7, 10, 16, 0, 0, 0, time.UTC)

func makeCalibrationTestRoot(t *testing.T) string {
	t.Helper()
	root := t.TempDir()
	if err := os.MkdirAll(filepath.Join(root, ".beads"), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, ".beads", "metadata.json"), []byte("{}\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	return root
}

func validCalibrationReceipt(n int) CalibrationReceipt {
	stamp := calibrationTestTime.Add(time.Duration(n) * time.Minute)
	loops := make(map[string]CalibrationLoopReceipt, len(calibrationLoopNames))
	for _, loop := range calibrationLoopNames {
		loops[loop] = CalibrationLoopReceipt{
			Outcome:       CalibrationOutcomeValidNoop,
			BeforeHash:    "stable-" + loop,
			AfterHash:     "stable-" + loop,
			EvidenceCount: 10,
			Detail:        "calibration inputs checked; no threshold change required",
		}
	}
	return CalibrationReceipt{
		SessionID: fmt.Sprintf("session-%02d", n),
		SprintID:  fmt.Sprintf("sprint-%02d", n),
		Host:      "clavain-test",
		Timestamp: stamp.Format(time.RFC3339Nano),
		Loops:     loops,
	}
}

func mustRecordCalibrationReceipt(t *testing.T, root string, receipt CalibrationReceipt) {
	t.Helper()
	if err := recordCalibrationReceiptAt(root, receipt); err != nil {
		t.Fatalf("recordCalibrationReceiptAt: %v", err)
	}
}

func TestCalibrationStreakV1MigrationResetsProof(t *testing.T) {
	root := makeCalibrationTestRoot(t)
	path := calibrationStreakPathAt(root)
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatal(err)
	}
	v1 := `{
  "schema_version": 1,
  "target": 10,
  "aggregate_current": 8,
  "aggregate_best": 8,
  "loops": {
    "routing": {"current": 8, "best": 8},
    "gate_threshold": {"current": 8, "best": 8},
    "phase_cost": {"current": 8, "best": 8}
  }
}`
	if err := os.WriteFile(path, []byte(v1), 0o644); err != nil {
		t.Fatal(err)
	}

	state, err := loadCalibrationStreakAt(root)
	if err != nil {
		t.Fatalf("loadCalibrationStreakAt: %v", err)
	}
	if state.SchemaVersion != calibrationStreakSchemaVersion {
		t.Fatalf("schema version = %d, want %d", state.SchemaVersion, calibrationStreakSchemaVersion)
	}
	if state.AggregateCurrent != 0 || state.AggregateBest != 0 {
		t.Fatalf("migrated aggregate = %d/%d, want 0/0", state.AggregateCurrent, state.AggregateBest)
	}
	for _, loop := range calibrationLoopNames {
		if got := state.Loops[loop]; got.Current != 0 || got.Best != 0 {
			t.Fatalf("migrated %s = %+v, want zeroed counters", loop, got)
		}
	}
	if state.ProofEpoch == "" || state.ProofStartedAt == "" {
		t.Fatalf("migration did not start a proof epoch: %+v", state)
	}
	if len(state.Receipts) != 0 {
		t.Fatalf("migration retained unverified receipts: %+v", state.Receipts)
	}

	persisted, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(persisted), `"schema_version": 2`) {
		t.Fatalf("migration was not persisted: %s", persisted)
	}
}

func TestCalibrationStreakRecordsValidReceipt(t *testing.T) {
	root := makeCalibrationTestRoot(t)
	receipt := validCalibrationReceipt(1)
	mustRecordCalibrationReceipt(t, root, receipt)

	state, err := loadCalibrationStreakAt(root)
	if err != nil {
		t.Fatal(err)
	}
	if state.AggregateCurrent != 1 || state.AggregateBest != 1 {
		t.Fatalf("aggregate = %d/%d, want 1/1", state.AggregateCurrent, state.AggregateBest)
	}
	if len(state.Receipts) != 1 {
		t.Fatalf("receipts = %d, want 1", len(state.Receipts))
	}
	got := state.Receipts[0]
	if got.SessionID != receipt.SessionID || got.SprintID != receipt.SprintID || got.Host == "" || got.Timestamp == "" {
		t.Fatalf("receipt identity/evidence fields not persisted: %+v", got)
	}
	for _, loop := range calibrationLoopNames {
		if got.Loops[loop].Detail == "" || got.Loops[loop].EvidenceCount != 10 {
			t.Fatalf("%s receipt incomplete: %+v", loop, got.Loops[loop])
		}
	}
}

func TestCalibrationStreakLoopFailureResetsProof(t *testing.T) {
	root := makeCalibrationTestRoot(t)
	mustRecordCalibrationReceipt(t, root, validCalibrationReceipt(1))
	mustRecordCalibrationReceipt(t, root, validCalibrationReceipt(2))
	failed := validCalibrationReceipt(3)
	gate := failed.Loops["gate_threshold"]
	gate.Outcome = CalibrationOutcomeFailed
	gate.Detail = "gate calibration command exited nonzero"
	failed.Loops["gate_threshold"] = gate
	mustRecordCalibrationReceipt(t, root, failed)

	state, err := loadCalibrationStreakAt(root)
	if err != nil {
		t.Fatal(err)
	}
	if state.Loops["gate_threshold"].Current != 0 || state.AggregateCurrent != 0 {
		t.Fatalf("failed loop did not reset current proof: %+v", state)
	}
	if state.Loops["gate_threshold"].Best != 2 || state.AggregateBest != 2 {
		t.Fatalf("failed loop erased best proof: %+v", state)
	}
}

func TestCalibrationStreakRejectsDuplicateSessionOrSprint(t *testing.T) {
	for _, tc := range []struct {
		name   string
		mutate func(*CalibrationReceipt)
	}{
		{name: "session", mutate: func(r *CalibrationReceipt) { r.SprintID = "different-sprint" }},
		{name: "sprint", mutate: func(r *CalibrationReceipt) { r.SessionID = "different-session" }},
	} {
		t.Run(tc.name, func(t *testing.T) {
			root := makeCalibrationTestRoot(t)
			first := validCalibrationReceipt(1)
			mustRecordCalibrationReceipt(t, root, first)
			duplicate := first
			duplicate.Loops = validCalibrationReceipt(2).Loops
			tc.mutate(&duplicate)
			err := recordCalibrationReceiptAt(root, duplicate)
			if err == nil || !strings.Contains(err.Error(), "duplicate") {
				t.Fatalf("duplicate record error = %v, want duplicate rejection", err)
			}
			state, loadErr := loadCalibrationStreakAt(root)
			if loadErr != nil {
				t.Fatal(loadErr)
			}
			if len(state.Receipts) != 1 {
				t.Fatalf("duplicate receipt was persisted: %+v", state.Receipts)
			}
		})
	}
}

func TestCalibrationStreakManualAndHashDriftResetProof(t *testing.T) {
	t.Run("manual", func(t *testing.T) {
		root := makeCalibrationTestRoot(t)
		mustRecordCalibrationReceipt(t, root, validCalibrationReceipt(1))
		mustRecordCalibrationReceipt(t, root, validCalibrationReceipt(2))
		if err := recordCalibrationManualAt(root, "phase_cost", "reflect-command", calibrationTestTime.Add(3*time.Minute)); err != nil {
			t.Fatal(err)
		}
		state, err := loadCalibrationStreakAt(root)
		if err != nil {
			t.Fatal(err)
		}
		if state.Loops["phase_cost"].Current != 0 || state.AggregateCurrent != 0 {
			t.Fatalf("manual intervention did not reset proof: %+v", state)
		}
		if len(state.ManualResets) != 1 || state.ManualResets[0].Reason != "reflect-command" {
			t.Fatalf("manual reset audit missing: %+v", state.ManualResets)
		}
	})

	t.Run("hash drift", func(t *testing.T) {
		root := makeCalibrationTestRoot(t)
		first := validCalibrationReceipt(1)
		for _, loop := range calibrationLoopNames {
			value := first.Loops[loop]
			value.Outcome = CalibrationOutcomeUpdated
			value.BeforeHash = "before-" + loop
			value.AfterHash = "after-" + loop
			first.Loops[loop] = value
		}
		mustRecordCalibrationReceipt(t, root, first)
		drift := validCalibrationReceipt(2)
		for _, loop := range calibrationLoopNames {
			value := drift.Loops[loop]
			value.BeforeHash = "after-" + loop
			value.AfterHash = "after-" + loop
			drift.Loops[loop] = value
		}
		routing := drift.Loops["routing"]
		routing.BeforeHash = "manually-edited-routing-hash"
		routing.AfterHash = "manually-edited-routing-hash"
		drift.Loops["routing"] = routing
		mustRecordCalibrationReceipt(t, root, drift)
		state, err := loadCalibrationStreakAt(root)
		if err != nil {
			t.Fatal(err)
		}
		if state.Loops["routing"].Current != 0 || state.AggregateCurrent != 0 {
			t.Fatalf("hash drift did not reset proof: %+v", state)
		}
	})
}

func TestCalibrationStreakConcurrentWritersDoNotLoseReceipts(t *testing.T) {
	root := makeCalibrationTestRoot(t)
	const writers = 24
	errCh := make(chan error, writers)
	var wg sync.WaitGroup
	for i := 1; i <= writers; i++ {
		wg.Add(1)
		go func(n int) {
			defer wg.Done()
			errCh <- recordCalibrationReceiptAt(root, validCalibrationReceipt(n))
		}(i)
	}
	wg.Wait()
	close(errCh)
	for err := range errCh {
		if err != nil {
			t.Fatalf("concurrent record: %v", err)
		}
	}
	state, err := loadCalibrationStreakAt(root)
	if err != nil {
		t.Fatal(err)
	}
	if len(state.Receipts) != writers {
		t.Fatalf("receipts = %d, want %d", len(state.Receipts), writers)
	}
	if state.AggregateCurrent != writers {
		t.Fatalf("aggregate current = %d, want %d", state.AggregateCurrent, writers)
	}
}

func TestCalibrationStreakVerifyRequiresTarget(t *testing.T) {
	root := makeCalibrationTestRoot(t)
	for i := 1; i <= 9; i++ {
		mustRecordCalibrationReceipt(t, root, validCalibrationReceipt(i))
	}
	if err := verifyCalibrationStreakAt(root, 10); err == nil {
		t.Fatal("verify with nine receipts succeeded; want target failure")
	}
	mustRecordCalibrationReceipt(t, root, validCalibrationReceipt(10))
	if err := verifyCalibrationStreakAt(root, 10); err != nil {
		t.Fatalf("verify with ten receipts: %v", err)
	}
}

func TestCalibrationStreakVerifyRejectsTamperedCache(t *testing.T) {
	root := makeCalibrationTestRoot(t)
	for i := 1; i <= 10; i++ {
		mustRecordCalibrationReceipt(t, root, validCalibrationReceipt(i))
	}
	path := calibrationStreakPathAt(root)
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var raw map[string]any
	if err := json.Unmarshal(data, &raw); err != nil {
		t.Fatal(err)
	}
	raw["aggregate_current"] = float64(999)
	data, err = json.MarshalIndent(raw, "", "  ")
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, append(data, '\n'), 0o644); err != nil {
		t.Fatal(err)
	}

	err = verifyCalibrationStreakAt(root, 10)
	if err == nil || !strings.Contains(err.Error(), "tampered") {
		t.Fatalf("verify tampered cache error = %v, want tampered rejection", err)
	}
}

func TestCalibrationProofRootFindsNearestBeadsMetadata(t *testing.T) {
	root := makeCalibrationTestRoot(t)
	nested := filepath.Join(root, "a", "b", "c")
	if err := os.MkdirAll(nested, 0o755); err != nil {
		t.Fatal(err)
	}
	old, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	if err := os.Chdir(nested); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = os.Chdir(old) })
	t.Setenv("CLAVAIN_CALIBRATION_ROOT", "")
	t.Setenv("SPRINT_LIB_PROJECT_DIR", "")

	got, err := calibrationProofRoot("")
	if err != nil {
		t.Fatal(err)
	}
	want, err := canonicalCalibrationDir(root)
	if err != nil {
		t.Fatal(err)
	}
	if got != want {
		t.Fatalf("calibrationProofRoot = %q, want %q", got, want)
	}
}
