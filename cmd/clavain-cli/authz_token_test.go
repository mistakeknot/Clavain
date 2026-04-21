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

	"github.com/mistakeknot/intercore/pkg/authz"
)

// ─── sandbox ──────────────────────────────────────────────────────────

// setupTokenSandbox builds a temp project root at schema v34 with a keypair,
// chdirs into it, and isolates $HOME so no global policy or key leaks in.
// Caller gets (root-path, cleanup). Tests read $CLAVAIN_AGENT_ID via
// t.Setenv directly — the sandbox does not set it (forces each test to
// declare its agent identity explicitly).
func setupTokenSandbox(t *testing.T) string {
	t.Helper()
	origWD, _ := os.Getwd()
	fakeHome := t.TempDir()
	t.Setenv("HOME", fakeHome)

	dir := t.TempDir()
	clavainDir := filepath.Join(dir, ".clavain")
	if err := os.MkdirAll(clavainDir, 0o755); err != nil {
		t.Fatalf("mkdir .clavain: %v", err)
	}

	dbPath := filepath.Join(clavainDir, "intercore.db")
	db, err := sql.Open("sqlite", dbPath+"?_busy_timeout=5000")
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	db.SetMaxOpenConns(1)

	// Schema v34: authorizations + authz_tokens + v1 migration marker. Kept
	// in sync with core/intercore/internal/db/db.go §v33→v34.
	stmts := []string{
		`CREATE TABLE IF NOT EXISTS authorizations (
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
			created_at       INTEGER NOT NULL,
			sig_version      INTEGER NOT NULL DEFAULT 0,
			signature        BLOB,
			signed_at        INTEGER
		)`,
		`CREATE TABLE IF NOT EXISTS authz_tokens (
			id            TEXT PRIMARY KEY,
			op_type       TEXT NOT NULL,
			target        TEXT NOT NULL,
			agent_id      TEXT NOT NULL CHECK(length(trim(agent_id)) > 0),
			bead_id       TEXT,
			delegate_to   TEXT,
			expires_at    INTEGER NOT NULL,
			consumed_at   INTEGER,
			revoked_at    INTEGER,
			issued_by     TEXT NOT NULL,
			parent_token  TEXT REFERENCES authz_tokens(id) ON DELETE RESTRICT,
			root_token    TEXT,
			depth         INTEGER NOT NULL DEFAULT 0 CHECK (depth >= 0 AND depth <= 3),
			sig_version   INTEGER NOT NULL DEFAULT 2,
			signature     BLOB NOT NULL,
			created_at    INTEGER NOT NULL
		)`,
		`CREATE INDEX IF NOT EXISTS tokens_by_root   ON authz_tokens(root_token, consumed_at, revoked_at)`,
		`CREATE INDEX IF NOT EXISTS tokens_by_parent ON authz_tokens(parent_token)`,
		`CREATE INDEX IF NOT EXISTS tokens_by_agent  ON authz_tokens(agent_id, created_at DESC)`,
	}
	for _, s := range stmts {
		if _, err := db.Exec(s); err != nil {
			t.Fatalf("schema: %v", err)
		}
	}
	db.Close()

	// Keypair under project root's .clavain/keys/.
	kp, err := authz.GenerateKey()
	if err != nil {
		t.Fatalf("generate key: %v", err)
	}
	if err := authz.WriteKeyPair(dir, kp); err != nil {
		t.Fatalf("write key: %v", err)
	}

	if err := os.Chdir(dir); err != nil {
		t.Fatalf("chdir: %v", err)
	}
	t.Cleanup(func() { _ = os.Chdir(origWD) })
	return dir
}

// captureTokenStdout runs fn with os.Stdout redirected to a pipe. Returns the
// stdout output and fn's error. Used for handlers that emit the opaque
// token string or the unset-env sentinel block.
func captureTokenStdout(t *testing.T, fn func() error) (string, error) {
	t.Helper()
	r, w, err := os.Pipe()
	if err != nil {
		t.Fatalf("pipe: %v", err)
	}
	orig := os.Stdout
	os.Stdout = w
	defer func() { os.Stdout = orig }()

	done := make(chan []byte)
	go func() {
		all, _ := io.ReadAll(r)
		done <- all
	}()

	runErr := fn()
	w.Close()
	out := <-done
	r.Close()
	return string(out), runErr
}

