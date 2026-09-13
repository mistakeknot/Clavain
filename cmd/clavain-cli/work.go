package main

// The work command is a diagnostic preview only. It reads explicitly registered
// Beads authorities and deliberately has no admission, binding, or mutation path.

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"time"
	"unicode"
)

const (
	workBindingAuthority = "not_live"
	workCoverage         = "none"
	workCoverageScope    = "enforcement"
	workHistoryStatus    = "unavailable"
	workSessionsStatus   = "unknown"
	workRegistryLimit    = 1 << 20
	workPlanLimit        = 1 << 20
	workDefaultOutputMax = 4 << 20
)

var (
	workUUIDPattern    = regexp.MustCompile(`^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$`)
	errWorkOutputLimit = errors.New("work authority output limit exceeded")
)

type workDependencies struct {
	bdPath        string
	timeout       time.Duration
	maxOutputByte int
}

func defaultWorkDependencies() workDependencies {
	return workDependencies{bdPath: "bd", timeout: 10 * time.Second, maxOutputByte: workDefaultOutputMax}
}

type workRegistry struct {
	Version           int                   `json:"version"`
	AuthorityEndpoint workAuthorityEndpoint `json:"authority_endpoint"`
	Trackers          []workTracker         `json:"trackers"`
}

type workAuthorityEndpoint struct {
	Kind     string `json:"kind"`
	Identity string `json:"identity"`
}

type workTracker struct {
	TrackerUUID  string           `json:"tracker_uuid"`
	Root         string           `json:"root"`
	Repositories []workRepository `json:"repositories"`
}

type workRepository struct {
	Alias    string `json:"alias"`
	Worktree string `json:"worktree"`
}

type workBead struct {
	ID           string
	Title        string
	Status       string
	Assignee     string
	SearchFields map[string]string
}

type workTask struct {
	TrackerUUID   string   `json:"tracker_uuid"`
	BeadID        string   `json:"bead_id"`
	Title         string   `json:"title"`
	BeadsStatus   string   `json:"beads_status"`
	BeadsAssignee string   `json:"beads_assignee"`
	Aliases       []string `json:"repository_aliases"`
}

type workCandidate struct {
	workTask
	Score          int      `json:"evidence_score"`
	MatchedFields  []string `json:"matched_fields"`
	Classification string   `json:"classification"`
	Reason         string   `json:"reason"`
}

type workResult struct {
	Command               string          `json:"command"`
	BindingAuthority      string          `json:"binding_authority"`
	ImplementationAllowed bool            `json:"implementation_allowed"`
	Coverage              string          `json:"coverage"`
	CoverageScope         string          `json:"coverage_scope"`
	AuthorityStatus       string          `json:"authority_status"`
	ResultStatus          string          `json:"result_status"`
	HistoryStatus         string          `json:"history_status"`
	AttachedSessions      string          `json:"attached_sessions"`
	ClassificationLimit   string          `json:"classification_limit"`
	Task                  *workTask       `json:"task,omitempty"`
	Candidates            []workCandidate `json:"candidates,omitempty"`
	Explanation           string          `json:"explanation,omitempty"`
}

type workFailure struct {
	Command               string `json:"command"`
	BindingAuthority      string `json:"binding_authority"`
	ImplementationAllowed bool   `json:"implementation_allowed"`
	Coverage              string `json:"coverage"`
	CoverageScope         string `json:"coverage_scope"`
	AuthorityStatus       string `json:"authority_status"`
	ResultStatus          string `json:"result_status"`
	HistoryStatus         string `json:"history_status"`
	AttachedSessions      string `json:"attached_sessions"`
	Error                 string `json:"error"`
}

type workCLIError struct{ cause error }

func (e *workCLIError) Error() string { return e.cause.Error() }
func (e *workCLIError) Unwrap() error { return e.cause }
func (e *workCLIError) ExitCode() int { return 1 }

type workOptions struct {
	verb      string
	registry  string
	authority string
	text      string
	plan      string
	task      string
	json      bool
}

func cmdWork(args []string) error {
	return runWorkCLI(args, os.Stdout, os.Stderr, defaultWorkDependencies())
}

