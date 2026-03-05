package main

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/vmihailenco/msgpack/v5"
	"gopkg.in/yaml.v3"
)

func TestEvidenceManifestRoundtrip(t *testing.T) {
	m := EvidenceManifest{
		SchemaVersion:      1,
		SourcePlugin:       "interspect",
		EvidenceType:       "profiler_event",
		SessionID:          "abc123",
		Phase:              "executing",
		Timestamp:          1709654400,
		BeadID:             "iv-test",
		Severity:           "warning",
		ReplayInstructions: "Run profiler again",
		Attachments:        []string{"trace.json"},
	}

	data, err := yaml.Marshal(m)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}

	var decoded EvidenceManifest
	if err := yaml.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}

	if decoded.SourcePlugin != "interspect" {
		t.Errorf("SourcePlugin: got %q, want 'interspect'", decoded.SourcePlugin)
	}
	if decoded.EvidenceType != "profiler_event" {
		t.Errorf("EvidenceType: got %q", decoded.EvidenceType)
	}
	if len(decoded.Attachments) != 1 {
		t.Errorf("Attachments: got %d, want 1", len(decoded.Attachments))
	}
}

func TestEvidenceRecordMsgpack(t *testing.T) {
	rec := EvidenceRecord{
		BeadID:       "iv-test",
		SourcePlugin: "interflux",
		EvidenceType: "regression",
		FindingID:    "fd-abc123",
		SessionID:    "session-1",
		Severity:     "error",
		Timestamp:    1709654400,
	}

	data, err := msgpack.Marshal(rec)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}

	var decoded EvidenceRecord
	if err := msgpack.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}

	if decoded.SourcePlugin != "interflux" {
		t.Errorf("SourcePlugin: got %q", decoded.SourcePlugin)
	}
	if decoded.FindingID != "fd-abc123" {
		t.Errorf("FindingID: got %q", decoded.FindingID)
	}
}

func TestEvidenceToScenario(t *testing.T) {
	tmpDir := t.TempDir()
	t.Setenv("SPRINT_LIB_PROJECT_DIR", tmpDir)

	err := cmdEvidenceToScenario([]string{"test-finding-001"})
	if err != nil {
		t.Fatalf("evidence-to-scenario: %v", err)
	}

	// Check scenario was created in dev, not holdout
	devDir := filepath.Join(tmpDir, ".clavain", "scenarios", "dev")
	entries, err := os.ReadDir(devDir)
	if err != nil {
		t.Fatalf("read dev dir: %v", err)
	}
	if len(entries) == 0 {
		t.Fatal("expected scenario file in dev/")
	}

	// Verify it's not in holdout
	holdoutDir := filepath.Join(tmpDir, ".clavain", "scenarios", "holdout")
	holdoutEntries, _ := os.ReadDir(holdoutDir)
	if len(holdoutEntries) > 0 {
		t.Error("evidence scenario should not be in holdout/")
	}

	// Verify scenario content
	data, _ := os.ReadFile(filepath.Join(devDir, entries[0].Name()))
	var s Scenario
	yaml.Unmarshal(data, &s)
	if s.Holdout {
		t.Error("scenario holdout flag should be false")
	}
	if s.SchemaVersion != 1 {
		t.Errorf("schema_version: got %d, want 1", s.SchemaVersion)
	}
}

func TestEvidenceDir(t *testing.T) {
	tmpDir := t.TempDir()
	t.Setenv("SPRINT_LIB_PROJECT_DIR", tmpDir)

	dir := evidenceDir()
	expected := filepath.Join(tmpDir, ".clavain", "evidence")
	if dir != expected {
		t.Errorf("got %q, want %q", dir, expected)
	}
	if _, err := os.Stat(dir); os.IsNotExist(err) {
		t.Error("evidence dir should be created")
	}
}

func TestCreateFluxDriveDevScenario(t *testing.T) {
	tmpDir := t.TempDir()
	t.Setenv("SPRINT_LIB_PROJECT_DIR", tmpDir)

	// Non-error severity should be skipped
	err := createFluxDriveDevScenario("abc123def456", "minor issue", "warning")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	devDir := filepath.Join(tmpDir, ".clavain", "scenarios", "dev")
	entries, _ := os.ReadDir(devDir)
	if len(entries) > 0 {
		t.Error("warning severity should not create scenario")
	}

	// Error severity should create scenario
	err = createFluxDriveDevScenario("abc123def456", "critical regression in auth", "error")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	entries, _ = os.ReadDir(devDir)
	if len(entries) != 1 {
		t.Errorf("expected 1 scenario, got %d", len(entries))
	}

	// Same hash should not duplicate
	err = createFluxDriveDevScenario("abc123def456", "critical regression in auth", "error")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	entries, _ = os.ReadDir(devDir)
	if len(entries) != 1 {
		t.Errorf("expected no duplicate, got %d", len(entries))
	}
}

func TestTruncate(t *testing.T) {
	if truncate("short", 10) != "short" {
		t.Error("short string should not be truncated")
	}
	result := truncate("this is a very long string", 15)
	if len(result) > 15 {
		t.Errorf("truncated string too long: %d", len(result))
	}
	if result[len(result)-3:] != "..." {
		t.Error("truncated string should end with ...")
	}
}