// silenceStderr swaps os.Stderr for the duration of fn, discarding output.
// Handlers emit "ERROR <class>:" lines on failure paths — useful in prod,
// noise in test logs.
func silenceStderr(t *testing.T, fn func() error) error {
	t.Helper()
	r, w, err := os.Pipe()
	if err != nil {
		t.Fatalf("pipe: %v", err)
	}
	orig := os.Stderr
	os.Stderr = w
	defer func() {
		os.Stderr = orig
		w.Close()
		_, _ = io.Copy(io.Discard, r)
		r.Close()
	}()
	return fn()
}

// exitClass returns the 5-class code that main.go would translate `err` to.
// nil → 0; an ExitCoder wrapper → its code; else → 1.
func exitClass(err error) int {
	if err == nil {
		return 0
	}
	var ec interface{ ExitCode() int }
	if errors.As(err, &ec) {
		return ec.ExitCode()
	}
	return 1
}

// issueViaHandler runs cmdPolicyTokenIssue with a fresh stdout capture and
// extracts the opaque token string (first line). Used as a composition
// primitive by consume/delegate/revoke tests.
func issueViaHandler(t *testing.T, agent, op, target, forAgent, ttl, bead string) string {
	t.Helper()
	t.Setenv("CLAVAIN_AGENT_ID", agent)
	args := []string{
		"--op=" + op,
		"--target=" + target,
		"--for=" + forAgent,
		"--ttl=" + ttl,
	}
	if bead != "" {
		args = append(args, "--bead="+bead)
	}
	out, err := captureTokenStdout(t, func() error { return cmdPolicyTokenIssue(args) })
	if err != nil {
		t.Fatalf("issue: %v", err)
	}
	line := strings.TrimSpace(strings.SplitN(out, "\n", 2)[0])
	if line == "" {
		t.Fatalf("issue: no opaque string on stdout; got %q", out)
	}
	return line
}

// ─── issue ────────────────────────────────────────────────────────────

func TestPolicyTokenIssue_Success(t *testing.T) {
	setupTokenSandbox(t)
	t.Setenv("CLAVAIN_AGENT_ID", "claude")

	out, err := captureTokenStdout(t, func() error {
		return cmdPolicyTokenIssue([]string{
			"--op=bead-close",
			"--target=sylveste-qdqr.28",
			"--for=codex",
			"--ttl=60m",
			"--bead=sylveste-qdqr.28",
		})
	})
	if err != nil {
		t.Fatalf("issue: %v", err)
	}
	opaque := strings.TrimSpace(out)
	if !strings.Contains(opaque, ".") {
		t.Fatalf("opaque string missing '.' separator: %q", opaque)
	}
	id, _, err := authz.ParseTokenString(opaque)
	if err != nil {
		t.Fatalf("parse: %v", err)
	}

	// Row exists, audit row exists (op_type=authz.token-issue).
	db, _, err := openIntercoreDB()
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	defer db.Close()
	tok, err := authz.GetToken(db, id)
	if err != nil {
		t.Fatalf("GetToken: %v", err)
	}
	if tok.AgentID != "codex" {
		t.Errorf("token agent_id = %q, want codex", tok.AgentID)
	}
	if tok.IssuedBy != "claude" {
		t.Errorf("token issued_by = %q, want claude", tok.IssuedBy)
	}
	var count int
	if err := db.QueryRow(
		`SELECT COUNT(*) FROM authorizations WHERE op_type = 'authz.token-issue' AND target = ?`, tok.ID,
	).Scan(&count); err != nil {
		t.Fatalf("count audit: %v", err)
	}
	if count != 1 {
		t.Errorf("audit rows = %d, want 1", count)
	}
}

