package main

// Preparation has its own receipt namespace and never calls review submit.
import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"
)

type prepareRequest struct {
	Version      int               `json:"version"`
	Key          string            `json:"key"`
	Project      string            `json:"project"`
	Actor        string            `json:"actor"`
	Transcriber  string            `json:"transcriber"`
	BudgetTokens int               `json:"budget_tokens"`
	BudgetMode   *string           `json:"budget_mode,omitempty"`
	Sources      map[string]string `json:"sources"`
	CoverageGaps []string          `json:"coverage_gaps"`
	Proposal     reviewProposal    `json:"proposal"`
}
type ratifyFile struct {
	Old     string `json:"old"`
	New     string `json:"new"`
	Content string `json:"content"`
}
type ratifyReceipt struct {
	Version   int                   `json:"version"`
	Request   prepareRequest        `json:"request"`
	Hash      string                `json:"hash"`
	ID        string                `json:"id"`
	Status    string                `json:"status"`
	Reason    string                `json:"reason,omitempty"`
	Parent    string                `json:"parent"`
	Commit    string                `json:"commit,omitempty"`
	Branch    string                `json:"branch"`
	Author    string                `json:"author"`
	Committer string                `json:"committer"`
	Message   string                `json:"message"`
	Files     map[string]ratifyFile `json:"files"`
	UpdatedAt time.Time             `json:"updated_at"`
}

func prepareHash(b []byte) string { h := sha256.Sum256(b); return hex.EncodeToString(h[:]) }
func preparePaths(base string, s prepareRequest) (string, string) {
	p := prepareHash([]byte(s.Project))
	k := prepareHash([]byte(s.Key))
	dir := filepath.Join(filepath.Dir(base), "prepare", p[:32], k[:32])
	return dir, filepath.Join(dir, "ratification.json")
}
func validatePrepare(s prepareRequest) error {
	p := s.Proposal
	if s.Version != 1 || s.Key != fmt.Sprintf("%s:%d", p.ID, p.Revision) || p.ID == "" || p.Revision < 1 || p.Status != "accepted" || p.AcceptedAt == nil || p.AcceptedAt.IsZero() || strings.TrimSpace(s.Actor) == "" || strings.TrimSpace(s.Transcriber) == "" {
		return errors.New("attributed accepted synthesis revision and retry key required")
	}
	mode := "capped"
	if s.BudgetMode != nil {
		mode = *s.BudgetMode
	}
	switch mode {
	case "capped":
		if s.BudgetTokens <= 0 {
			return errors.New("capped preparation requires a positive token budget")
		}
	case "uncapped":
		if s.BudgetTokens != 0 {
			return errors.New("uncapped preparation requires budget_tokens: 0")
		}
	default:
		return errors.New("unknown preparation budget mode")
	}
	project, err := canonicalReviewDir(s.Project)
	if err != nil {
		return err
	}
	if project != s.Project || p.Project != project {
		return errors.New("preparation project mismatch")
	}
	for _, v := range []string{s.Actor, s.Transcriber, p.ID} {
		if strings.ContainsAny(v, "\r\n\x00") || v != strings.TrimSpace(v) {
			return errors.New("invalid receipt identity")
		}
	}
	for _, g := range p.Guidance {
		if !reviewRelative(g.Path) || g.Text == "" || g.Scope == "" || g.Rationale == "" || g.BaseRevision == "" {
			return errors.New("displayed guidance path, text, scope, rationale and base hash required")
		}
	}
	for path, hash := range s.Sources {
		if !reviewRelative(path) || hash == "" {
			return errors.New("invalid canonical source binding")
		}
	}
	return nil
}

