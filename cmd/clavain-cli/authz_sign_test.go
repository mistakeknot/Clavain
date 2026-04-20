package main

import (
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/mistakeknot/intercore/pkg/authz"
)

// setupSigningSandbox creates a temp project root with:
//   - .clavain/intercore.db at schema v33 (signing columns + cutover marker)
//   - an isolated HOME so no global policy bleeds in
//
// It chdirs into the sandbox and returns the absolute project root.
func setupSigningSandbox(t *testing.T) string {
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
	// v33-equivalent schema: v32 + signing columns + partial index + marker.
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
		`CREATE INDEX IF NOT EXISTS authz_unsigned ON authorizations(sig_version, signed_at) WHERE signature IS NULL AND sig_version >= 1`,
		`INSERT OR IGNORE INTO authorizations (id, op_type, target, agent_id, mode, created_at, sig_version)
		 VALUES ('migration-033-cutover-marker', 'migration.signing-enabled', 'authorizations',
		         'system:migration-033', 'auto', CAST(strftime('%s','now') AS INTEGER), 1)`,
	}
	for _, s := range stmts {
		if _, err := db.Exec(s); err != nil {
			t.Fatalf("schema: %v", err)
		}
	}
	db.Close()

	if err := os.Chdir(dir); err != nil {
		t.Fatalf("chdir: %v", err)
	}
	t.Cleanup(func() { _ = os.Chdir(origWD) })
	return dir
}

// insertSignableRow inserts a post-cutover row (sig_version=1, signature NULL)
// for the signing tests to pick up.
func insertSignableRow(t *testing.T, root, beadID, opType string) string {
	t.Helper()
	dbPath := filepath.Join(root, ".clavain", "intercore.db")
	db, _ := sql.Open("sqlite", dbPath)
	defer db.Close()
	id := "01HQ" + beadID + "TEST" + opType
	if len(id) > 64 {
		id = id[:64]
	}
	_, err := db.Exec(`INSERT INTO authorizations
		(id, op_type, target, agent_id, bead_id, mode, policy_match, policy_hash,
		 created_at, sig_version)
		VALUES (?, ?, ?, 'claude-test', ?, 'auto', ?, 'hashABC', ?, 1)`,
		id, opType, beadID, beadID, opType+"#0", time.Now().Unix())
	if err != nil {
		t.Fatalf("insert row: %v", err)
	}
	return id
}

// ─── init-key ─────────────────────────────────────────────────────────

func TestPolicyInitKey_CreatesKeypairWithCorrectPerms(t *testing.T) {
	root := setupSigningSandbox(t)
	out, err := captureStdoutAuthz(t, func() error {
		return cmdPolicyInitKey(nil)
	})
	if err != nil {
		t.Fatalf("init-key: %v\nout=%s", err, string(out))
	}

	privPath, pubPath := authz.KeyPaths(root)
	privInfo, err := os.Stat(privPath)
	if err != nil {
		t.Fatalf("stat priv: %v", err)
	}
	if privInfo.Mode().Perm() != 0o400 {
		t.Errorf("priv perms = %o, want 0400", privInfo.Mode().Perm())
	}
	pubInfo, err := os.Stat(pubPath)
	if err != nil {
		t.Fatalf("stat pub: %v", err)
	}
	if pubInfo.Mode().Perm() != 0o444 {
		t.Errorf("pub perms = %o, want 0444", pubInfo.Mode().Perm())
	}

	var parsed map[string]string
	if jerr := json.Unmarshal(out, &parsed); jerr != nil {
		t.Fatalf("unmarshal: %v (out=%s)", jerr, out)
	}
	if parsed["status"] != "ok" || parsed["fingerprint"] == "" {
		t.Errorf("bad output: %+v", parsed)
	}
}

