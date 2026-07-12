package main

import (
	"database/sql"
	"encoding/json"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
	"time"

	"github.com/mistakeknot/intercore/pkg/authz"
)

type legacyAnchorProposalForTest struct {
	Status              string   `json:"status"`
	Schema              int      `json:"schema"`
	LegacyCount         int      `json:"legacy_count"`
	LegacyIDs           []string `json:"legacy_ids"`
	ManifestSHA256      string   `json:"manifest_sha256"`
	PublicKeySHA256     string   `json:"public_key_sha256"`
	CutoverMarkerSHA256 string   `json:"cutover_marker_sha256"`
}

func TestPolicyAnchorLegacy_InspectAndCreateExactlyOnce(t *testing.T) {
	root := setupLegacyProposalDomain(t, 2)
	proposal := inspectLegacyAnchor(t, root)
	if proposal.Status != "proposal" || proposal.Schema != 36 {
		t.Fatalf("proposal identity = %+v", proposal)
	}
	if proposal.LegacyCount != 2 || len(proposal.LegacyIDs) != 2 {
		t.Fatalf("proposal membership = %+v", proposal)
	}
	if proposal.LegacyIDs[0] != "legacy-00" || proposal.LegacyIDs[1] != "legacy-01" {
		t.Fatalf("proposal IDs not stable/sorted: %v", proposal.LegacyIDs)
	}
	for name, value := range map[string]string{
		"manifest":       proposal.ManifestSHA256,
		"public key":     proposal.PublicKeySHA256,
		"cutover marker": proposal.CutoverMarkerSHA256,
	} {
		if len(value) != 64 {
			t.Fatalf("%s digest length = %d", name, len(value))
		}
	}

	out, err := captureStdoutAuthz(t, func() error {
		return cmdPolicyAnchorLegacy([]string{
			"--project-root=" + root,
			"--expect-count=2",
			"--expect-digest=" + proposal.ManifestSHA256,
		})
	})
	if err != nil {
		t.Fatalf("anchor-legacy: %v (out=%s)", err, out)
	}
	manifest, err := authz.LoadLegacyManifest(root)
	if err != nil {
		t.Fatalf("LoadLegacyManifest: %v", err)
	}
	if manifest.ManifestSHA256 != proposal.ManifestSHA256 || manifest.LegacyCount != 2 {
		t.Fatalf("stored manifest = %+v", manifest)
	}
	if _, err := captureStdoutAuthz(t, func() error {
		return cmdPolicyAnchorLegacy([]string{
			"--project-root=" + root,
			"--expect-count=2",
			"--expect-digest=" + proposal.ManifestSHA256,
		})
	}); err == nil {
		t.Fatal("anchor-legacy overwrote an existing manifest")
	}
}

func TestPolicyAnchorLegacy_RequiresReviewedExpectationAndSigner(t *testing.T) {
	t.Run("missing expectation", func(t *testing.T) {
		root := setupLegacyProposalDomain(t, 1)
		if _, err := captureStdoutAuthz(t, func() error {
			return cmdPolicyAnchorLegacy([]string{"--project-root=" + root})
		}); err == nil {
			t.Fatal("nonempty legacy set anchored without an expectation")
		}
	})
	t.Run("wrong count", func(t *testing.T) {
		root := setupLegacyProposalDomain(t, 1)
		proposal := inspectLegacyAnchor(t, root)
		if _, err := captureStdoutAuthz(t, func() error {
			return cmdPolicyAnchorLegacy([]string{
				"--project-root=" + root,
				"--expect-count=2",
				"--expect-digest=" + proposal.ManifestSHA256,
			})
		}); err == nil {
			t.Fatal("legacy set anchored with the wrong expected count")
		}
	})
	t.Run("wrong digest", func(t *testing.T) {
		root := setupLegacyProposalDomain(t, 1)
		proposal := inspectLegacyAnchor(t, root)
		if _, err := captureStdoutAuthz(t, func() error {
			return cmdPolicyAnchorLegacy([]string{
				"--project-root=" + root,
				"--expect-count=1",
				"--expect-digest=" + strings.Repeat("0", 64),
			})
		}); err == nil || proposal.ManifestSHA256 == strings.Repeat("0", 64) {
			t.Fatal("legacy set anchored with the wrong expected digest")
		}
	})
	t.Run("verifier only", func(t *testing.T) {
		root := setupLegacyProposalDomain(t, 1)
		proposal := inspectLegacyAnchor(t, root)
		priv, _ := authz.KeyPaths(root)
		if err := os.Remove(priv); err != nil {
			t.Fatal(err)
		}
		if _, err := captureStdoutAuthz(t, func() error {
			return cmdPolicyAnchorLegacy([]string{
				"--project-root=" + root,
				"--expect-count=1",
				"--expect-digest=" + proposal.ManifestSHA256,
			})
		}); err == nil {
			t.Fatal("verifier-only host created a manifest")
		}
	})
}