func (s prepareRequest) uncapped() bool {
	return s.BudgetMode != nil && *s.BudgetMode == "uncapped"
}
func prepareFileHash(project, path string) (string, []byte, error) {
	if !reviewRelative(path) {
		return "", nil, errors.New("invalid source path")
	}
	full, err := safeReviewPath(project, path)
	if err != nil {
		return "", nil, err
	}
	data, err := os.ReadFile(full)
	if os.IsNotExist(err) {
		return "missing", nil, nil
	}
	if err != nil {
		return "", nil, err
	}
	return prepareHash(data), data, nil
}
func ratifyPrepare(base string, s prepareRequest, run reviewRunner) (r ratifyReceipt, err error) {
	if err = validatePrepare(s); err != nil {
		return
	}
	dir, path := preparePaths(base, s)
	if err = os.MkdirAll(dir, 0700); err != nil {
		return
	}
	if err = os.MkdirAll(base, 0700); err != nil {
		return
	}
	// This is exactly the legacy execution worker's project lock.
	projectHash := sha256.Sum256([]byte(s.Project))
	lock, e := reviewLock(filepath.Join(base, fmt.Sprintf("project-%x.lock", projectHash[:16])), true)
	if e != nil {
		return r, fmt.Errorf("project execution lock unavailable: %w", e)
	}
	defer lock.Close()
	raw, _ := json.Marshal(s)
	hash := prepareHash(raw)
	fail := func(e error) (ratifyReceipt, error) {
		if r.Status == "persisted" {
			return r, e
		}
		r.Status = "blocked"
		r.Reason = e.Error()
		r.UpdatedAt = time.Now().UTC()
		if r.Hash != "" {
			if we := reviewWrite(path, r); we != nil {
				return r, we
			}
		}
		return r, e
	}
	git := func(args ...string) (string, error) {
		b, e := run(s.Project, "git", args...)
		return strings.TrimSpace(string(b)), e
	}
	branch, e := git("symbolic-ref", "--short", "HEAD")
	if e != nil || branch != "main" {
		return r, errors.New("ratification requires main")
	}
	head, e := git("rev-parse", "HEAD")
	if e != nil {
		return r, e
	}
	if data, e := os.ReadFile(path); e == nil {
		if e = json.Unmarshal(data, &r); e != nil {
			return r, e
		}
		if r.Hash != hash {
			return r, errors.New("ratification retry key reused with different accepted content")
		}
	} else if !os.IsNotExist(e) {
		return r, e
	} else {
		status, e := git("status", "--porcelain")
		if e != nil {
			return r, e
		}
		if status != "" {
			return r, errors.New("ratification requires a clean checkout; preserve unrelated changes")
		}
		author, e := git("var", "GIT_AUTHOR_IDENT")
		if e != nil || author == "" {
			return r, errors.New("configured author identity required")
		}
		committer, e := git("var", "GIT_COMMITTER_IDENT")
		if e != nil || committer == "" {
			return r, errors.New("configured committer identity required")
		}
		// git var can infer a host identity. Require explicit name and email too.
		for _, key := range []string{"user.name", "user.email"} {
			value, e := git("config", "--get", key)
			if e != nil || value == "" {
				return r, fmt.Errorf("explicit git %s required", key)
			}
		}
		r = ratifyReceipt{Version: 1, Request: s, Hash: hash, ID: hash, Status: "persisting", Parent: head, Branch: branch, Author: author, Committer: committer, Files: map[string]ratifyFile{}, UpdatedAt: time.Now().UTC()}
		r.Message = fmt.Sprintf("docs: ratify accepted guidance %s revision %d\n\nAutarch-Ratification: %s\nRuler: %s\nSynthesis: %s\nTranscriber: %s\n", s.Proposal.ID, s.Proposal.Revision, hash, s.Actor, s.Key, s.Transcriber)
		blocks := guidanceBlocks(reviewReceipt{Request: reviewSubmission{Proposal: s.Proposal}, ProposalID: s.Proposal.ID, ProposalRevision: s.Proposal.Revision})
		for _, g := range s.Proposal.Guidance {
			actual, data, e := prepareFileHash(s.Project, g.Path)
			if e != nil {
				return r, e
			}
			if actual != g.BaseRevision {
				return r, fmt.Errorf("guidance base changed: %s", g.Path)
			}
			if old, ok := r.Files[g.Path]; ok && old.Old != actual {
				return r, errors.New("conflicting guidance bases")
			}
			content := string(data) + strings.Join(blocks[g.Path], "")
			r.Files[g.Path] = ratifyFile{Old: actual, New: prepareHash([]byte(content)), Content: content}
		}
		if err = reviewWrite(path, r); err != nil {
			return
		}
	}
	// Recover only the exact journaled commit; a matching trailer alone is insufficient.
	if r.Status == "persisted" && r.Commit != "" {
		if _, e = run(s.Project, "git", "merge-base", "--is-ancestor", r.Commit, "HEAD"); e != nil {
			return r, errors.New("persisted ratification commit is no longer an ancestor of main; receipt retained")
		}
		if len(r.Files) > 0 {
			if e = verifyRatificationCommit(r, r.Commit, run); e != nil {
				return r, e
			}
		}
		return r, nil
	}
	if head != r.Parent {
		parent, e := git("rev-parse", "HEAD^")
		if e != nil {
			return fail(e)
		}
		message, e := git("show", "-s", "--format=%B", "HEAD")
		if e != nil {
			return fail(e)
		}
		identities, e := git("show", "-s", "--format=%an <%ae>%n%cn <%ce>", "HEAD")
		if e != nil {
			return fail(e)
		}
		identity := func(v string) string {
			i := strings.LastIndex(v, ">")
			if i < 0 {
				return ""
			}
			return v[:i+1]
		}
		if parent != r.Parent || message != strings.TrimSpace(r.Message) || identities != identity(r.Author)+"\n"+identity(r.Committer) || (r.Commit != "" && r.Commit != head) {
			return fail(errors.New("HEAD moved outside journaled ratification"))
		}
		changed, e := run(s.Project, "git", "diff-tree", "--no-commit-id", "--name-only", "-z", "-r", head)
		if e != nil {
			return fail(e)
		}
		names := strings.Split(strings.TrimSuffix(string(changed), "\x00"), "\x00")
		if len(names) != len(r.Files) {
			return fail(errors.New("ratification commit includes unreviewed paths"))
		}
		for _, name := range names {
			if _, ok := r.Files[name]; !ok {
				return fail(errors.New("ratification commit scope mismatch"))
			}
		}
		for name, f := range r.Files {
			actual, _, e := prepareFileHash(s.Project, name)
			if e != nil || actual != f.New {
				return fail(fmt.Errorf("committed guidance changed: %s", name))
			}
			committed, e := run(s.Project, "git", "show", head+":"+name)
			if e != nil || prepareHash(committed) != f.New {
				return fail(errors.New("committed guidance hash mismatch"))
			}
		}
		r.Commit = head
		r.Status = "persisted"
		r.Reason = ""
		r.UpdatedAt = time.Now().UTC()
		return r, reviewWrite(path, r)
	}
	if r.Commit != "" {
		return fail(errors.New("ratification commit was rewound"))
	}
	// No changes outside the displayed paths may enter a recovering commit.
	changed, e := run(s.Project, "git", "diff", "--name-only", "-z", r.Parent)
	if e != nil {
		return fail(e)
	}
	untracked, e := run(s.Project, "git", "ls-files", "--others", "--exclude-standard", "-z")
	if e != nil {
		return fail(e)
	}
	for _, name := range strings.Split(string(append(changed, untracked...)), "\x00") {
		if name != "" {
			if _, ok := r.Files[name]; !ok {
				return fail(fmt.Errorf("unrelated change during ratification: %s", name))
			}
		}
	}
	names := []string{}
	for name, f := range r.Files {
		actual, _, e := prepareFileHash(s.Project, name)
		if e != nil {
			return fail(e)
		}
		if actual != f.Old && actual != f.New {
			return fail(fmt.Errorf("ratification target conflict: %s", name))
		}
		names = append(names, name)
	}
	sort.Strings(names)
	for _, name := range names {
		f := r.Files[name]
		full := filepath.Join(s.Project, name)
		if err = os.MkdirAll(filepath.Dir(full), 0755); err != nil {
			return fail(err)
		}
		tmp, e := os.CreateTemp(filepath.Dir(full), ".ratify-")
		if e != nil {
			return fail(e)
		}
		_, e = tmp.WriteString(f.Content)
		if e == nil {
			e = tmp.Sync()
		}
		ce := tmp.Close()
		if e == nil {
			e = ce
		}
		if e == nil {
			e = os.Rename(tmp.Name(), full)
		}
		os.Remove(tmp.Name())
		if e != nil {
			return fail(e)
		}
	}
	if len(names) == 0 {
		r.Commit = r.Parent
		r.Status = "persisted"
		return r, reviewWrite(path, r)
	}
	if _, e = git(append([]string{"add", "--"}, names...)...); e != nil {
		return fail(e)
	}
	// A file-backed message preserves literal user wording and deliberate newlines.
	messagePath := filepath.Join(dir, "ratification-message.txt")
	if e = os.WriteFile(messagePath, []byte(r.Message), 0600); e != nil {
		return fail(e)
	}
	if _, e = git(append([]string{"commit", "--only", "--cleanup=verbatim", "--file", messagePath, "--"}, names...)...); e != nil {
		return fail(e)
	}
	// Verify the commit through the same crash-recovery path, under this lock.
	r.Commit, e = git("rev-parse", "HEAD")
	if e != nil {
		return fail(e)
	}
	if e = verifyRatificationCommit(r, r.Commit, run); e != nil {
		return fail(e)
	}
	for name, f := range r.Files {
		got, _, e := prepareFileHash(s.Project, name)
		if e != nil || got != f.New {
			return fail(fmt.Errorf("guidance changed during commit: %s", name))
		}
	}
	r.Status = "persisted"
	r.Reason = ""
	r.UpdatedAt = time.Now().UTC()
	return r, reviewWrite(path, r)
}