func TestPolicyInitKey_RefusesOverwriteWithoutRotate(t *testing.T) {
	setupSigningSandbox(t)
	if _, err := captureStdoutAuthz(t, func() error { return cmdPolicyInitKey(nil) }); err != nil {
		t.Fatalf("first init-key: %v", err)
	}
	_, err := captureStdoutAuthz(t, func() error { return cmdPolicyInitKey(nil) })
	if err == nil {
		t.Fatal("expected second init-key to refuse")
	}
}

func TestPolicyInitKey_RotateFlagReplaces(t *testing.T) {
	root := setupSigningSandbox(t)
	if _, err := captureStdoutAuthz(t, func() error { return cmdPolicyInitKey(nil) }); err != nil {
		t.Fatalf("first init-key: %v", err)
	}
	pub1, _ := authz.LoadPubKey(root)
	fp1 := authz.KeyFingerprint(pub1)

	if _, err := captureStdoutAuthz(t, func() error { return cmdPolicyInitKey([]string{"--rotate"}) }); err != nil {
		t.Fatalf("init-key --rotate: %v", err)
	}
	pub2, _ := authz.LoadPubKey(root)
	if authz.KeyFingerprint(pub2) == fp1 {
		t.Fatal("rotate did not produce a new key")
	}
}

// ─── sign ─────────────────────────────────────────────────────────────

func TestPolicySign_SignsUnsignedRows(t *testing.T) {
	root := setupSigningSandbox(t)
	if _, err := captureStdoutAuthz(t, func() error { return cmdPolicyInitKey(nil) }); err != nil {
		t.Fatalf("init-key: %v", err)
	}
	rowID := insertSignableRow(t, root, "sylveste-qdqr", "bead-close")

	out, err := captureStdoutAuthz(t, func() error { return cmdPolicySign(nil) })
	if err != nil {
		t.Fatalf("sign: %v (out=%s)", err, out)
	}

	db, _ := sql.Open("sqlite", filepath.Join(root, ".clavain", "intercore.db"))
	defer db.Close()
	var sig []byte
	var signedAt sql.NullInt64
	if err := db.QueryRow(`SELECT signature, signed_at FROM authorizations WHERE id=?`, rowID).Scan(&sig, &signedAt); err != nil {
		t.Fatalf("scan: %v", err)
	}
	if len(sig) == 0 {
		t.Fatal("signature remained NULL")
	}
	if !signedAt.Valid {
		t.Error("signed_at not set")
	}

	// Cutover marker should also be signed.
	var markerSig []byte
	if err := db.QueryRow(`SELECT signature FROM authorizations WHERE id='migration-033-cutover-marker'`).Scan(&markerSig); err != nil {
		t.Fatalf("marker scan: %v", err)
	}
	if len(markerSig) == 0 {
		t.Error("cutover marker remained unsigned; sign should cover it")
	}
}

func TestPolicySign_SkipsPreCutoverRows(t *testing.T) {
	root := setupSigningSandbox(t)
	if _, err := captureStdoutAuthz(t, func() error { return cmdPolicyInitKey(nil) }); err != nil {
		t.Fatalf("init-key: %v", err)
	}

	// Insert a pre-cutover (sig_version=0) row directly.
	dbPath := filepath.Join(root, ".clavain", "intercore.db")
	db, _ := sql.Open("sqlite", dbPath)
	_, err := db.Exec(`INSERT INTO authorizations
		(id, op_type, target, agent_id, mode, created_at, sig_version)
		VALUES ('pre-cutover-1', 'bead-close', 'old-bead', 'claude', 'auto', ?, 0)`,
		time.Now().Unix()-3600)
	if err != nil {
		t.Fatalf("insert pre-cutover: %v", err)
	}
	db.Close()

	if _, err := captureStdoutAuthz(t, func() error { return cmdPolicySign(nil) }); err != nil {
		t.Fatalf("sign: %v", err)
	}

	db, _ = sql.Open("sqlite", dbPath)
	defer db.Close()
	var sig []byte
	if err := db.QueryRow(`SELECT signature FROM authorizations WHERE id='pre-cutover-1'`).Scan(&sig); err != nil {
		t.Fatalf("scan: %v", err)
	}
	if sig != nil {
		t.Error("pre-cutover row should not be signed")
	}
}

