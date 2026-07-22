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

func TestWriteBeadSideband_NoLegacyWrite(t *testing.T) {
	root := t.TempDir()
	t.Setenv("INTERBAND_ROOT", root)
	sessionID := "sideband-test-no-legacy"
	legacyPath := filepath.Join("/tmp", "clavain-bead-"+sessionID+".json")
	_ = os.Remove(legacyPath)

	if err := writeBeadSideband(sessionID, "bead-9", "executing", "advanced"); err != nil {
		t.Fatalf("writeBeadSideband: %v", err)
	}
	if _, err := os.Stat(legacyPath); !os.IsNotExist(err) {
		t.Errorf("legacy /tmp sideband must not be written (Sylveste-zlc); stat err = %v", err)
	}
}

func TestWriteBeadSideband_EnvSessionFallback(t *testing.T) {
	root := t.TempDir()
	t.Setenv("INTERBAND_ROOT", root)
	t.Setenv("CLAUDE_SESSION_ID", "")
	t.Setenv("CLAUDE_CODE_SESSION_ID", "env-sess-7")

	if err := writeBeadSideband("", "bead-9", "executing", "advanced"); err != nil {
		t.Fatalf("writeBeadSideband: %v", err)
	}
	b, err := os.ReadFile(filepath.Join(root, "interphase", "bead", "env-sess-7.json"))
	if err != nil {
		t.Fatalf("envelope not keyed by CLAUDE_CODE_SESSION_ID (Sylveste-23k): %v", err)
	}
	var env struct {
		SessionID string `json:"session_id"`
	}
	if err := json.Unmarshal(b, &env); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if env.SessionID != "env-sess-7" {
		t.Errorf("session_id = %q, want env-sess-7", env.SessionID)
	}
}

func TestWriteBeadSideband_NoSessionIsNoop(t *testing.T) {
	t.Setenv("CLAUDE_SESSION_ID", "")
	t.Setenv("CLAUDE_CODE_SESSION_ID", "")
	if err := writeBeadSideband("", "b", "p", ""); err != nil {
		t.Errorf("empty session should no-op, got %v", err)
	}
}
