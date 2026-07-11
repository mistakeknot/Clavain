package main

import (
	"database/sql"
	"encoding/hex"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/mistakeknot/intercore/pkg/authz"
)

// ─── Project root helpers ──────────────────────────────────────────────

// projectRootForDB returns the project root given an intercore.db path.
// Layout: <root>/.clavain/intercore.db → <root>.
func projectRootForDB(dbPath string) string {
	return filepath.Dir(filepath.Dir(dbPath))
}

// openIntercoreDBAndRoot opens the DB and returns (db, dbPath, projectRoot).
func openIntercoreDBAndRoot(flagSets ...map[string]string) (*sql.DB, string, string, error) {
	db, path, err := openIntercoreDB(flagSets...)
	if err != nil {
		return nil, "", "", err
	}
	return db, path, projectRootForDB(path), nil
}

// ─── policy init-key ──────────────────────────────────────────────────

// cmdPolicyInitKey generates and persists a fresh Ed25519 keypair under the
// project root's .clavain/keys/ directory. Refuses to overwrite an existing
// key unless --rotate is passed (in which case it defers to cmdPolicyRotateKey
// semantics: archive the old, write the new).
//
//	clavain-cli policy init-key [--rotate] [--project-root=<path>]
func cmdPolicyInitKey(args []string) error {
	flags := parseAuthzArgs(args)
	root, err := resolveProjectRoot(flags)
	if err != nil {
		return err
	}

	if _, ok := flags["rotate"]; ok {
		return cmdPolicyRotateKey(args)
	}

	kp, err := authz.GenerateKey()
	if err != nil {
		return fmt.Errorf("policy init-key: %w", err)
	}
	if err := authz.WriteKeyPair(root, kp); err != nil {
		if err == authz.ErrKeyAlreadyExists {
			return fmt.Errorf("policy init-key: key already exists at %s; pass --rotate to replace it", filepath.Join(root, ".clavain", "keys"))
		}
		return fmt.Errorf("policy init-key: %w", err)
	}
	privPath, pubPath := authz.KeyPaths(root)
	fp := authz.KeyFingerprint(kp.Pub)
	return outputJSON(map[string]string{
		"status":      "ok",
		"private_key": privPath,
		"public_key":  pubPath,
		"fingerprint": fp,
	})
}

// ─── policy rotate-key ─────────────────────────────────────────────────

// cmdPolicyRotateKey archives the current keypair under its fingerprint and
// writes a fresh one at the canonical paths. Rotation is refused once signed
// history exists because the verifier currently trusts one active public key.
//
//	clavain-cli policy rotate-key [--project-root=<path>]
func cmdPolicyRotateKey(args []string) error {
	flags := parseAuthzArgs(args)
	db, _, root, err := openIntercoreDBAndRoot(flags)
	if err != nil {
		return fmt.Errorf("policy rotate-key: %w", err)
	}
	defer db.Close()

	var signedRows int
	if err := db.QueryRow(`SELECT COUNT(*) FROM authorizations WHERE signature IS NOT NULL`).Scan(&signedRows); err != nil {
		return fmt.Errorf("policy rotate-key: inspect signed history: %w", err)
	}
	if signedRows > 0 {
		return fmt.Errorf("policy rotate-key: refused: %d signed authorization row(s) depend on the active key; multi-key verification is not implemented", signedRows)
	}

	newKP, err := authz.GenerateKey()
	if err != nil {
		return fmt.Errorf("policy rotate-key: generate: %w", err)
	}
	archivedPriv, archivedPub, err := authz.RotateKey(root, newKP)
	if err != nil {
		return fmt.Errorf("policy rotate-key: %w", err)
	}
	privPath, pubPath := authz.KeyPaths(root)
	return outputJSON(map[string]string{
		"status":           "ok",
		"new_fingerprint":  authz.KeyFingerprint(newKP.Pub),
		"private_key":      privPath,
		"public_key":       pubPath,
		"archived_private": archivedPriv,
		"archived_public":  archivedPub,
	})
}

// ─── policy sign ──────────────────────────────────────────────────────