func verifyRatificationCommit(r ratifyReceipt, commit string, run reviewRunner) error {
	git := func(args ...string) (string, error) {
		data, err := run(r.Request.Project, "git", args...)
		return strings.TrimSpace(string(data)), err
	}
	parent, err := git("rev-parse", commit+"^")
	if err != nil {
		return err
	}
	message, err := git("show", "-s", "--format=%B", commit)
	if err != nil {
		return err
	}
	identities, err := git("show", "-s", "--format=%an <%ae>%n%cn <%ce>", commit)
	if err != nil {
		return err
	}
	identity := func(v string) string {
		i := strings.LastIndex(v, ">")
		if i < 0 {
			return ""
		}
		return v[:i+1]
	}
	if parent != r.Parent || message != strings.TrimSpace(r.Message) || identities != identity(r.Author)+"\n"+identity(r.Committer) {
		return errors.New("ratification commit does not match journaled parent, attribution and message")
	}
	data, err := run(r.Request.Project, "git", "diff-tree", "--no-commit-id", "--name-only", "-z", "-r", commit)
	if err != nil {
		return err
	}
	names := strings.Split(strings.TrimSuffix(string(data), "\x00"), "\x00")
	if len(names) != len(r.Files) {
		return errors.New("ratification commit has unreviewed scope")
	}
	for _, name := range names {
		f, ok := r.Files[name]
		if !ok {
			return errors.New("ratification commit path mismatch")
		}
		data, err := run(r.Request.Project, "git", "show", commit+":"+name)
		if err != nil || prepareHash(data) != f.New {
			return fmt.Errorf("ratification committed hash mismatch: %s", name)
		}
	}
	return nil
}

func cmdPrepare(args []string) error {
	if len(args) == 2 && args[0] == "work" {
		return workPrepare(args[1])
	}
	if len(args) != 1 || (args[0] != "ratify" && args[0] != "submit" && args[0] != "status") {
		return errors.New("usage: clavain-cli prepare ratify|submit|status")
	}
	var s prepareRequest
	if err := json.NewDecoder(io.LimitReader(os.Stdin, 2<<20)).Decode(&s); err != nil {
		return err
	}
	base, err := reviewBaseDir()
	if err != nil {
		return err
	}
	if args[0] != "ratify" {
		var r prepareReceipt
		var path string
		if args[0] == "status" {
			r, path, err = readPrepare(base, s)
		} else {
			r, path, err = submitPrepare(base, s)
		}
		if err != nil {
			return err
		}
		if args[0] == "submit" && r.Status != "reviewed" {
			if err = launchPrepare(path); err != nil {
				return err
			}
		}
		return json.NewEncoder(os.Stdout).Encode(r)
	}
	r, err := ratifyPrepare(base, s, reviewRun)
	if e := json.NewEncoder(os.Stdout).Encode(r); e != nil {
		return e
	}
	return err
}
