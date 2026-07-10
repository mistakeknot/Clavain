package main

import (
	"errors"
	"os"
	"path/filepath"
	"testing"
)

func TestCalibrateGateTiersAutoFlag(t *testing.T) {
	tmp := t.TempDir()
	clavainDir := filepath.Join(tmp, ".clavain")
	if err := os.MkdirAll(clavainDir, 0o755); err != nil {
		t.Fatalf("mkdir .clavain: %v", err)
	}
	if err := os.WriteFile(filepath.Join(clavainDir, "intercore.db"), []byte{}, 0o644); err != nil {
		t.Fatalf("touch intercore.db: %v", err)
	}

	oldCwd, err := os.Getwd()
	if err != nil {
		t.Fatalf("getwd: %v", err)
	}
	defer func() { _ = os.Chdir(oldCwd) }()
	if err := os.Chdir(tmp); err != nil {
		t.Fatalf("chdir temp: %v", err)
	}

	_ = cmdCalibrateGateTiers([]string{"--auto"})
}

func TestCalibrateGateTiersNoSignalsPreservesArtifact(t *testing.T) {
	tmp := t.TempDir()
	clavainDir := filepath.Join(tmp, ".clavain")
	if err := os.MkdirAll(clavainDir, 0o755); err != nil {
		t.Fatalf("mkdir .clavain: %v", err)
	}
	if err := os.WriteFile(filepath.Join(clavainDir, "intercore.db"), []byte{}, 0o644); err != nil {
		t.Fatalf("touch intercore.db: %v", err)
	}

	calPath := filepath.Join(clavainDir, "gate-tier-calibration.json")
	original := []byte(`{
  "created_at": 1,
  "since_id": 0,
  "tiers": {
    "tests|executing|shipping": {
      "tier": "soft",
      "locked": false,
      "fpr": 0,
      "fnr": 0,
      "weighted_n": 1,
      "updated_at": 1
    }
  }
}
`)
	if err := os.WriteFile(calPath, original, 0o644); err != nil {
		t.Fatalf("write calibration: %v", err)
	}

	binDir := filepath.Join(tmp, "bin")
	if err := os.MkdirAll(binDir, 0o755); err != nil {
		t.Fatalf("mkdir bin: %v", err)
	}
	if err := os.WriteFile(filepath.Join(binDir, "ic"), []byte("#!/usr/bin/env bash\nprintf '%s\\n' '{\"signals\":[],\"cursor\":0}'\n"), 0o755); err != nil {
		t.Fatalf("write fake ic: %v", err)
	}
	t.Setenv("PATH", binDir+string(os.PathListSeparator)+os.Getenv("PATH"))
	oldICBin := icBin
	icBin = ""
	t.Cleanup(func() { icBin = oldICBin })

	oldCwd, err := os.Getwd()
	if err != nil {
		t.Fatalf("getwd: %v", err)
	}
	defer func() { _ = os.Chdir(oldCwd) }()
	if err := os.Chdir(tmp); err != nil {
		t.Fatalf("chdir temp: %v", err)
	}

	err = cmdCalibrateGateTiers([]string{"--auto"})
	if !errors.Is(err, ErrNoNewSignals) {
		t.Fatalf("no-signal error = %v, want ErrNoNewSignals", err)
	}
	after, readErr := os.ReadFile(calPath)
	if readErr != nil {
		t.Fatalf("read calibration: %v", readErr)
	}
	if string(after) != string(original) {
		t.Fatalf("no-signal calibration changed artifact:\n got: %s\nwant: %s", after, original)
	}
}