// cmdPolicySign reads unsigned post-cutover rows and writes Ed25519
// signatures. Filters narrow which rows participate; no filters = sign every
// unsigned post-cutover row (bootstrap case).
//
//	clavain-cli policy sign [--op=<op>] [--target=<t>] [--bead=<id>]
//	                        [--since=<duration>] [--project-root=<path>]
func cmdPolicySign(args []string) error {
	flags := parseAuthzArgs(args)
	db, _, root, err := openIntercoreDBAndRoot(flags)
	if err != nil {
		return err
	}
	defer db.Close()

	kp, err := authz.LoadPrivKey(root)
	if err != nil {
		return fmt.Errorf("policy sign: %w", err)
	}

	where := []string{"signature IS NULL", "sig_version >= 1"}
	params := []interface{}{}
	if v, ok := flags["op"]; ok {
		where = append(where, "op_type = ?")
		params = append(params, v)
	}
	if v, ok := flags["target"]; ok {
		where = append(where, "target = ?")
		params = append(params, v)
	}
	if v, ok := flags["bead"]; ok {
		where = append(where, "bead_id = ?")
		params = append(params, v)
	}
	if v, ok := flags["since"]; ok {
		d, err := time.ParseDuration(v)
		if err != nil {
			return fmt.Errorf("policy sign: invalid --since: %w", err)
		}
		where = append(where, "created_at >= ?")
		params = append(params, time.Now().Add(-d).Unix())
	}

	q := fmt.Sprintf(`
		SELECT id, op_type, target, agent_id, IFNULL(bead_id,''), mode,
		       IFNULL(policy_match,''), IFNULL(policy_hash,''),
		       IFNULL(vetted_sha,''), IFNULL(vetting,''),
		       IFNULL(cross_project_id,''), created_at
		FROM authorizations
		WHERE %s
		ORDER BY created_at ASC`, strings.Join(where, " AND "))
	rows, err := db.Query(q, params...)
	if err != nil {
		return fmt.Errorf("policy sign: query: %w", err)
	}

	type toSign struct {
		row authz.SignRow
	}
	var queue []toSign
	for rows.Next() {
		var r authz.SignRow
		if err := rows.Scan(&r.ID, &r.OpType, &r.Target, &r.AgentID, &r.BeadID, &r.Mode,
			&r.PolicyMatch, &r.PolicyHash, &r.VettedSHA, &r.Vetting,
			&r.CrossProjectID, &r.CreatedAt); err != nil {
			rows.Close()
			return fmt.Errorf("policy sign: scan: %w", err)
		}
		queue = append(queue, toSign{row: r})
	}
	rows.Close()

	now := time.Now().Unix()
	signed := 0
	for _, q := range queue {
		sig, err := authz.Sign(kp.Priv, q.row)
		if err != nil {
			return fmt.Errorf("policy sign: row %s: %w", q.row.ID, err)
		}
		if _, err := db.Exec(`UPDATE authorizations SET signature=?, signed_at=? WHERE id=? AND signature IS NULL`,
			sig, now, q.row.ID); err != nil {
			return fmt.Errorf("policy sign: update %s: %w", q.row.ID, err)
		}
		signed++
	}
	return outputJSON(map[string]interface{}{
		"status":      "ok",
		"signed":      signed,
		"fingerprint": authz.KeyFingerprint(kp.Pub),
	})
}