func TestPolicyAnchorLegacy_ExplicitEmptyBootstrap(t *testing.T) {
	root := setupLegacyProposalDomain(t, 0)
	if _, err := captureStdoutAuthz(t, func() error {
		return cmdPolicyAnchorLegacy([]string{"--project-root=" + root, "--expect-empty"})
	}); err != nil {
		t.Fatalf("anchor empty legacy set: %v", err)
	}
	manifest, err := authz.LoadLegacyManifest(root)
	if err != nil {
		t.Fatal(err)
	}
	if manifest.LegacyCount != 0 || manifest.LegacyRows == nil {
		t.Fatalf("empty manifest = %+v", manifest)
	}
}

func TestPolicyVerify_RejectsDowngradeOutsideDisplayFilter(t *testing.T) {
	root := setupLegacyAnchoredDomain(t, 2)
	signedID := insertSignableRow(t, root, "downgrade-target", "bead-close")
	if _, err := captureStdoutAuthz(t, func() error {
		return cmdPolicySign([]string{"--project-root=" + root})
	}); err != nil {
		t.Fatalf("sign target row: %v", err)
	}
	if _, err := captureStdoutAuthz(t, func() error {
		return cmdPolicyVerify([]string{"--project-root=" + root})
	}); err != nil {
		t.Fatalf("clean anchored verify: %v", err)
	}

	db := openLegacyTestDB(t, root)
	if _, err := db.Exec(`UPDATE authorizations SET sig_version=0 WHERE id=?`, signedID); err != nil {
		t.Fatal(err)
	}
	if _, err := captureStdoutAuthz(t, func() error {
		return cmdPolicyVerify([]string{
			"--project-root=" + root,
			"--op=operation-that-does-not-match",
		})
	}); err == nil {
		t.Fatal("filtered verify accepted a signed row downgraded to sig_version=0")
	}
}

func TestPolicyVerify_RejectsLegacyMembershipTampering(t *testing.T) {
	cases := []struct {
		name   string
		tamper func(*testing.T, *sql.DB)
	}{
		{name: "mutation", tamper: func(t *testing.T, db *sql.DB) {
			_, err := db.Exec(`UPDATE authorizations SET target='changed' WHERE id='legacy-00'`)
			if err != nil {
				t.Fatal(err)
			}
		}},
		{name: "insertion", tamper: func(t *testing.T, db *sql.DB) {
			_, err := db.Exec(`INSERT INTO authorizations (id,op_type,target,agent_id,mode,created_at,sig_version) VALUES ('legacy-extra','bead-close','x','old','auto',1,0)`)
			if err != nil {
				t.Fatal(err)
			}
		}},
		{name: "deletion", tamper: func(t *testing.T, db *sql.DB) {
			_, err := db.Exec(`DELETE FROM authorizations WHERE id='legacy-00'`)
			if err != nil {
				t.Fatal(err)
			}
		}},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			root := setupLegacyAnchoredDomain(t, 2)
			db := openLegacyTestDB(t, root)
			tc.tamper(t, db)
			if _, err := captureStdoutAuthz(t, func() error {
				return cmdPolicyVerify([]string{"--project-root=" + root})
			}); err == nil {
				t.Fatal("verify accepted altered legacy membership")
			}
		})
	}
}

