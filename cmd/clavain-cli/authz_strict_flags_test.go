package main

import (
	"strings"
	"testing"
)

// Sylveste-8umf: parseAuthzArgs collected every --key into a map and commands
// read only the keys they knew, so an unrecognized flag was a silent no-op
// that looked like a successful answer. Recorded shape: `policy audit --count`
// against a binary predating --count printed the full 62KB row listing.
// These tests pin the strict parser and one command-level rejection so the
// permissive behaviour cannot quietly return.

func TestParseAuthzArgsStrict_RejectsUnknownFlag(t *testing.T) {
	_, err := parseAuthzArgsStrict("policy audit", []string{"--count", "--bogus=1"}, "count", "verify")
	if err == nil {
		t.Fatal("unknown flag --bogus accepted; the 8umf no-op is back")
	}
	if !strings.Contains(err.Error(), "--bogus") {
		t.Fatalf("error must name the offending flag, got: %v", err)
	}
	if !strings.Contains(err.Error(), "--count") {
		t.Fatalf("error must list the allowed set, got: %v", err)
	}
}

func TestParseAuthzArgsStrict_AcceptsKnownAndPositional(t *testing.T) {
	flags, err := parseAuthzArgsStrict("policy check", []string{"bead-close", "--bead=iv-1", "--target=x"},
		"bead", "target")
	if err != nil {
		t.Fatalf("known flags rejected: %v", err)
	}
	if flags["_pos_0"] != "bead-close" || flags["bead"] != "iv-1" {
		t.Fatalf("parse drifted: %v", flags)
	}
}

func TestParseAuthzArgsStrict_NamesEveryUnknown(t *testing.T) {
	_, err := parseAuthzArgsStrict("policy sign", []string{"--zzz", "--aaa"}, "op")
	if err == nil {
		t.Fatal("expected rejection")
	}
	if !strings.Contains(err.Error(), "--aaa") || !strings.Contains(err.Error(), "--zzz") {
		t.Fatalf("all unknown flags must be named, got: %v", err)
	}
}

// The recorded incident at command level: audit with a flag nothing reads must
// be an error, not the full listing with a clean exit.
func TestPolicyAudit_UnknownFlagIsAnError(t *testing.T) {
	setupAuthzSandbox(t, "")
	err := cmdPolicyAudit([]string{"--tokens"})
	if err == nil {
		t.Fatal("policy audit --tokens exited clean; a flag nothing reads looked answered")
	}
	if !strings.Contains(err.Error(), "--tokens") {
		t.Fatalf("rejection must name the flag, got: %v", err)
	}
}

// The flip side: enforcing strict flags must not break the invocations the
// estate actually makes (audited 2026-08-24 across Sylveste/Clavain/dotfiles).
func TestPolicyAudit_AuditedCallerFlagsStillParse(t *testing.T) {
	for _, args := range [][]string{
		{"--verify"},
		{"--verify", "--op=git-push-main"},
		{"--since=24h"},
		{"--count"},
	} {
		if _, err := parseAuthzArgsStrict("policy audit", args,
			"agent", "bead", "capped", "count", "limit", "op", "project-root", "since", "verify"); err != nil {
			t.Fatalf("live caller invocation %v now rejected: %v", args, err)
		}
	}
}