// cmdPolicyRecordSigned records one authorization decision and signs that
// exact row in a single transaction. Gate wrappers call this before executing
// the authorized operation, so an audit failure cannot produce an unaudited
// irreversible action and matching injected rows are never swept up.
func cmdPolicyRecordSigned(args []string) error {
	flags := parseAuthzArgs(args)
	for _, key := range []string{"op", "target", "agent", "mode"} {
		if flags[key] == "" {
			return fmt.Errorf("policy record-signed: missing --%s", key)
		}
	}
	db, _, root, err := openIntercoreDBAndRoot(flags)
	if err != nil {
		return err
	}
	defer db.Close()
	kp, err := authz.LoadPrivKey(root)
	if err != nil {
		return fmt.Errorf("policy record-signed: %w", err)
	}

	now := time.Now().Unix()
	record := authz.RecordArgs{
		OpType:         flags["op"],
		Target:         flags["target"],
		AgentID:        flags["agent"],
		BeadID:         flags["bead"],
		Mode:           flags["mode"],
		PolicyMatch:    flags["policy-match"],
		PolicyHash:     flags["policy-hash"],
		VettedSHA:      flags["vetted-sha"],
		CrossProjectID: flags["cross-project-id"],
		CreatedAt:      now,
	}
	tx, err := db.Begin()
	if err != nil {
		return fmt.Errorf("policy record-signed: begin: %w", err)
	}
	defer tx.Rollback()
	id, err := authz.RecordWithID(tx, record)
	if err != nil {
		return fmt.Errorf("policy record-signed: record: %w", err)
	}
	row := authz.SignRow{
		ID:             id,
		OpType:         record.OpType,
		Target:         record.Target,
		AgentID:        record.AgentID,
		BeadID:         record.BeadID,
		Mode:           record.Mode,
		PolicyMatch:    record.PolicyMatch,
		PolicyHash:     record.PolicyHash,
		VettedSHA:      record.VettedSHA,
		CrossProjectID: record.CrossProjectID,
		CreatedAt:      now,
	}
	sig, err := authz.Sign(kp.Priv, row)
	if err != nil {
		return fmt.Errorf("policy record-signed: sign: %w", err)
	}
	result, err := tx.Exec(`UPDATE authorizations SET signature=?, signed_at=? WHERE id=? AND signature IS NULL`, sig, now, id)
	if err != nil {
		return fmt.Errorf("policy record-signed: update: %w", err)
	}
	if affected, err := result.RowsAffected(); err != nil || affected != 1 {
		return fmt.Errorf("policy record-signed: signed rows=%d, want 1 (err=%v)", affected, err)
	}
	if err := tx.Commit(); err != nil {
		return fmt.Errorf("policy record-signed: commit: %w", err)
	}
	return outputJSON(map[string]interface{}{
		"status":      "ok",
		"id":          id,
		"signed":      1,
		"fingerprint": authz.KeyFingerprint(kp.Pub),
	})
}

type authorizationRowStore interface {
	QueryRow(query string, args ...interface{}) *sql.Row
	Exec(query string, args ...interface{}) (sql.Result, error)
}

func signAuthorizationByID(store authorizationRowStore, kp authz.KeyPair, id string, signedAt int64) error {
	var row authz.SignRow
	var existing []byte
	if err := store.QueryRow(`
		SELECT id, op_type, target, agent_id, IFNULL(bead_id,''), mode,
		       IFNULL(policy_match,''), IFNULL(policy_hash,''), IFNULL(vetted_sha,''),
		       IFNULL(vetting,''), IFNULL(cross_project_id,''), created_at, signature
		FROM authorizations WHERE id=?`, id,
	).Scan(&row.ID, &row.OpType, &row.Target, &row.AgentID, &row.BeadID, &row.Mode,
		&row.PolicyMatch, &row.PolicyHash, &row.VettedSHA, &row.Vetting,
		&row.CrossProjectID, &row.CreatedAt, &existing); err != nil {
		return fmt.Errorf("load authorization %s: %w", id, err)
	}
	if existing != nil {
		return fmt.Errorf("authorization %s already signed", id)
	}
	sig, err := authz.Sign(kp.Priv, row)
	if err != nil {
		return fmt.Errorf("sign authorization %s: %w", id, err)
	}
	result, err := store.Exec(`UPDATE authorizations SET signature=?, signed_at=? WHERE id=? AND signature IS NULL`, sig, signedAt, id)
	if err != nil {
		return fmt.Errorf("update authorization %s: %w", id, err)
	}
	affected, err := result.RowsAffected()
	if err != nil || affected != 1 {
		return fmt.Errorf("authorization %s signed rows=%d, want 1 (err=%v)", id, affected, err)
	}
	return nil
}

// ─── policy verify ────────────────────────────────────────────────────

// verifyRow is the per-row verify report emitted by cmdPolicyVerify and
// the --verify arm of cmdPolicyAudit.
type verifyRow struct {
	ID          string `json:"id"`
	Vintage     string `json:"vintage"` // "post-signing" | "pre-signing" | "marker"
	Valid       bool   `json:"valid"`
	SigVersion  int    `json:"sig_version"`
	Fingerprint string `json:"fingerprint,omitempty"`
	Reason      string `json:"reason,omitempty"`
}

