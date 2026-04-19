package main

import (
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
