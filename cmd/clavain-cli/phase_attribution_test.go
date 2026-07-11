package main

import (
	"io"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

type phaseAdvanceHarness struct {
	logPath string
}

func setupPhaseAdvanceHarness(t *testing.T, attributeFails, interstatFails bool) phaseAdvanceHarness {
	t.Helper()
	root := t.TempDir()
	binDir := filepath.Join(root, "bin")
	interstatRoot := filepath.Join(root, "interstat")
	if err := os.MkdirAll(filepath.Join(interstatRoot, "scripts"), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(binDir, 0o755); err != nil {
		t.Fatal(err)
	}
	logPath := filepath.Join(root, "calls.log")
	if err := os.WriteFile(logPath, nil, 0o644); err != nil {
		t.Fatal(err)
	}

	writeExecutable := func(path, content string) {
		t.Helper()
		if err := os.WriteFile(path, []byte(content), 0o755); err != nil {
			t.Fatal(err)
		}
	}
	writeExecutable(filepath.Join(binDir, "bd"), `#!/usr/bin/env bash
set -eu
printf 'bd:%s\n' "$*" >>"$PHASE_ATTR_LOG"
if [[ "${1:-}" == "show" && "${3:-}" == "--json" ]]; then
  printf '%s\n' '[{"id":"bead-7","labels":[]}]'
  exit 0
fi
if [[ "${1:-}" == "state" && "${3:-}" == "ic_run_id" ]]; then
  printf 'run-42\n'
fi
`)
	writeExecutable(filepath.Join(binDir, "ic"), `#!/usr/bin/env bash
set -eu
printf 'ic:%s\n' "$*" >>"$PHASE_ATTR_LOG"
if [[ "${1:-}" == "--json" && "${2:-}" == "run" && "${3:-}" == "advance" ]]; then
  printf '%s\n' '{"advanced":true,"from_phase":"planned","to_phase":"executing","event_type":"advance"}'
  exit 0
fi
if [[ "${1:-}" == "--json" && "${2:-}" == "run" && "${3:-}" == "status" ]]; then
  printf '%s\n' '{"id":"run-42","project_dir":"/tmp/project","phase":"planned","status":"active","created_at":1}'
  exit 0
fi
if [[ "${1:-}" == "session" && "${2:-}" == "attribute" && "${IC_ATTRIBUTE_FAIL:-0}" == "1" ]]; then
  printf 'forced attribution failure\n' >&2
  exit 2
fi
if [[ "${1:-}" == "health" ]]; then
  exit 0
fi
if [[ "${1:-}" == "state" && "${2:-}" == "get" ]]; then
  printf 'null\n'
  exit 0
fi
if [[ "${1:-}" == "state" && "${2:-}" == "set" ]]; then
  cat >/dev/null
  exit 0
fi
exit 0
`)
	writeExecutable(filepath.Join(interstatRoot, "scripts", "set-bead-context.sh"), `#!/usr/bin/env bash
set -eu
printf 'interstat:%s\n' "$*" >>"$PHASE_ATTR_LOG"
if [[ "${INTERSTAT_CONTEXT_FAIL:-0}" == "1" ]]; then
  printf 'forced interstat failure\n' >&2
  exit 3
fi
`)

	t.Setenv("PATH", binDir+string(os.PathListSeparator)+os.Getenv("PATH"))
	t.Setenv("PHASE_ATTR_LOG", logPath)
	t.Setenv("INTERSTAT_ROOT", interstatRoot)
	t.Setenv("CLAUDE_SESSION_ID", "session-env")
	t.Setenv("CLAVAIN_SKIP_BUDGET", "1")
	t.Setenv("SPRINT_LIB_PROJECT_DIR", root)
	t.Setenv("HOME", root)
	if attributeFails {
		t.Setenv("IC_ATTRIBUTE_FAIL", "1")
	} else {
		t.Setenv("IC_ATTRIBUTE_FAIL", "0")
	}
	if interstatFails {
		t.Setenv("INTERSTAT_CONTEXT_FAIL", "1")
	} else {
		t.Setenv("INTERSTAT_CONTEXT_FAIL", "0")
	}

	oldICBin := icBin
	icBin = ""
	oldRunIDCache := runIDCache
	runIDCache = map[string]string{}
	t.Cleanup(func() {
		icBin = oldICBin
		runIDCache = oldRunIDCache
	})
	return phaseAdvanceHarness{logPath: logPath}
}

func capturePhaseAdvanceStderr(t *testing.T, fn func() error) (string, error) {
	t.Helper()
	original := os.Stderr
	readPipe, writePipe, err := os.Pipe()
	if err != nil {
		t.Fatal(err)
	}
	os.Stderr = writePipe
	defer func() { os.Stderr = original }()

	callErr := fn()
	if err := writePipe.Close(); err != nil {
		t.Fatal(err)
	}
	data, err := io.ReadAll(readPipe)
	if err != nil {
		t.Fatal(err)
	}
	_ = readPipe.Close()
	return string(data), callErr
}

func readPhaseAdvanceCalls(t *testing.T, path string) []string {
	t.Helper()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	return strings.Split(strings.TrimSpace(string(data)), "\n")
}

func indexPhaseAdvanceCall(calls []string, exact string) int {
	for i, call := range calls {
		if call == exact {
			return i
		}
	}
	return -1
}

func TestSprintAdvanceRefreshesIntercoreThenInterstatAttribution(t *testing.T) {
	harness := setupPhaseAdvanceHarness(t, false, false)

	if err := cmdSprintAdvance([]string{"bead-7", "planned"}); err != nil {
		t.Fatalf("cmdSprintAdvance: %v", err)
	}

	calls := readPhaseAdvanceCalls(t, harness.logPath)
	attribute := indexPhaseAdvanceCall(calls, "ic:session attribute --session=session-env --bead=bead-7 --run=run-42 --phase=executing")
	context := indexPhaseAdvanceCall(calls, "interstat:session-env bead-7 executing")
	if attribute < 0 {
		t.Fatalf("Intercore attribution call missing from %v", calls)
	}
	if context < 0 {
		t.Fatalf("Interstat context call missing from %v", calls)
	}
	if attribute >= context {
		t.Fatalf("attribution order = Intercore index %d, Interstat index %d; want Intercore first", attribute, context)
	}
}

func TestSprintAdvanceAttributionFailuresWarnButDoNotFailCommittedAdvance(t *testing.T) {
	for _, tc := range []struct {
		name             string
		attributeFails   bool
		interstatFails   bool
		warningSubstring string
	}{
		{name: "Intercore", attributeFails: true, warningSubstring: "Intercore attribution failed"},
		{name: "Interstat", interstatFails: true, warningSubstring: "Interstat attribution failed"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			harness := setupPhaseAdvanceHarness(t, tc.attributeFails, tc.interstatFails)
			stderr, err := capturePhaseAdvanceStderr(t, func() error {
				return cmdSprintAdvance([]string{"bead-7", "planned"})
			})
			if err != nil {
				t.Fatalf("committed phase advance reported failure: %v", err)
			}
			if !strings.Contains(stderr, tc.warningSubstring) {
				t.Fatalf("stderr %q missing warning %q", stderr, tc.warningSubstring)
			}
			calls := readPhaseAdvanceCalls(t, harness.logPath)
			if indexPhaseAdvanceCall(calls, "interstat:session-env bead-7 executing") < 0 {
				t.Fatalf("Interstat context refresh was skipped: %v", calls)
			}
		})
	}
}

func TestPhaseAttributionSessionIDPrefersEnvironmentThenFile(t *testing.T) {
	oldPath := phaseAttributionSessionFile
	phaseAttributionSessionFile = filepath.Join(t.TempDir(), "session-id")
	t.Cleanup(func() { phaseAttributionSessionFile = oldPath })
	if err := os.WriteFile(phaseAttributionSessionFile, []byte("session-file\n"), 0o600); err != nil {
		t.Fatal(err)
	}

	t.Setenv("CLAUDE_SESSION_ID", "session-env")
	if got := phaseAttributionSessionID(); got != "session-env" {
		t.Fatalf("phaseAttributionSessionID with env = %q, want session-env", got)
	}
	t.Setenv("CLAUDE_SESSION_ID", "")
	if got := phaseAttributionSessionID(); got != "session-file" {
		t.Fatalf("phaseAttributionSessionID fallback = %q, want session-file", got)
	}
}
