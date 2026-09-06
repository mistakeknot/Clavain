package main

// The review adapter is L2 policy: durable acceptance, project/tracker binding,
// scheduling and role dispatch. Intercore remains the execution/routing record.
import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"
	"syscall"
	"time"
)

type reviewBuild struct {
	Command []string   `json:"command"`
	Checks  [][]string `json:"checks"`
	Binary  string     `json:"binary"`
}
type reviewGuidance struct {
	Path         string `json:"path"`
	Text         string `json:"text"`
	Scope        string `json:"scope"`
	Rationale    string `json:"rationale"`
	BaseRevision string `json:"base_revision"`
	Supersedes   string `json:"supersedes,omitempty"`
}
type reviewProposal struct {
	ID           string           `json:"id"`
	Project      string           `json:"project"`
	Revision     int              `json:"revision"`
	Status       string           `json:"status"`
	AcceptedAt   *time.Time       `json:"accepted_at"`
	Outcome      string           `json:"outcome"`
	Change       string           `json:"change"`
	Scope        []string         `json:"scope"`
	Guidance     []reviewGuidance `json:"guidance"`
	Priority     int              `json:"priority"`
	Dependencies []string         `json:"dependencies"`
	BudgetTokens int              `json:"budget_tokens"`
	Checklist    []string         `json:"checklist"`
	Build        reviewBuild      `json:"build"`
	Tracker      string           `json:"tracker"`
}
type reviewSubmission struct {
	Version  int            `json:"version"`
	Key      string         `json:"key"`
	Project  string         `json:"project"`
	Tracker  string         `json:"tracker"`
	Proposal reviewProposal `json:"proposal"`
}
type reviewReceipt struct {
	Request          reviewSubmission `json:"request"`
	Hash             string           `json:"hash"`
	ID               string           `json:"id"`
	Project          string           `json:"project"`
	Tracker          string           `json:"tracker"`
	ProposalID       string           `json:"proposal_id"`
	ProposalRevision int              `json:"proposal_revision"`
	Status           string           `json:"status"`
	WorkID           string           `json:"work_id,omitempty"`
	RunID            string           `json:"run_id,omitempty"`
	DispatchID       string           `json:"dispatch_id,omitempty"`
	Model            string           `json:"model,omitempty"`
	Reason           string           `json:"reason,omitempty"`
	Build            string           `json:"build,omitempty"`
	Binary           string           `json:"binary,omitempty"`
	GuidanceStarted  bool             `json:"guidance_started,omitempty"`
	WorkerPID        int              `json:"worker_pid,omitempty"`
	StartedAt        time.Time        `json:"started_at,omitempty"`
	BaseCommit       string           `json:"base_commit,omitempty"`
	UpdatedAt        time.Time        `json:"updated_at"`
}
type reviewRunner func(dir, name string, args ...string) ([]byte, error)

func reviewRun(dir, name string, args ...string) ([]byte, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 45*time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, name, args...)
	cmd.Dir = dir
	var out, stderr bytes.Buffer
	cmd.Stdout, cmd.Stderr = &out, &stderr
	if err := cmd.Run(); err != nil {
		return out.Bytes(), fmt.Errorf("%s: %w: %s", name, err, strings.TrimSpace(stderr.String()))
	}
	return out.Bytes(), nil
}

