package main

import (
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestWorkRoutingIncidentReplay(t *testing.T) {
	base := filepath.Join("testdata", "work-incidents")
	data, err := os.ReadFile(filepath.Join(base, "manifest.json"))
	if err != nil {
		t.Fatal(err)
	}
	var manifest struct {
		Fixtures []struct{ Fixture, SHA256 string }
	}
	if err := json.Unmarshal(data, &manifest); err != nil {
		t.Fatal(err)
	}
	if len(manifest.Fixtures) != 2 {
		t.Fatal("expected two independent routing briefs")
	}
	briefs := make([]string, 0, 2)
	for _, source := range manifest.Fixtures {
		data, err := os.ReadFile(filepath.Join(base, source.Fixture))
		if err != nil {
			t.Fatal(err)
		}
		if fmt.Sprintf("%x", sha256.Sum256(data)) != source.SHA256 {
			t.Fatal("incident source changed without provenance update")
		}
		briefs = append(briefs, string(data))
	}
	for i, query := range briefs {
		other := 1 - i
		rows, _ := json.Marshal([]map[string]string{{"id": "related-1", "title": []string{"Adaptive calibration", "Eleven-project capacity preparation"}[other], "status": "open", "assignee": "existing-owner", "description": briefs[other]}})
		fixture := newWorkFixture(t, string(rows), `[]`)
		out, stderr, err := runWorkForTest(t, "discover", "--registry="+fixture.registry, "--authority=local-fixture", "--text="+query, "--json")
		if err != nil {
			t.Fatalf("replay: %v %s", err, stderr)
		}
		var result workResult
		if err := json.Unmarshal([]byte(out), &result); err != nil {
			t.Fatal(err)
		}
		if len(result.Candidates) != 1 || result.Candidates[0].Score <= 0 || result.Candidates[0].Classification != "ambiguous_shared_evidence_candidate" {
			t.Fatalf("related initiative absent or silently merged: %+v", result.Candidates)
		}
		if result.ImplementationAllowed || result.Candidates[0].BeadsAssignee != "existing-owner" {
			t.Fatal("discovery altered ownership or admitted implementation")
		}
	}
}

func TestWorkRealBeadsProjectIdentity(t *testing.T) {
	fixture := newWorkFixture(t, `[]`, `[]`)
	for root, id := range map[string]string{fixture.rootA: workUUIDA, fixture.rootB: workUUIDB} {
		data := `{"database":"dolt","backend":"dolt","dolt_mode":"embedded","dolt_database":"fixture","project_id":"` + id + `"}`
		if err := os.WriteFile(filepath.Join(root, ".beads", "metadata.json"), []byte(data), 0600); err != nil {
			t.Fatal(err)
		}
	}
	_, stderr, err := runWorkForTest(t, "discover", "--registry="+fixture.registry, "--authority=local-fixture")
	if err != nil {
		t.Fatalf("real Beads metadata rejected: %v; %s", err, stderr)
	}
}

func TestWorkExactReferencePreservesBeadCase(t *testing.T) {
	registry := workRegistry{Trackers: []workTracker{{TrackerUUID: workUUIDA}}}
	beads := map[string][]workBead{workUUIDA: {{ID: "Case-1", Status: "in_progress"}}}
	for _, tc := range []struct{ id, classification string }{{"Case-1", "exact_tracker_task_reference"}, {"case-1", "active_work_unranked"}} {
		candidates := discoverWorkCandidates(registry, beads, workUUIDA+":"+tc.id)
		if len(candidates) != 1 || candidates[0].Classification != tc.classification {
			t.Fatalf("case-sensitive identity: %+v", candidates)
		}
	}
}

func TestWorkChildEnvironmentAndDirectoryArePinned(t *testing.T) {
	root := t.TempDir()
	bin := filepath.Join(t.TempDir(), "bd")
	script := "#!/bin/sh\nif [ \"${BEADS_DIR+x}${BEADS_DB+x}${BEADS_DOLT_PASSWORD+x}${DOLT_ROOT_PATH+x}${XDG_CONFIG_HOME+x}\" != \"\" ]; then printf contaminated; else printf isolated; fi > \"$3/environment\"\n/bin/pwd > \"$3/cwd\"\nprintf '[]'\n"
	if err := os.WriteFile(bin, []byte(script), 0700); err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{"BEADS_DIR", "BEADS_DB", "BEADS_DOLT_PASSWORD", "DOLT_ROOT_PATH", "XDG_CONFIG_HOME"} {
		t.Setenv(name, "synthetic-selector")
	}
	_, err := readTrackerBeads(workTracker{TrackerUUID: workUUIDA, Root: root}, workDependencies{bdPath: bin, timeout: 2 * time.Second, maxOutputByte: 1024})
	if err != nil {
		t.Fatal(err)
	}
	environment, _ := os.ReadFile(filepath.Join(root, "environment"))
	cwd, _ := os.ReadFile(filepath.Join(root, "cwd"))
	wantRoot, _ := filepath.EvalSymlinks(root)
	if string(environment) != "isolated" || strings.TrimSpace(string(cwd)) != wantRoot {
		t.Fatalf("authority process selection not pinned: isolation=%s cwd=%q", environment, cwd)
	}
}

func TestWorkUnknownTrackerIsMissingMapping(t *testing.T) {
	fixture := newWorkFixture(t, `[]`, `[]`)
	_, stderr, err := runWorkForTest(t, "status", "--registry="+fixture.registry, "--authority=local-fixture", "--task=33333333-3333-4333-8333-333333333333:a-1")
	if err == nil || !strings.Contains(stderr, "tracker mapping missing") {
		t.Fatalf("missing tracker mapping obscured: %v %s", err, stderr)
	}
	if _, err := os.Stat(fixture.argvLog); !os.IsNotExist(err) {
		t.Fatal("authority queried despite missing tracker mapping")
	}
}

func TestWorkRecordOwnerIsNotClaimAssignee(t *testing.T) {
	for _, assignee := range []string{"", "binding-123"} {
		t.Run("assignee="+assignee, func(t *testing.T) {
			fixture := newWorkFixture(t, `[{"id":"a-1","title":"Owned record","status":"open","owner":"record-owner@example.invalid","assignee":"`+assignee+`"}]`, `[]`)
			out, stderr, err := runWorkForTest(t, "status", "--registry="+fixture.registry, "--authority=local-fixture", "--task="+workUUIDA+":a-1", "--json")
			if err != nil {
				t.Fatalf("distinct record owner rejected: %v; %s", err, stderr)
			}
			var result workResult
			if err := json.Unmarshal([]byte(out), &result); err != nil {
				t.Fatal(err)
			}
			if result.Task == nil || result.Task.BeadsAssignee != assignee {
				t.Fatalf("record owner became claimant: %s", out)
			}
		})
	}
}

func TestWorkInheritedOutputPipeIsBounded(t *testing.T) {
	bin := filepath.Join(t.TempDir(), "bd")
	if err := os.WriteFile(bin, []byte("#!/bin/sh\n(/bin/sleep 4; printf late) &\nprintf ready > \"$3/started\"\nprintf '[]'\n"), 0700); err != nil {
		t.Fatal(err)
	}
	root := t.TempDir()
	started := time.Now()
	_, err := readTrackerBeads(workTracker{TrackerUUID: workUUIDA, Root: root}, workDependencies{bdPath: bin, timeout: 2 * time.Second, maxOutputByte: 1024})
	t.Logf("elapsed=%s error=%v", time.Since(started), err)
	if _, statErr := os.Stat(filepath.Join(root, "started")); statErr != nil {
		t.Fatalf("helper did not spawn descendant: %v", statErr)
	}
	if elapsed := time.Since(started); elapsed > 2*time.Second {
		t.Fatalf("inherited pipe exceeded deadline: %s, err=%v", elapsed, err)
	}
	if err == nil {
		t.Fatal("incomplete helper lifecycle reported as successful authority read")
	}
}
