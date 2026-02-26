package main

import "testing"

func TestFindIC_NotOnPath(t *testing.T) {
	// Save and clear icBin cache
	old := icBin
	icBin = ""
	defer func() { icBin = old }()

	// With a clean PATH that doesn't have ic, findIC should fail
	t.Setenv("PATH", "/nonexistent")
	_, err := findIC()
	if err == nil {
		t.Error("expected error when ic not on PATH")
	}
}

func TestBDAvailable(t *testing.T) {
	// Just verify it doesn't panic
	_ = bdAvailable()
}

func TestICAvailable(t *testing.T) {
	// Just verify it doesn't panic
	_ = icAvailable()
}