func TestPolicyTokenIssue_ErrorPaths(t *testing.T) {
	setupTokenSandbox(t)

	t.Run("missing_agent_id", func(t *testing.T) {
		t.Setenv("CLAVAIN_AGENT_ID", "")
		err := cmdPolicyTokenIssue([]string{
			"--op=bead-close", "--target=x", "--for=y", "--ttl=1h",
		})
		if err == nil {
			t.Fatal("want error for missing CLAVAIN_AGENT_ID")
		}
	})

	t.Run("missing_flag", func(t *testing.T) {
		t.Setenv("CLAVAIN_AGENT_ID", "claude")
		err := cmdPolicyTokenIssue([]string{"--op=bead-close"})
		if err == nil {
			t.Fatal("want usage error for missing flags")
		}
	})

	t.Run("invalid_ttl", func(t *testing.T) {
		t.Setenv("CLAVAIN_AGENT_ID", "claude")
		err := cmdPolicyTokenIssue([]string{
			"--op=bead-close", "--target=x", "--for=y", "--ttl=not-a-duration",
		})
		if err == nil {
			t.Fatal("want error for invalid TTL")
		}
	})
}

// ─── consume ──────────────────────────────────────────────────────────

func TestPolicyTokenConsume_Success(t *testing.T) {
	setupTokenSandbox(t)
	opaque := issueViaHandler(t, "claude", "bead-close", "sylveste-qdqr.28", "codex", "60m", "")

	// Consume as codex.
	t.Setenv("CLAVAIN_AGENT_ID", "codex")
	out, err := captureTokenStdout(t, func() error {
		return cmdPolicyTokenConsume([]string{
			"--token=" + opaque,
			"--expect-op=bead-close",
			"--expect-target=sylveste-qdqr.28",
		})
	})
	if err != nil {
		t.Fatalf("consume: %v", err)
	}
	if !strings.Contains(out, "# authz-unset-begin") {
		t.Errorf("stdout missing unset-begin sentinel: %q", out)
	}
	if !strings.Contains(out, "unset CLAVAIN_AUTHZ_TOKEN") {
		t.Errorf("stdout missing unset command: %q", out)
	}
	if !strings.Contains(out, "# authz-unset-end") {
		t.Errorf("stdout missing unset-end sentinel: %q", out)
	}
}

func TestPolicyTokenConsume_ExitClasses(t *testing.T) {
	setupTokenSandbox(t)

	t.Run("already_consumed_class2", func(t *testing.T) {
		opaque := issueViaHandler(t, "claude", "bead-close", "t1", "codex", "60m", "")
		t.Setenv("CLAVAIN_AGENT_ID", "codex")
		// First consume succeeds.
		if _, err := captureTokenStdout(t, func() error {
			return cmdPolicyTokenConsume([]string{"--token=" + opaque, "--expect-op=bead-close", "--expect-target=t1"})
		}); err != nil {
			t.Fatalf("first consume: %v", err)
		}
		// Second exits class 2.
		var secondErr error
		_ = silenceStderr(t, func() error {
			_, secondErr = captureTokenStdout(t, func() error {
				return cmdPolicyTokenConsume([]string{"--token=" + opaque, "--expect-op=bead-close", "--expect-target=t1"})
			})
			return nil
		})
		if got := exitClass(secondErr); got != 2 {
			t.Errorf("double-consume exit class = %d, want 2", got)
		}
	})

	t.Run("caller_mismatch_class4", func(t *testing.T) {
		opaque := issueViaHandler(t, "claude", "bead-close", "t2", "codex", "60m", "")
		t.Setenv("CLAVAIN_AGENT_ID", "imposter") // not codex
		var consumeErr error
		_ = silenceStderr(t, func() error {
			_, consumeErr = captureTokenStdout(t, func() error {
				return cmdPolicyTokenConsume([]string{"--token=" + opaque, "--expect-op=bead-close", "--expect-target=t2"})
			})
			return nil
		})
		if got := exitClass(consumeErr); got != 4 {
			t.Errorf("caller-mismatch exit class = %d, want 4", got)
		}
	})

	t.Run("bad_token_string_class3", func(t *testing.T) {
		t.Setenv("CLAVAIN_AGENT_ID", "codex")
		var err error
		_ = silenceStderr(t, func() error {
			_, err = captureTokenStdout(t, func() error {
				return cmdPolicyTokenConsume([]string{"--token=not-a-token", "--expect-op=x", "--expect-target=y"})
			})
			return nil
		})
		if got := exitClass(err); got != 3 {
			t.Errorf("malformed-token exit class = %d, want 3", got)
		}
	})

	t.Run("expect_mismatch_class4", func(t *testing.T) {
		opaque := issueViaHandler(t, "claude", "bead-close", "t3", "codex", "60m", "")
		t.Setenv("CLAVAIN_AGENT_ID", "codex")
		var err error
		_ = silenceStderr(t, func() error {
			_, err = captureTokenStdout(t, func() error {
				return cmdPolicyTokenConsume([]string{"--token=" + opaque, "--expect-op=git-push-main", "--expect-target=t3"})
			})
			return nil
		})
		if got := exitClass(err); got != 4 {
			t.Errorf("expect-mismatch exit class = %d, want 4", got)
		}
	})
}

