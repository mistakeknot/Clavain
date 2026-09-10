package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
	"time"
)

// A real kernel-owned process survives the simulated supervisor loss. These
// deterministic seats never call a model or establish human acceptance.
func TestLivePreparationInvalidationDrainsExistingWorker(t *testing.T) {
	if os.Getenv("CLAVAIN_LIVE_REVIEW") != "1" || runtime.GOOS != "darwin" {
		t.Skip("explicit isolated kernel fixture")
	}
	for _, kind := range []string{"policy", "source", "watchdog", "truncated", "pinned-kernel", "live-policy", "live-source"} {
		t.Run(kind, func(t *testing.T) {
			base, s := ratifyFixture(t)
			policyData, err := os.ReadFile("../../config/routing.yaml")
			if err != nil {
				t.Fatal(err)
			}
			policy := filepath.Join(t.TempDir(), "routing.yaml")
			os.WriteFile(policy, policyData, 0600)
			t.Setenv("CLAVAIN_ROUTING_POLICY", policy)
			source, err := filepath.Abs("../..")
			if err != nil {
				t.Fatal(err)
			}
			t.Setenv("CLAVAIN_DIR", source)
			if _, err = ratifyPrepare(base, s, reviewRun); err != nil {
				t.Fatal(err)
			}
			r, path, err := submitPrepare(base, s)
			if err != nil {
				t.Fatal(err)
			}
			r.KernelDB = filepath.Join(s.Project, ".clavain", "intercore.db")
			if kind == "pinned-kernel" {
				r.KernelDB = filepath.Join(t.TempDir(), "intercore.db")
			}
			if err = os.MkdirAll(filepath.Dir(r.KernelDB), 0700); err != nil {
				t.Fatal(err)
			}
			if _, err = reviewRun(filepath.Dir(r.KernelDB), "ic", "--db="+r.KernelDB, "init"); err != nil {
				t.Fatal(err)
			}
			run := prepareRunner(r)
			data, err := run(s.Project, "ic", "--json", "run", "create", "--project="+s.Project, "--goal=deterministic invalidation fixture", "--token-budget=1000", "--budget-enforce", "--max-agents=6", "--max-dispatches=6")
			var created struct {
				ID string `json:"id"`
			}
			if err != nil || json.Unmarshal(data, &created) != nil || created.ID == "" {
				t.Fatal(err, string(data))
			}
			r.RunID = created.ID
			dir := filepath.Join(filepath.Dir(path), "attempt-1", "planning")
			os.MkdirAll(dir, 0700)
			prompt := filepath.Join(dir, "prompt.md")
			os.WriteFile(prompt, []byte("Synthetic sleeping seat; no model call.\n"), 0600)
			wrapper := filepath.Join(dir, "launch.sh")
			os.WriteFile(wrapper, []byte("#!/bin/bash\ntrap 'exit 143' TERM INT\nsleep 120 &\nwait $!\n"), 0700)
			data, err = run(s.Project, "ic", "--json", "dispatch", "spawn", "--type=codex", "--project="+s.Project, "--run-id="+r.RunID, "--scope-id="+r.RunID, "--max-active-per-run=1", "--max-agents-per-run=6", "--budget-enforce", "--prompt-file="+prompt, "--output="+filepath.Join(dir, "response.md"), "--name=invalidation-fixture", "--dispatch-sh="+wrapper)
			var spawned struct {
				ID  string `json:"id"`
				PID int    `json:"pid"`
			}
			if err != nil || json.Unmarshal(data, &spawned) != nil || spawned.ID == "" {
				t.Fatal(err, string(data))
			}
			t.Cleanup(func() {
				_ = stopReviewWorkerWithRunner(reviewReceipt{Project: s.Project, DispatchID: spawned.ID, WorkerPID: spawned.PID}, dir, run)
			})
			if kind == "pinned-kernel" {
				if _, err := reviewRun(s.Project, "ic", "--db="+filepath.Join(s.Project, ".clavain", "intercore.db"), "init"); err != nil {
					t.Fatal(err)
				}
			}
			usage := "{\"type\":\"turn.completed\",\"usage\":{\"input_tokens\":20,\"output_tokens\":5}}\n"
			if kind == "truncated" {
				usage += "{\"type\":"
			}
			os.WriteFile(filepath.Join(dir, "usage.jsonl"), []byte(usage), 0600)
			phase := preparePhase{Role: "planning", Intent: true, DispatchID: spawned.ID, PID: spawned.PID, StartedAt: time.Now().UTC()}
			want := "routing policy changed"
			switch kind {
			case "source":
				os.WriteFile(filepath.Join(s.Project, "GUIDANCE.md"), []byte("Changed after worker launch\n"), 0600)
				want = "canonical source changed"
			case "watchdog":
				phase.StartedAt = time.Now().Add(-16 * time.Minute)
				want = "watchdog expired"
			case "live-policy", "live-source":
				if kind == "live-source" {
					want = "canonical source changed"
				}
			default:
				os.WriteFile(policy, append(policyData, []byte("\n# deliberate drift\n")...), 0600)
			}
			r.Status = "planning"
			r.Attempts = []prepareAttempt{{Number: 1, Planner: phase, Reviewer: preparePhase{Role: "plan-review"}}}
			if err = reviewWrite(path, r); err != nil {
				t.Fatal(err)
			}
			if kind == "live-policy" || kind == "live-source" {
				changed := make(chan error, 1)
				go func() {
					time.Sleep(200 * time.Millisecond)
					if kind == "live-source" {
						changed <- os.WriteFile(filepath.Join(s.Project, "GUIDANCE.md"), []byte("Changed during supervision\n"), 0600)
					} else {
						changed <- os.WriteFile(policy, append(policyData, []byte("\n# live drift\n")...), 0600)
					}
				}()
				t.Cleanup(func() {
					if err := <-changed; err != nil {
						t.Error(err)
					}
				})
			}
			err = workPrepare(path)
			if err == nil {
				t.Fatal("invalidation unexpectedly succeeded")
			}
			if kind != "truncated" && !strings.Contains(err.Error(), want) {
				t.Fatal(err)
			}
			after, _, err := readPrepare(base, s)
			if err != nil {
				t.Fatal(err)
			}
			p := after.Attempts[0].Planner
			if after.Status != "blocked" || p.UsageTokens != 25 || p.Complete || after.Attempts[0].Reviewer.Intent {
				t.Fatalf("lost accounting or advanced work: %+v", after)
			}
			if p.UsageComplete != (kind != "truncated") {
				t.Fatalf("invalid completeness: %+v", p)
			}
			data, err = run(s.Project, "ic", "--json", "dispatch", "poll", spawned.ID)
			var terminal struct {
				Status string `json:"status"`
			}
			if err != nil || json.Unmarshal(data, &terminal) != nil || terminal.Status == "running" || terminal.Status == "spawned" {
				t.Fatal("orphaned worker", err, string(data))
			}
			// Retrying cannot launch a replacement or alter the reconciled charge.
			_ = workPrepare(path)
			again, _, err := readPrepare(base, s)
			if err != nil || prepareUsage(again) != 25 || len(again.Attempts) != 1 || again.Attempts[0].Planner.DispatchID != spawned.ID || again.Attempts[0].Reviewer.Intent {
				t.Fatal("retry changed identity or spend", err)
			}
		})
	}
}
