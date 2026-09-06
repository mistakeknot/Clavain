package main

import (
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

// Real kernel and actual child processes in an isolated fixture. The worker
// is deterministic test code, not a model or a human acceptance test.
func TestLiveReviewKernelLifecycle(t *testing.T) {
	if os.Getenv("CLAVAIN_LIVE_REVIEW") != "1" || runtime.GOOS != "darwin" {
		t.Skip("explicit local Intercore process integration")
	}
	if _, err := exec.LookPath("ic"); err != nil {
		t.Fatal(err)
	}
	s := reviewFixture(t)
	write := func(path, text string, mode os.FileMode) {
		t.Helper()
		if err := os.MkdirAll(filepath.Dir(path), 0700); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(path, []byte(text), mode); err != nil {
			t.Fatal(err)
		}
	}
	run := func(name string, args ...string) string {
		t.Helper()
		data, err := reviewRun(s.Project, name, args...)
		if err != nil {
			t.Fatal(err)
		}
		return string(data)
	}
	run("git", "init", "--initial-branch=main")
	run("git", "config", "user.name", "Review Fixture")
	run("git", "config", "user.email", "fixture@example.invalid")
	write(filepath.Join(s.Project, ".gitignore"), ".clavain/\nbuild/\n", 0600)
	write(filepath.Join(s.Project, "app.sh"), "#!/bin/sh\necho original\n", 0700)
	write(filepath.Join(s.Project, "AGENTS.md"), "Fixture project guidance.\n", 0600)
	run("git", "add", ".gitignore", "app.sh", "AGENTS.md")
	run("git", "commit", "-m", "fixture baseline")
	run("ic", "init")
	toolsDir := filepath.Join(s.Tracker, "tools")
	write(filepath.Join(toolsDir, "bd"), `#!/usr/bin/env python3
import sys,json,pathlib
args=sys.argv[1:]
path=pathlib.Path.cwd()/'.beads/mock.json'
items=json.loads(path.read_text()) if path.exists() else []
if args[:2]==['config','get']: print('fixture')
elif args[0]=='list': print(json.dumps(items))
elif args[0]=='create':
 item={'id':args[args.index('--id')+1], 'external_ref':args[args.index('--external-ref')+1]}
 items.append(item);path.write_text(json.dumps(items));print(json.dumps(item))
else: raise SystemExit('unexpected test tracker command')
`, 0700)
	t.Setenv("PATH", toolsDir+string(os.PathListSeparator)+os.Getenv("PATH"))
	clavain := filepath.Join(s.Tracker, "clavain")
	write(filepath.Join(clavain, "scripts", "dispatch.sh"), `#!/usr/bin/env bash
set -euo pipefail
[[ "$1" == --role && "$2" == routine-execution ]]
output=""
while [[ $# -gt 0 ]]; do if [[ "$1" == -o ]]; then output="$2"; shift; fi; shift; done
ic route record --agent=fixture --model=fixture-model --rule=dispatch-profile --dispatch="$CLAVAIN_DISPATCH_ID" --run="$CLAVAIN_RUN_ID" --bead="$CLAVAIN_BEAD_ID" >/dev/null
printf '#!/bin/sh\necho reviewed-build\n' > app.sh
git add app.sh AGENTS.md
git commit -m 'apply fixture accepted scope'
printf '{"type":"turn.completed","usage":{"input_tokens":20,"output_tokens":5}}\n' >> "$CLAVAIN_REVIEW_EVENTS"
printf 'fixture worker completed\n' > "$output"
printf '%s\n' '--- VERDICT ---' 'STATUS: pass' 'SUMMARY: fixture checks' '---' > "$output.verdict"
`, 0700)
	t.Setenv("CLAVAIN_DIR", clavain)
	s.Proposal.Scope = []string{"app.sh"}
	s.Proposal.Build = reviewBuild{Command: []string{"sh", "-c", "mkdir -p build && cp app.sh build/app && chmod +x build/app"}, Checks: [][]string{{"sh", "-n", "app.sh"}}, Binary: "build/app"}
	base := sha256.Sum256([]byte("Fixture project guidance.\n"))
	s.Proposal.Guidance = []reviewGuidance{{Path: "AGENTS.md", Text: "Preserve the original review observation.", Scope: "Review", Rationale: "Continuity", BaseRevision: fmt.Sprintf("%x", base)}}
	receipts := t.TempDir()
	_, path, err := submitReview(receipts, s, reviewRun)
	if err != nil {
		t.Fatal(err)
	}
	if err = workReview(path); err != nil {
		data, _ := os.ReadFile(filepath.Join(filepath.Dir(path), "worker.log"))
		t.Log(string(data))
		t.Fatal(err)
	}
	data, _ := os.ReadFile(path)
	var result reviewReceipt
	if err = json.Unmarshal(data, &result); err != nil {
		t.Fatal(err)
	}
	if result.Status != "ready_for_retest" || result.DispatchID == "" || result.RunID == "" || result.Model != "fixture-model" {
		t.Fatalf("missing lifecycle evidence: %+v", result)
	}
	if actual := run(result.Binary); strings.TrimSpace(actual) != "reviewed-build" {
		t.Fatal(actual)
	}
	var dispatch map[string]any
	if err = json.Unmarshal([]byte(run("ic", "--json", "dispatch", "status", result.DispatchID)), &dispatch); err != nil {
		t.Fatal(err)
	}
	if dispatch["status"] != "completed" {
		t.Fatal(dispatch)
	}
	if again, _, err := submitReview(receipts, s, reviewRun); err != nil || again.DispatchID != result.DispatchID {
		t.Fatal("retry changed actual kernel dispatch")
	}
	t.Log("real Intercore run/dispatch and invoked fixture binary:", result.RunID, result.DispatchID, result.Build)
}