func TestPolicyTokenConsume_UsesEnvWhenNoFlag(t *testing.T) {
	setupTokenSandbox(t)
	opaque := issueViaHandler(t, "claude", "bead-close", "tenv", "codex", "60m", "")

	t.Setenv("CLAVAIN_AGENT_ID", "codex")
	t.Setenv("CLAVAIN_AUTHZ_TOKEN", opaque)
	_, err := captureTokenStdout(t, func() error {
		return cmdPolicyTokenConsume([]string{
			"--expect-op=bead-close", "--expect-target=tenv",
		})
	})
	if err != nil {
		t.Fatalf("consume via env: %v", err)
	}
}

// ─── delegate ─────────────────────────────────────────────────────────

func TestPolicyTokenDelegate_Success(t *testing.T) {
	setupTokenSandbox(t)
	parentOpaque := issueViaHandler(t, "user", "bead-close", "t", "claude", "60m", "")
	parentID, _, _ := authz.ParseTokenString(parentOpaque)

	// Claude (holder) delegates to codex.
	t.Setenv("CLAVAIN_AGENT_ID", "claude")
	out, err := captureTokenStdout(t, func() error {
		return cmdPolicyTokenDelegate([]string{
			"--from=" + parentID,
			"--to=codex",
			"--ttl=30m",
		})
	})
	if err != nil {
		t.Fatalf("delegate: %v", err)
	}
	childOpaque := strings.TrimSpace(out)
	childID, _, err := authz.ParseTokenString(childOpaque)
	if err != nil {
		t.Fatalf("parse child: %v", err)
	}

	db, _, _ := openIntercoreDB()
	defer db.Close()
	child, _ := authz.GetToken(db, childID)
	if child.Depth != 1 {
		t.Errorf("child depth = %d, want 1", child.Depth)
	}
	if child.AgentID != "codex" {
		t.Errorf("child agent_id = %q, want codex", child.AgentID)
	}
	if child.ParentToken != parentID {
		t.Errorf("child parent_token = %q, want %q", child.ParentToken, parentID)
	}
	if child.RootToken != parentID {
		t.Errorf("child root_token = %q, want %q (parent IS root)", child.RootToken, parentID)
	}
}

func TestPolicyTokenDelegate_POPMismatchClass4(t *testing.T) {
	setupTokenSandbox(t)
	parentOpaque := issueViaHandler(t, "user", "bead-close", "t", "claude", "60m", "")
	parentID, _, _ := authz.ParseTokenString(parentOpaque)

	t.Setenv("CLAVAIN_AGENT_ID", "imposter")
	var err error
	_ = silenceStderr(t, func() error {
		_, err = captureTokenStdout(t, func() error {
			return cmdPolicyTokenDelegate([]string{
				"--from=" + parentID,
				"--to=codex",
				"--ttl=30m",
			})
		})
		return nil
	})
	if got := exitClass(err); got != 4 {
		t.Errorf("pop-mismatch exit class = %d, want 4", got)
	}
}

// ─── revoke ───────────────────────────────────────────────────────────

func TestPolicyTokenRevoke_Success(t *testing.T) {
	setupTokenSandbox(t)
	opaque := issueViaHandler(t, "claude", "bead-close", "t", "codex", "60m", "")
	id, _, _ := authz.ParseTokenString(opaque)

	out, err := captureTokenStdout(t, func() error {
		return cmdPolicyTokenRevoke([]string{"--token=" + id})
	})
	if err != nil {
		t.Fatalf("revoke: %v", err)
	}
	var payload map[string]interface{}
	if err := json.Unmarshal([]byte(out), &payload); err != nil {
		t.Fatalf("unmarshal: %v (%q)", err, out)
	}
	if n, _ := payload["revoked"].(float64); int(n) != 1 {
		t.Errorf("revoked = %v, want 1", payload["revoked"])
	}
}