func runWorkCLI(args []string, stdout, stderr io.Writer, deps workDependencies) error {
	opts, err := parseWorkOptions(args)
	if err == nil {
		var result workResult
		result, err = executeWork(opts, deps)
		if err == nil {
			if renderErr := renderWorkResult(stdout, result, opts.json); renderErr != nil {
				err = fmt.Errorf("work: render output: %w", renderErr)
			} else {
				return nil
			}
		}
	}

	jsonOutput := false
	verb := "unknown"
	if opts != nil {
		jsonOutput = opts.json
		verb = opts.verb
	} else {
		for _, arg := range args {
			if arg == "--json" {
				jsonOutput = true
			}
		}
		if len(args) > 0 {
			verb = args[0]
		}
	}
	failure := workFailure{
		Command:               verb,
		BindingAuthority:      workBindingAuthority,
		ImplementationAllowed: false,
		Coverage:              workCoverage,
		CoverageScope:         workCoverageScope,
		AuthorityStatus:       "unavailable",
		ResultStatus:          "unavailable",
		HistoryStatus:         workHistoryStatus,
		AttachedSessions:      workSessionsStatus,
		Error:                 err.Error(),
	}
	if jsonOutput {
		encoded, marshalErr := json.MarshalIndent(failure, "", "  ")
		if marshalErr == nil {
			fmt.Fprintln(stderr, string(encoded))
		} else {
			fmt.Fprintf(stderr, "work: %v (binding_authority=%s implementation_allowed=false coverage=%s)\n", err, workBindingAuthority, workCoverage)
		}
	} else {
		fmt.Fprintf(stderr, "work: %v\n", err)
		fmt.Fprintf(stderr, "binding_authority=%s implementation_allowed=false coverage=%s coverage_scope=%s authority_status=unavailable result_status=unavailable history_status=%s attached_sessions=%s\n", workBindingAuthority, workCoverage, workCoverageScope, workHistoryStatus, workSessionsStatus)
	}
	return &workCLIError{cause: err}
}

