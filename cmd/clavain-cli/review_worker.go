package main

import (
	"bufio"
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
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

func reviewDispatchScript() (string, error) {
	var candidates []string
	for _, key := range []string{"CLAVAIN_DIR", "CLAVAIN_SOURCE_DIR", "CLAUDE_PLUGIN_ROOT"} {
		if dir := os.Getenv(key); dir != "" {
			candidates = append(candidates, filepath.Join(dir, "scripts", "dispatch.sh"))
		}
	}
	if exe, err := os.Executable(); err == nil {
		candidates = append(candidates, filepath.Join(filepath.Dir(exe), "clavain", "scripts", "dispatch.sh"))
		candidates = append(candidates, filepath.Join(filepath.Dir(exe), "..", "scripts", "dispatch.sh"), filepath.Join(filepath.Dir(exe), "..", "..", "scripts", "dispatch.sh"))
	}
	for _, p := range candidates {
		if s, err := os.Stat(p); err == nil && !s.IsDir() {
			return filepath.Abs(p)
		}
	}
	return "", errors.New("Clavain role dispatcher unavailable; configure CLAVAIN_DIR")
}
func governedReviewCommand(script, project, prompt, output, name, role string) *exec.Cmd {
	cmd := exec.Command("bash", script, "--role", role, "-C", project, "--prompt-file", prompt, "-o", output, "--name", name)
	cmd.Dir = project
	return cmd
}
func reviewScopeContains(p reviewProposal, path string) bool {
	for _, scope := range p.Scope {
		if path == filepath.Clean(scope) || strings.HasPrefix(path, filepath.Clean(scope)+"/") {
			return true
		}
	}
	for _, g := range p.Guidance {
		if path == g.Path {
			return true
		}
	}
	return false
}
func reviewCheckScope(r reviewReceipt) error {
	paths, err := reviewRun(r.Project, "git", "diff", "--name-only", "-z", r.BaseCommit)
	if err != nil {
		return err
	}
	untracked, err := reviewRun(r.Project, "git", "ls-files", "--others", "--exclude-standard", "-z")
	if err != nil {
		return err
	}
	for _, path := range strings.Split(string(append(paths, untracked...)), "\x00") {
		if path != "" && !reviewScopeContains(r.Request.Proposal, path) {
			return fmt.Errorf("worker changed unapproved path %s; retained for review", path)
		}
	}
	return nil
}
func guidanceBlocks(r reviewReceipt) map[string][]string {
	blocks := map[string][]string{}
	for i, g := range r.Request.Proposal.Guidance {
		marker := fmt.Sprintf("<!-- autarch-ruling:%s:%d:%d -->", r.ProposalID, r.ProposalRevision, i)
		blocks[g.Path] = append(blocks[g.Path], fmt.Sprintf("\n\n%s\n%s\n\nScope: %s\nRationale: %s\n", marker, g.Text, g.Scope, g.Rationale))
	}
	return blocks
}
func safeReviewPath(project, relative string) (string, error) {
	path := filepath.Join(project, relative)
	existing := path
	for {
		_, err := os.Lstat(existing)
		if err == nil {
			break
		}
		if !os.IsNotExist(err) {
			return "", err
		}
		parent := filepath.Dir(existing)
		if parent == existing {
			return "", err
		}
		existing = parent
	}
	real, err := filepath.EvalSymlinks(existing)
	if err != nil {
		return "", err
	}
	if real != existing {
		return "", fmt.Errorf("approved path contains a symlink: %s", relative)
	}
	if rel, err := filepath.Rel(project, real); err != nil || rel == ".." || strings.HasPrefix(rel, "../") {
		return "", errors.New("approved path leaves project")
	}
	return path, nil
}
func persistReviewGuidance(r reviewReceipt) error {
	blocks := guidanceBlocks(r)
	files := map[string][]byte{}
	// Validate EVERY base before writing ANY document, including repeated paths.
	for _, g := range r.Request.Proposal.Guidance {
		path, err := safeReviewPath(r.Project, g.Path)
		if err != nil {
			return err
		}
		data, err := os.ReadFile(path)
		if err != nil && !os.IsNotExist(err) {
			return err
		}
		suffix := []byte(strings.Join(blocks[g.Path], ""))
		alreadyWritten := len(suffix) > 0 && bytes.HasSuffix(data, suffix)
		if alreadyWritten {
			data = bytes.TrimSuffix(data, suffix)
		}
		sum := sha256.Sum256(data)
		actual := hex.EncodeToString(sum[:])
		if os.IsNotExist(err) || (alreadyWritten && len(data) == 0 && g.BaseRevision == "missing") {
			actual = "missing"
		}
		if actual != g.BaseRevision {
			return fmt.Errorf("guidance base changed: %s; review a revised proposal", g.Path)
		}
		files[g.Path] = data
	}
	for relative, data := range files {
		path := filepath.Join(r.Project, relative)
		for _, block := range blocks[relative] {
			data = append(data, []byte(block)...)
		}
		if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil {
			return err
		}
		f, err := os.CreateTemp(filepath.Dir(path), ".ruling-")
		if err != nil {
			return err
		}
		temporary := f.Name()
		if err = f.Chmod(0644); err == nil {
			_, err = f.Write(data)
		}
		if err == nil {
			err = f.Sync()
		}
		closeErr := f.Close()
		if err != nil {
			os.Remove(temporary)
			return err
		}
		if closeErr != nil {
			os.Remove(temporary)
			return closeErr
		}
		if err = os.Rename(temporary, path); err != nil {
			os.Remove(temporary)
			return err
		}
		directory, err := os.Open(filepath.Dir(path))
		if err != nil {
			return err
		}
		err = directory.Sync()
		directory.Close()
		if err != nil {
			return err
		}

	}
	return nil
}
func verifyReviewGuidance(r reviewReceipt) error {
	for relative, blocks := range guidanceBlocks(r) {
		path, err := safeReviewPath(r.Project, relative)
		if err != nil {
			return err
		}
		data, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		for _, block := range blocks {
			if !strings.Contains(string(data), block) {
				return fmt.Errorf("accepted guidance changed or missing: %s", relative)
			}
		}
	}
	return nil
}
func reviewUsage(path string) (int, error) {
	f, err := os.Open(path)
	if err != nil {
		return 0, err
	}
	defer f.Close()
	scan := bufio.NewScanner(f)
	scan.Buffer(make([]byte, 4096), 8<<20)
	total := 0
	for scan.Scan() {
		var event struct {
			Type  string `json:"type"`
			Usage struct {
				Input  int `json:"input_tokens"`
				Output int `json:"output_tokens"`
			} `json:"usage"`
		}
		if json.Unmarshal(scan.Bytes(), &event) == nil && event.Type == "turn.completed" {
			total += event.Usage.Input + event.Usage.Output
		}
	}
	return total, scan.Err()
}
func updateReviewRoute(r *reviewReceipt) {
	data, err := reviewRun(r.Project, "ic", "--json", "route", "list", "--dispatch="+r.DispatchID, "--limit=1")
	if err != nil {
		return
	}
	var records []struct {
		Model   string          `json:"selected_model"`
		Context json.RawMessage `json:"context_json"`
	}
	if json.Unmarshal(data, &records) != nil || len(records) == 0 {
		return
	}
	r.Model = records[0].Model
	var ctx map[string]any
	raw := records[0].Context
	var encoded string
	if json.Unmarshal(raw, &encoded) == nil {
		raw = []byte(encoded)
	}
	if json.Unmarshal(raw, &ctx) == nil {
		if why, ok := ctx["fallback_reason"].(string); ok && why != "" {
			r.Reason = "Governed fallback: " + why
		}
	}
}
func shellReviewQuote(s string) string { return "'" + strings.ReplaceAll(s, "'", "'\\''") + "'" }
func reviewDispatches(r reviewReceipt) ([]struct {
	ID      string `json:"id"`
	PID     int    `json:"pid"`
	Project string `json:"project_dir"`
}, error) {
	data, err := reviewRun(r.Project, "ic", "--json", "dispatch", "list", "--scope="+r.RunID)
	var entries []struct {
		ID      string `json:"id"`
		PID     int    `json:"pid"`
		Project string `json:"project_dir"`
	}
	if err == nil {
		err = json.Unmarshal(data, &entries)
	}
	return entries, err
}

// The kernel owns dispatch cancellation. If it is unavailable, kill only the
// process group whose live command still contains this exact private wrapper.
// Never trust a retained PID after it has been reused by an unrelated process.
func stopReviewWorker(r reviewReceipt, dir string) error {
	// Resolve and stop the actual group BEFORE asking the kernel to kill its
	// leader. Otherwise a successful kernel kill can orphan the model child.
	groupStopped := false
	if r.WorkerPID > 1 {
		command, err := exec.Command("ps", "-p", strconv.Itoa(r.WorkerPID), "-o", "command=").Output()
		if err == nil && strings.Contains(string(command), filepath.Join(dir, "launch.sh")) {
			stopped, err := stopReviewWorkerGroup(r.WorkerPID)
			if err != nil {
				return err
			}
			groupStopped = stopped
		}
	}
	_, err := reviewRun(r.Project, "ic", "dispatch", "kill", r.DispatchID)
	if groupStopped {
		return nil
	}
	if err != nil {
		return fmt.Errorf("worker cancellation awaiting kernel reconciliation: %w", err)
	}
	// A missing leader does not establish that all children stopped. The
	// wrapper also traps TERM to terminate its group when kernel kill wins.
	return nil
}

func runReviewCheck(project string, command []string, log *os.File) error {
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Minute)
	defer cancel()
	check := exec.CommandContext(ctx, command[0], command[1:]...)
	check.Dir = project
	check.Stdout, check.Stderr = log, log
	check.SysProcAttr = reviewCheckAttr()
	check.Cancel = func() error {
		return killReviewCheckGroup(check)
	}
	check.WaitDelay = 5 * time.Second
	return check.Run()
}