func TestPolicyTokenRevoke_CascadeRoot(t *testing.T) {
	setupTokenSandbox(t)
	parentOpaque := issueViaHandler(t, "user", "bead-close", "t", "claude", "60m", "")
	parentID, _, _ := authz.ParseTokenString(parentOpaque)

	// Delegate to produce a descendant.
	t.Setenv("CLAVAIN_AGENT_ID", "claude")
	_, err := captureTokenStdout(t, func() error {
		return cmdPolicyTokenDelegate([]string{
			"--from=" + parentID, "--to=codex", "--ttl=30m",
		})
	})
	if err != nil {
		t.Fatalf("delegate: %v", err)
	}

	out, err := captureTokenStdout(t, func() error {
		return cmdPolicyTokenRevoke([]string{"--token=" + parentID, "--cascade"})
	})
	if err != nil {
		t.Fatalf("cascade revoke: %v", err)
	}
	var payload map[string]interface{}
	if err := json.Unmarshal([]byte(out), &payload); err != nil {
		t.Fatalf("unmarshal: %v (%q)", err, out)
	}
	if n, _ := payload["revoked"].(float64); int(n) != 2 {
		t.Errorf("cascade revoked = %v, want 2", payload["revoked"])
	}
}

func TestPolicyTokenRevoke_CascadeOnNonRoot(t *testing.T) {
	setupTokenSandbox(t)
	parentOpaque := issueViaHandler(t, "user", "bead-close", "t", "claude", "60m", "")
	parentID, _, _ := authz.ParseTokenString(parentOpaque)

	t.Setenv("CLAVAIN_AGENT_ID", "claude")
	childOut, _ := captureTokenStdout(t, func() error {
		return cmdPolicyTokenDelegate([]string{
			"--from=" + parentID, "--to=codex", "--ttl=30m",
		})
	})
	childID, _, _ := authz.ParseTokenString(strings.TrimSpace(childOut))

	// Cascade on child (non-root) must be refused with exit 4.
	var err error
	_ = silenceStderr(t, func() error {
		_, err = captureTokenStdout(t, func() error {
			return cmdPolicyTokenRevoke([]string{"--token=" + childID, "--cascade"})
		})
		return nil
	})
	if got := exitClass(err); got != 4 {
		t.Errorf("cascade-on-non-root exit class = %d, want 4", got)
	}
	if !errors.Is(err, authz.ErrCascadeOnNonRoot) {
		t.Errorf("err = %v, want ErrCascadeOnNonRoot", err)
	}
}

// ─── list / show / verify ─────────────────────────────────────────────

func TestPolicyTokenList(t *testing.T) {
	setupTokenSandbox(t)
	_ = issueViaHandler(t, "claude", "bead-close", "a", "codex", "60m", "")
	_ = issueViaHandler(t, "claude", "bead-close", "b", "agent-x", "60m", "")
	_ = issueViaHandler(t, "claude", "git-push", "c", "codex", "60m", "")

	out, err := captureTokenStdout(t, func() error {
		return cmdPolicyTokenList([]string{"--agent=codex"})
	})
	if err != nil {
		t.Fatalf("list: %v", err)
	}
	var rows []tokenJSON
	if err := json.Unmarshal([]byte(out), &rows); err != nil {
		t.Fatalf("unmarshal: %v (%q)", err, out)
	}
	if len(rows) != 2 {
		t.Errorf("agent=codex rows = %d, want 2", len(rows))
	}

	out, err = captureTokenStdout(t, func() error {
		return cmdPolicyTokenList([]string{"--op=bead-close"})
	})
	if err != nil {
		t.Fatalf("list op: %v", err)
	}
	rows = nil
	_ = json.Unmarshal([]byte(out), &rows)
	if len(rows) != 2 {
		t.Errorf("op=bead-close rows = %d, want 2", len(rows))
	}
}