// verifySummary aggregates pass/fail counts.
type verifySummary struct {
	Total       int `json:"total"`
	Passed      int `json:"passed"`
	Failed      int `json:"failed"`
	PreSigning  int `json:"pre_signing"`
	Marker      int `json:"marker"`
	PostSigning int `json:"post_signing"`
}

// cmdPolicyVerify reads every authorizations row, classifies its vintage,
// verifies post-signing rows against the project pubkey, and prints a JSON
// report. Exit 1 if any post-signing row fails verification.
//
//	clavain-cli policy verify [--json] [--since=<duration>] [--op=<op>]
//	                          [--project-root=<path>]
func cmdPolicyVerify(args []string) error {
	flags := parseAuthzArgs(args)
	db, _, root, err := openIntercoreDBAndRoot(flags)
	if err != nil {
		return err
	}
	defer db.Close()

	report, err := runPolicyVerify(db, root, flags)
	if err != nil {
		return fmt.Errorf("policy verify: %w", err)
	}
	if err := outputJSON(report); err != nil {
		return err
	}
	if report.Summary.Failed > 0 {
		return fmt.Errorf("policy verify: %d row(s) failed verification", report.Summary.Failed)
	}
	return nil
}

// policyVerifyReport is the top-level verify output.
type policyVerifyReport struct {
	Fingerprint string        `json:"fingerprint"`
	Rows        []verifyRow   `json:"rows"`
	Summary     verifySummary `json:"summary"`
}

// runPolicyVerify is shared by `policy verify` and `policy audit --verify`.
// It loads the project pubkey (if any) and walks rows matching the flag
// filters, verifying each post-signing signature.
func runPolicyVerify(db *sql.DB, root string, flags map[string]string) (policyVerifyReport, error) {
	pub, pubErr := authz.LoadPubKey(root)
	fp := ""
	if pubErr == nil {
		fp = authz.KeyFingerprint(pub)
	}

	where := []string{"1=1"}
	params := []interface{}{}
	if v, ok := flags["since"]; ok {
		d, err := time.ParseDuration(v)
		if err != nil {
			return policyVerifyReport{}, fmt.Errorf("invalid --since: %w", err)
		}
		where = append(where, "created_at >= ?")
		params = append(params, time.Now().Add(-d).Unix())
	}
	for _, k := range []string{"op", "agent", "bead"} {
		if v, ok := flags[k]; ok {
			col := map[string]string{"op": "op_type", "agent": "agent_id", "bead": "bead_id"}[k]
			where = append(where, col+" = ?")
			params = append(params, v)
		}
	}

	q := fmt.Sprintf(`
		SELECT id, op_type, target, agent_id, IFNULL(bead_id,''), mode,
		       IFNULL(policy_match,''), IFNULL(policy_hash,''),
		       IFNULL(vetted_sha,''), IFNULL(vetting,''),
		       IFNULL(cross_project_id,''), created_at,
		       sig_version, signature
		FROM authorizations
		WHERE %s
		ORDER BY created_at ASC`, strings.Join(where, " AND "))
	rows, err := db.Query(q, params...)
	if err != nil {
		return policyVerifyReport{}, fmt.Errorf("query: %w", err)
	}
	defer rows.Close()

	report := policyVerifyReport{Fingerprint: fp}
	for rows.Next() {
		var r authz.SignRow
		var sigVersion int
		var sig []byte
		if err := rows.Scan(&r.ID, &r.OpType, &r.Target, &r.AgentID, &r.BeadID, &r.Mode,
			&r.PolicyMatch, &r.PolicyHash, &r.VettedSHA, &r.Vetting,
			&r.CrossProjectID, &r.CreatedAt, &sigVersion, &sig); err != nil {
			return policyVerifyReport{}, fmt.Errorf("scan: %w", err)
		}

		vr := verifyRow{ID: r.ID, SigVersion: sigVersion, Fingerprint: fp}
		switch {
		case r.OpType == "migration.signing-enabled":
			vr.Vintage = "marker"
			vr.Valid = verifyWithPub(pub, r, sig)
			if !vr.Valid && sig == nil {
				vr.Reason = "unsigned marker (run `policy sign` to sign it)"
			}
			report.Summary.Marker++
		case sigVersion == 0:
			vr.Vintage = "pre-signing"
			vr.Valid = true // pre-cutover rows are vintage, not failures
			report.Summary.PreSigning++
		default:
			vr.Vintage = "post-signing"
			vr.Valid = verifyWithPub(pub, r, sig)
			if !vr.Valid {
				if pubErr != nil {
					vr.Reason = "pubkey not loaded: " + pubErr.Error()
				} else if sig == nil {
					vr.Reason = "signature is NULL"
				} else {
					vr.Reason = "signature invalid (tampering or wrong key)"
				}
			}
			report.Summary.PostSigning++
		}

		if vr.Valid {
			report.Summary.Passed++
		} else {
			report.Summary.Failed++
		}
		report.Summary.Total++
		report.Rows = append(report.Rows, vr)
	}
	return report, nil
}

