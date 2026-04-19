package main

import (
	"database/sql"
	"encoding/json"
	"errors"
	"io"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// setupAuthzSandbox creates a temp dir with:
//   - .clavain/intercore.db: a freshly migrated SQLite DB that has the
//     authorizations table (migration 032 equivalent).
//   - .clavain/policy.yaml: caller-provided project policy YAML content.
//
// It chdirs into the temp dir for the duration of the test and returns the
// sandbox path. os.Getwd() outside the sandbox still works after cleanup.
func setupAuthzSandbox(t *testing.T, projectPolicyYAML string) string {
	t.Helper()
	origWD, err := os.Getwd()
	if err != nil {
		t.Fatalf("getwd: %v", err)
	}
	// Also suppress global policy so tests are deterministic:
	// set HOME to a path where ~/.clavain/policy.yaml does not exist.
	fakeHome := t.TempDir()
	t.Setenv("HOME", fakeHome)

	dir := t.TempDir()
	clavainDir := filepath.Join(dir, ".clavain")
	if err := os.MkdirAll(clavainDir, 0o755); err != nil {
		t.Fatalf("mkdir .clavain: %v", err)
	}

	// Create a minimal schema that matches what authz.Record expects.
	// Mirrors core/intercore/internal/db/migrations/032_authorizations.sql
	// plus enough pragmas for clean insertion.
	dbPath := filepath.Join(clavainDir, "intercore.db")
	db, err := sql.Open("sqlite", dbPath+"?_busy_timeout=5000")
	if err != nil {
		t.Fatalf("open test db: %v", err)
	}
	db.SetMaxOpenConns(1)
	schema := `
CREATE TABLE IF NOT EXISTS authorizations (
  id               TEXT PRIMARY KEY,
  op_type          TEXT NOT NULL,
  target           TEXT NOT NULL,
  agent_id         TEXT NOT NULL CHECK(length(trim(agent_id)) > 0),
  bead_id          TEXT,
  mode             TEXT NOT NULL CHECK(mode IN ('auto','confirmed','blocked','force_auto')),
  policy_match     TEXT,
  policy_hash      TEXT,
  vetted_sha       TEXT,
  vetting          TEXT CHECK(vetting IS NULL OR json_valid(vetting)),
  cross_project_id TEXT,
  created_at       INTEGER NOT NULL
);`
	if _, err := db.Exec(schema); err != nil {
		t.Fatalf("create schema: %v", err)
	}
	db.Close()

	if projectPolicyYAML != "" {
		if err := os.WriteFile(filepath.Join(clavainDir, "policy.yaml"), []byte(projectPolicyYAML), 0o644); err != nil {
			t.Fatalf("write policy.yaml: %v", err)
		}
	}

	if err := os.Chdir(dir); err != nil {
		t.Fatalf("chdir: %v", err)
	}
	t.Cleanup(func() { _ = os.Chdir(origWD) })
	return dir
}

// captureStdoutAuthz runs fn, captures stdout, returns the captured bytes and
// whatever error fn returned.
func captureStdoutAuthz(t *testing.T, fn func() error) ([]byte, error) {
	t.Helper()
	old := os.Stdout
	r, w, _ := os.Pipe()
	os.Stdout = w

	done := make(chan []byte)
	go func() {
		b, _ := io.ReadAll(r)
		done <- b
	}()

	err := fn()

	w.Close()
	os.Stdout = old
	out := <-done
	return out, err
}

// policyAutoBeadClose is a minimal valid policy: bead-close auto + catchall confirm.
const policyAutoBeadClose = `version: 1
rules:
  - op: bead-close
    mode: auto
  - op: "*"
    mode: confirm
`

// policyBlockBeadClose has bead-close explicitly blocked.
const policyBlockBeadClose = `version: 1
rules:
  - op: bead-close
    mode: block
  - op: "*"
    mode: confirm
`

// policyWithRequires needs tests_passed to pass.
const policyWithRequires = `version: 1
rules:
  - op: bead-close
    mode: auto
    requires:
      tests_passed: true
  - op: "*"
    mode: confirm
`

// ─── Check exit-code contract ─────────────────────────────────────────

func TestPolicyCheck_ExitCode_Auto(t *testing.T) {
	setupAuthzSandbox(t, policyAutoBeadClose)
	out, err := captureStdoutAuthz(t, func() error {
		return cmdPolicyCheck([]string{"bead-close", "--target=x"})
	})
	if err != nil {
		t.Fatalf("expected nil error for auto mode, got %v", err)
	}
	var parsed PolicyCheckOutput
	if jerr := json.Unmarshal(out, &parsed); jerr != nil {
		t.Fatalf("unmarshal %q: %v", string(out), jerr)
	}
	if parsed.Mode != "auto" {
		t.Errorf("mode=%q, want auto", parsed.Mode)
	}
}

func TestPolicyCheck_ExitCode_Confirm(t *testing.T) {
	// Policy requires tests_passed; we don't pass the flag → confirm.
	setupAuthzSandbox(t, policyWithRequires)
	out, err := captureStdoutAuthz(t, func() error {
		return cmdPolicyCheck([]string{"bead-close", "--target=x"})
	})
	if !errors.Is(err, ErrPolicyConfirm) {
		t.Fatalf("expected ErrPolicyConfirm, got %v (out=%q)", err, string(out))
	}
}

func TestPolicyCheck_ExitCode_Block(t *testing.T) {
	setupAuthzSandbox(t, policyBlockBeadClose)
	_, err := captureStdoutAuthz(t, func() error {
		return cmdPolicyCheck([]string{"bead-close", "--target=x"})
	})
	if !errors.Is(err, ErrPolicyBlocked) {
		t.Fatalf("expected ErrPolicyBlocked, got %v", err)
	}
}

func TestPolicyCheck_ExitCode_Malformed(t *testing.T) {
	setupAuthzSandbox(t, "this is :: not yaml:: [::::")
	_, err := captureStdoutAuthz(t, func() error {
		return cmdPolicyCheck([]string{"bead-close", "--target=x"})
	})
	if !errors.Is(err, ErrPolicyMalformed) {
		t.Fatalf("expected ErrPolicyMalformed, got %v", err)
	}
}

func TestPolicyCheck_JSONOutput_HasSchema(t *testing.T) {
	setupAuthzSandbox(t, policyAutoBeadClose)
	out, err := captureStdoutAuthz(t, func() error {
		return cmdPolicyCheck([]string{"bead-close", "--target=x"})
	})
	if err != nil {
		t.Fatalf("check: %v", err)
	}
	var parsed map[string]interface{}
	if jerr := json.Unmarshal(out, &parsed); jerr != nil {
		t.Fatalf("unmarshal %q: %v", string(out), jerr)
	}
	for _, k := range []string{"schema", "mode", "policy_match", "policy_hash", "reason"} {
		if _, ok := parsed[k]; !ok {
			t.Errorf("missing required key %q in output %q", k, string(out))
		}
	}
	if got, ok := parsed["schema"].(float64); !ok || int(got) != policyCheckOutputSchema {
		t.Errorf("schema=%v, want %d", parsed["schema"], policyCheckOutputSchema)
	}
	if ph, _ := parsed["policy_hash"].(string); ph == "" {
		t.Errorf("policy_hash must be non-empty")
	}
}

// ─── Record writes a row ──────────────────────────────────────────────

func TestPolicyRecord_WritesRow(t *testing.T) {
	sandbox := setupAuthzSandbox(t, policyAutoBeadClose)
	err := cmdPolicyRecord([]string{
		"--op=bead-close",
		"--target=sylveste-test",
		"--agent=claude-test",
		"--mode=auto",
		"--bead=sylveste-test",
		"--policy-match=bead-close#0",
		"--policy-hash=abc123",
	})
	if err != nil {
		t.Fatalf("record: %v", err)
	}

	dbPath := filepath.Join(sandbox, ".clavain", "intercore.db")
	db, _ := sql.Open("sqlite", dbPath)
	defer db.Close()
	var count int
	if err := db.QueryRow("SELECT COUNT(*) FROM authorizations WHERE bead_id=?", "sylveste-test").Scan(&count); err != nil {
		t.Fatalf("count: %v", err)
	}
	if count != 1 {
		t.Errorf("authorizations rows=%d, want 1", count)
	}
	var mode, match, hash string
	if err := db.QueryRow("SELECT mode, policy_match, policy_hash FROM authorizations WHERE bead_id=?", "sylveste-test").Scan(&mode, &match, &hash); err != nil {
		t.Fatalf("scan: %v", err)
	}
	if mode != "auto" || match != "bead-close#0" || hash != "abc123" {
		t.Errorf("row = (%q,%q,%q), want (auto, bead-close#0, abc123)", mode, match, hash)
	}
}

// ─── Lint invariants ──────────────────────────────────────────────────

func TestPolicyLint_RejectsMissingCatchall(t *testing.T) {
	setupAuthzSandbox(t, `version: 1
rules:
  - op: bead-close
    mode: auto
`)
	_, err := captureStdoutAuthz(t, func() error {
		return cmdPolicyLint(nil)
	})
	if err == nil {
		t.Fatal("expected lint to fail on missing catchall")
	}
	if !strings.Contains(err.Error(), "problem") {
		t.Errorf("err=%v, want 'problem(s)'", err)
	}
}

func TestPolicyLint_RejectsProjectLoosenWithoutAllowOverride(t *testing.T) {
	// Global requires tests_passed; project drops it without allow_override.
	// LoadEffective should return merge error, propagated by lint.
	fakeHome := t.TempDir()
	t.Setenv("HOME", fakeHome)

	globalPath := filepath.Join(fakeHome, ".clavain")
	if err := os.MkdirAll(globalPath, 0o755); err != nil {
		t.Fatalf("mkdir global: %v", err)
	}
	if err := os.WriteFile(filepath.Join(globalPath, "policy.yaml"), []byte(`version: 1
rules:
  - op: bead-close
    mode: auto
    requires:
      tests_passed: true
  - op: "*"
    mode: confirm
`), 0o644); err != nil {
		t.Fatalf("write global policy: %v", err)
	}
	// Note: setupAuthzSandbox overrides HOME; call before it.
	dir := t.TempDir()
	clavainDir := filepath.Join(dir, ".clavain")
	os.MkdirAll(clavainDir, 0o755)
	os.WriteFile(filepath.Join(clavainDir, "policy.yaml"), []byte(`version: 1
rules:
  - op: bead-close
    mode: auto
    requires: {}
`), 0o644)

	origWD, _ := os.Getwd()
	os.Chdir(dir)
	t.Cleanup(func() { _ = os.Chdir(origWD) })

	_, err := captureStdoutAuthz(t, func() error {
		return cmdPolicyLint(nil)
	})
	if err == nil {
		t.Fatal("expected lint to fail on project dropping required boolean")
	}
	if !strings.Contains(err.Error(), "merge failed") {
		t.Errorf("err=%v, want 'merge failed'", err)
	}
}

func TestPolicyLint_GateWithoutRule(t *testing.T) {
	// Policy has only catchall. A gate file declares op=widget-delete with no matching rule.
	// With catchall present, lint should pass (catchall covers).
	// Remove catchall → lint should flag.
	dir := setupAuthzSandbox(t, `version: 1
rules:
  - op: bead-close
    mode: auto
  - op: "*"
    mode: confirm
`)
	gatesDir := filepath.Join(dir, ".clavain", "gates")
	os.MkdirAll(gatesDir, 0o755)
	os.WriteFile(filepath.Join(gatesDir, "widget-delete.gate"), []byte("op=widget-delete\n"), 0o644)

	// With catchall: passes
	_, err := captureStdoutAuthz(t, func() error { return cmdPolicyLint(nil) })
	if err != nil {
		t.Fatalf("lint with catchall should pass: %v", err)
	}

	// Without catchall: fails
	os.WriteFile(filepath.Join(dir, ".clavain", "policy.yaml"), []byte(`version: 1
rules:
  - op: bead-close
    mode: auto
`), 0o644)
	_, err = captureStdoutAuthz(t, func() error { return cmdPolicyLint(nil) })
	if err == nil {
		t.Fatal("expected lint to fail when gate declared with no rule and no catchall")
	}
}

// ─── List produces structured output ──────────────────────────────────

func TestPolicyList_ShowsMergedRules(t *testing.T) {
	setupAuthzSandbox(t, policyAutoBeadClose)
	out, err := captureStdoutAuthz(t, func() error {
		return cmdPolicyList(nil)
	})
	if err != nil {
		t.Fatalf("list: %v", err)
	}
	var parsed map[string]interface{}
	if jerr := json.Unmarshal(out, &parsed); jerr != nil {
		t.Fatalf("unmarshal: %v", jerr)
	}
	if _, ok := parsed["policy"]; !ok {
		t.Errorf("missing policy key")
	}
	if h, _ := parsed["policy_hash"].(string); h == "" {
		t.Errorf("missing policy_hash")
	}
}