func parseWorkOptions(args []string) (*workOptions, error) {
	if len(args) == 0 {
		return nil, errors.New("usage: work <discover|status|explain> --registry=FILE --authority=IDENTITY [--json]")
	}
	verb := args[0]
	if verb != "discover" && verb != "status" && verb != "explain" {
		return &workOptions{verb: verb, json: hasWorkJSONFlag(args[1:])}, fmt.Errorf("unsupported work verb %q; supported verbs: discover, status, explain", verb)
	}
	opts := &workOptions{verb: verb}
	flags := flag.NewFlagSet("work "+verb, flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	flags.StringVar(&opts.registry, "registry", "", "explicit work registry JSON")
	flags.StringVar(&opts.authority, "authority", "", "exact registered authority endpoint identity")
	flags.BoolVar(&opts.json, "json", false, "emit JSON")
	if verb == "discover" {
		flags.StringVar(&opts.text, "text", "", "user task text used only as ranking evidence")
		flags.StringVar(&opts.plan, "plan", "", "supplied plan file used only as ranking evidence")
	} else {
		flags.StringVar(&opts.task, "task", "", "exact trackerUUID:BeadID")
	}
	if err := flags.Parse(args[1:]); err != nil {
		return opts, fmt.Errorf("invalid work %s flags: %w", verb, err)
	}
	if len(flags.Args()) != 0 {
		return opts, fmt.Errorf("unexpected positional arguments for work %s", verb)
	}
	if opts.registry == "" {
		return opts, errors.New("--registry is required; no registry is activated by default")
	}
	if opts.authority == "" {
		return opts, errors.New("--authority is required; select the exact registered endpoint identity")
	}
	if (verb == "status" || verb == "explain") && opts.task == "" {
		return opts, errors.New("--task is required and must be trackerUUID:BeadID")
	}
	return opts, nil
}

func hasWorkJSONFlag(args []string) bool {
	for _, arg := range args {
		if arg == "--json" || strings.HasPrefix(arg, "--json=") {
			return true
		}
	}
	return false
}

func executeWork(opts *workOptions, deps workDependencies) (workResult, error) {
	registry, err := loadWorkRegistry(opts.registry)
	if err != nil {
		return workResult{}, err
	}
	if opts.authority != registry.AuthorityEndpoint.Identity {
		return workResult{}, fmt.Errorf("selected authority identity %q does not exactly match registry endpoint %q", opts.authority, registry.AuthorityEndpoint.Identity)
	}
	if registry.AuthorityEndpoint.Kind == "remote" {
		return workResult{}, fmt.Errorf("required authority unavailable: remote endpoint %q is not implemented in this read-only slice", registry.AuthorityEndpoint.Identity)
	}
	if registry.AuthorityEndpoint.Kind != "local" {
		return workResult{}, fmt.Errorf("required authority unavailable: unsupported endpoint kind %q", registry.AuthorityEndpoint.Kind)
	}

	selectedTracker := ""
	if opts.verb == "status" || opts.verb == "explain" {
		var parseErr error
		selectedTracker, _, parseErr = parseQualifiedWorkTask(opts.task)
		if parseErr != nil {
			return workResult{}, parseErr
		}
		found := false
		for _, tracker := range registry.Trackers {
			if tracker.TrackerUUID == selectedTracker {
				found = true
			}
		}
		if !found {
			return workResult{}, fmt.Errorf("tracker mapping missing: %s", selectedTracker)
		}
	}
	beadsByTracker := make(map[string][]workBead, len(registry.Trackers))
	for _, tracker := range registry.Trackers {
		if selectedTracker != "" && tracker.TrackerUUID != selectedTracker {
			continue
		}
		if err := validateTrackerMetadata(tracker); err != nil {
			return workResult{}, err
		}
		beads, err := readTrackerBeads(tracker, deps)
		if err != nil {
			return workResult{}, err
		}
		beadsByTracker[tracker.TrackerUUID] = beads
	}

	result := workResult{
		Command:               opts.verb,
		BindingAuthority:      workBindingAuthority,
		ImplementationAllowed: false,
		Coverage:              workCoverage,
		CoverageScope:         workCoverageScope,
		AuthorityStatus:       "available_read_only",
		HistoryStatus:         workHistoryStatus,
		AttachedSessions:      workSessionsStatus,
		ClassificationLimit:   "lexical evidence ranking only; exact tracker UUID plus Bead ID identifies a task, while all other matches remain ambiguous shared-evidence candidates for agent disposition; no ranking grants implementation authority",
	}

	switch opts.verb {
	case "discover":
		evidence := opts.text
		if opts.plan != "" {
			plan, readErr := readBoundedRegularFile(opts.plan, workPlanLimit, "plan")
			if readErr != nil {
				return workResult{}, readErr
			}
			evidence += "\n" + string(plan)
		}
		result.Candidates = discoverWorkCandidates(registry, beadsByTracker, evidence)
		result.ResultStatus = "candidates_found"
		if len(result.Candidates) == 0 {
			result.ResultStatus = "no_results"
		}
		result.Explanation = "Candidates are evidence-only. Every in-progress Bead is retained even when its lexical score is zero. Optional Alwe history is unavailable and no private session history was read."
	case "status", "explain":
		trackerUUID, beadID, parseErr := parseQualifiedWorkTask(opts.task)
		if parseErr != nil {
			return workResult{}, parseErr
		}
		task, found := findWorkTask(registry, beadsByTracker, trackerUUID, beadID)
		if !found {
			return workResult{}, fmt.Errorf("authoritative task not found: %s:%s", trackerUUID, beadID)
		}
		result.Task = &task
		result.ResultStatus = "task_found"
		if opts.verb == "status" {
			result.Explanation = "BEADS assignee and status are authoritative tracker fields only; implementation binding and attached sessions remain unknown."
		} else {
			result.Explanation = "This is a read-only diagnostic explanation, not an admission decision. BEADS assigneeship is not a verified implementation binding; no host or security boundary is established."
		}
	}
	return result, nil
}

func loadWorkRegistry(path string) (workRegistry, error) {
	data, err := readBoundedRegularFile(path, workRegistryLimit, "registry")
	if err != nil {
		return workRegistry{}, err
	}
	if err := rejectDuplicateJSONKeys(data); err != nil {
		return workRegistry{}, fmt.Errorf("malformed registry: %w", err)
	}
	var registry workRegistry
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&registry); err != nil {
		return workRegistry{}, fmt.Errorf("malformed registry: %w", err)
	}
	if err := requireJSONEOF(decoder); err != nil {
		return workRegistry{}, fmt.Errorf("malformed registry: %w", err)
	}
	if err := validateWorkRegistry(registry); err != nil {
		return workRegistry{}, fmt.Errorf("invalid registry: %w", err)
	}
	return registry, nil
}

