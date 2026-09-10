package main

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func ratifyFixture(t *testing.T) (string, prepareRequest) {
	t.Helper()
	project := t.TempDir()
	project, _ = filepath.EvalSymlinks(project)
	base := t.TempDir()
	for _, args := range [][]string{{"init", "-b", "main"}, {"config", "user.name", "Fixture Ruler"}, {"config", "user.email", "fixture@example.invalid"}} {
		if _, e := reviewRun(project, "git", args...); e != nil {
			t.Fatal(e)
		}
	}
	os.WriteFile(filepath.Join(project, "GUIDANCE.md"), []byte("Original guidance\n"), 0600)
	reviewRun(project, "git", "add", "GUIDANCE.md")
	reviewRun(project, "git", "commit", "-m", "fixture")
	now := time.Now().UTC()
	s := prepareRequest{Version: 1, Key: "synthesis:1", Project: project, Actor: "fixture-human", Transcriber: "autarch", BudgetTokens: 1000, Proposal: reviewProposal{ID: "synthesis", Revision: 1, Project: project, Status: "accepted", AcceptedAt: &now, Outcome: "A reviewed plan", Scope: []string{"src"}, Guidance: []reviewGuidance{{Path: "GUIDANCE.md", Text: "Keep this exact ruling.", Scope: "Project", Rationale: "An explicit fixture ruling", BaseRevision: prepareHash([]byte("Original guidance\n"))}}}, Sources: map[string]string{"GUIDANCE.md": prepareHash([]byte("Original guidance\n"))}}
	return base, s
}

func TestPrepareRatifyRecoversLostCommitAcknowledgement(t *testing.T) {
	base, s := ratifyFixture(t)
	lost := true
	run := func(dir, name string, args ...string) ([]byte, error) {
		out, err := reviewRun(dir, name, args...)
		if name == "git" && len(args) > 0 && args[0] == "commit" && err == nil && lost {
			lost = false
			return nil, errors.New("fixture lost acknowledgement after commit")
		}
		return out, err
	}
	if _, err := ratifyPrepare(base, s, run); err == nil {
		t.Fatal("fixture did not interrupt")
	}
	head, _ := reviewRun(s.Project, "git", "rev-parse", "HEAD")
	recovered, err := ratifyPrepare(base, s, reviewRun)
	if err != nil || recovered.Status != "persisted" || recovered.Commit != strings.TrimSpace(string(head)) {
		t.Fatal("exact commit not reconciled", err, recovered)
	}
}

func TestPrepareStatusDoesNotCreateOrLaunch(t *testing.T) {
	base, s := ratifyFixture(t)
	dir, _ := preparePaths(base, s)
	if _, _, err := readPrepare(base, s); !os.IsNotExist(err) {
		t.Fatal("missing receipt not explicit", err)
	}
	if _, err := os.Stat(dir); !os.IsNotExist(err) {
		t.Fatal("status created preparation namespace")
	}
}

func TestRatificationRetryAfterMainAdvancesRetainsOriginalReceipt(t *testing.T) {
	base, s := ratifyFixture(t)
	first, err := ratifyPrepare(base, s, reviewRun)
	if err != nil {
		t.Fatal(err)
	}
	_, path := preparePaths(base, s)
	before, _ := os.ReadFile(path)
	os.WriteFile(filepath.Join(s.Project, "unrelated.txt"), []byte("later work"), 0600)
	reviewRun(s.Project, "git", "add", "unrelated.txt")
	reviewRun(s.Project, "git", "commit", "-m", "later work")
	again, err := ratifyPrepare(base, s, reviewRun)
	if err != nil || again.Commit != first.Commit {
		t.Fatal("retry demoted persisted receipt", err)
	}
	after, _ := os.ReadFile(path)
	if string(before) != string(after) {
		t.Fatal("persisted receipt mutated")
	}
	second := s
	second.Key = "second:1"
	second.Proposal.ID = "second"
	second.Proposal.Guidance = append([]reviewGuidance(nil), s.Proposal.Guidance...)
	second.Proposal.Guidance[0].BaseRevision = first.Files["GUIDANCE.md"].New
	second.Proposal.Guidance[0].Text = "Another explicit ruling"
	if _, err = ratifyPrepare(base, second, reviewRun); err != nil {
		t.Fatal(err)
	}
	if _, err = ratifyPrepare(base, s, reviewRun); err != nil {
		t.Fatal("second synthesis invalidated first persistence", err)
	}
}

