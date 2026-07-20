package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestWriteBeadSideband_EnvelopeShape(t *testing.T) {
	root := t.TempDir()
	t.Setenv("INTERBAND_ROOT", root)
	sessionID := "sess-1"
	legacyPath := filepath.Join("/tmp", "clavain-bead-"+sessionID+".json")
	t.Cleanup(func() { _ = os.Remove(legacyPath) })

	if err := writeBeadSideband(sessionID, "bead-9", "executing", "advanced"); err != nil {
		t.Fatalf("writeBeadSideband: %v", err)
	}
	b, err := os.ReadFile(filepath.Join(root, "interphase", "bead", sessionID+".json"))
	if err != nil {
		t.Fatalf("read: %v", err)
	}
	var env struct {
		Version   string `json:"version"`
		Namespace string `json:"namespace"`
		Type      string `json:"type"`
		SessionID string `json:"session_id"`
		Timestamp string `json:"timestamp"`
		Payload   struct {
			ID     string `json:"id"`
			Phase  string `json:"phase"`
			Reason string `json:"reason"`
			Ts     int64  `json:"ts"`
		} `json:"payload"`
	}
	if err := json.Unmarshal(b, &env); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if env.Version != "1.0.0" || env.Namespace != "interphase" || env.Type != "bead_phase" || env.SessionID != "sess-1" || env.Timestamp == "" {
		t.Errorf("envelope: %+v", env)
	}
	if env.Payload.ID != "bead-9" || env.Payload.Phase != "executing" || env.Payload.Reason != "advanced" || env.Payload.Ts == 0 {
		t.Errorf("payload: %+v", env.Payload)
	}
}

func TestWriteBeadSideband_LegacyPayloadShape(t *testing.T) {
	root := t.TempDir()
	t.Setenv("INTERBAND_ROOT", root)
	sessionID := "sideband-test-legacy"
	legacyPath := filepath.Join("/tmp", "clavain-bead-"+sessionID+".json")
	t.Cleanup(func() { _ = os.Remove(legacyPath) })

	if err := writeBeadSideband(sessionID, "bead-9", "executing", "advanced"); err != nil {
		t.Fatalf("writeBeadSideband: %v", err)
	}
	b, err := os.ReadFile(legacyPath)
	if err != nil {
		t.Fatalf("read legacy payload: %v", err)
	}
	var payload struct {
		ID     string `json:"id"`
		Phase  string `json:"phase"`
		Reason string `json:"reason"`
		Ts     int64  `json:"ts"`
	}
	if err := json.Unmarshal(b, &payload); err != nil {
		t.Fatalf("unmarshal legacy payload: %v", err)
	}
	if payload.ID != "bead-9" || payload.Phase != "executing" || payload.Reason != "advanced" || payload.Ts == 0 {
		t.Errorf("legacy payload: %+v", payload)
	}
}

func TestWriteBeadSideband_NoSessionIsNoop(t *testing.T) {
	if err := writeBeadSideband("", "b", "p", ""); err != nil {
		t.Errorf("empty session should no-op, got %v", err)
	}
}