// ─── verify ───────────────────────────────────────────────────────────

func TestPolicyVerify_DetectsMutation(t *testing.T) {
	root := setupSigningSandbox(t)
	if _, err := captureStdoutAuthz(t, func() error { return cmdPolicyInitKey(nil) }); err != nil {
		t.Fatalf("init-key: %v", err)
	}
	rowID := insertSignableRow(t, root, "sylveste-qdqr", "bead-close")
	if _, err := captureStdoutAuthz(t, func() error { return cmdPolicySign(nil) }); err != nil {
		t.Fatalf("sign: %v", err)
	}

	// First verify: should pass.
	out, err := captureStdoutAuthz(t, func() error { return cmdPolicyVerify(nil) })
	if err != nil {
		t.Fatalf("verify (clean): %v\nout=%s", err, out)
	}

	// Mutate op_type directly in SQL — this simulates tampering.
	db, _ := sql.Open("sqlite", filepath.Join(root, ".clavain", "intercore.db"))
	if _, err := db.Exec(`UPDATE authorizations SET op_type='tampered' WHERE id=?`, rowID); err != nil {
		t.Fatalf("tamper: %v", err)
	}
	db.Close()

	out, err = captureStdoutAuthz(t, func() error { return cmdPolicyVerify(nil) })
	if err == nil {
		t.Fatal("verify (tampered): expected failure, got nil")
	}
	// Confirm the per-row report flagged the mutated row.
	var report policyVerifyReport
	if jerr := json.Unmarshal(out, &report); jerr != nil {
		t.Fatalf("unmarshal report: %v (out=%s)", jerr, out)
	}
	if report.Summary.Failed < 1 {
		t.Errorf("expected >=1 failed row, got %d", report.Summary.Failed)
	}
	foundBad := false
	for _, r := range report.Rows {
		if r.ID == rowID && !r.Valid {
			foundBad = true
		}
	}
	if !foundBad {
		t.Errorf("tampered row %s not flagged in report", rowID)
	}
}

func TestPolicyVerify_ExitCodes(t *testing.T) {
	root := setupSigningSandbox(t)
	if _, err := captureStdoutAuthz(t, func() error { return cmdPolicyInitKey(nil) }); err != nil {
		t.Fatalf("init-key: %v", err)
	}
	// No rows beyond marker yet. Sign the marker, then verify should pass.
	if _, err := captureStdoutAuthz(t, func() error { return cmdPolicySign(nil) }); err != nil {
		t.Fatalf("sign marker: %v", err)
	}
	if _, err := captureStdoutAuthz(t, func() error { return cmdPolicyVerify(nil) }); err != nil {
		t.Fatalf("verify should succeed with only signed marker: %v", err)
	}

	// Insert an unsigned post-cutover row → verify must fail.
	insertSignableRow(t, root, "unsigned-bead", "bead-close")
	if _, err := captureStdoutAuthz(t, func() error { return cmdPolicyVerify(nil) }); err == nil {
		t.Fatal("expected verify failure with unsigned post-cutover row")
	}
}

func TestPolicyAuditVerify_UsesSameReport(t *testing.T) {
	root := setupSigningSandbox(t)
	if _, err := captureStdoutAuthz(t, func() error { return cmdPolicyInitKey(nil) }); err != nil {
		t.Fatalf("init-key: %v", err)
	}
	_ = root
	out, err := captureStdoutAuthz(t, func() error { return cmdPolicyAudit([]string{"--verify"}) })
	// Marker is unsigned at this point → expected to fail.
	if err == nil {
		t.Fatal("expected audit --verify to fail when marker unsigned")
	}
	var report policyVerifyReport
	if jerr := json.Unmarshal(out, &report); jerr != nil {
		t.Fatalf("unmarshal: %v (out=%s)", jerr, out)
	}
	if report.Summary.Marker == 0 {
		t.Error("marker row not classified")
	}
}