func canonicalReviewDir(path string) (string, error) {
	if !filepath.IsAbs(path) {
		return "", errors.New("absolute project and tracker paths required")
	}
	p, err := filepath.EvalSymlinks(path)
	if err != nil {
		return "", err
	}
	st, err := os.Stat(p)
	if err != nil {
		return "", err
	}
	if !st.IsDir() {
		return "", errors.New("expected directory")
	}
	return p, nil
}
func reviewRelative(path string) bool {
	p := filepath.Clean(path)
	return path != "" && p != "." && !filepath.IsAbs(p) && p != ".." && !strings.HasPrefix(p, ".."+string(filepath.Separator)) && p != ".git" && !strings.HasPrefix(p, ".git/")
}
func validateReview(s reviewSubmission) error {
	p := s.Proposal
	if s.Version != 1 || s.Key == "" || p.ID == "" || p.Revision < 1 || p.Status != "accepted" || p.AcceptedAt == nil {
		return errors.New("versioned, explicitly accepted proposal and retry key required")
	}
	if s.Key != fmt.Sprintf("%s:%d", p.ID, p.Revision) {
		return errors.New("retry key must identify the accepted proposal revision")
	}
	project, err := canonicalReviewDir(s.Project)
	if err != nil {
		return err
	}
	tracker, err := canonicalReviewDir(s.Tracker)
	if err != nil {
		return err
	}
	if project != s.Project || tracker != s.Tracker || p.Project != project || p.Tracker != tracker {
		return errors.New("proposal project/tracker mismatch")
	}
	if rel, err := filepath.Rel(tracker, project); err != nil || rel == ".." || strings.HasPrefix(rel, "../") {
		return errors.New("tracker must belong to project or an enclosing workspace")
	}
	if _, err := os.Stat(filepath.Join(tracker, ".beads")); err != nil {
		return fmt.Errorf("tracker unavailable: %w", err)
	}
	if p.Priority < 0 || p.Priority > 4 || p.BudgetTokens <= 0 {
		return errors.New("approved priority and positive token budget required")
	}
	if p.Change == "" || len(p.Scope) == 0 || len(p.Checklist) == 0 {
		return errors.New("approved change, scope and retest checklist required")
	}
	for _, path := range p.Scope {
		if !reviewRelative(path) {
			return fmt.Errorf("invalid approved scope: %s", path)
		}
	}
	for _, g := range p.Guidance {
		if !reviewRelative(g.Path) || g.Text == "" || g.Scope == "" || g.Rationale == "" || g.BaseRevision == "" {
			return errors.New("guidance needs a scoped path, text, rationale and base revision")
		}
	}
	if len(p.Build.Command) == 0 || len(p.Build.Checks) == 0 || !reviewRelative(p.Build.Binary) {
		return errors.New("reviewed build command, checks and binary required")
	}
	for _, command := range p.Build.Checks {
		if len(command) == 0 {
			return errors.New("empty build check")
		}
	}
	return nil
}
func reviewWrite(path string, v any) error {
	data, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		return err
	}
	f, err := os.CreateTemp(filepath.Dir(path), ".receipt-")
	if err != nil {
		return err
	}
	tmp := f.Name()
	defer os.Remove(tmp)
	if _, err = f.Write(data); err == nil {
		err = f.Sync()
	}
	closeErr := f.Close()
	if err != nil {
		return err
	}
	if closeErr != nil {
		return closeErr
	}
	if err = os.Rename(tmp, path); err != nil {
		return err
	}
	d, err := os.Open(filepath.Dir(path))
	if err != nil {
		return err
	}
	defer d.Close()
	return d.Sync()
}
func reviewLock(path string, nonblock bool) (*os.File, error) {
	f, err := os.OpenFile(path, os.O_CREATE|os.O_RDWR, 0600)
	if err != nil {
		return nil, err
	}
	flags := syscall.LOCK_EX
	if nonblock {
		flags |= syscall.LOCK_NB
	}
	if err = syscall.Flock(int(f.Fd()), flags); err != nil {
		f.Close()
		return nil, err
	}
	return f, nil
}

// submitReview persists before side effects. Stable Beads ID and Intercore scope
// reconcile a crash after creation; an uncertain worker launch is never retried.
func submitReview(base string, s reviewSubmission, run reviewRunner) (reviewReceipt, string, error) {
	var r reviewReceipt
	if err := validateReview(s); err != nil {
		return r, "", err
	}
	keyHash := sha256.Sum256([]byte(s.Project + "\n" + s.Key))
	dir := filepath.Join(base, hex.EncodeToString(keyHash[:16]))
	if err := os.MkdirAll(dir, 0700); err != nil {
		return r, "", err
	}
	lock, err := reviewLock(filepath.Join(dir, "submission.lock"), false)
	if err != nil {
		return r, "", err
	}
	defer lock.Close()
	path := filepath.Join(dir, "receipt.json")
	raw, _ := json.Marshal(s)
	sum := sha256.Sum256(raw)
	hash := hex.EncodeToString(sum[:])
	if data, err := os.ReadFile(path); err == nil {
		if err = json.Unmarshal(data, &r); err != nil {
			return r, path, err
		}
		if r.Hash != hash {
			return r, path, errors.New("retry key reused with different approved content")
		}
		return r, path, nil
	} else if !os.IsNotExist(err) {
		return r, path, err
	}
	r = reviewReceipt{Request: s, Hash: hash, ID: s.Proposal.ID, Project: s.Project, Tracker: s.Tracker, ProposalID: s.Proposal.ID, ProposalRevision: s.Proposal.Revision, Status: "queued", UpdatedAt: time.Now().UTC()}
	if err = reviewWrite(path, r); err != nil {
		return r, path, err
	}
	return r, path, nil
}

