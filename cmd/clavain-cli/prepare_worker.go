package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"time"
)

func prepareCompact(raw []byte) []byte {
	var b bytes.Buffer
	if json.Compact(&b, raw) != nil {
		return nil
	}
	return b.Bytes()
}

type prepareSpec struct {
	Change       string      `json:"change"`
	Scope        []string    `json:"scope"`
	Tracker      string      `json:"tracker"`
	Dependencies []string    `json:"dependencies"`
	Build        reviewBuild `json:"build"`
	BudgetTokens int         `json:"budget_tokens"`
	Experience   []string    `json:"experience"`
	Checklist    []string    `json:"checklist"`
}
type prepareBundle struct {
	Plan              string            `json:"plan"`
	Specification     *prepareSpec      `json:"specification"`
	SynthesisID       string            `json:"synthesis_id"`
	SynthesisRevision int               `json:"synthesis_revision"`
	SynthesisHash     string            `json:"synthesis_hash"`
	Sources           map[string]string `json:"sources"`
}
type preparePhase struct {
	Role            string          `json:"role"`
	Intent          bool            `json:"launch_intent"`
	DispatchID      string          `json:"dispatch_id,omitempty"`
	PID             int             `json:"pid,omitempty"`
	StartedAt       time.Time       `json:"started_at"`
	UsageTokens     int             `json:"usage_tokens"`
	UsageComplete   bool            `json:"usage_complete"`
	AccountingError string          `json:"accounting_error,omitempty"`
	Overshoot       int             `json:"overshoot"`
	Model           string          `json:"model,omitempty"`
	Route           json.RawMessage `json:"route,omitempty"`
	Digest          string          `json:"digest,omitempty"`
	Complete        bool            `json:"complete"`
}
type prepareAttempt struct {
	Number       int            `json:"number"`
	Planner      preparePhase   `json:"planner"`
	Reviewer     preparePhase   `json:"reviewer"`
	Bundle       *prepareBundle `json:"bundle,omitempty"`
	BundleDigest string         `json:"bundle_digest,omitempty"`
	Verdict      string         `json:"verdict,omitempty"`
}
type prepareReceipt struct {
	Version      int               `json:"version"`
	ID           string            `json:"id"`
	Hash         string            `json:"hash"`
	Request      prepareRequest    `json:"request"`
	Ratification ratifyReceipt     `json:"ratification"`
	Status       string            `json:"status"`
	Reason       string            `json:"reason,omitempty"`
	Owner        string            `json:"owner"`
	RunID        string            `json:"run_id,omitempty"`
	KernelDB     string            `json:"kernel_db,omitempty"`
	PolicySource string            `json:"policy_source"`
	PolicyHash   string            `json:"policy_hash"`
	Sources      map[string]string `json:"sources"`
	Attempts     []prepareAttempt  `json:"attempts"`
	BundleDigest string            `json:"bundle_digest,omitempty"`
	UpdatedAt    time.Time         `json:"updated_at"`
}

// Resolve once before creating any run. A later project-local database must
// never redirect a resumed preparation's accounting or route receipts.
func prepareKernelPath(project string) (string, error) {
	for dir := project; ; dir = filepath.Dir(dir) {
		candidate := filepath.Join(dir, ".clavain", "intercore.db")
		if info, err := os.Stat(candidate); err == nil && info.Mode().IsRegular() {
			return filepath.EvalSymlinks(candidate)
		} else if err != nil && !os.IsNotExist(err) {
			return "", err
		}
		if filepath.Dir(dir) == dir {
			break
		}
	}
	return "", errors.New("existing Intercore database required for preparation")
}

func prepareRunner(r prepareReceipt) reviewRunner {
	return func(dir, name string, args ...string) ([]byte, error) {
		if name != "ic" {
			return reviewRun(dir, name, args...)
		}
		if !filepath.IsAbs(r.KernelDB) {
			return nil, errors.New("preparation kernel database is not pinned")
		}
		info, err := os.Stat(r.KernelDB)
		if err != nil {
			return nil, err
		}
		if !info.Mode().IsRegular() {
			return nil, errors.New("preparation kernel database is not a file")
		}
		return reviewRun(filepath.Dir(r.KernelDB), name, append([]string{"--db=" + r.KernelDB}, args...)...)
	}
}

