package main

import (
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func reviewFixture(t *testing.T) reviewSubmission {
	t.Helper()
	root, _ := filepath.EvalSymlinks(t.TempDir())
	_ = os.Mkdir(filepath.Join(root, ".beads"), 0700)
	project := filepath.Join(root, "project")
	_ = os.Mkdir(project, 0700)
	now := time.Now().UTC()
	return reviewSubmission{Version: 1, Key: "p:1", Project: project, Tracker: root, Proposal: reviewProposal{ID: "p", Project: project, Tracker: root, Revision: 1, Status: "accepted", AcceptedAt: &now, Outcome: "Readable reviews", Change: "Keep the decision visible", Scope: []string{"internal/reviewtui"}, Priority: 1, BudgetTokens: 5000, Checklist: []string{"Read the question after a long response"}, Build: reviewBuild{Command: []string{"go", "build", "-o", "build/app", "."}, Checks: [][]string{{"go", "test", "./..."}}, Binary: "build/app"}}}
}

type reviewFake struct {
	t                    *testing.T
	s                    reviewSubmission
	beads                []map[string]any
	runs                 []map[string]any
	creates, runsCreated int
	unavailable          bool
}

func (f *reviewFake) run(dir, name string, args ...string) ([]byte, error) {
	f.t.Helper()
	if f.unavailable {
		return nil, errors.New("tracker unavailable")
	}
	if name == "bd" {
		if dir != f.s.Tracker {
			f.t.Fatal("Beads targeted wrong tracker")
		}
		switch args[0] {
		case "config":
			return []byte("test\n"), nil
		case "list":
			return json.Marshal(f.beads)
		case "create":
			f.creates++
			item := map[string]any{}
			for i := 1; i < len(args)-1; i++ {
				if args[i] == "--id" {
					item["id"] = args[i+1]
				}
				if args[i] == "--external-ref" {
					item["external_ref"] = args[i+1]
				}
			}
			f.beads = append(f.beads, item)
			return json.Marshal(item)
		case "show":
			return []byte(`[{"status":"open"}]`), nil
		}
	} else if name == "ic" {
		if dir != f.s.Project {
			f.t.Fatal("Intercore targeted wrong project")
		}
		if args[2] == "list" {
			return json.Marshal(f.runs)
		}
		if args[2] == "create" {
			f.runsCreated++
			item := map[string]any{"id": "run-1", "project_dir": dir}
			f.runs = append(f.runs, item)
			return json.Marshal(item)
		}
	}
	return nil, errors.New("unexpected command " + name + strings.Join(args, " "))
}
func TestReviewRetriesReconcileExternalRecords(t *testing.T) {
	s := reviewFixture(t)
	fake := &reviewFake{t: t, s: s, beads: []map[string]any{}, runs: []map[string]any{}}
	base := t.TempDir()
	r, path, err := submitReview(base, s, fake.run)
	if err != nil {
		t.Fatal(err)
	}
	if err = prepareReview(&r, path, fake.run); err != nil {
		t.Fatal(err)
	}
	// Simulate lost acknowledgement and a crash after creation before run ID save.
	r.RunID = ""
	if err = reviewWrite(path, r); err != nil {
		t.Fatal(err)
	}
	r, path, err = submitReview(base, s, fake.run)
	if err != nil {
		t.Fatal(err)
	}
	if err = prepareReview(&r, path, fake.run); err != nil {
		t.Fatal(err)
	}
	if fake.creates != 1 || fake.runsCreated != 1 || r.WorkID == "" || r.RunID != "run-1" {
		t.Fatalf("duplicate submission: %+v %+v", fake, r)
	}
	s.Proposal.Change = "Unreviewed change"
	if _, _, err = submitReview(base, s, fake.run); err == nil {
		t.Fatal("changed approval reused retry key")
	}
}
func TestReviewRejectsUnapprovedCrossProjectAndUnsafeScope(t *testing.T) {
	for _, change := range []func(*reviewSubmission){func(s *reviewSubmission) { s.Proposal.Status = "proposed" }, func(s *reviewSubmission) { s.Proposal.Project = t.TempDir() }, func(s *reviewSubmission) { s.Proposal.Scope = []string{"../other"} }, func(s *reviewSubmission) { s.Proposal.BudgetTokens = 0 }, func(s *reviewSubmission) { s.Proposal.Tracker = t.TempDir() }} {
		s := reviewFixture(t)
		change(&s)
		if err := validateReview(s); err == nil {
			t.Fatal("unsafe approval admitted")
		}
	}
}
func TestReviewDefersPriorityAndDependencies(t *testing.T) {
	for _, priority := range []int{1, 3} {
		s := reviewFixture(t)
		s.Proposal.Priority = priority
		if priority == 1 {
			s.Proposal.Dependencies = []string{"test-blocker"}
		}
		fake := &reviewFake{t: t, s: s, beads: []map[string]any{}, runs: []map[string]any{}}
		r, path, err := submitReview(t.TempDir(), s, fake.run)
		if err != nil {
			t.Fatal(err)
		}
		if err = prepareReview(&r, path, fake.run); err != nil {
			t.Fatal(err)
		}
		if r.Status != "deferred" || r.RunID != "" || fake.runsCreated != 0 {
			t.Fatal("deferred work launched")
		}
	}
}
func TestReviewUnavailableTrackerCannotBecomeEmptyTracker(t *testing.T) {
	s := reviewFixture(t)
	f := &reviewFake{t: t, s: s, unavailable: true}
	r, path, err := submitReview(t.TempDir(), s, f.run)
	if err != nil {
		t.Fatal(err)
	}
	if err = prepareReview(&r, path, f.run); err == nil || f.creates != 0 {
		t.Fatal("unavailable tracker became new work")
	}
}
func TestReviewCommandUsesGovernedRoleAtActualLaunch(t *testing.T) {
	dir := t.TempDir()
	script := filepath.Join(dir, "dispatch.sh")
	out := filepath.Join(dir, "args")
	if err := os.WriteFile(script, []byte("#!/bin/sh\nprintf '%s\\n' \"$@\" > \"$TEST_ARGS\"\npwd >> \"$TEST_ARGS\"\n"), 0700); err != nil {
		t.Fatal(err)
	}
	t.Setenv("TEST_ARGS", out)
	cmd := governedReviewCommand(script, dir, "prompt", "output", "work", "routine-execution")
	if err := cmd.Run(); err != nil {
		t.Fatal(err)
	}
	data, _ := os.ReadFile(out)
	if !strings.Contains(string(data), "--role\nroutine-execution\n") || strings.Contains(string(data), "dangerously-skip-permissions") {
		t.Fatal(string(data))
	}
}
func TestReviewScopeAndUsageEvidence(t *testing.T) {
	s := reviewFixture(t)
	if reviewScopeContains(s.Proposal, "internal/elsewhere/file.go") || !reviewScopeContains(s.Proposal, "internal/reviewtui/model.go") {
		t.Fatal("scope widened")
	}
	path := filepath.Join(t.TempDir(), "events")
	_ = os.WriteFile(path, []byte("{\"type\":\"turn.completed\",\"usage\":{\"input_tokens\":10,\"output_tokens\":3}}\n{\"type\":\"turn.completed\",\"usage\":{\"input_tokens\":5,\"output_tokens\":2}}\n"), 0600)
	if got, err := reviewUsage(path); err != nil || got != 20 {
		t.Fatalf("usage=%d %v", got, err)
	}
}

func TestReviewGuidanceRejectsFileSymlinkAndGroupsSameBase(t *testing.T) {
	s := reviewFixture(t)
	outside := filepath.Join(s.Tracker, "outside.md")
	_ = os.WriteFile(outside, []byte("Original"), 0600)
	link := filepath.Join(s.Project, "design.md")
	_ = os.Symlink(outside, link)
	sum := sha256.Sum256([]byte("Original"))
	base := fmt.Sprintf("%x", sum)
	s.Proposal.Guidance = []reviewGuidance{{Path: "design.md", Text: "Rule one", Scope: "Review", Rationale: "Clarity", BaseRevision: base}}
	r := reviewReceipt{Request: s, Project: s.Project, ProposalID: "p", ProposalRevision: 1}
	if err := persistReviewGuidance(r); err == nil {
		t.Fatal("followed guidance symlink")
	}
	data, _ := os.ReadFile(outside)
	if string(data) != "Original" {
		t.Fatal("changed outside project")
	}
	_ = os.Remove(link)
	_ = os.WriteFile(link, []byte("Original"), 0600)
	r.Request.Proposal.Guidance = append(r.Request.Proposal.Guidance, reviewGuidance{Path: "design.md", Text: "Rule two", Scope: "Review", Rationale: "Continuity", BaseRevision: base})
	if err := persistReviewGuidance(r); err != nil {
		t.Fatal(err)
	}
	if err := verifyReviewGuidance(r); err != nil {
		t.Fatal(err)
	}
	_ = os.WriteFile(link, []byte("Deleted ruling"), 0600)
	if err := verifyReviewGuidance(r); err == nil {
		t.Fatal("worker removed accepted guidance undetected")
	}
}

func TestReviewGuidanceReplayAfterPartialPreparation(t *testing.T) {
	req := reviewFixture(t)
	original := []byte("# Guidance\n")
	sum := sha256.Sum256(original)
	req.Proposal.Guidance = []reviewGuidance{{Path: "GUIDANCE.md", BaseRevision: fmt.Sprintf("%x", sum), Text: "Preserve intent", Scope: "project", Rationale: "human ruling"}, {Path: "docs/NEW.md", BaseRevision: "missing", Text: "Retain evidence", Scope: "review", Rationale: "provenance"}}
	os.WriteFile(filepath.Join(req.Project, "GUIDANCE.md"), original, 0644)
	r := reviewReceipt{Project: req.Project, ProposalID: "p", ProposalRevision: 1, Request: req, GuidanceStarted: true}
	// Simulate a crash after the first document's atomic rename.
	first := r
	first.Request.Proposal.Guidance = req.Proposal.Guidance[:1]
	if err := persistReviewGuidance(first); err != nil {
		t.Fatal(err)
	}
	if err := persistReviewGuidance(r); err != nil {
		t.Fatal(err)
	}
	if err := persistReviewGuidance(r); err != nil {
		t.Fatal(err)
	}
	data, _ := os.ReadFile(filepath.Join(req.Project, "GUIDANCE.md"))
	if strings.Count(string(data), "Preserve intent") != 1 {
		t.Fatal("duplicated accepted ruling")
	}
	if err := verifyReviewGuidance(r); err != nil {
		t.Fatal(err)
	}
}