func TestRatificationRejectsWhitespaceIdentityBeforeWriting(t *testing.T) {
	base, s := ratifyFixture(t)
	s.Actor += " "
	if _, err := ratifyPrepare(base, s, reviewRun); err == nil {
		t.Fatal("ambiguous commit identity accepted")
	}
}

func TestPrepareSubmissionBindsRatificationAndBudget(t *testing.T) {
	base, s := ratifyFixture(t)
	if _, err := ratifyPrepare(base, s, reviewRun); err != nil {
		t.Fatal(err)
	}
	source, _ := filepath.Abs("../..")
	t.Setenv("CLAVAIN_DIR", source)
	t.Setenv("CLAVAIN_ROUTING_POLICY", filepath.Join(source, "config", "routing.yaml"))
	r, path, err := submitPrepare(base, s)
	if err != nil {
		t.Fatal(err)
	}
	if r.Status != "accepted" || r.RunID != "" || len(r.Attempts) != 0 {
		t.Fatal("submission itself dispatched work")
	}
	if r.Sources["GUIDANCE.md"] == s.Sources["GUIDANCE.md"] {
		t.Fatal("ratified source binding not replaced")
	}
	var context struct {
		Request      prepareRequest    `json:"accepted_request"`
		Sources      map[string]string `json:"current_sources"`
		Ratification struct {
			Commit  string `json:"commit"`
			Changes map[string]struct {
				Before string `json:"before"`
				After  string `json:"after"`
			} `json:"changed_sources"`
		} `json:"ratification"`
	}
	if err := json.Unmarshal(prepareSourceContext(r), &context); err != nil {
		t.Fatal(err)
	}
	if context.Request.Sources["GUIDANCE.md"] != s.Sources["GUIDANCE.md"] || context.Sources["GUIDANCE.md"] != r.Sources["GUIDANCE.md"] || context.Ratification.Commit != r.Ratification.Commit {
		t.Fatal("planning/review context lacks original and ratified source provenance")
	}
	change := context.Ratification.Changes["GUIDANCE.md"]
	if change.Before != s.Sources["GUIDANCE.md"] || change.After != r.Sources["GUIDANCE.md"] {
		t.Fatal("prompt does not explain the ratified guidance hash transition")
	}
	data, _ := os.ReadFile(path)
	var receipt prepareReceipt
	if json.Unmarshal(data, &receipt) != nil {
		t.Fatal("invalid durable receipt")
	}
	s.BudgetTokens++
	if _, _, err = submitPrepare(base, s); err == nil {
		t.Fatal("changed budget accepted under same key")
	}
}

func TestPrepareRatifyCommitsOnlyDisplayedGuidanceAndRetries(t *testing.T) {
	base, s := ratifyFixture(t)
	r, err := ratifyPrepare(base, s, reviewRun)
	if err != nil {
		t.Fatal(err)
	}
	if r.Status != "persisted" || r.Commit == "" || r.Parent == r.Commit {
		t.Fatalf("missing commit receipt: %+v", r)
	}
	again, err := ratifyPrepare(base, s, reviewRun)
	if err != nil || again.Commit != r.Commit {
		t.Fatal("non-idempotent ratification", err)
	}
	names, _ := reviewRun(s.Project, "git", "diff-tree", "--no-commit-id", "--name-only", "-r", r.Commit)
	if strings.TrimSpace(string(names)) != "GUIDANCE.md" {
		t.Fatalf("unexpected commit scope %q", names)
	}
	s.Proposal.Guidance[0].Text = "changed payload"
	if _, err = ratifyPrepare(base, s, reviewRun); err == nil {
		t.Fatal("same key allowed different ruling")
	}
}

func TestPrepareRatifyRejectsAllBasesBeforeAnyWrite(t *testing.T) {
	base, s := ratifyFixture(t)
	s.Proposal.Guidance = append(s.Proposal.Guidance, reviewGuidance{Path: "OTHER.md", Text: "Ruling", Scope: "project", Rationale: "reason", BaseRevision: "wrong"})
	if _, err := ratifyPrepare(base, s, reviewRun); err == nil {
		t.Fatal("bad base accepted")
	}
	data, _ := os.ReadFile(filepath.Join(s.Project, "GUIDANCE.md"))
	if string(data) != "Original guidance\n" {
		t.Fatal("partial write before base validation")
	}
}