// verifyWithPub returns true iff pub is loaded and sig verifies over row.
// Returns false (not an error) when pub is nil — that's a "can't verify"
// outcome, surfaced to the caller via Reason.
func verifyWithPub(pub []byte, row authz.SignRow, sig []byte) bool {
	if pub == nil || sig == nil {
		return false
	}
	return authz.Verify(pub, row, sig)
}

// ─── policy quarantine ────────────────────────────────────────────────

// cmdPolicyQuarantine records a key-compromise event. It writes a new
// authorizations row of op_type='policy.quarantine' with target set to the
// compromised-key fingerprint. The new row is itself signed by the CURRENT
// project key (which must differ from the quarantined fingerprint).
//
// Rows signed by the quarantined key become untrusted at verify time: verify
// can be taught to flag them, but the quarantine marker itself is the
// authoritative signal of breach — a conservative auditor walks the table,
// finds the quarantine marker, and treats earlier rows with matching
// fingerprint as suspect.
//
//	clavain-cli policy quarantine --before-key=<fp> [--reason=<text>]
//	                              [--project-root=<path>]
func cmdPolicyQuarantine(args []string) error {
	flags := parseAuthzArgs(args)
	fp, ok := flags["before-key"]
	if !ok || fp == "" {
		return fmt.Errorf("policy quarantine: --before-key=<fingerprint> required")
	}
	if _, err := hex.DecodeString(fp); err != nil || len(fp) < 8 {
		return fmt.Errorf("policy quarantine: --before-key must be hex (≥8 chars)")
	}

	db, _, root, err := openIntercoreDBAndRoot(flags)
	if err != nil {
		return err
	}
	defer db.Close()

	// Refuse if the current key matches the quarantined fingerprint:
	// quarantining with the compromised key itself provides no assurance.
	if kp, kerr := authz.LoadPrivKey(root); kerr == nil {
		if authz.KeyFingerprint(kp.Pub) == fp {
			return fmt.Errorf("policy quarantine: current project key has fingerprint %s; rotate-key first", fp)
		}
	}

	reason := flags["reason"]
	if reason == "" {
		reason = "manual quarantine"
	}

	if err := authz.Record(db, authz.RecordArgs{
		OpType:      "policy.quarantine",
		Target:      fp,
		AgentID:     "clavain-cli:policy-quarantine",
		Mode:        "auto",
		PolicyMatch: "policy.quarantine",
		PolicyHash:  "",
		Vetting:     map[string]interface{}{"reason": reason, "quarantined_key_fingerprint": fp},
	}); err != nil {
		return fmt.Errorf("policy quarantine: record: %w", err)
	}

	return outputJSON(map[string]string{
		"status":              "ok",
		"quarantined_key":     fp,
		"quarantine_recorded": "authorizations(op_type=policy.quarantine)",
		"reason":              reason,
	})
}

// ─── helpers ──────────────────────────────────────────────────────────

// resolveProjectRoot picks the --project-root flag, else derives from the
// intercore.db walk-up. Used by key-management handlers that don't need the
// DB open (init-key, rotate-key).
func resolveProjectRoot(flags map[string]string) (string, error) {
	if root, explicit, err := explicitAuthzProjectRoot(flags); err != nil {
		return "", err
	} else if explicit {
		return root, nil
	}
	dbPath := findIntercoreDB()
	if dbPath == "" {
		cwd, _ := os.Getwd()
		return cwd, nil
	}
	return projectRootForDB(dbPath), nil
}

// ─── audit --verify augmentation ──────────────────────────────────────