func prepareUsage(r prepareReceipt) int {
	n := 0
	for _, a := range r.Attempts {
		n += a.Planner.UsageTokens + a.Reviewer.UsageTokens
	}
	return n
}
func checkPrepareSources(project string, sources map[string]string) error {
	for p, want := range sources {
		got, _, e := prepareFileHash(project, p)
		if e != nil {
			return e
		}
		if got != want {
			return fmt.Errorf("canonical source changed: %s", p)
		}
	}
	return nil
}

// Status reads an existing receipt only: no directory creation or supervisor spawn.
func readPrepare(base string, s prepareRequest) (r prepareReceipt, path string, err error) {
	if err = validatePrepare(s); err != nil {
		return
	}
	dir, _ := preparePaths(base, s)
	path = filepath.Join(dir, "preparation.json")
	data, e := os.ReadFile(path)
	if e != nil {
		return r, path, e
	}
	if err = json.Unmarshal(data, &r); err != nil {
		return
	}
	raw, _ := json.Marshal(s)
	if r.Hash != prepareHash(raw) {
		err = errors.New("preparation retry key reused with different content")
	}
	return
}
func submitPrepare(base string, s prepareRequest) (r prepareReceipt, path string, err error) {
	if err = validatePrepare(s); err != nil {
		return
	}
	if s.BudgetTokens <= 0 || s.Proposal.Outcome == "" || len(s.Proposal.Scope) == 0 || len(s.Sources) == 0 {
		return r, "", errors.New("explicit positive preparation budget, outcome, scope and source bindings required")
	}
	dir, ratifyPath := preparePaths(base, s)
	data, e := os.ReadFile(ratifyPath)
	if e != nil {
		return r, "", fmt.Errorf("persisted ratification required: %w", e)
	}
	lock, e := reviewLock(filepath.Join(dir, "submission.lock"), false)
	if e != nil {
		return r, "", e
	}
	defer lock.Close()
	if old, p, e := readPrepare(base, s); e == nil {
		return old, p, nil
	} else if !os.IsNotExist(e) {
		return r, p, e
	}
	var ratified ratifyReceipt
	if e = json.Unmarshal(data, &ratified); e != nil {
		return r, "", e
	}
	raw, _ := json.Marshal(s)
	hash := prepareHash(raw)
	if ratified.Status != "persisted" || ratified.Hash != hash || ratified.Commit == "" {
		return r, "", errors.New("matching persisted ratification receipt required")
	}
	sources := map[string]string{}
	for p, h := range s.Sources {
		sources[p] = h
	}
	for p, f := range ratified.Files {
		if old, ok := sources[p]; ok && old != f.Old {
			return r, "", errors.New("ratification source provenance mismatch")
		}
		sources[p] = f.New
	}
	if err = checkPrepareSources(s.Project, sources); err != nil {
		return
	}
	script, e := reviewDispatchScript()
	if e != nil {
		return r, "", e
	}
	policy := os.Getenv("CLAVAIN_ROUTING_POLICY")
	if policy == "" {
		policy = filepath.Join(filepath.Dir(filepath.Dir(script)), "config", "routing.yaml")
	}
	policy, e = filepath.Abs(policy)
	if e != nil {
		return r, "", e
	}
	policyData, e := os.ReadFile(policy)
	if e != nil {
		return r, "", e
	}
	r = prepareReceipt{Version: 1, ID: hash, Hash: hash, Request: s, Ratification: ratified, Status: "accepted", Owner: "Clavain", PolicySource: policy, PolicyHash: prepareHash(policyData), Sources: sources, UpdatedAt: time.Now().UTC()}
	path = filepath.Join(dir, "preparation.json")
	err = reviewWrite(path, r)
	return
}
func launchPrepare(path string) error {
	// The lifetime lock is checked here and acquired again by the child. A loser
	// never calls a model. Durable phase launch intent resolves a crashed parent.
	dir := filepath.Dir(path)
	lock, err := reviewLock(filepath.Join(dir, "worker.lock"), true)
	if err != nil {
		if reviewLockBusy(err) {
			return nil
		}
		return err
	}
	// Release before spawn: otherwise the child can lose to its own parent.
	lock.Close()
	exe, err := os.Executable()
	if err != nil {
		return err
	}
	log, err := os.OpenFile(filepath.Join(dir, "supervisor.log"), os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0600)
	if err != nil {
		return err
	}
	defer log.Close()
	cmd := exec.Command(exe, "prepare", "work", path)
	cmd.SysProcAttr = reviewSupervisorAttr()
	cmd.Stdout, cmd.Stderr = log, log
	if err = cmd.Start(); err != nil {
		return err
	}
	return cmd.Process.Release()
}
func prepareRoute(r prepareReceipt, role, producer, contextPath string) (map[string]any, error) {
	args := []string{"--json", "route", "dispatch", "--policy=" + r.PolicySource, "--role=" + role, "--context-file=" + contextPath}
	if producer != "" {
		args = append(args, "--producer-identity="+producer)
	}
	data, err := prepareRunner(r)(r.Request.Project, "ic", args...)
	if err != nil {
		return nil, err
	}
	var route map[string]any
	if err = json.Unmarshal(data, &route); err != nil {
		return nil, err
	}
	if route["policy_hash"] != r.PolicyHash || route["frontier_required"] != true {
		return nil, errors.New("frontier planning/routing policy binding unavailable")
	}
	return route, nil
}
func runPreparePhase(r *prepareReceipt, a *prepareAttempt, p *preparePhase, path, producer string) error {
	dir := filepath.Join(filepath.Dir(path), fmt.Sprintf("attempt-%d", a.Number), p.Role)
	if err := os.MkdirAll(dir, 0700); err != nil {
		return err
	}
	if p.Complete {
		return nil
	}
	persist := func() error { r.UpdatedAt = time.Now().UTC(); return reviewWrite(path, r) }
	contextPath := filepath.Join(dir, "decision.json")
	decision := map[string]any{"reasons": []string{"foundational-invariants", "broad-consequences", "difficult-verification"}, "rationale": "Prepare and independently review a plan bound to exact human guidance; implementation remains a separate human action.", "investigation_active": true}
	if err := reviewWrite(contextPath, decision); err != nil {
		return err
	}
	remaining := r.Request.BudgetTokens - (prepareUsage(*r) - p.UsageTokens)
	if remaining <= 0 {
		return errors.New("approved preparation budget exhausted")
	}
	if !p.Intent {
		route, err := prepareRoute(*r, p.Role, producer, contextPath)
		if err != nil {
			return err
		}
		profile, ok := route["profile"].(map[string]any)
		if !ok {
			return errors.New("missing frontier profile")
		}
		backend, _ := profile["backend"].(string)
		if backend != "codex" && backend != "claude" {
			return errors.New("accounting-capable backend required")
		}
		if runtime.GOOS != "darwin" {
			return errors.New("local preparation pilot requires the macOS scope sandbox")
		}
		if err = checkPrepareSources(r.Request.Project, r.Sources); err != nil {
			return err
		}
		source, _ := json.MarshalIndent(r.Request, "", "  ")
		prompt := "Prepare a technical implementation plan reflecting ALL accepted guidance verbatim. Read authoritative project files and challenge contradictions explicitly. You may only read source files. Do not implement, commit, ratify, invoke execution workflows, call agents or start background processes. Return ONLY a JSON object with plan (Markdown string) and specification (null if no runnable implementation specification can be established). A specification has change, scope, tracker, dependencies, build {command,checks,binary}, budget_tokens (proposed implementation allowance, never approval), experience, checklist. Include dependencies, verification, experience examples and retest criteria. Preserve exact rulings, corrections and coverage gaps.\n\n" + string(source)
		if p.Role == "plan-review" {
			bundle, _ := json.MarshalIndent(a.Bundle, "", "  ")
			prompt = "Independently review this EXACT preparation bundle against its accepted guidance and canonical sources. Read only. Do not implement, mutate files, dispatch agents or run execution. Report deficiencies and end with VERDICT: PASS or VERDICT: BLOCKED. Review includes the complete specification and its proposed implementation budget.\n\nAccepted synthesis:\n" + string(source) + "\n\nBundle:\n" + string(bundle)
		} else if len(r.Attempts) > 1 {
			prior := r.Attempts[len(r.Attempts)-2]
			priorDir := filepath.Join(filepath.Dir(path), fmt.Sprintf("attempt-%d", prior.Number), "plan-review", "response.md")
			review, _ := os.ReadFile(priorDir)
			prompt += "\n\nPrevious independent review; address every deficiency:\n" + string(review)
		}
		promptPath := filepath.Join(dir, "prompt.md")
		if err = os.WriteFile(promptPath, []byte(prompt), 0600); err != nil {
			return err
		}
		script, err := reviewDispatchScript()
		if err != nil {
			return err
		}
		cmd := governedReviewCommand(script, r.Request.Project, promptPath, filepath.Join(dir, "response.md"), "autarch-prepare", p.Role)
		cmd.Args = append(cmd.Args, "-s", "read-only", "--plan", promptPath)
		if producer != "" {
			cmd.Args = append(cmd.Args, "--producer-identity", producer)
		}
		sandbox := "(version 1)\n(allow default)\n(deny file-write* (subpath " + strconv.Quote(r.Request.Project) + "))\n"
		// Governed dispatch records to the existing kernel DB. Only its three
		// SQLite files are writable inside the otherwise read-only project.
		for _, suffix := range []string{"", "-wal", "-shm"} {
			sandbox += "(allow file-write* (literal " + strconv.Quote(r.KernelDB+suffix) + "))\n"
		}
		sandboxPath := filepath.Join(dir, "scope.sb")
		if err = os.WriteFile(sandboxPath, []byte(sandbox), 0600); err != nil {
			return err
		}
		idPath := filepath.Join(dir, "dispatch-id")
		wrapper := "#!/usr/bin/env bash\nset -euo pipefail\ncd " + shellReviewQuote(r.Request.Project) + "\nfor ((i=0;i<100;i++)); do [[ -s " + shellReviewQuote(idPath) + " ]] && break; sleep 0.1; done\n[[ -s " + shellReviewQuote(idPath) + " ]] || exit 1\nexport CLAVAIN_DISPATCH_ID=\"$(cat " + shellReviewQuote(idPath) + ")\"\n"
		for k, v := range map[string]string{"CLAVAIN_REQUIRE_USAGE": "1", "CLAVAIN_TOKEN_BUDGET": fmt.Sprint(remaining), "CLAVAIN_REVIEW_EVENTS": filepath.Join(dir, "usage.jsonl"), "CLAVAIN_RUN_ID": r.RunID, "CLAVAIN_INTERCORE_DB": r.KernelDB, "CLAVAIN_ROUTING_POLICY": r.PolicySource, "CLAVAIN_DECISION_CONTEXT": contextPath} {
			wrapper += "export " + k + "=" + shellReviewQuote(v) + "\n"
		}
		wrapper += "trap 'trap \"\" TERM; kill -TERM -- -$$ 2>/dev/null; exit 143' TERM INT\nset +e\n/usr/bin/sandbox-exec -f " + shellReviewQuote(sandboxPath)
		for _, arg := range cmd.Args {
			wrapper += " " + shellReviewQuote(arg)
		}
		wrapper += " > " + shellReviewQuote(filepath.Join(dir, "worker.log")) + " 2>&1 &\nworker=$!\nwait \"$worker\"\nrc=$?\nprintf '%s' \"$rc\" > " + shellReviewQuote(filepath.Join(dir, "exit-code")) + "\nexit \"$rc\"\n"
		wrapperPath := filepath.Join(dir, "launch.sh")
		if err = os.WriteFile(wrapperPath, []byte(wrapper), 0700); err != nil {
			return err
		}
		p.Intent = true
		p.StartedAt = time.Now().UTC()
		if err = persist(); err != nil {
			return err
		}
		data, err := prepareRunner(*r)(r.Request.Project, "ic", "--json", "dispatch", "spawn", "--type="+backend, "--project="+r.Request.Project, "--run-id="+r.RunID, "--scope-id="+r.RunID, "--max-active-per-run=1", "--max-agents-per-run=6", "--budget-enforce", "--prompt-file="+promptPath, "--output="+filepath.Join(dir, "response.md"), "--name=autarch-prepare", "--dispatch-sh="+wrapperPath)
		if err != nil {
			return fmt.Errorf("model launch uncertain; no replacement authorized: %w; kernel response: %s", err, strings.TrimSpace(string(data)))
		}
		var spawned struct {
			ID  string `json:"id"`
			PID int    `json:"pid"`
		}
		if err = json.Unmarshal(data, &spawned); err != nil {
			return err
		}
		if spawned.ID == "" {
			return errors.New("missing launched dispatch identity")
		}
		p.DispatchID, p.PID = spawned.ID, spawned.PID
		if err = persist(); err != nil {
			return err
		}
		if err = os.WriteFile(idPath, []byte(p.DispatchID), 0600); err != nil {
			return err
		}
	}
	if p.DispatchID == "" {
		return errors.New("launch intent has no dispatch identity; Clavain reconciliation required")
	}
	cancellationReason := ""
	for {
		usage, _ := readReviewUsage(filepath.Join(dir, "usage.jsonl"), p.DispatchID, false)
		p.UsageTokens = usage.Tokens
		if time.Now().After(p.StartedAt.Add(15 * time.Minute)) {
			cancellationReason = "15-minute preparation watchdog expired"
		}
		if p.UsageTokens >= remaining {
			cancellationReason = "approved preparation budget exhausted"
		}
		data, err := prepareRunner(*r)(r.Request.Project, "ic", "--json", "dispatch", "poll", p.DispatchID)
		if err != nil {
			return err
		}
		var d struct {
			Status  string `json:"status"`
			Project string `json:"project_dir"`
			PID     int    `json:"pid"`
		}
		if err = json.Unmarshal(data, &d); err != nil {
			return err
		}
		if d.Project != r.Request.Project {
			return errors.New("preparation dispatch project mismatch")
		}
		p.PID = d.PID
		if d.Status == "running" || d.Status == "spawned" {
			if cancellationReason != "" {
				rr := reviewReceipt{Project: r.Request.Project, DispatchID: p.DispatchID, WorkerPID: p.PID}
				if err := stopReviewWorker(rr, dir); err != nil {
					p.AccountingError = err.Error()
					_ = persist()
					return err
				}
			}
			_ = persist()
			time.Sleep(time.Second)
			continue
		}
		// A completed phase discovered after restart is consumed even when the
		// supervisor was absent longer than the watchdog; no live worker remains.
		if d.Status == "completed" && p.UsageTokens < remaining {
			cancellationReason = ""
		}
		rr := reviewReceipt{Project: r.Request.Project, DispatchID: p.DispatchID, Request: reviewSubmission{Proposal: reviewProposal{BudgetTokens: remaining}}}
		err = settleReviewUsage(&rr, dir, prepareRunner(*r))
		p.UsageTokens, p.UsageComplete, p.Overshoot = rr.UsageTokens, rr.UsageComplete, rr.BudgetOvershoot
		if err != nil {
			p.AccountingError = err.Error()
			_ = persist()
			return err
		}
		p.AccountingError = ""
		if !p.UsageComplete {
			p.AccountingError = "terminal usage evidence incomplete"
		}
		if err = persist(); err != nil {
			return err
		}
		if cancellationReason != "" {
			return errors.New(cancellationReason)
		}
		if !p.UsageComplete || p.UsageTokens >= remaining {
			return errors.New("complete accounting and remaining approved preparation budget required")
		}
		exit, e := os.ReadFile(filepath.Join(dir, "exit-code"))
		if e != nil || strings.TrimSpace(string(exit)) != "0" || d.Status != "completed" {
			return errors.New("preparation worker failed; retained usage and artifacts")
		}
		break
	}
	data, err := prepareRunner(*r)(r.Request.Project, "ic", "--json", "route", "list", "--dispatch="+p.DispatchID, "--limit=20")
	if err != nil {
		return err
	}
	var records []struct {
		PolicyHash string          `json:"policy_hash"`
		Model      string          `json:"selected_model"`
		Context    json.RawMessage `json:"context_json"`
	}
	if err = json.Unmarshal(data, &records); err != nil {
		return err
	}
	var original []json.RawMessage
	if err = json.Unmarshal(data, &original); err != nil {
		return err
	}
	for i := 0; i < len(records); {
		raw := records[i].Context
		var encoded string
		if json.Unmarshal(raw, &encoded) == nil {
			raw = []byte(encoded)
		}
		var state struct {
			Terminal bool `json:"terminal"`
		}
		if json.Unmarshal(raw, &state) != nil || !state.Terminal {
			records = append(records[:i], records[i+1:]...)
		} else {
			i++
		}
	}
	if len(records) != 1 || records[0].PolicyHash != r.PolicyHash {
		return errors.New("missing or mismatched actual route receipt")
	}
	var encoded string
	raw := records[0].Context
	if json.Unmarshal(raw, &encoded) == nil {
		raw = []byte(encoded)
	}
	var context struct {
		Terminal  bool   `json:"terminal"`
		Role      string `json:"role"`
		Producer  string `json:"producer_identity"`
		Execution struct {
			Model string `json:"model"`
		} `json:"execution"`
		Result struct {
			Exit    int    `json:"exit_code"`
			Failure string `json:"failure_class"`
		} `json:"result"`
		Route struct {
			Frontier bool   `json:"frontier_required"`
			Hash     string `json:"policy_hash"`
		} `json:"resolved_route"`
	}
	if err = json.Unmarshal(raw, &context); err != nil {
		return err
	}
	if !context.Terminal || context.Role != p.Role || context.Producer != producer || context.Result.Exit != 0 || context.Result.Failure != "success" || !context.Route.Frontier || context.Route.Hash != r.PolicyHash || context.Execution.Model != records[0].Model || records[0].Model == "" || records[0].Model == producer {
		return errors.New("actual independent frontier route did not complete successfully")
	}
	p.Model = records[0].Model
	for _, entry := range original {
		var candidate struct {
			Context json.RawMessage `json:"context_json"`
		}
		if json.Unmarshal(entry, &candidate) == nil && bytes.Equal(candidate.Context, records[0].Context) {
			p.Route, _ = json.Marshal([]json.RawMessage{entry})
			break
		}
	}
	if len(p.Route) == 0 {
		return errors.New("actual route record could not be retained")
	}
	response, err := os.ReadFile(filepath.Join(dir, "response.md"))
	if err != nil {
		return err
	}
	p.Digest = prepareHash(response)
	p.Complete = true
	return persist()
}

