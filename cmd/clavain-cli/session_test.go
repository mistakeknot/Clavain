package main

import "testing"

// mk-rd9f: the binary reads the session from the registers Claude Code sets,
// in the same order as hooks/lib.sh's clavain_session_id.
func TestSessionRegisterID_Precedence(t *testing.T) {
	t.Setenv("CLAUDE_SESSION_ID", "env-start")
	t.Setenv("CLAUDE_CODE_SESSION_ID", "env-app")
	if got := sessionRegisterID(); got != "env-start" {
		t.Errorf("both set: got %q, want env-start", got)
	}
	t.Setenv("CLAUDE_SESSION_ID", "")
	if got := sessionRegisterID(); got != "env-app" {
		t.Errorf("start hook never fired: got %q, want env-app", got)
	}
	t.Setenv("CLAUDE_CODE_SESSION_ID", "  ")
	if got := sessionRegisterID(); got != "" {
		t.Errorf("nothing set: got %q, want empty", got)
	}
}

// bead-claim without the start hook must not claim as "unknown": that value
// is what the collision check treats as unclaimed.
func TestBeadClaim_SessionFromAppRegister(t *testing.T) {
	t.Setenv("CLAUDE_SESSION_ID", "")
	t.Setenv("CLAUDE_CODE_SESSION_ID", "app-sess-3")
	if got := sessionRegisterID(); got == "" || got == "unknown" {
		t.Fatalf("claim identity collapsed to %q with CLAUDE_CODE_SESSION_ID set", got)
	}
}