// ─── quarantine ───────────────────────────────────────────────────────

func TestPolicyQuarantine_FlagsPreBreachRows(t *testing.T) {
	root := setupSigningSandbox(t)
	if _, err := captureStdoutAuthz(t, func() error { return cmdPolicyInitKey(nil) }); err != nil {
		t.Fatalf("init-key: %v", err)
	}
	// Grab current key fingerprint; rotate so we aren't quarantining the active key.
	pub, _ := authz.LoadPubKey(root)
	oldFP := authz.KeyFingerprint(pub)
	if _, err := captureStdoutAuthz(t, func() error { return cmdPolicyInitKey([]string{"--rotate"}) }); err != nil {
		t.Fatalf("rotate: %v", err)
	}

	out, err := captureStdoutAuthz(t, func() error {
		return cmdPolicyQuarantine([]string{"--before-key=" + oldFP, "--reason=test"})
	})
	if err != nil {
		t.Fatalf("quarantine: %v\nout=%s", err, out)
	}

	// A quarantine row should exist with op_type=policy.quarantine and target=<fp>.
	db, _ := sql.Open("sqlite", filepath.Join(root, ".clavain", "intercore.db"))
	defer db.Close()
	var count int
	if err := db.QueryRow(`SELECT COUNT(*) FROM authorizations
		WHERE op_type='policy.quarantine' AND target=?`, oldFP).Scan(&count); err != nil {
		t.Fatalf("count: %v", err)
	}
	if count != 1 {
		t.Errorf("quarantine rows=%d, want 1", count)
	}
	// Row must be signable (sig_version=1) so the next `policy sign` covers it.
	var sigVer int
	if err := db.QueryRow(`SELECT sig_version FROM authorizations
		WHERE op_type='policy.quarantine' AND target=?`, oldFP).Scan(&sigVer); err != nil {
		t.Fatalf("scan sig_version: %v", err)
	}
	if sigVer != 1 {
		t.Errorf("quarantine row sig_version=%d, want 1", sigVer)
	}
}

func TestPolicyQuarantine_RefusesCurrentKey(t *testing.T) {
	root := setupSigningSandbox(t)
	if _, err := captureStdoutAuthz(t, func() error { return cmdPolicyInitKey(nil) }); err != nil {
		t.Fatalf("init-key: %v", err)
	}
	pub, _ := authz.LoadPubKey(root)
	fp := authz.KeyFingerprint(pub)
	_, err := captureStdoutAuthz(t, func() error {
		return cmdPolicyQuarantine([]string{"--before-key=" + fp})
	})
	if err == nil {
		t.Fatal("expected quarantine to refuse when --before-key matches current key")
	}
}

func TestPolicyQuarantine_RequiresBeforeKeyFlag(t *testing.T) {
	setupSigningSandbox(t)
	_, err := captureStdoutAuthz(t, func() error { return cmdPolicyQuarantine(nil) })
	if err == nil {
		t.Fatal("expected quarantine without --before-key to error")
	}
}

// ─── sanity: fingerprint hex ──────────────────────────────────────────

func TestQuarantine_RejectsNonHexFingerprint(t *testing.T) {
	setupSigningSandbox(t)
	_, err := captureStdoutAuthz(t, func() error {
		return cmdPolicyQuarantine([]string{"--before-key=NOT_HEX!!!"})
	})
	if err == nil {
		t.Fatal("expected non-hex fingerprint to be rejected")
	}
	// sanity: ensure hex decode of a valid 16-char hex doesn't surface a reject.
	if _, err := hex.DecodeString("abcdefabcdefabcd"); err != nil {
		t.Fatal("test data broken")
	}
}