func workPrepare(path string) error {
	dir := filepath.Dir(path)
	lock, err := reviewLock(filepath.Join(dir, "worker.lock"), true)
	if err != nil {
		if reviewLockBusy(err) {
			return nil
		}
		return err
	}
	defer lock.Close()
	var r prepareReceipt
	data, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	if err = json.Unmarshal(data, &r); err != nil {
		return err
	}
	requestBytes, _ := json.Marshal(r.Request)
	if r.Hash != prepareHash(requestBytes) || r.Ratification.Hash != r.Hash {
		return errors.New("preparation request/ratification integrity mismatch")
	}
	if r.Status == "reviewed" {
		return nil
	}
	save := func(status, reason string) error {
		r.Status, r.Reason, r.UpdatedAt = status, reason, time.Now().UTC()
		return reviewWrite(path, r)
	}
	blocked := func(err error) error {
		if e := save("blocked", err.Error()); e != nil {
			return e
		}
		return err
	}
	if r.KernelDB == "" {
		if r.RunID != "" || len(r.Attempts) != 0 {
			return blocked(errors.New("existing preparation lacks pinned kernel database; owner reconciliation required"))
		}
		r.KernelDB, err = prepareKernelPath(r.Request.Project)
		if err != nil {
			return blocked(err)
		}
		if err = reviewWrite(path, r); err != nil {
			return err
		}
	}
	policy, err := os.ReadFile(r.PolicySource)
	if err != nil {
		return blocked(err)
	}
	if prepareHash(policy) != r.PolicyHash {
		return blocked(errors.New("routing policy changed"))
	}
	if err = checkPrepareSources(r.Request.Project, r.Sources); err != nil {
		return save("needs_changes", err.Error())
	}
	if r.RunID == "" {
		scope := "autarch-prepare:" + prepareHash([]byte(r.Request.Project+"\n"+r.Request.Key))
		data, e := prepareRunner(r)(r.Request.Project, "ic", "--json", "run", "list", "--scope="+scope)
		if e != nil {
			return blocked(e)
		}
		var runs []struct {
			ID      string `json:"id"`
			Project string `json:"project_dir"`
		}
		if e = json.Unmarshal(data, &runs); e != nil {
			return blocked(e)
		}
		if len(runs) > 1 {
			return blocked(errors.New("ambiguous preparation runs"))
		}
		if len(runs) == 1 {
			if runs[0].Project != r.Request.Project {
				return blocked(errors.New("run project mismatch"))
			}
			r.RunID = runs[0].ID
		} else {
			data, e = prepareRunner(r)(r.Request.Project, "ic", "--json", "run", "create", "--project="+r.Request.Project, "--goal="+r.Request.Proposal.Outcome, "--scope-id="+scope, "--token-budget="+fmt.Sprint(r.Request.BudgetTokens), "--budget-enforce", "--max-agents=6", "--max-dispatches=6")
			if e != nil {
				return blocked(e)
			}
			var run struct {
				ID string `json:"id"`
			}
			if e = json.Unmarshal(data, &run); e != nil {
				return blocked(e)
			}
			r.RunID = run.ID
		}
		if r.RunID == "" {
			return blocked(errors.New("missing preparation run identity"))
		}
		if err = save("accepted", ""); err != nil {
			return err
		}
	}
	for {
		if len(r.Attempts) == 0 || r.Attempts[len(r.Attempts)-1].Verdict == "blocked" {
			if len(r.Attempts) >= 3 {
				return save("needs_changes", "Three independent planning/review attempts exhausted")
			}
			r.Attempts = append(r.Attempts, prepareAttempt{Number: len(r.Attempts) + 1, Planner: preparePhase{Role: "planning"}, Reviewer: preparePhase{Role: "plan-review"}})
		}
		a := &r.Attempts[len(r.Attempts)-1]
		if err = save("planning", ""); err != nil {
			return err
		}
		if err = runPreparePhase(&r, a, &a.Planner, path, ""); err != nil {
			return blocked(err)
		}
		attemptDir := filepath.Join(dir, fmt.Sprintf("attempt-%d", a.Number))
		if a.Bundle == nil {
			raw, e := os.ReadFile(filepath.Join(attemptDir, "planning", "response.md"))
			if e != nil {
				return blocked(e)
			}
			if prepareHash(raw) != a.Planner.Digest {
				return blocked(errors.New("planner output changed"))
			}
			var authored struct {
				Plan          string       `json:"plan"`
				Specification *prepareSpec `json:"specification"`
			}
			if e = json.Unmarshal(raw, &authored); e != nil {
				return blocked(fmt.Errorf("planner must return exact JSON bundle: %w", e))
			}
			if strings.TrimSpace(authored.Plan) == "" {
				return blocked(errors.New("empty plan"))
			}
			a.Bundle = &prepareBundle{Plan: authored.Plan, Specification: authored.Specification, SynthesisID: r.Request.Proposal.ID, SynthesisRevision: r.Request.Proposal.Revision, SynthesisHash: r.Hash, Sources: r.Sources}
			bytes, _ := json.Marshal(a.Bundle)
			a.BundleDigest = prepareHash(bytes)
			if err = reviewWrite(filepath.Join(attemptDir, "bundle.json"), a.Bundle); err != nil {
				return blocked(err)
			}
			if err = save("reviewing", ""); err != nil {
				return err
			}
		}
		if err = save("reviewing", ""); err != nil {
			return err
		}
		if err = runPreparePhase(&r, a, &a.Reviewer, path, a.Planner.Model); err != nil {
			return blocked(err)
		}
		raw, e := os.ReadFile(filepath.Join(attemptDir, "plan-review", "response.md"))
		if e != nil {
			return blocked(e)
		}
		if prepareHash(raw) != a.Reviewer.Digest {
			return blocked(errors.New("review output changed"))
		}
		verdict := ""
		for _, line := range strings.Split(string(raw), "\n") {
			switch strings.TrimSpace(line) {
			case "VERDICT: PASS":
				if verdict != "" {
					return blocked(errors.New("ambiguous review verdict"))
				}
				verdict = "pass"
			case "VERDICT: BLOCKED":
				if verdict != "" {
					return blocked(errors.New("ambiguous review verdict"))
				}
				verdict = "blocked"
			}
		}
		if verdict == "" {
			return blocked(errors.New("explicit independent review verdict required"))
		}
		a.Verdict = verdict
		if err = reviewWrite(filepath.Join(attemptDir, "attempt.json"), a); err != nil {
			return blocked(err)
		}
		if verdict == "blocked" {
			if err = save("needs_changes", "Independent review requires a revised plan"); err != nil {
				return err
			}
			continue
		}
		bundle, e := os.ReadFile(filepath.Join(attemptDir, "bundle.json"))
		if e != nil {
			return blocked(e)
		}
		var disk prepareBundle
		if e = json.Unmarshal(bundle, &disk); e != nil {
			return blocked(e)
		}
		canonical, _ := json.Marshal(disk)
		if prepareHash(canonical) != a.BundleDigest {
			return blocked(errors.New("reviewed bundle digest mismatch"))
		}
		if err = checkPrepareSources(r.Request.Project, r.Sources); err != nil {
			return save("needs_changes", err.Error())
		}
		r.BundleDigest = prepareHash([]byte(a.BundleDigest + "\n" + a.Reviewer.Digest + "\n" + prepareHash(a.Reviewer.Route)))
		return save("reviewed", "One outcome has an independently reviewed plan. Implementation requires separate human approval.")
	}
}