func validateWorkRegistry(registry workRegistry) error {
	if registry.Version != 1 {
		return fmt.Errorf("version must be 1")
	}
	if registry.AuthorityEndpoint.Kind != "local" && registry.AuthorityEndpoint.Kind != "remote" {
		return fmt.Errorf("authority_endpoint.kind must be local or remote")
	}
	if strings.TrimSpace(registry.AuthorityEndpoint.Identity) == "" || registry.AuthorityEndpoint.Identity != strings.TrimSpace(registry.AuthorityEndpoint.Identity) {
		return fmt.Errorf("authority_endpoint.identity must be exact and nonempty")
	}
	if len(registry.Trackers) == 0 {
		return fmt.Errorf("at least one tracker is required")
	}
	trackerIDs := make(map[string]struct{})
	roots := make(map[string]struct{})
	aliases := make(map[string]struct{})
	worktrees := make(map[string]struct{})
	for _, tracker := range registry.Trackers {
		if !workUUIDPattern.MatchString(tracker.TrackerUUID) {
			return fmt.Errorf("tracker_uuid %q is not a UUID", tracker.TrackerUUID)
		}
		key := strings.ToLower(tracker.TrackerUUID)
		if _, exists := trackerIDs[key]; exists {
			return fmt.Errorf("duplicate tracker_uuid %q", tracker.TrackerUUID)
		}
		trackerIDs[key] = struct{}{}
		if err := validatePinnedAbsolutePath(tracker.Root); err != nil {
			return fmt.Errorf("tracker %s root: %w", tracker.TrackerUUID, err)
		}
		if _, exists := roots[tracker.Root]; exists {
			return fmt.Errorf("duplicate authoritative root %q", tracker.Root)
		}
		roots[tracker.Root] = struct{}{}
		if len(tracker.Repositories) == 0 {
			return fmt.Errorf("tracker %s requires at least one repository mapping", tracker.TrackerUUID)
		}
		for _, repo := range tracker.Repositories {
			if strings.TrimSpace(repo.Alias) == "" || repo.Alias != strings.TrimSpace(repo.Alias) {
				return fmt.Errorf("repository alias must be exact and nonempty")
			}
			aliasKey := strings.ToLower(repo.Alias)
			if _, exists := aliases[aliasKey]; exists {
				return fmt.Errorf("duplicate repository alias %q", repo.Alias)
			}
			aliases[aliasKey] = struct{}{}
			if err := validatePinnedAbsolutePath(repo.Worktree); err != nil {
				return fmt.Errorf("repository %s worktree: %w", repo.Alias, err)
			}
			if _, exists := worktrees[repo.Worktree]; exists {
				return fmt.Errorf("duplicate repository worktree %q", repo.Worktree)
			}
			worktrees[repo.Worktree] = struct{}{}
		}
	}
	return nil
}

func validatePinnedAbsolutePath(path string) error {
	if path == "" || !filepath.IsAbs(path) || filepath.Clean(path) != path || path == string(filepath.Separator) || strings.ContainsRune(path, '\x00') {
		return errors.New("path must be absolute, clean, non-root, and contain no NUL")
	}
	return nil
}

func validateTrackerMetadata(tracker workTracker) error {
	resolved, err := filepath.EvalSymlinks(tracker.Root)
	if err != nil {
		return fmt.Errorf("authority root unavailable for tracker %s: %w", tracker.TrackerUUID, err)
	}
	if resolved != tracker.Root {
		return fmt.Errorf("authority root for tracker %s is not the exact non-symlink path", tracker.TrackerUUID)
	}
	info, err := os.Stat(resolved)
	if err != nil || !info.IsDir() {
		return fmt.Errorf("authority root unavailable for tracker %s", tracker.TrackerUUID)
	}
	if err := verifyMetadataUUID(filepath.Join(resolved, ".beads", "metadata.json"), tracker.TrackerUUID, true); err != nil {
		return fmt.Errorf("tracker %s: %w", tracker.TrackerUUID, err)
	}
	for _, repo := range tracker.Repositories {
		metadata := filepath.Join(repo.Worktree, ".beads", "metadata.json")
		if _, err := os.Stat(metadata); err == nil {
			if err := verifyMetadataUUID(metadata, tracker.TrackerUUID, true); err != nil {
				return fmt.Errorf("repository %s: %w", repo.Alias, err)
			}
		} else if !os.IsNotExist(err) {
			return fmt.Errorf("repository %s metadata unavailable: %w", repo.Alias, err)
		}
	}
	return nil
}

