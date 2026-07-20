package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"time"
)

// writeBeadSideband mirrors interphase's _gate_update_statusline envelope
// (interband protocol 1.0.0) so the statusline keeps working as interphase
// retires (brainstorm KD 11). Both writes are atomic tmp+rename,
// best-effort at call sites.
func writeBeadSideband(sessionID, beadID, phase, reason string) error {
	if sessionID == "" {
		return nil
	}

	now := time.Now()
	payload := map[string]any{
		"id":     beadID,
		"phase":  phase,
		"reason": reason,
		"ts":     now.Unix(),
	}
	envelope := map[string]any{
		"version":    "1.0.0",
		"namespace":  "interphase",
		"type":       "bead_phase",
		"session_id": sessionID,
		"timestamp":  now.UTC().Format("2006-01-02T15:04:05Z"),
		"payload":    payload,
	}
	envelopeBytes, err := json.Marshal(envelope)
	if err != nil {
		return err
	}

	root := os.Getenv("INTERBAND_ROOT")
	if root == "" {
		home, err := os.UserHomeDir()
		if err != nil {
			return err
		}
		root = filepath.Join(home, ".interband")
	}
	dir := filepath.Join(root, "interphase", "bead")
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return err
	}
	if err := atomicWrite(filepath.Join(dir, sessionID+".json"), envelopeBytes); err != nil {
		return err
	}

	// Legacy fallback path interline still reads.
	payloadBytes, err := json.Marshal(payload)
	if err != nil {
		return err
	}
	return atomicWrite(filepath.Join("/tmp", "clavain-bead-"+sessionID+".json"), payloadBytes)
}

func atomicWrite(path string, data []byte) error {
	tmp := fmt.Sprintf("%s.tmp.%d", path, os.Getpid())
	defer func() { _ = os.Remove(tmp) }()
	if err := os.WriteFile(tmp, data, 0o644); err != nil {
		return err
	}
	return os.Rename(tmp, path)
}
