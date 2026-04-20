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
func openIntercoreDBAndRoot() (*sql.DB, string, string, error) {
	db, path, err := openIntercoreDB()
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
// writes a fresh one at the canonical paths. The archived key remains readable
// so pre-rotation signatures stay verifiable against its pub file.
//
//	clavain-cli policy rotate-key [--project-root=<path>]
func cmdPolicyRotateKey(args []string) error {
	flags := parseAuthzArgs(args)
	root, err := resolveProjectRoot(flags)
	if err != nil {
		return err
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
	db, _, root, err := openIntercoreDBAndRoot()
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
	db, _, root, err := openIntercoreDBAndRoot()
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

	db, _, root, err := openIntercoreDBAndRoot()
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
	if v, ok := flags["project-root"]; ok && v != "" {
		if _, err := os.Stat(v); err != nil {
			return "", fmt.Errorf("--project-root %s: %w", v, err)
		}
		return v, nil
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
func maybeAuditVerify(db *sql.DB, flags map[string]string) error {
	root := projectRootForDB(findIntercoreDB())
	if root == "" || root == "." {
		cwd, _ := os.Getwd()
		root = cwd
	}
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