func verifyMetadataUUID(path, want string, required bool) error {
	data, err := readBoundedRegularFile(path, 64<<10, "tracker metadata")
	if err != nil {
		if !required && os.IsNotExist(err) {
			return nil
		}
		return err
	}
	if err := rejectDuplicateJSONKeys(data); err != nil {
		return fmt.Errorf("malformed tracker metadata: %w", err)
	}
	var values map[string]json.RawMessage
	if err := json.Unmarshal(data, &values); err != nil {
		return fmt.Errorf("malformed tracker metadata: %w", err)
	}
	found := make(map[string]struct{})
	for _, key := range []string{"project_id"} {
		raw, ok := values[key]
		if !ok {
			continue
		}
		var value string
		if err := json.Unmarshal(raw, &value); err != nil || !workUUIDPattern.MatchString(value) {
			return fmt.Errorf("metadata %s must contain a valid UUID string", key)
		}
		found[strings.ToLower(value)] = struct{}{}
	}
	if len(found) == 0 {
		return errors.New("tracker metadata UUID missing; database name is not accepted as identity")
	}
	if len(found) != 1 {
		return errors.New("tracker metadata UUID is ambiguous")
	}
	if _, ok := found[strings.ToLower(want)]; !ok {
		return fmt.Errorf("tracker UUID mismatch: metadata does not match pinned registry UUID %s", want)
	}
	return nil
}

type cappedWorkBuffer struct {
	bytes.Buffer
	max      int
	exceeded bool
}

func (b *cappedWorkBuffer) Write(p []byte) (int, error) {
	if b.Buffer.Len()+len(p) > b.max {
		b.exceeded = true
		remaining := b.max - b.Buffer.Len()
		if remaining > 0 {
			_, _ = b.Buffer.Write(p[:remaining])
		}
		return len(p), errWorkOutputLimit
	}
	return b.Buffer.Write(p)
}

func readTrackerBeads(tracker workTracker, deps workDependencies) ([]workBead, error) {
	if deps.bdPath == "" {
		deps.bdPath = "bd"
	}
	if deps.timeout <= 0 {
		deps.timeout = 10 * time.Second
	}
	if deps.maxOutputByte <= 0 {
		deps.maxOutputByte = workDefaultOutputMax
	}
	ctx, cancel := context.WithTimeout(context.Background(), deps.timeout)
	defer cancel()
	argv := []string{"--readonly", "--directory", tracker.Root, "list", "--all", "--limit", "0", "--include-gates", "--json"}
	cmd := exec.CommandContext(ctx, deps.bdPath, argv...)
	cmd.Dir = tracker.Root
	cmd.Env = workReadEnvironment()
	cmd.WaitDelay = 250 * time.Millisecond
	var stdout cappedWorkBuffer
	stdout.max = deps.maxOutputByte
	var stderr cappedWorkBuffer
	stderr.max = 64 << 10
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	err := cmd.Run()
	if ctx.Err() == context.DeadlineExceeded {
		return nil, fmt.Errorf("authority read timed out for tracker %s", tracker.TrackerUUID)
	}
	if stderr.exceeded || stderr.Len() > stderr.max {
		return nil, fmt.Errorf("bounded authority stderr exceeded %d bytes for tracker %s", stderr.max, tracker.TrackerUUID)
	}
	if stdout.exceeded || stdout.Len() > deps.maxOutputByte {
		return nil, fmt.Errorf("bounded authority output exceeded %d bytes for tracker %s", deps.maxOutputByte, tracker.TrackerUUID)
	}
	if err != nil {
		message := strings.TrimSpace(stderr.String())
		if message != "" {
			return nil, fmt.Errorf("bd authority command failed for tracker %s: %w: %s", tracker.TrackerUUID, err, message)
		}
		return nil, fmt.Errorf("bd authority command failed for tracker %s: %w", tracker.TrackerUUID, err)
	}
	beads, err := parseWorkBeads(stdout.Bytes())
	if err != nil {
		return nil, fmt.Errorf("malformed authority output for tracker %s: %w", tracker.TrackerUUID, err)
	}
	return beads, nil
}

// Pass only process essentials; inherited tracker and configuration selectors
// must not redirect the explicitly selected diagnostic read.
func workReadEnvironment() []string {
	var env []string
	for _, key := range []string{"PATH", "HOME", "USER", "LOGNAME", "TMPDIR", "TMP", "TEMP", "LANG", "LC_ALL", "LC_CTYPE", "SystemRoot", "WINDIR"} {
		if value, ok := os.LookupEnv(key); ok {
			env = append(env, key+"="+value)
		}
	}
	return env
}

