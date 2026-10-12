package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"
)

// sessionRegisterID is the session this process runs in, read from the
// registers Claude Code actually populates (mk-rd9f): CLAUDE_SESSION_ID
// (written by clavain's session-start hook, so absent in every session whose
// start hook did not fire) and then CLAUDE_CODE_SESSION_ID (exported by Claude
// Code itself into the Bash tool). Empty when neither is set; callers choose
// their own fallback. This is the ONLY place the binary may read either
// variable directly — tests/structural/test_session_registers.py fails on any
// other os.Getenv("CLAUDE_SESSION_ID").
func sessionRegisterID() string {
	if v := strings.TrimSpace(os.Getenv("CLAUDE_SESSION_ID")); v != "" {
		return v
	}
	return strings.TrimSpace(os.Getenv("CLAUDE_CODE_SESSION_ID"))
}

// writeBeadSideband writes the kernel-authored interband envelope
// (interband protocol 1.0.0) so the statusline keeps working as interphase
// retires (brainstorm KD 11). Atomic tmp+rename, best-effort at call sites.
// Session keying (Sylveste-23k): an empty sessionID falls back to
// CLAUDE_SESSION_ID then CLAUDE_CODE_SESSION_ID (exported to every Bash
// subprocess since CC 2.1.132), so callers need not thread session ids.
func writeBeadSideband(sessionID, beadID, phase, reason string) error {
	if sessionID == "" {
		sessionID = sessionRegisterID()
	}
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
	return atomicWrite(filepath.Join(dir, sessionID+".json"), envelopeBytes)
}

func atomicWrite(path string, data []byte) error {
	tmp := fmt.Sprintf("%s.tmp.%d", path, os.Getpid())
	defer func() { _ = os.Remove(tmp) }()
	if err := os.WriteFile(tmp, data, 0o644); err != nil {
		return err
	}
	return os.Rename(tmp, path)
}
