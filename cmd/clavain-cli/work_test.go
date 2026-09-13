package main

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

const (
	workUUIDA = "11111111-1111-4111-8111-111111111111"
	workUUIDB = "22222222-2222-4222-8222-222222222222"
)

type workFixture struct {
	registry string
	rootA    string
	rootB    string
	argvLog  string
}

func newWorkFixture(t *testing.T, outputA, outputB string) workFixture {
	t.Helper()
	base, err := filepath.EvalSymlinks(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	rootA := filepath.Join(base, "tracker-a")
	rootB := filepath.Join(base, "tracker-b")
	for _, item := range []struct {
		root   string
		uuid   string
		output string
	}{
		{rootA, workUUIDA, outputA},
		{rootB, workUUIDB, outputB},
	} {
		if err := os.MkdirAll(filepath.Join(item.root, ".beads"), 0o755); err != nil {
			t.Fatal(err)
		}
		metadata := `{"project_id":"` + item.uuid + `"}`
		if err := os.WriteFile(filepath.Join(item.root, ".beads", "metadata.json"), []byte(metadata), 0o644); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(filepath.Join(item.root, ".fixture-output.json"), []byte(item.output), 0o644); err != nil {
			t.Fatal(err)
		}
	}

	binDir := filepath.Join(base, "bin")
	if err := os.Mkdir(binDir, 0o755); err != nil {
		t.Fatal(err)
	}
	argvLog := filepath.Join(base, "argv.log")
	// This executable is intentionally a process-level fake: production still
	// has to build a fixed argv and cannot pass task text through a shell.
	script := `#!/bin/sh
base="${0%/*}/.."
argv_log="$base/argv.log"
: > "$argv_log"
for arg in "$@"; do
  printf '%s\n' "$arg" >> "$argv_log"
done
if [ -f "$base/sleep" ]; then
  read -r delay < "$base/sleep"
  /bin/sleep "$delay"
fi
if [ -f "$base/exit" ]; then
  read -r exit_code < "$base/exit"
  printf '%s\n' 'fixture authority failure' >&2
  exit "$exit_code"
fi
root=''
previous=''
for arg in "$@"; do
  if [ "$previous" = '--directory' ]; then root="$arg"; fi
  previous="$arg"
done
exec /bin/cat "$root/.fixture-output.json"
`
	if err := os.WriteFile(filepath.Join(binDir, "bd"), []byte(script), 0o755); err != nil {
		t.Fatal(err)
	}
	t.Setenv("PATH", binDir+string(os.PathListSeparator)+os.Getenv("PATH"))

	registryPath := filepath.Join(base, "registry.json")
	registry := map[string]any{
		"version": 1,
		"authority_endpoint": map[string]any{
			"kind":     "local",
			"identity": "local-fixture",
		},
		"trackers": []any{
			map[string]any{
				"tracker_uuid": workUUIDA,
				"root":         rootA,
				"repositories": []any{map[string]any{"alias": "alpha", "worktree": rootA}},
			},
			map[string]any{
				"tracker_uuid": workUUIDB,
				"root":         rootB,
				"repositories": []any{map[string]any{"alias": "beta", "worktree": rootB}},
			},
		},
	}
	data, err := json.Marshal(registry)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(registryPath, data, 0o644); err != nil {
		t.Fatal(err)
	}
	return workFixture{registry: registryPath, rootA: rootA, rootB: rootB, argvLog: argvLog}
}

func runWorkForTest(t *testing.T, args ...string) (string, string, error) {
	t.Helper()
	var stdout, stderr bytes.Buffer
	err := runWorkCLI(args, &stdout, &stderr, workDependencies{
		bdPath:        "bd",
		timeout:       2 * time.Second,
		maxOutputByte: 8 << 10,
	})
	return stdout.String(), stderr.String(), err
}

func TestWorkRegistryRequiredAndStrict(t *testing.T) {
	_, stderr, err := runWorkForTest(t, "discover", "--authority=local-fixture")
	if err == nil || !strings.Contains(stderr, "--registry is required") {
		t.Fatalf("missing registry: err=%v stderr=%q", err, stderr)
	}

	base := t.TempDir()
	malformed := filepath.Join(base, "malformed.json")
	if err := os.WriteFile(malformed, []byte(`{"version":1,`), 0o644); err != nil {
		t.Fatal(err)
	}
	_, stderr, err = runWorkForTest(t, "discover", "--registry="+malformed, "--authority=local-fixture")
	if err == nil || !strings.Contains(stderr, "malformed registry") {
		t.Fatalf("malformed registry: err=%v stderr=%q", err, stderr)
	}

	duplicate := filepath.Join(base, "duplicate.json")
	if err := os.WriteFile(duplicate, []byte(`{"version":1,"version":1,"authority_endpoint":{"kind":"local","identity":"x"},"trackers":[]}`), 0o644); err != nil {
		t.Fatal(err)
	}
	_, stderr, err = runWorkForTest(t, "discover", "--registry="+duplicate, "--authority=x")
	if err == nil || !strings.Contains(stderr, "duplicate JSON key") {
		t.Fatalf("duplicate registry key: err=%v stderr=%q", err, stderr)
	}

	unknown := filepath.Join(base, "unknown.json")
	if err := os.WriteFile(unknown, []byte(`{"version":1,"authority_endpoint":{"kind":"local","identity":"x"},"trackers":[],"activate":true}`), 0o644); err != nil {
		t.Fatal(err)
	}
	_, stderr, err = runWorkForTest(t, "discover", "--registry="+unknown, "--authority=x")
	if err == nil || !strings.Contains(stderr, "unknown field") {
		t.Fatalf("unknown registry field: err=%v stderr=%q", err, stderr)
	}
}

func TestWorkRegistryRejectsDuplicateAndUnsafeMappings(t *testing.T) {
	fixture := newWorkFixture(t, `[]`, `[]`)
	data, err := os.ReadFile(fixture.registry)
	if err != nil {
		t.Fatal(err)
	}
	var raw map[string]any
	if err := json.Unmarshal(data, &raw); err != nil {
		t.Fatal(err)
	}
	trackers := raw["trackers"].([]any)
	trackers[1].(map[string]any)["tracker_uuid"] = workUUIDA
	duplicatePath := filepath.Join(t.TempDir(), "duplicate-tracker.json")
	encoded, _ := json.Marshal(raw)
	if err := os.WriteFile(duplicatePath, encoded, 0o644); err != nil {
		t.Fatal(err)
	}
	_, stderr, err := runWorkForTest(t, "discover", "--registry="+duplicatePath, "--authority=local-fixture")
	if err == nil || !strings.Contains(stderr, "duplicate tracker_uuid") {
		t.Fatalf("duplicate tracker: err=%v stderr=%q", err, stderr)
	}

	trackers[1].(map[string]any)["tracker_uuid"] = workUUIDB
	trackers[1].(map[string]any)["root"] = "relative/root"
	unsafePath := filepath.Join(t.TempDir(), "unsafe-root.json")
	encoded, _ = json.Marshal(raw)
	if err := os.WriteFile(unsafePath, encoded, 0o644); err != nil {
		t.Fatal(err)
	}
	_, stderr, err = runWorkForTest(t, "discover", "--registry="+unsafePath, "--authority=local-fixture")
	if err == nil || !strings.Contains(stderr, "absolute, clean") {
		t.Fatalf("relative root: err=%v stderr=%q", err, stderr)
	}

	trackers[1].(map[string]any)["root"] = fixture.rootB
	trackers[1].(map[string]any)["repositories"] = []any{map[string]any{"alias": "alpha", "worktree": fixture.rootB}}
	ambiguousPath := filepath.Join(t.TempDir(), "ambiguous-alias.json")
	encoded, _ = json.Marshal(raw)
	if err := os.WriteFile(ambiguousPath, encoded, 0o644); err != nil {
		t.Fatal(err)
	}
	_, stderr, err = runWorkForTest(t, "discover", "--registry="+ambiguousPath, "--authority=local-fixture")
	if err == nil || !strings.Contains(stderr, "duplicate repository alias") {
		t.Fatalf("ambiguous alias: err=%v stderr=%q", err, stderr)
	}
}

func TestWorkRejectsReplicaUUIDMismatchBeforeBD(t *testing.T) {
	fixture := newWorkFixture(t, `[]`, `[]`)
	if err := os.WriteFile(filepath.Join(fixture.rootA, ".beads", "metadata.json"), []byte(`{"project_id":"`+workUUIDB+`"}`), 0o644); err != nil {
		t.Fatal(err)
	}
	_, stderr, err := runWorkForTest(t, "discover", "--registry="+fixture.registry, "--authority=local-fixture")
	if err == nil || !strings.Contains(stderr, "tracker UUID mismatch") {
		t.Fatalf("UUID mismatch: err=%v stderr=%q", err, stderr)
	}
	if _, statErr := os.Stat(fixture.argvLog); !os.IsNotExist(statErr) {
		t.Fatalf("bd ran before UUID validation; argv log stat=%v", statErr)
	}
}

func TestWorkRegistryMissingMappingBlocks(t *testing.T) {
	fixture := newWorkFixture(t, `[]`, `[]`)
	data, err := os.ReadFile(fixture.registry)
	if err != nil {
		t.Fatal(err)
	}
	var raw map[string]any
	if err := json.Unmarshal(data, &raw); err != nil {
		t.Fatal(err)
	}
	trackers := raw["trackers"].([]any)
	trackers[0].(map[string]any)["repositories"] = []any{}
	path := filepath.Join(t.TempDir(), "missing-mapping.json")
	encoded, _ := json.Marshal(raw)
	if err := os.WriteFile(path, encoded, 0o644); err != nil {
		t.Fatal(err)
	}
	_, stderr, err := runWorkForTest(t, "discover", "--registry="+path, "--authority=local-fixture")
	if err == nil || !strings.Contains(stderr, "requires at least one repository mapping") {
		t.Fatalf("missing mapping: err=%v stderr=%q", err, stderr)
	}
}

func TestWorkStatusUsesQualifiedIdentityAcrossTrackers(t *testing.T) {
	fixture := newWorkFixture(t,
		`[{"id":"shared-7","title":"Alpha task","description":"alpha","status":"open","assignee":"alice","labels":[]}]`,
		`[{"id":"shared-7","title":"Beta task","description":"beta","status":"in_progress","assignee":"bob","labels":[]}]`)
	stdout, stderr, err := runWorkForTest(t, "status", "--registry="+fixture.registry, "--authority=local-fixture", "--task="+workUUIDB+":shared-7", "--json")
	if err != nil {
		t.Fatalf("status: %v stderr=%q", err, stderr)
	}
	if !strings.Contains(stdout, `"title": "Beta task"`) || strings.Contains(stdout, `"title": "Alpha task"`) {
		t.Fatalf("status did not preserve tracker identity: %s", stdout)
	}
	for _, want := range []string{`"beads_assignee": "bob"`, `"beads_status": "in_progress"`, `"attached_sessions": "unknown"`, `"implementation_allowed": false`} {
		if !strings.Contains(stdout, want) {
			t.Errorf("status missing %s: %s", want, stdout)
		}
	}

	_, stderr, err = runWorkForTest(t, "status", "--registry="+fixture.registry, "--authority=local-fixture", "--task=shared-7")
	if err == nil || !strings.Contains(stderr, "trackerUUID:BeadID") {
		t.Fatalf("unqualified task: err=%v stderr=%q", err, stderr)
	}
	_, stderr, err = runWorkForTest(t, "status", "--registry="+fixture.registry, "--authority=local-fixture", "--task="+workUUIDB+":missing")
	if err == nil || !strings.Contains(stderr, "authoritative task not found") {
		t.Fatalf("unknown task: err=%v stderr=%q", err, stderr)
	}
}

func TestWorkAuthorityInvocationIsReadonlyFixedArgvAndDataIsNotShell(t *testing.T) {
	marker := filepath.Join(t.TempDir(), "must-not-exist")
	description := "literal $(touch " + marker + ") ; `touch " + marker + "`"
	output, _ := json.Marshal([]map[string]any{{
		"id": "alpha-1", "title": "Parser", "description": description,
		"status": "open", "assignee": "", "labels": []string{"parser"},
	}})
	fixture := newWorkFixture(t, string(output), `[]`)
	stdout, stderr, err := runWorkForTest(t, "discover", "--registry="+fixture.registry, "--authority=local-fixture", "--text=parser", "--json")
	if err != nil {
		t.Fatalf("discover: %v stderr=%q", err, stderr)
	}
	if !strings.Contains(stdout, "alpha-1") {
		t.Fatalf("candidate missing: %s", stdout)
	}
	if _, err := os.Stat(marker); !os.IsNotExist(err) {
		t.Fatalf("task description was executed as shell data: %v", err)
	}
	argv, err := os.ReadFile(fixture.argvLog)
	if err != nil {
		t.Fatal(err)
	}
	want := strings.Join([]string{"--readonly", "--directory", fixture.rootB, "list", "--all", "--limit", "0", "--include-gates", "--json", ""}, "\n")
	if string(argv) != want {
		t.Fatalf("bd argv = %q, want %q", argv, want)
	}
}

func TestWorkDiscoverUsesPlanAndRetainsAllActiveWork(t *testing.T) {
	fixture := newWorkFixture(t,
		`[
 {"id":"alpha-1","title":"Canonical ownership","objective":"Bind exact tracker identity","description":"registry mapping","status":"open","assignee":"","labels":["ownership"],"artifact_refs":["docs/plans/ownership.md"]},
 {"id":"alpha-2","title":"Unrelated active","description":"different topic","status":"in_progress","assignee":"agent-a","labels":[]},
 {"id":"alpha-3","title":"Unrelated open","description":"different topic","status":"open","assignee":"","labels":[]}
]`, `[]`)
	plan := filepath.Join(t.TempDir(), "PLAN.md")
	if err := os.WriteFile(plan, []byte("Use exact tracker identity from docs/plans/ownership.md"), 0o644); err != nil {
		t.Fatal(err)
	}
	stdout, stderr, err := runWorkForTest(t, "discover", "--registry="+fixture.registry, "--authority=local-fixture", "--plan="+plan, "--json")
	if err != nil {
		t.Fatalf("discover: %v stderr=%q", err, stderr)
	}
	if !strings.Contains(stdout, "alpha-1") || !strings.Contains(stdout, "alpha-2") || strings.Contains(stdout, "alpha-3") {
		t.Fatalf("ranking/active retention mismatch: %s", stdout)
	}
	for _, want := range []string{`"classification": "ambiguous_shared_evidence_candidate"`, `"implementation_allowed": false`, `"binding_authority": "not_live"`, `"coverage": "none"`} {
		if !strings.Contains(stdout, want) {
			t.Errorf("discover missing %s: %s", want, stdout)
		}
	}
}

func TestWorkExactReferenceIsEvidenceNotImplementationAuthority(t *testing.T) {
	fixture := newWorkFixture(t, `[{"id":"alpha-1","title":"Ownership","description":"registry","status":"open","assignee":"","labels":[]}]`, `[]`)
	stdout, stderr, err := runWorkForTest(t, "discover", "--registry="+fixture.registry, "--authority=local-fixture", "--text="+workUUIDA+":alpha-1", "--json")
	if err != nil {
		t.Fatalf("discover: %v stderr=%q", err, stderr)
	}
	if !strings.Contains(stdout, `"classification": "exact_tracker_task_reference"`) || !strings.Contains(stdout, `"implementation_allowed": false`) {
		t.Fatalf("exact evidence incorrectly classified: %s", stdout)
	}
}

func TestWorkAuthorityFailuresAreNotEmptySuccess(t *testing.T) {
	t.Run("malformed", func(t *testing.T) {
		fixture := newWorkFixture(t, `{bad`, `[]`)
		_, stderr, err := runWorkForTest(t, "discover", "--registry="+fixture.registry, "--authority=local-fixture", "--json")
		if err == nil || !strings.Contains(stderr, `"authority_status": "unavailable"`) || !strings.Contains(stderr, "malformed authority output") {
			t.Fatalf("malformed output: err=%v stderr=%q", err, stderr)
		}
	})
	t.Run("nonzero", func(t *testing.T) {
		fixture := newWorkFixture(t, `[]`, `[]`)
		if err := os.WriteFile(filepath.Join(filepath.Dir(fixture.argvLog), "exit"), []byte("9\n"), 0600); err != nil {
			t.Fatal(err)
		}
		_, stderr, err := runWorkForTest(t, "discover", "--registry="+fixture.registry, "--authority=local-fixture", "--json")
		if err == nil || !strings.Contains(stderr, `"authority_status": "unavailable"`) || !strings.Contains(stderr, "bd authority command failed") {
			t.Fatalf("nonzero output: err=%v stderr=%q", err, stderr)
		}
	})
	t.Run("bounded", func(t *testing.T) {
		fixture := newWorkFixture(t, strings.Repeat("x", 9<<10), `[]`)
		_, stderr, err := runWorkForTest(t, "discover", "--registry="+fixture.registry, "--authority=local-fixture", "--json")
		if err == nil || !strings.Contains(stderr, "bounded authority output exceeded") {
			t.Fatalf("oversized output: err=%v stderr=%q", err, stderr)
		}
	})
	t.Run("timeout", func(t *testing.T) {
		fixture := newWorkFixture(t, `[]`, `[]`)
		if err := os.WriteFile(filepath.Join(filepath.Dir(fixture.argvLog), "sleep"), []byte("4\n"), 0600); err != nil {
			t.Fatal(err)
		}
		_, stderr, err := runWorkForTest(t, "discover", "--registry="+fixture.registry, "--authority=local-fixture", "--json")
		if err == nil || !strings.Contains(stderr, "authority read timed out") {
			t.Fatalf("timeout: err=%v stderr=%q", err, stderr)
		}
	})
}

func TestWorkRemoteAuthorityUnavailableCannotFallBack(t *testing.T) {
	base := t.TempDir()
	registry := filepath.Join(base, "registry.json")
	data := `{"version":1,"authority_endpoint":{"kind":"remote","identity":"ssh://authority.example/tracker"},"trackers":[{"tracker_uuid":"` + workUUIDA + `","root":"/srv/tracker","repositories":[{"alias":"alpha","worktree":"/srv/alpha"}]}]}`
	if err := os.WriteFile(registry, []byte(data), 0o644); err != nil {
		t.Fatal(err)
	}
	t.Setenv("PATH", t.TempDir())
	_, stderr, err := runWorkForTest(t, "discover", "--registry="+registry, "--authority=ssh://authority.example/tracker", "--json")
	if err == nil || !strings.Contains(stderr, "required authority unavailable") || !strings.Contains(stderr, `"coverage": "none"`) {
		t.Fatalf("remote authority: err=%v stderr=%q", err, stderr)
	}
	if strings.Contains(stderr, "fallback") {
		t.Fatalf("remote authority suggested or used fallback: %s", stderr)
	}
}

func TestWorkNoResultsIsDistinctFromUnavailable(t *testing.T) {
	fixture := newWorkFixture(t, `[]`, `[]`)
	stdout, stderr, err := runWorkForTest(t, "discover", "--registry="+fixture.registry, "--authority=local-fixture", "--text=no-match-here", "--json")
	if err != nil {
		t.Fatalf("empty authoritative result: %v stderr=%q", err, stderr)
	}
	for _, want := range []string{`"authority_status": "available_read_only"`, `"result_status": "no_results"`} {
		if !strings.Contains(stdout, want) {
			t.Errorf("empty result missing %s: %s", want, stdout)
		}
	}
}

func TestWorkHumanAndJSONOutputAndUnsupportedVerb(t *testing.T) {
	fixture := newWorkFixture(t, `[{"id":"alpha-1","title":"Ownership","description":"registry","status":"open","assignee":"alice","labels":[]}]`, `[]`)
	human, stderr, err := runWorkForTest(t, "explain", "--registry="+fixture.registry, "--authority=local-fixture", "--task="+workUUIDA+":alpha-1")
	if err != nil {
		t.Fatalf("human explain: %v stderr=%q", err, stderr)
	}
	for _, want := range []string{"binding_authority=not_live", "implementation_allowed=false", "coverage=none", "BEADS assignee: alice", "attached sessions: unknown"} {
		if !strings.Contains(human, want) {
			t.Errorf("human output missing %q: %s", want, human)
		}
	}

	jsonOut, stderr, err := runWorkForTest(t, "explain", "--registry="+fixture.registry, "--authority=local-fixture", "--task="+workUUIDA+":alpha-1", "--json")
	if err != nil {
		t.Fatalf("JSON explain: %v stderr=%q", err, stderr)
	}
	var decoded map[string]any
	if err := json.Unmarshal([]byte(jsonOut), &decoded); err != nil {
		t.Fatalf("JSON output invalid: %v\n%s", err, jsonOut)
	}
	if decoded["implementation_allowed"] != false || decoded["coverage"] != "none" {
		t.Fatalf("JSON safety fields missing: %#v", decoded)
	}

	_, stderr, err = runWorkForTest(t, "bind", "--registry="+fixture.registry, "--authority=local-fixture")
	if err == nil || !strings.Contains(stderr, "unsupported work verb") {
		t.Fatalf("unsupported verb: err=%v stderr=%q", err, stderr)
	}
}