// maybeAuditVerify is called by cmdPolicyAudit when --verify is passed. It
// replaces the audit rowset with the verify report and sets an error return
// when any post-signing row fails.
func maybeAuditVerify(db *sql.DB, root string, flags map[string]string) error {
	report, err := runPolicyVerify(db, root, flags)
	if err != nil {
		return fmt.Errorf("policy audit --verify: %w", err)
	}
	if err := outputJSON(report); err != nil {
		return err
	}
	if report.Summary.Failed > 0 {
		return fmt.Errorf("policy audit --verify: %d row(s) failed", report.Summary.Failed)
	}
	return nil
}

// cmdPolicyDoctor reports whether an authz domain has a usable database and
// public trust anchor, and whether this host owns the matching private key.
// It never emits private-key paths or material.
//
//	clavain-cli policy doctor [--project-root=<path>] [--require-signer]
//	                          [--expected-pub=<fingerprint>]
func cmdPolicyDoctor(args []string) error {
	flags := parseAuthzArgs(args)
	db, dbPath, root, err := openIntercoreDBAndRoot(flags)
	if err != nil {
		return fmt.Errorf("policy doctor: %w", err)
	}
	defer db.Close()

	if err := db.Ping(); err != nil {
		return fmt.Errorf("policy doctor: database unavailable: %w", err)
	}
	var schema int
	if err := db.QueryRow(`PRAGMA user_version`).Scan(&schema); err != nil {
		return fmt.Errorf("policy doctor: read schema: %w", err)
	}
	if schema != 35 {
		return fmt.Errorf("policy doctor: unsupported intercore schema %d; require 35", schema)
	}
	var quickCheck string
	if err := db.QueryRow(`PRAGMA quick_check`).Scan(&quickCheck); err != nil {
		return fmt.Errorf("policy doctor: database quick_check: %w", err)
	}
	if quickCheck != "ok" {
		return fmt.Errorf("policy doctor: database quick_check=%q, want ok", quickCheck)
	}
	if _, err := db.Exec(`
		SELECT id, op_type, target, agent_id, bead_id, mode, policy_match,
		       policy_hash, vetted_sha, vetting, cross_project_id, created_at,
		       sig_version, signature, signed_at
		FROM authorizations LIMIT 0`); err != nil {
		return fmt.Errorf("policy doctor: authorizations schema invalid: %w", err)
	}
	pub, err := authz.LoadPubKey(root)
	if err != nil {
		return fmt.Errorf("policy doctor: public key unavailable: %w", err)
	}
	fingerprint := authz.KeyFingerprint(pub)
	if expected := strings.TrimSpace(flags["expected-pub"]); expected != "" && expected != fingerprint {
		return fmt.Errorf("policy doctor: public key fingerprint %s does not match expected %s", fingerprint, expected)
	}

	role := "signer"
	if _, err := authz.LoadPrivKey(root); err != nil {
		if err == authz.ErrKeyNotFound {
			role = "verifier"
		} else {
			return fmt.Errorf("policy doctor: private key invalid: %w", err)
		}
	}
	if _, required := flags["require-signer"]; required && role != "signer" {
		return fmt.Errorf("policy doctor: signer required at %s; this host is verifier-only", root)
	}
	if role == "signer" {
		probeTx, err := db.Begin()
		if err != nil {
			return fmt.Errorf("policy doctor: begin write probe: %w", err)
		}
		probeID := fmt.Sprintf("doctor-probe-%d", time.Now().UnixNano())
		_, probeErr := probeTx.Exec(`
			INSERT INTO authorizations (id, op_type, target, agent_id, mode, created_at, sig_version)
			VALUES (?, 'policy.doctor-probe', 'rollback', 'clavain-cli:doctor', 'auto', ?, 1)`,
			probeID, time.Now().Unix())
		rollbackErr := probeTx.Rollback()
		if probeErr != nil {
			return fmt.Errorf("policy doctor: database is not writable: %w", probeErr)
		}
		if rollbackErr != nil {
			return fmt.Errorf("policy doctor: rollback write probe: %w", rollbackErr)
		}
	}

	return outputJSON(map[string]interface{}{
		"status":       "ok",
		"role":         role,
		"project_root": root,
		"database":     dbPath,
		"schema":       schema,
		"fingerprint":  fingerprint,
	})
}