func parseWorkBeads(data []byte) ([]workBead, error) {
	if err := rejectDuplicateJSONKeys(data); err != nil {
		return nil, err
	}
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.UseNumber()
	var rows []map[string]json.RawMessage
	if err := decoder.Decode(&rows); err != nil {
		return nil, err
	}
	if err := requireJSONEOF(decoder); err != nil {
		return nil, err
	}
	if rows == nil {
		return nil, errors.New("expected a JSON array, got null")
	}
	seen := make(map[string]struct{})
	beads := make([]workBead, 0, len(rows))
	for i, row := range rows {
		id, err := workStringField(row, "id", true)
		if err != nil {
			return nil, fmt.Errorf("row %d: %w", i, err)
		}
		if _, exists := seen[id]; exists {
			return nil, fmt.Errorf("row %d: duplicate bead id %q", i, id)
		}
		seen[id] = struct{}{}
		title, err := workStringField(row, "title", true)
		if err != nil {
			return nil, fmt.Errorf("row %d: %w", i, err)
		}
		status, err := workStringField(row, "status", true)
		if err != nil {
			return nil, fmt.Errorf("row %d: %w", i, err)
		}
		assignee, err := workOwnerField(row)
		if err != nil {
			return nil, fmt.Errorf("row %d: %w", i, err)
		}
		fields := map[string]string{"title": title}
		for _, key := range []string{"objective", "description", "labels", "artifact_refs", "acceptance_criteria", "notes", "design", "external_ref"} {
			if raw, ok := row[key]; ok {
				value, err := workEvidenceText(raw)
				if err != nil {
					return nil, fmt.Errorf("row %d field %s: %w", i, key, err)
				}
				fields[key] = value
			}
		}
		beads = append(beads, workBead{ID: id, Title: title, Status: status, Assignee: assignee, SearchFields: fields})
	}
	return beads, nil
}

func workStringField(row map[string]json.RawMessage, key string, required bool) (string, error) {
	raw, ok := row[key]
	if !ok {
		if required {
			return "", fmt.Errorf("required field %q missing", key)
		}
		return "", nil
	}
	var value string
	if err := json.Unmarshal(raw, &value); err != nil {
		return "", fmt.Errorf("field %q must be a string", key)
	}
	if required && strings.TrimSpace(value) == "" {
		return "", fmt.Errorf("required field %q is empty", key)
	}
	return value, nil
}

func workOwnerField(row map[string]json.RawMessage) (string, error) {
	// Beads owner identifies the record owner, not the current claim holder.
	// An unassigned task stays unassigned even when owner is populated.
	return workStringField(row, "assignee", false)
}

func workEvidenceText(raw json.RawMessage) (string, error) {
	var value any
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()
	if err := decoder.Decode(&value); err != nil {
		return "", err
	}
	var parts []string
	var collect func(any) error
	collect = func(v any) error {
		switch item := v.(type) {
		case nil:
			return nil
		case string:
			parts = append(parts, item)
		case []any:
			for _, child := range item {
				if err := collect(child); err != nil {
					return err
				}
			}
		case map[string]any:
			keys := make([]string, 0, len(item))
			for key := range item {
				keys = append(keys, key)
			}
			sort.Strings(keys)
			for _, key := range keys {
				if err := collect(item[key]); err != nil {
					return err
				}
			}
		default:
			return fmt.Errorf("expected text, text array, or text object")
		}
		return nil
	}
	if err := collect(value); err != nil {
		return "", err
	}
	return strings.Join(parts, " "), nil
}

func discoverWorkCandidates(registry workRegistry, byTracker map[string][]workBead, evidence string) []workCandidate {
	tokens := workTokens(evidence)
	candidates := make([]workCandidate, 0)
	for _, tracker := range registry.Trackers {
		aliases := trackerAliases(tracker)
		for _, bead := range byTracker[tracker.TrackerUUID] {
			qualified := tracker.TrackerUUID + ":" + bead.ID
			exact := containsExactQualifiedReference(evidence, qualified)
			score, fields := scoreWorkBead(bead, tokens, evidence)
			active := strings.EqualFold(bead.Status, "in_progress")
			if !exact && score == 0 && !active {
				continue
			}
			classification := "ambiguous_shared_evidence_candidate"
			reason := "lexical overlap is evidence only and requires agent disposition"
			if exact {
				classification = "exact_tracker_task_reference"
				reason = "input contains the exact tracker UUID plus Bead ID; implementation remains blocked because binding authority is not live"
			} else if active && score == 0 {
				classification = "active_work_unranked"
				reason = "retained because every in-progress task is shown, regardless of lexical rank"
			}
			candidates = append(candidates, workCandidate{
				workTask: workTask{TrackerUUID: tracker.TrackerUUID, BeadID: bead.ID, Title: bead.Title, BeadsStatus: bead.Status, BeadsAssignee: bead.Assignee, Aliases: aliases},
				Score:    score, MatchedFields: fields, Classification: classification, Reason: reason,
			})
		}
	}
	sort.SliceStable(candidates, func(i, j int) bool {
		if candidates[i].Classification != candidates[j].Classification {
			order := map[string]int{"exact_tracker_task_reference": 0, "ambiguous_shared_evidence_candidate": 1, "active_work_unranked": 2}
			return order[candidates[i].Classification] < order[candidates[j].Classification]
		}
		if candidates[i].Score != candidates[j].Score {
			return candidates[i].Score > candidates[j].Score
		}
		if candidates[i].TrackerUUID != candidates[j].TrackerUUID {
			return candidates[i].TrackerUUID < candidates[j].TrackerUUID
		}
		return candidates[i].BeadID < candidates[j].BeadID
	})
	return candidates
}