func prepareReview(r *reviewReceipt, path string, run reviewRunner) error {
	s := r.Request
	bd := func(args ...string) ([]byte, error) { return run(s.Tracker, "bd", args...) }
	prefix, err := bd("config", "get", "issue_prefix")
	if err != nil {
		return err
	}
	p := strings.TrimSpace(string(prefix))
	if !regexp.MustCompile(`^[a-zA-Z0-9_-]+$`).MatchString(p) {
		return errors.New("tracker did not return a valid issue prefix")
	}
	if r.WorkID == "" {
		r.WorkID = p + "-review-" + filepath.Base(filepath.Dir(path))[:16]
		if err = reviewWrite(path, r); err != nil {
			return err
		}
	}
	var issues []struct {
		ID          string `json:"id"`
		ExternalRef string `json:"external_ref"`
	}
	// Listing must succeed; an unavailable tracker must never look like no work.
	data, err := bd("list", "--all", "--limit", "0", "--json")
	if err != nil {
		return err
	}
	if err = json.Unmarshal(data, &issues); err != nil {
		return err
	}
	external := "autarch-review:" + r.Hash
	found := false
	for _, issue := range issues {
		if issue.ID == r.WorkID {
			if issue.ExternalRef != external {
				return errors.New("stable work ID collision")
			}
			found = true
		}
	}
	if !found {
		body, _ := json.MarshalIndent(s.Proposal, "", "  ")
		bodyPath := filepath.Join(filepath.Dir(path), "approved-proposal.json")
		if err = os.WriteFile(bodyPath, body, 0600); err != nil {
			return err
		}
		args := []string{"create", "--id", r.WorkID, "--title", s.Proposal.Outcome, "--body-file", bodyPath, "--priority", fmt.Sprint(s.Proposal.Priority), "--external-ref", external, "--labels", "autarch-review-managed", "--json"}
		if len(s.Proposal.Dependencies) > 0 {
			deps := []string{}
			for _, id := range s.Proposal.Dependencies {
				deps = append(deps, "blocks:"+id)
			}
			args = append(args, "--deps", strings.Join(deps, ","))
		}
		if _, err = bd(args...); err != nil {
			return err
		}
	}
	if s.Proposal.Priority > 2 {
		r.Status = "deferred"
		r.Reason = "Accepted low-priority work is retained for later scheduling"
		return reviewWrite(path, r)
	}
	for _, dep := range s.Proposal.Dependencies {
		data, err := bd("show", dep, "--json")
		if err != nil {
			return err
		}
		var entries []struct {
			Status string `json:"status"`
		}
		if err = json.Unmarshal(data, &entries); err != nil {
			return err
		}
		if len(entries) != 1 || entries[0].Status != "closed" {
			r.Status = "deferred"
			r.Reason = "Waiting for dependency " + dep
			return reviewWrite(path, r)
		}
	}
	if r.RunID == "" {
		data, err := run(s.Project, "ic", "--json", "run", "list", "--scope="+external)
		if err != nil {
			return err
		}
		var runs []struct {
			ID      string `json:"id"`
			Project string `json:"project_dir"`
		}
		if err = json.Unmarshal(data, &runs); err != nil {
			return err
		}
		if len(runs) > 1 {
			return errors.New("ambiguous execution runs; reconciliation required")
		}
		if len(runs) == 1 {
			if runs[0].Project != s.Project {
				return errors.New("execution run project mismatch")
			}
			r.RunID = runs[0].ID
		} else {
			data, err = run(s.Project, "ic", "--json", "run", "create", "--project="+s.Project, "--goal="+s.Proposal.Outcome, "--scope-id="+external, "--token-budget="+fmt.Sprint(s.Proposal.BudgetTokens), "--budget-enforce", "--max-agents=1", "--max-dispatches=1")
			if err != nil {
				return err
			}
			var created struct {
				ID string `json:"id"`
			}
			if err = json.Unmarshal(data, &created); err != nil {
				return err
			}
			if created.ID == "" {
				return errors.New("Intercore returned no stable run ID")
			}
			r.RunID = created.ID
		}
		if err = reviewWrite(path, r); err != nil {
			return err
		}
	}
	r.Status = "queued"
	r.Reason = "Accepted work is eligible for governed execution"
	return reviewWrite(path, r)
}

func reviewBaseDir() (string, error) {
	home, err := os.UserHomeDir()
	return filepath.Join(home, ".clavain", "reviews"), err
}
func cmdReview(args []string) error {
	if len(args) == 0 {
		return errors.New("usage: clavain-cli review submit|status|work")
	}
	if args[0] == "work" {
		if len(args) != 2 {
			return errors.New("review work requires receipt path")
		}
		return workReview(args[1])
	}
	if args[0] != "submit" && args[0] != "status" {
		return errors.New("unknown review operation")
	}
	var s reviewSubmission
	if err := json.NewDecoder(io.LimitReader(os.Stdin, 2<<20)).Decode(&s); err != nil {
		return err
	}
	base, err := reviewBaseDir()
	if err != nil {
		return err
	}
	r, path, err := submitReview(base, s, reviewRun)
	if err != nil {
		return err
	}
	if args[0] != "submit" && args[0] != "status" {
		return errors.New("unknown review operation")
	}
	// A detached supervisor owns execution. Repeated status polls can restart a
	// queued/deferred supervisor; its lifetime lock prevents duplicate launches.
	if r.Status == "queued" || r.Status == "deferred" || r.Status == "running" || (r.Status == "blocked" && r.DispatchID == "") {
		exe, err := os.Executable()
		if err != nil {
			return err
		}
		cmd := exec.Command(exe, "review", "work", path)
		cmd.Dir = s.Project
		cmd.SysProcAttr = &syscall.SysProcAttr{Setsid: true}
		log, err := os.OpenFile(filepath.Join(filepath.Dir(path), "supervisor.log"), os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0600)
		if err != nil {
			return err
		}
		cmd.Stdout, cmd.Stderr = log, log
		err = cmd.Start()
		log.Close()
		if err != nil {
			return err
		}
		_ = cmd.Process.Release()
	}
	return json.NewEncoder(os.Stdout).Encode(r)
}