func TestPolicyVerify_RejectsMissingManifestMarkerSpoofAndUnknownVersion(t *testing.T) {
	t.Run("missing manifest", func(t *testing.T) {
		root := setupLegacyAnchoredDomain(t, 1)
		path := authz.LegacyManifestPath(root)
		if err := os.Chmod(path, 0o644); err != nil {
			t.Fatal(err)
		}
		if err := os.Remove(path); err != nil {
			t.Fatal(err)
		}
		if _, err := captureStdoutAuthz(t, func() error {
			return cmdPolicyVerify([]string{"--project-root=" + root})
		}); err == nil {
			t.Fatal("verify accepted a missing manifest")
		}
	})
	t.Run("duplicate marker identity", func(t *testing.T) {
		root := setupLegacyAnchoredDomain(t, 1)
		db := openLegacyTestDB(t, root)
		if _, err := db.Exec(`INSERT INTO authorizations (id,op_type,target,agent_id,mode,created_at,sig_version) VALUES ('forged-marker','migration.signing-enabled','authorizations','system:migration-033','auto',1,1)`); err != nil {
			t.Fatal(err)
		}
		if _, err := captureStdoutAuthz(t, func() error {
			return cmdPolicyVerify([]string{"--project-root=" + root})
		}); err == nil {
			t.Fatal("verify accepted a second cutover marker")
		}
	})
	t.Run("unknown signature version", func(t *testing.T) {
		root := setupLegacyAnchoredDomain(t, 1)
		db := openLegacyTestDB(t, root)
		if _, err := db.Exec(`UPDATE authorizations SET sig_version=2 WHERE id='legacy-00'`); err != nil {
			t.Fatal(err)
		}
		if _, err := captureStdoutAuthz(t, func() error {
			return cmdPolicyVerify([]string{"--project-root=" + root})
		}); err == nil {
			t.Fatal("verify accepted an unknown signature version")
		}
	})
}

func setupLegacyProposalDomain(t *testing.T, legacyCount int) string {
	t.Helper()
	root := setupSigningSandbox(t)
	db := openLegacyTestDB(t, root)
	if _, err := db.Exec(`PRAGMA user_version=36`); err != nil {
		t.Fatal(err)
	}
	for i := 0; i < legacyCount; i++ {
		id := "legacy-" + strconv.FormatInt(int64(i), 10)
		if i < 10 {
			id = "legacy-0" + strconv.Itoa(i)
		}
		if _, err := db.Exec(`
			INSERT INTO authorizations (id,op_type,target,agent_id,mode,created_at,sig_version)
			VALUES (?, 'bead-close', ?, 'legacy-agent', 'auto', ?, 0)`,
			id, "target-"+strconv.Itoa(i), time.Now().Add(-time.Duration(i+1)*time.Hour).Unix(),
		); err != nil {
			t.Fatal(err)
		}
	}
	if _, err := captureStdoutAuthz(t, func() error {
		return cmdPolicyInitKey([]string{"--project-root=" + root})
	}); err != nil {
		t.Fatalf("init key: %v", err)
	}
	if _, err := captureStdoutAuthz(t, func() error {
		return cmdPolicySign([]string{"--project-root=" + root})
	}); err != nil {
		t.Fatalf("sign cutover marker: %v", err)
	}
	return root
}

func setupLegacyAnchoredDomain(t *testing.T, legacyCount int) string {
	t.Helper()
	root := setupLegacyProposalDomain(t, legacyCount)
	proposal := inspectLegacyAnchor(t, root)
	args := []string{"--project-root=" + root}
	if legacyCount == 0 {
		args = append(args, "--expect-empty")
	} else {
		args = append(args,
			"--expect-count="+strconv.Itoa(proposal.LegacyCount),
			"--expect-digest="+proposal.ManifestSHA256,
		)
	}
	if _, err := captureStdoutAuthz(t, func() error { return cmdPolicyAnchorLegacy(args) }); err != nil {
		t.Fatalf("anchor legacy: %v", err)
	}
	return root
}

func inspectLegacyAnchor(t *testing.T, root string) legacyAnchorProposalForTest {
	t.Helper()
	out, err := captureStdoutAuthz(t, func() error {
		return cmdPolicyAnchorLegacy([]string{"--project-root=" + root, "--inspect"})
	})
	if err != nil {
		t.Fatalf("anchor inspect: %v (out=%s)", err, out)
	}
	var proposal legacyAnchorProposalForTest
	if err := json.Unmarshal(out, &proposal); err != nil {
		t.Fatalf("decode proposal: %v (out=%s)", err, out)
	}
	return proposal
}

func openLegacyTestDB(t *testing.T, root string) *sql.DB {
	t.Helper()
	db, err := sql.Open("sqlite", filepath.Join(root, ".clavain", "intercore.db"))
	if err != nil {
		t.Fatal(err)
	}
	db.SetMaxOpenConns(1)
	t.Cleanup(func() { _ = db.Close() })
	return db
}