func scoreWorkBead(bead workBead, tokens []string, evidence string) (int, []string) {
	if len(tokens) == 0 {
		return 0, nil
	}
	score := 0
	var matched []string
	query := strings.ToLower(strings.TrimSpace(evidence))
	for field, text := range bead.SearchFields {
		lower := strings.ToLower(text)
		fieldScore := 0
		for _, token := range tokens {
			if strings.Contains(lower, token) {
				fieldScore++
			}
		}
		if query != "" && strings.Contains(lower, query) {
			fieldScore += 5
		}
		if fieldScore > 0 {
			score += fieldScore
			matched = append(matched, field)
		}
	}
	sort.Strings(matched)
	return score, matched
}

func workTokens(text string) []string {
	seen := make(map[string]struct{})
	var tokens []string
	for _, field := range strings.FieldsFunc(strings.ToLower(text), func(r rune) bool {
		return !(unicode.IsLetter(r) || unicode.IsDigit(r) || r == '_' || r == '-' || r == '.' || r == '/')
	}) {
		if len(field) < 3 || workStopWord(field) {
			continue
		}
		if _, ok := seen[field]; ok {
			continue
		}
		seen[field] = struct{}{}
		tokens = append(tokens, field)
	}
	return tokens
}

func workStopWord(value string) bool {
	switch value {
	case "and", "the", "for", "from", "that", "this", "with", "into", "must", "use", "only":
		return true
	default:
		return false
	}
}

func containsExactQualifiedReference(text, reference string) bool {
	start := 0
	for {
		index := strings.Index(text[start:], reference)
		if index < 0 {
			return false
		}
		index += start
		beforeOK := index == 0 || workReferenceBoundary(rune(text[index-1]))
		after := index + len(reference)
		afterOK := after == len(text) || workReferenceBoundary(rune(text[after]))
		if beforeOK && afterOK {
			return true
		}
		start = index + 1
	}
}

func workReferenceBoundary(r rune) bool {
	return unicode.IsSpace(r) || strings.ContainsRune("()[]{}<>,;\"'", r)
}

func parseQualifiedWorkTask(value string) (string, string, error) {
	parts := strings.Split(value, ":")
	if len(parts) != 2 || !workUUIDPattern.MatchString(parts[0]) || strings.TrimSpace(parts[1]) == "" || parts[1] != strings.TrimSpace(parts[1]) {
		return "", "", errors.New("--task must be an exact trackerUUID:BeadID reference")
	}
	return parts[0], parts[1], nil
}

func findWorkTask(registry workRegistry, byTracker map[string][]workBead, trackerUUID, beadID string) (workTask, bool) {
	for _, tracker := range registry.Trackers {
		if !strings.EqualFold(tracker.TrackerUUID, trackerUUID) {
			continue
		}
		for _, bead := range byTracker[tracker.TrackerUUID] {
			if bead.ID == beadID {
				return workTask{TrackerUUID: tracker.TrackerUUID, BeadID: bead.ID, Title: bead.Title, BeadsStatus: bead.Status, BeadsAssignee: bead.Assignee, Aliases: trackerAliases(tracker)}, true
			}
		}
		return workTask{}, false
	}
	return workTask{}, false
}

func trackerAliases(tracker workTracker) []string {
	aliases := make([]string, 0, len(tracker.Repositories))
	for _, repo := range tracker.Repositories {
		aliases = append(aliases, repo.Alias)
	}
	sort.Strings(aliases)
	return aliases
}

