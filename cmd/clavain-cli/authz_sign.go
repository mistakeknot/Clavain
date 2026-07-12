package main

import (
	"context"
	"database/sql"
	"encoding/hex"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
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

	where := []string{"signature IS NULL", "sig_version = 1"}
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

// ─── policy anchor-legacy ──────────────────────────────────────────────

type authorizationSnapshotRow struct {
	Row        authz.SignRow
	SigVersion int
	Signature  []byte
	SignedAt   sql.NullInt64
}

type authorizationSnapshot struct {
	Schema int
	Rows   []authorizationSnapshotRow
}

type authorizationSnapshotQueryer interface {
	QueryContext(context.Context, string, ...interface{}) (*sql.Rows, error)
	QueryRowContext(context.Context, string, ...interface{}) *sql.Row
}

type legacyAnchorProposal struct {
	Snapshot authorizationSnapshot
	Marker   authz.SignRow
	Legacy   []authz.SignRow
	Manifest authz.LegacyManifest
}

type legacyAnchorReport struct {
	Status              string   `json:"status"`
	Schema              int      `json:"schema"`
	LegacyCount         int      `json:"legacy_count"`
	LegacyIDs           []string `json:"legacy_ids"`
	ManifestSHA256      string   `json:"manifest_sha256"`
	PublicKeySHA256     string   `json:"public_key_sha256"`
	CutoverMarkerSHA256 string   `json:"cutover_marker_sha256"`
	ManifestPath        string   `json:"manifest_path,omitempty"`
}

// cmdPolicyAnchorLegacy inspects or creates the one-time signed public anchor
// for the exact sig_version=0 authorization set. Nonempty histories require an
// operator-reviewed count and digest; there is no overwrite or re-anchor path.
//
//	clavain-cli policy anchor-legacy --inspect [--project-root=<path>]
//	clavain-cli policy anchor-legacy --expect-count=<n> --expect-digest=<sha256>
//	clavain-cli policy anchor-legacy --expect-empty
func cmdPolicyAnchorLegacy(args []string) error {
	flags := parseAuthzArgs(args)
	db, _, root, err := openIntercoreDBAndRoot(flags)
	if err != nil {
		return fmt.Errorf("policy anchor-legacy: %w", err)
	}
	defer db.Close()
	pub, err := authz.LoadPubKey(root)
	if err != nil {
		return fmt.Errorf("policy anchor-legacy: load public key: %w", err)
	}

	ctx := context.Background()
	if _, inspect := flags["inspect"]; inspect {
		tx, err := db.BeginTx(ctx, &sql.TxOptions{ReadOnly: true})
		if err != nil {
			return fmt.Errorf("policy anchor-legacy: begin inspection: %w", err)
		}
		defer tx.Rollback()
		proposal, err := buildLegacyAnchorProposal(ctx, tx, pub)
		if err != nil {
			return fmt.Errorf("policy anchor-legacy: inspect: %w", err)
		}
		return outputJSON(proposal.report("proposal", root))
	}

	kp, err := authz.LoadPrivKey(root)
	if err != nil {
		return fmt.Errorf("policy anchor-legacy: signer key required: %w", err)
	}
	conn, err := db.Conn(ctx)
	if err != nil {
		return fmt.Errorf("policy anchor-legacy: reserve connection: %w", err)
	}
	defer conn.Close()
	if _, err := conn.ExecContext(ctx, "BEGIN IMMEDIATE"); err != nil {
		return fmt.Errorf("policy anchor-legacy: freeze authorization writes: %w", err)
	}
	committed := false
	defer func() {
		if !committed {
			_, _ = conn.ExecContext(ctx, "ROLLBACK")
		}
	}()

	proposal, err := buildLegacyAnchorProposal(ctx, conn, pub)
	if err != nil {
		return fmt.Errorf("policy anchor-legacy: inspect locked ledger: %w", err)
	}
	if proposal.Snapshot.Schema != 36 {
		return fmt.Errorf("policy anchor-legacy: schema %d is inspect-only; run the reviewed schema-36 migration before creating the anchor", proposal.Snapshot.Schema)
	}
	if err := validateLegacyAnchorExpectation(flags, proposal.Manifest); err != nil {
		return fmt.Errorf("policy anchor-legacy: %w", err)
	}
	manifest := proposal.Manifest
	if err := authz.SignLegacyManifest(kp.Priv, &manifest); err != nil {
		return fmt.Errorf("policy anchor-legacy: sign: %w", err)
	}
	if err := authz.VerifyLegacyManifest(pub, manifest, proposal.Marker, proposal.Legacy); err != nil {
		return fmt.Errorf("policy anchor-legacy: self-verify: %w", err)
	}
	if err := authz.WriteLegacyManifest(root, manifest); err != nil {
		return fmt.Errorf("policy anchor-legacy: persist: %w", err)
	}
	if _, err := conn.ExecContext(ctx, "COMMIT"); err != nil {
		return fmt.Errorf("policy anchor-legacy: release ledger lock: %w", err)
	}
	committed = true
	proposal.Manifest = manifest
	return outputJSON(proposal.report("anchored", root))
}

func loadAuthorizationSnapshot(ctx context.Context, q authorizationSnapshotQueryer) (authorizationSnapshot, error) {
	var snapshot authorizationSnapshot
	if err := q.QueryRowContext(ctx, `PRAGMA user_version`).Scan(&snapshot.Schema); err != nil {
		return authorizationSnapshot{}, fmt.Errorf("read schema: %w", err)
	}
	rows, err := q.QueryContext(ctx, `
		SELECT id, op_type, target, agent_id, IFNULL(bead_id,''), mode,
		       IFNULL(policy_match,''), IFNULL(policy_hash,''),
		       IFNULL(vetted_sha,''), IFNULL(vetting,''),
		       IFNULL(cross_project_id,''), created_at,
		       sig_version, signature, signed_at
		FROM authorizations
		ORDER BY created_at ASC, id ASC`)
	if err != nil {
		return authorizationSnapshot{}, fmt.Errorf("query authorizations: %w", err)
	}
	defer rows.Close()
	for rows.Next() {
		var record authorizationSnapshotRow
		r := &record.Row
		if err := rows.Scan(&r.ID, &r.OpType, &r.Target, &r.AgentID, &r.BeadID, &r.Mode,
			&r.PolicyMatch, &r.PolicyHash, &r.VettedSHA, &r.Vetting,
			&r.CrossProjectID, &r.CreatedAt, &record.SigVersion, &record.Signature,
			&record.SignedAt); err != nil {
			return authorizationSnapshot{}, fmt.Errorf("scan authorization: %w", err)
		}
		snapshot.Rows = append(snapshot.Rows, record)
	}
	if err := rows.Err(); err != nil {
		return authorizationSnapshot{}, fmt.Errorf("iterate authorizations: %w", err)
	}
	return snapshot, nil
}

func buildLegacyAnchorProposal(ctx context.Context, q authorizationSnapshotQueryer, pub []byte) (legacyAnchorProposal, error) {
	snapshot, err := loadAuthorizationSnapshot(ctx, q)
	if err != nil {
		return legacyAnchorProposal{}, err
	}
	if snapshot.Schema != 35 && snapshot.Schema != 36 {
		return legacyAnchorProposal{}, fmt.Errorf("unsupported intercore schema %d; require 35 for inspection or 36 for sealing", snapshot.Schema)
	}

	var marker authz.SignRow
	markerCount := 0
	legacy := make([]authz.SignRow, 0)
	for _, record := range snapshot.Rows {
		if record.Row.OpType == "migration.signing-enabled" {
			markerCount++
			if record.Row.ID != authz.LegacyCutoverMarkerID {
				return legacyAnchorProposal{}, fmt.Errorf("unexpected signing marker id %q", record.Row.ID)
			}
			marker = record.Row
		}
		switch record.SigVersion {
		case 0:
			if record.Signature != nil || record.SignedAt.Valid {
				return legacyAnchorProposal{}, fmt.Errorf("legacy row %s has signing metadata", record.Row.ID)
			}
			legacy = append(legacy, record.Row)
		case 1:
			if !record.SignedAt.Valid || !authz.Verify(pub, record.Row, record.Signature) {
				return legacyAnchorProposal{}, fmt.Errorf("signed row %s does not verify", record.Row.ID)
			}
		default:
			return legacyAnchorProposal{}, fmt.Errorf("row %s has unsupported sig_version %d", record.Row.ID, record.SigVersion)
		}
	}
	if markerCount != 1 || marker.ID != authz.LegacyCutoverMarkerID {
		return legacyAnchorProposal{}, fmt.Errorf("require exactly one fixed migration-033 signing marker; found %d", markerCount)
	}
	manifest, err := authz.BuildLegacyManifest(pub, marker, legacy)
	if err != nil {
		return legacyAnchorProposal{}, err
	}
	return legacyAnchorProposal{Snapshot: snapshot, Marker: marker, Legacy: legacy, Manifest: manifest}, nil
}

func (p legacyAnchorProposal) report(status, root string) legacyAnchorReport {
	ids := make([]string, len(p.Manifest.LegacyRows))
	for i, row := range p.Manifest.LegacyRows {
		ids[i] = row.ID
	}
	return legacyAnchorReport{
		Status:              status,
		Schema:              p.Snapshot.Schema,
		LegacyCount:         p.Manifest.LegacyCount,
		LegacyIDs:           ids,
		ManifestSHA256:      p.Manifest.ManifestSHA256,
		PublicKeySHA256:     p.Manifest.PublicKeySHA256,
		CutoverMarkerSHA256: p.Manifest.CutoverMarker.PayloadSHA256,
		ManifestPath:        authz.LegacyManifestPath(root),
	}
}

func validateLegacyAnchorExpectation(flags map[string]string, manifest authz.LegacyManifest) error {
	_, expectEmpty := flags["expect-empty"]
	countText, hasCount := flags["expect-count"]
	digest, hasDigest := flags["expect-digest"]
	if expectEmpty {
		if hasCount || hasDigest {
			return fmt.Errorf("--expect-empty cannot be combined with --expect-count or --expect-digest")
		}
		if manifest.LegacyCount != 0 {
			return fmt.Errorf("expected empty legacy set, found %d row(s); inspect and review the nonempty proposal", manifest.LegacyCount)
		}
		return nil
	}
	if !hasCount || !hasDigest {
		return fmt.Errorf("nonempty and reviewed migrations require both --expect-count and --expect-digest (or --expect-empty for a fresh ledger)")
	}
	count, err := strconv.Atoi(countText)
	if err != nil || count < 0 {
		return fmt.Errorf("invalid --expect-count %q", countText)
	}
	decoded, err := hex.DecodeString(digest)
	if err != nil || len(decoded) != 32 || digest != hex.EncodeToString(decoded) {
		return fmt.Errorf("--expect-digest must be 32-byte lowercase hex")
	}
	if count != manifest.LegacyCount {
		return fmt.Errorf("legacy count changed: got %d, expected %d", manifest.LegacyCount, count)
	}
	if digest != manifest.ManifestSHA256 {
		return fmt.Errorf("legacy manifest digest changed: got %s, expected %s", manifest.ManifestSHA256, digest)
	}
	return nil
}

// ─── policy verify ────────────────────────────────────────────────────

// verifyRow is the per-row verify report emitted by cmdPolicyVerify and
// the --verify arm of cmdPolicyAudit.
type verifyRow struct {
	ID          string `json:"id"`
	Vintage     string `json:"vintage"` // "post-signing" | "pre-signing" | "marker" | "unknown"
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
	Unknown     int `json:"unknown"`
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
	if !report.LegacyAnchor.Valid {
		return fmt.Errorf("policy verify: legacy anchor invalid: %s", report.LegacyAnchor.Reason)
	}
	if report.Summary.Failed > 0 {
		return fmt.Errorf("policy verify: %d row(s) failed verification", report.Summary.Failed)
	}
	return nil
}

type legacyAnchorVerifyStatus struct {
	Valid          bool   `json:"valid"`
	ManifestSHA256 string `json:"manifest_sha256,omitempty"`
	LegacyCount    int    `json:"legacy_count"`
	Reason         string `json:"reason,omitempty"`
}

// policyVerifyReport is the top-level verify output.
type policyVerifyReport struct {
	Fingerprint  string                   `json:"fingerprint"`
	LegacyAnchor legacyAnchorVerifyStatus `json:"legacy_anchor"`
	Rows         []verifyRow              `json:"rows"`
	Summary      verifySummary            `json:"summary"`
}

// runPolicyVerify is shared by `policy verify` and `policy audit --verify`.
// It verifies the complete ledger and legacy anchor in one read snapshot.
// Filters affect presentation only; invalid rows are always reported.
func runPolicyVerify(db *sql.DB, root string, flags map[string]string) (policyVerifyReport, error) {
	pub, pubErr := authz.LoadPubKey(root)
	fp := ""
	if pubErr == nil {
		fp = authz.KeyFingerprint(pub)
	}

	var cutoff int64
	if v, ok := flags["since"]; ok {
		d, err := time.ParseDuration(v)
		if err != nil {
			return policyVerifyReport{}, fmt.Errorf("invalid --since: %w", err)
		}
		cutoff = time.Now().Add(-d).Unix()
	}

	ctx := context.Background()
	tx, err := db.BeginTx(ctx, &sql.TxOptions{ReadOnly: true})
	if err != nil {
		return policyVerifyReport{}, fmt.Errorf("begin verification snapshot: %w", err)
	}
	defer tx.Rollback()
	snapshot, err := loadAuthorizationSnapshot(ctx, tx)
	if err != nil {
		return policyVerifyReport{}, err
	}

	report := policyVerifyReport{Fingerprint: fp}
	report.LegacyAnchor = verifyLegacyAnchorSnapshot(root, pub, pubErr, snapshot)
	for _, record := range snapshot.Rows {
		r := record.Row
		vr := verifyRow{ID: r.ID, SigVersion: record.SigVersion, Fingerprint: fp}
		switch {
		case r.ID == authz.LegacyCutoverMarkerID:
			vr.Vintage = "marker"
			vr.Valid = r.OpType == "migration.signing-enabled" &&
				record.SigVersion == 1 && record.SignedAt.Valid &&
				verifyWithPub(pub, r, record.Signature)
			if !vr.Valid {
				vr.Reason = "fixed migration-033 marker is missing, malformed, or unverified"
			}
			report.Summary.Marker++
		case r.OpType == "migration.signing-enabled":
			vr.Vintage = "marker"
			vr.Valid = false
			vr.Reason = "unexpected duplicate signing marker id"
			report.Summary.Marker++
		case record.SigVersion == 0:
			vr.Vintage = "pre-signing"
			vr.Valid = report.LegacyAnchor.Valid && record.Signature == nil && !record.SignedAt.Valid
			if !vr.Valid {
				if record.Signature != nil || record.SignedAt.Valid {
					vr.Reason = "sig_version=0 row carries signing metadata"
				} else {
					vr.Reason = "row is not authenticated by the exact legacy manifest"
				}
			}
			report.Summary.PreSigning++
		case record.SigVersion == 1:
			vr.Vintage = "post-signing"
			vr.Valid = record.SignedAt.Valid && verifyWithPub(pub, r, record.Signature)
			if !vr.Valid {
				if pubErr != nil {
					vr.Reason = "pubkey not loaded: " + pubErr.Error()
				} else if record.Signature == nil {
					vr.Reason = "signature is NULL"
				} else if !record.SignedAt.Valid {
					vr.Reason = "signed_at is NULL"
				} else {
					vr.Reason = "signature invalid (tampering or wrong key)"
				}
			}
			report.Summary.PostSigning++
		default:
			vr.Vintage = "unknown"
			vr.Valid = false
			vr.Reason = fmt.Sprintf("unsupported sig_version %d", record.SigVersion)
			report.Summary.Unknown++
		}

		if vr.Valid {
			report.Summary.Passed++
		} else {
			report.Summary.Failed++
		}
		report.Summary.Total++
		if !vr.Valid || verifyRecordMatchesFilters(record, flags, cutoff) {
			report.Rows = append(report.Rows, vr)
		}
	}
	return report, nil
}

func verifyLegacyAnchorSnapshot(root string, pub []byte, pubErr error, snapshot authorizationSnapshot) legacyAnchorVerifyStatus {
	status := legacyAnchorVerifyStatus{}
	if snapshot.Schema != 36 {
		status.Reason = fmt.Sprintf("unsupported intercore schema %d; require 36", snapshot.Schema)
		return status
	}
	if pubErr != nil {
		status.Reason = "pubkey not loaded: " + pubErr.Error()
		return status
	}

	var marker authz.SignRow
	markerCount := 0
	legacy := make([]authz.SignRow, 0)
	for _, record := range snapshot.Rows {
		if record.Row.OpType == "migration.signing-enabled" {
			markerCount++
			if record.Row.ID == authz.LegacyCutoverMarkerID {
				marker = record.Row
				if record.SigVersion != 1 || !record.SignedAt.Valid || !verifyWithPub(pub, record.Row, record.Signature) {
					status.Reason = "fixed migration-033 marker is not a valid signed v1 row"
					return status
				}
			}
		}
		if record.SigVersion == 0 {
			if record.Signature != nil || record.SignedAt.Valid {
				status.Reason = fmt.Sprintf("legacy row %s carries signing metadata", record.Row.ID)
				return status
			}
			legacy = append(legacy, record.Row)
		}
	}
	if markerCount != 1 || marker.ID != authz.LegacyCutoverMarkerID {
		status.Reason = fmt.Sprintf("require exactly one fixed migration-033 marker; found %d", markerCount)
		return status
	}
	manifest, err := authz.LoadLegacyManifest(root)
	if err != nil {
		status.Reason = err.Error()
		return status
	}
	status.ManifestSHA256 = manifest.ManifestSHA256
	status.LegacyCount = manifest.LegacyCount
	if err := authz.VerifyLegacyManifest(pub, manifest, marker, legacy); err != nil {
		status.Reason = err.Error()
		return status
	}
	status.Valid = true
	return status
}

func verifyRecordMatchesFilters(record authorizationSnapshotRow, flags map[string]string, cutoff int64) bool {
	if cutoff != 0 && record.Row.CreatedAt < cutoff {
		return false
	}
	if op := flags["op"]; op != "" && record.Row.OpType != op {
		return false
	}
	if agent := flags["agent"]; agent != "" && record.Row.AgentID != agent {
		return false
	}
	if bead := flags["bead"]; bead != "" && record.Row.BeadID != bead {
		return false
	}
	return true
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
	if !report.LegacyAnchor.Valid {
		return fmt.Errorf("policy audit --verify: legacy anchor invalid: %s", report.LegacyAnchor.Reason)
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
	if schema != 36 {
		return fmt.Errorf("policy doctor: unsupported intercore schema %d; require 36", schema)
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
	verifyReport, err := runPolicyVerify(db, root, map[string]string{})
	if err != nil {
		return fmt.Errorf("policy doctor: verify authorization ledger: %w", err)
	}
	if !verifyReport.LegacyAnchor.Valid {
		return fmt.Errorf("policy doctor: legacy anchor invalid: %s", verifyReport.LegacyAnchor.Reason)
	}
	if verifyReport.Summary.Failed > 0 {
		return fmt.Errorf("policy doctor: %d authorization row(s) failed verification", verifyReport.Summary.Failed)
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
		"status":          "ok",
		"role":            role,
		"project_root":    root,
		"database":        dbPath,
		"schema":          schema,
		"fingerprint":     fingerprint,
		"manifest_sha256": verifyReport.LegacyAnchor.ManifestSHA256,
	})
}