func TestPolicyTokenShow(t *testing.T) {
	setupTokenSandbox(t)
	opaque := issueViaHandler(t, "claude", "bead-close", "t", "codex", "60m", "")
	id, _, _ := authz.ParseTokenString(opaque)

	out, err := captureTokenStdout(t, func() error {
		return cmdPolicyTokenShow([]string{"--token=" + id})
	})
	if err != nil {
		t.Fatalf("show: %v", err)
	}
	var payload map[string]interface{}
	if err := json.Unmarshal([]byte(out), &payload); err != nil {
		t.Fatalf("unmarshal: %v (%q)", err, out)
	}
	if v, _ := payload["sig_verified"].(bool); !v {
		t.Errorf("sig_verified = %v, want true", payload["sig_verified"])
	}
	chain, _ := payload["chain"].([]interface{})
	if len(chain) != 1 {
		t.Errorf("chain length = %d, want 1 (just the root)", len(chain))
	}
}

func TestPolicyTokenShow_NotFoundClass3(t *testing.T) {
	setupTokenSandbox(t)
	t.Setenv("CLAVAIN_AGENT_ID", "claude")

	var err error
	_ = silenceStderr(t, func() error {
		_, err = captureTokenStdout(t, func() error {
			return cmdPolicyTokenShow([]string{"--token=01J0GZZZZZZZZZZZZZZZZZZZZZ"})
		})
		return nil
	})
	if got := exitClass(err); got != 3 {
		t.Errorf("not-found exit class = %d, want 3", got)
	}
}

func TestPolicyTokenVerify_Success(t *testing.T) {
	setupTokenSandbox(t)
	opaque := issueViaHandler(t, "claude", "bead-close", "t", "codex", "60m", "")

	out, err := captureTokenStdout(t, func() error {
		return cmdPolicyTokenVerify([]string{"--token=" + opaque})
	})
	if err != nil {
		t.Fatalf("verify: %v", err)
	}
	var payload map[string]interface{}
	if err := json.Unmarshal([]byte(out), &payload); err != nil {
		t.Fatalf("unmarshal: %v (%q)", err, out)
	}
	if v, _ := payload["sig_verified"].(bool); !v {
		t.Errorf("sig_verified = %v, want true", payload["sig_verified"])
	}
}

func TestPolicyTokenVerify_SigForgeryClass4(t *testing.T) {
	setupTokenSandbox(t)
	opaque := issueViaHandler(t, "claude", "bead-close", "t", "codex", "60m", "")
	id, sig, _ := authz.ParseTokenString(opaque)
	// Flip a byte in the signature → verify must fail with sig-verify class.
	sig[0] ^= 0xFF
	forged := authz.EncodeTokenString(id, sig)

	var err error
	_ = silenceStderr(t, func() error {
		_, err = captureTokenStdout(t, func() error {
			return cmdPolicyTokenVerify([]string{"--token=" + forged})
		})
		return nil
	})
	if got := exitClass(err); got != 4 {
		t.Errorf("sig-forge exit class = %d, want 4", got)
	}
	if !errors.Is(err, authz.ErrSigVerify) {
		t.Errorf("err = %v, want ErrSigVerify", err)
	}
}

func TestPolicyTokenVerify_MalformedClass3(t *testing.T) {
	setupTokenSandbox(t)
	var err error
	_ = silenceStderr(t, func() error {
		_, err = captureTokenStdout(t, func() error {
			return cmdPolicyTokenVerify([]string{"--token=not-a-token"})
		})
		return nil
	})
	if got := exitClass(err); got != 3 {
		t.Errorf("malformed exit class = %d, want 3", got)
	}
}

// ─── dispatcher + usage ───────────────────────────────────────────────

func TestPolicyToken_UsageOnNoSub(t *testing.T) {
	err := cmdPolicyToken(nil)
	if err == nil {
		t.Fatal("want usage error")
	}
	if !strings.Contains(err.Error(), "Usage: policy token") {
		t.Errorf("error = %q, want usage prefix", err.Error())
	}
}

func TestPolicyToken_UnknownSub(t *testing.T) {
	err := cmdPolicyToken([]string{"frobnicate"})
	if err == nil {
		t.Fatal("want error for unknown subcommand")
	}
}