func renderWorkResult(w io.Writer, result workResult, jsonOutput bool) error {
	if jsonOutput {
		encoded, err := json.MarshalIndent(result, "", "  ")
		if err != nil {
			return err
		}
		_, err = fmt.Fprintln(w, string(encoded))
		return err
	}
	fmt.Fprintf(w, "work %s: binding_authority=%s implementation_allowed=%t coverage=%s coverage_scope=%s\n", result.Command, result.BindingAuthority, result.ImplementationAllowed, result.Coverage, result.CoverageScope)
	fmt.Fprintf(w, "authority: %s; result: %s; optional Alwe history: %s; attached sessions: %s\n", result.AuthorityStatus, result.ResultStatus, result.HistoryStatus, result.AttachedSessions)
	if result.Task != nil {
		fmt.Fprintf(w, "task: %s:%s — %q\n", result.Task.TrackerUUID, result.Task.BeadID, result.Task.Title)
		fmt.Fprintf(w, "BEADS status: %s\nBEADS assignee: %s\n", result.Task.BeadsStatus, displayWorkOwner(result.Task.BeadsAssignee))
	}
	for _, candidate := range result.Candidates {
		fmt.Fprintf(w, "candidate: %s:%s score=%d classification=%s status=%s BEADS_assignee=%s title=%q\n", candidate.TrackerUUID, candidate.BeadID, candidate.Score, candidate.Classification, candidate.BeadsStatus, displayWorkOwner(candidate.BeadsAssignee), candidate.Title)
	}
	if result.Explanation != "" {
		fmt.Fprintln(w, result.Explanation)
	}
	fmt.Fprintln(w, "classification limit:", result.ClassificationLimit)
	return nil
}

func displayWorkOwner(owner string) string {
	if owner == "" {
		return "unassigned"
	}
	quoted := strconv.Quote(owner)
	return quoted[1 : len(quoted)-1]
}

func readBoundedRegularFile(path string, limit int64, label string) ([]byte, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("%s unavailable: %w", label, err)
	}
	defer file.Close()
	info, err := file.Stat()
	if err != nil {
		return nil, fmt.Errorf("%s unavailable: %w", label, err)
	}
	if !info.Mode().IsRegular() {
		return nil, fmt.Errorf("%s must be a regular file", label)
	}
	if info.Size() > limit {
		return nil, fmt.Errorf("%s exceeds %d-byte limit", label, limit)
	}
	data, err := io.ReadAll(io.LimitReader(file, limit+1))
	if err != nil {
		return nil, fmt.Errorf("read %s: %w", label, err)
	}
	if int64(len(data)) > limit {
		return nil, fmt.Errorf("%s exceeds %d-byte limit", label, limit)
	}
	return data, nil
}

func rejectDuplicateJSONKeys(data []byte) error {
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.UseNumber()
	if err := scanWorkJSONValue(decoder); err != nil {
		return err
	}
	return requireJSONEOF(decoder)
}

func scanWorkJSONValue(decoder *json.Decoder) error {
	token, err := decoder.Token()
	if err != nil {
		return err
	}
	delim, ok := token.(json.Delim)
	if !ok {
		return nil
	}
	switch delim {
	case '{':
		seen := make(map[string]struct{})
		for decoder.More() {
			keyToken, err := decoder.Token()
			if err != nil {
				return err
			}
			key, ok := keyToken.(string)
			if !ok {
				return errors.New("object key is not a string")
			}
			if _, exists := seen[key]; exists {
				return fmt.Errorf("duplicate JSON key %q", key)
			}
			seen[key] = struct{}{}
			if err := scanWorkJSONValue(decoder); err != nil {
				return err
			}
		}
		end, err := decoder.Token()
		if err != nil || end != json.Delim('}') {
			return errors.New("malformed JSON object")
		}
	case '[':
		for decoder.More() {
			if err := scanWorkJSONValue(decoder); err != nil {
				return err
			}
		}
		end, err := decoder.Token()
		if err != nil || end != json.Delim(']') {
			return errors.New("malformed JSON array")
		}
	default:
		return errors.New("unexpected JSON delimiter")
	}
	return nil
}

func requireJSONEOF(decoder *json.Decoder) error {
	var extra any
	if err := decoder.Decode(&extra); err != io.EOF {
		if err == nil {
			return errors.New("multiple JSON values are not allowed")
		}
		return err
	}
	return nil
}