func workReview(path string) error {
	dir := filepath.Dir(path)
	lock, err := reviewLock(filepath.Join(dir, "worker.lock"), true)
	if err != nil {
		if reviewLockBusy(err) {
			return nil
		}
		return err
	}
	defer lock.Close()
	var r reviewReceipt
	data, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	if err = json.Unmarshal(data, &r); err != nil {
		return err
	}
	if err = validateReview(r.Request); err != nil {
		return err
	}
	fail := func(status string, err error) error {
		r.Status = status
		r.Reason = err.Error()
		r.UpdatedAt = time.Now().UTC()
		if writeErr := reviewWrite(path, r); writeErr != nil {
			return writeErr
		}
		return err
	}
	if r.Status == "ready_for_retest" || r.Status == "failed" || (r.Status == "blocked" && r.DispatchID != "") {
		return nil
	}
	projectHash := sha256.Sum256([]byte(r.Project))
	projectLock, err := reviewLock(filepath.Join(filepath.Dir(dir), fmt.Sprintf("project-%x.lock", projectHash[:16])), true)
	if err != nil {
		if reviewLockBusy(err) {
			return nil
		}
		return err
	}
	defer projectLock.Close()
	if r.Status != "running" {
		if err = prepareReview(&r, path, reviewRun); err != nil {
			return fail("blocked", err)
		}
		if r.Status == "deferred" {
			return nil
		}
		active, err := reviewRun(r.Project, "ic", "--json", "dispatch", "list", "--active")
		if err != nil {
			return fail("blocked", err)
		}
		var activeDispatches []struct {
			ID      string `json:"id"`
			Project string `json:"project_dir"`
		}
		if err = json.Unmarshal(active, &activeDispatches); err != nil {
			return fail("blocked", err)
		}
		for _, d := range activeDispatches {
			if d.Project == r.Project {
				r.Status = "queued"
				r.Reason = "Waiting for the project's existing execution " + d.ID
				return reviewWrite(path, r)
			}
		}
		script, err := reviewDispatchScript()
		if err != nil {
			return fail("blocked", err)
		}
		if runtime.GOOS != "darwin" {
			return fail("blocked", errors.New("review execution pilot requires the macOS scope sandbox"))
		}
		for _, scope := range r.Request.Proposal.Scope {
			if _, err = safeReviewPath(r.Project, scope); err != nil {
				return fail("blocked", err)
			}
		}
		status, err := reviewRun(r.Project, "git", "status", "--porcelain")
		if err != nil {
			return fail("blocked", err)
		}
		if strings.TrimSpace(string(status)) != "" {
			if !r.GuidanceStarted {
				return fail("blocked", errors.New("project has uncommitted changes; preserve them and retry from a clean checkout"))
			}
			guidanceOnly := r
			guidanceOnly.Request.Proposal.Scope = nil
			if err = reviewCheckScope(guidanceOnly); err != nil {
				return fail("blocked", err)
			}
		}
		head, err := reviewRun(r.Project, "git", "rev-parse", "HEAD")
		if err != nil {
			return fail("blocked", err)
		}
		if r.GuidanceStarted && r.BaseCommit != strings.TrimSpace(string(head)) {
			return fail("blocked", errors.New("project HEAD changed during guidance preparation; reconcile before launching"))
		}
		r.BaseCommit = strings.TrimSpace(string(head))
		budget, err := reviewRun(r.Project, "ic", "--json", "run", "budget", r.RunID)
		if err != nil {
			return fail("blocked", err)
		}
		var b struct {
			Budget   int  `json:"budget"`
			Used     int  `json:"used"`
			Exceeded bool `json:"exceeded"`
		}
		if err = json.Unmarshal(budget, &b); err != nil {
			return fail("blocked", err)
		}
		if b.Budget != r.Request.Proposal.BudgetTokens || b.Exceeded || b.Used >= b.Budget {
			return fail("blocked", errors.New("approved execution budget unavailable or exhausted"))
		}
		dispatches, err := reviewDispatches(r)
		if err != nil {
			return fail("blocked", err)
		}
		if len(dispatches) > 0 {
			return fail("blocked", errors.New("run already contains a worker; reconcile existing dispatch instead of launching another"))
		}
		r.GuidanceStarted = true
		r.UpdatedAt = time.Now().UTC()
		if err = reviewWrite(path, r); err != nil {
			return err
		}
		if err = persistReviewGuidance(r); err != nil {
			return fail("blocked", err)
		}
		proposal, _ := json.MarshalIndent(r.Request.Proposal, "", "  ")
		prompt := "Implement exactly this human-accepted response. Read project guidance first and apply it without another reminder. Enduring guidance has been inserted verbatim by Clavain: include it unchanged in the checked commit. Work only in approved scope and guidance paths. Do not spawn agents or background processes. Stop with evidence if scope needs expansion. Commit only approved files after relevant checks. The supervisor runs the approved checks/build independently. Do not claim a human retest passed.\n\n" + string(proposal)
		promptPath := filepath.Join(dir, "task.md")
		if err = os.WriteFile(promptPath, []byte(prompt), 0600); err != nil {
			return fail("blocked", err)
		}
		role := "routine-execution"
		if r.Request.Proposal.BudgetTokens >= 100000 {
			role = "deep-execution"
		}
		profile := "(version 1)\n(allow default)\n(deny file-write* (subpath " + strconv.Quote(r.Project) + "))\n"
		allowed := append([]string{".git", ".clavain", ".tldrs"}, r.Request.Proposal.Scope...)
		for _, g := range r.Request.Proposal.Guidance {
			allowed = append(allowed, g.Path)
		}
		for _, p := range allowed {
			profile += "(allow file-write* (subpath " + strconv.Quote(filepath.Join(r.Project, p)) + "))\n"
		}
		sandboxPath := filepath.Join(dir, "scope.sb")
		if err = os.WriteFile(sandboxPath, []byte(profile), 0600); err != nil {
			return fail("blocked", err)
		}
		cmd := governedReviewCommand(script, r.Project, promptPath, filepath.Join(dir, "response.md"), r.WorkID, role)
		idPath := filepath.Join(dir, "dispatch-id")
		wrapper := "#!/usr/bin/env bash\nset -euo pipefail\ncd " + shellReviewQuote(r.Project) + "\n"
		wrapper += "for ((i=0;i<100;i++)); do [[ -s " + shellReviewQuote(idPath) + " ]] && break; sleep 0.1; done\n[[ -s " + shellReviewQuote(idPath) + " ]] || exit 1\n"
		wrapper += "export CLAVAIN_DISPATCH_ID=\"$(cat " + shellReviewQuote(idPath) + ")\"\n"
		for key, value := range map[string]string{"CLAVAIN_RUN_ID": r.RunID, "CLAVAIN_BEAD_ID": r.WorkID, "CLAVAIN_REQUIRE_USAGE": "1", "CLAVAIN_REVIEW_EVENTS": filepath.Join(dir, "usage.jsonl")} {
			wrapper += "export " + key + "=" + shellReviewQuote(value) + "\n"
		}
		wrapper += "trap 'trap \"\" TERM; kill -TERM -- -$$ 2>/dev/null; exit 143' TERM INT\n"
		wrapper += "set +e\n/usr/bin/sandbox-exec -f " + shellReviewQuote(sandboxPath)
		for _, arg := range cmd.Args {
			wrapper += " " + shellReviewQuote(arg)
		}
		wrapper += " > " + shellReviewQuote(filepath.Join(dir, "worker.log")) + " 2>&1 &\nworker=$!\nwait \"$worker\"\nrc=$?\nprintf '%s' \"$rc\" > " + shellReviewQuote(filepath.Join(dir, "exit-code")) + "\nexit \"$rc\"\n"
		wrapperPath := filepath.Join(dir, "launch.sh")
		if err = os.WriteFile(wrapperPath, []byte(wrapper), 0700); err != nil {
			return fail("blocked", err)
		}
		r.Status = "running"
		r.StartedAt = time.Now().UTC()
		r.Reason = "Clavain is resolving an eligible execution role"
		r.UpdatedAt = time.Now().UTC()
		if err = reviewWrite(path, r); err != nil {
			return err
		}
		output, err := reviewRun(r.Project, "ic", "--json", "dispatch", "spawn", "--type=codex", "--project="+r.Project, "--scope-id="+r.RunID, "--prompt-file="+promptPath, "--output="+filepath.Join(dir, "response.md"), "--name="+r.WorkID, "--dispatch-sh="+wrapperPath)
		if err != nil {
			return fmt.Errorf("dispatch submission uncertain; supervisor will reconcile run %s: %w", r.RunID, err)
		}
		var spawned struct {
			ID  string `json:"id"`
			PID int    `json:"pid"`
		}
		if err = json.Unmarshal(output, &spawned); err != nil {
			return err
		}
		r.DispatchID = spawned.ID
		r.WorkerPID = spawned.PID
	}
	// On supervisor recovery, reconcile the actual kernel dispatch before any effect.
	if r.DispatchID == "" {
		entries, err := reviewDispatches(r)
		if err != nil {
			return fail("blocked", err)
		}
		if len(entries) != 1 || entries[0].Project != r.Project {
			return fail("blocked", errors.New("interrupted dispatch submission needs reconciliation; no worker was retried"))
		}
		r.DispatchID = entries[0].ID
		r.WorkerPID = entries[0].PID
	}
	if err = reviewWrite(path, r); err != nil {
		return err
	}
	if err = os.WriteFile(filepath.Join(dir, "dispatch-id"), []byte(r.DispatchID), 0600); err != nil {
		return err
	}
	log, err := os.OpenFile(filepath.Join(dir, "verification.log"), os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0600)
	if err != nil {
		return err
	} // keep running so the supervisor reconnects
	defer log.Close()
	lastUsage := -1
	if r.StartedAt.IsZero() {
		r.StartedAt = r.UpdatedAt
	}
	watchdog := r.StartedAt.Add(time.Hour)
	for {
		used, usageErr := reviewUsage(filepath.Join(dir, "usage.jsonl"))
		if usageErr == nil && used != lastUsage {
			if _, err = reviewRun(r.Project, "ic", "dispatch", "tokens", r.DispatchID, "--in="+fmt.Sprint(used), "--out=0"); err != nil {
				fmt.Fprintln(log, "Usage report pending:", err)
			} else {
				lastUsage = used
			}
		}
		if used > r.Request.Proposal.BudgetTokens {
			if stopErr := stopReviewWorker(r, dir); stopErr == nil {
				return fail("blocked", fmt.Errorf("approved budget reached: %d reported tokens; active model turns can exceed the limit", used))
			} else {
				fmt.Fprintln(log, "Budget exceeded; cancellation pending:", stopErr)
			}
		}
		if time.Now().After(watchdog) {
			if stopErr := stopReviewWorker(r, dir); stopErr == nil {
				return fail("blocked", errors.New("execution watchdog expired"))
			} else {
				fmt.Fprintln(log, "Watchdog expired; cancellation pending:", stopErr)
			}
		}
		result, err := reviewRun(r.Project, "ic", "--json", "dispatch", "poll", r.DispatchID)
		if err != nil {
			fmt.Fprintln(log, "Intercore poll temporarily unavailable:", err)
			time.Sleep(time.Second)
			continue
		}
		var dispatch struct {
			Status  string `json:"status"`
			Project string `json:"project_dir"`
			PID     int    `json:"pid"`
		}
		if err = json.Unmarshal(result, &dispatch); err != nil {
			fmt.Fprintln(log, "Intercore response could not be read:", err)
			time.Sleep(time.Second)
			continue
		}
		if dispatch.Project != r.Project {
			return errors.New("kernel dispatch project mismatch; retained for reconciliation")
		}
		r.WorkerPID = dispatch.PID
		updateReviewRoute(&r)
		r.UpdatedAt = time.Now().UTC()
		if err = reviewWrite(path, r); err != nil {
			return err
		}
		if dispatch.Status != "running" && dispatch.Status != "spawned" {
			exit, err := os.ReadFile(filepath.Join(dir, "exit-code"))
			if err != nil || strings.TrimSpace(string(exit)) != "0" {
				return fail("failed", errors.New("governed worker failed; see worker.log in the execution receipt"))
			}
			if dispatch.Status != "completed" {
				return fail("failed", fmt.Errorf("kernel dispatch ended %s", dispatch.Status))
			}
			break
		}
		time.Sleep(time.Second)
	}
	if lastUsage <= 0 {
		return fail("blocked", errors.New("worker returned without usage evidence"))
	}
	if err = verifyReviewGuidance(r); err != nil {
		return fail("blocked", err)
	}
	if err = reviewCheckScope(r); err != nil {
		return fail("blocked", err)
	}
	for _, command := range append(r.Request.Proposal.Build.Checks, r.Request.Proposal.Build.Command) {
		if err = runReviewCheck(r.Project, command, log); err != nil {
			return fail("failed", fmt.Errorf("approved build/check failed (%s): %w", command[0], err))
		}
	}
	if err = verifyReviewGuidance(r); err != nil {
		return fail("blocked", err)
	}
	if err = reviewCheckScope(r); err != nil {
		return fail("blocked", err)
	}
	status, err := reviewRun(r.Project, "git", "status", "--porcelain")
	if err != nil {
		return fail("blocked", err)
	}
	if strings.TrimSpace(string(status)) != "" {
		return fail("blocked", errors.New("worker left uncommitted changes; complete the checked commit before retest"))
	}
	binary := filepath.Join(r.Project, r.Request.Proposal.Build.Binary)
	real, err := filepath.EvalSymlinks(binary)
	if err != nil {
		return fail("failed", err)
	}
	if real != binary {
		return fail("blocked", errors.New("retest binary must be a direct project artifact"))
	}
	info, err := os.Stat(binary)
	if err != nil || !info.Mode().IsRegular() || info.Mode()&0111 == 0 {
		return fail("failed", errors.New("retest binary missing or not executable"))
	}
	bytes, err := os.ReadFile(binary)
	if err != nil {
		return fail("failed", err)
	}
	sum := sha256.Sum256(bytes)
	head, err := reviewRun(r.Project, "git", "rev-parse", "HEAD")
	if err != nil {
		return fail("failed", err)
	}
	r.Build = strings.TrimSpace(string(head)) + ":sha256:" + hex.EncodeToString(sum[:])
	r.Binary = binary
	r.Status = "ready_for_retest"
	r.Reason = "Approved checks passed and executable hashed; your build-specific retest is still required"
	r.UpdatedAt = time.Now().UTC()
	return reviewWrite(path, r)
}
