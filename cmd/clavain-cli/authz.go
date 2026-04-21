package main

import (
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/mistakeknot/intercore/pkg/authz"
	_ "modernc.org/sqlite"
)

// ─── Exit-code sentinels (translated to os.Exit codes by main.go) ──────

// ErrPolicyConfirm signals the caller must confirm the op (exit 1 for non-tty).
var ErrPolicyConfirm = errors.New("policy: confirmation required")

// ErrPolicyBlocked signals the op is policy-blocked (exit 2).
var ErrPolicyBlocked = errors.New("policy: operation blocked")

// ErrPolicyMalformed signals the policy YAML is unparseable (exit 3).
var ErrPolicyMalformed = errors.New("policy: malformed")

// ─── Policy check output schema ──────────────────────────────────────

// policyCheckOutputSchema is bumped when the shape of PolicyCheckOutput changes.
const policyCheckOutputSchema = 1

// PolicyCheckOutput is the stdout JSON from `policy check`.
type PolicyCheckOutput struct {
	Schema      int    `json:"schema"`
	Mode        string `json:"mode"`
	PolicyMatch string `json:"policy_match"`
	PolicyHash  string `json:"policy_hash"`
	Reason      string `json:"reason"`
}

// ─── Helpers ──────────────────────────────────────────────────────────

// policyDefaultPaths returns default lookup paths for the 3 layered policies.
// Empty string means "skip this layer".
func policyDefaultPaths() (global, project, env string) {
	if home, err := os.UserHomeDir(); err == nil {
		global = filepath.Join(home, ".clavain", "policy.yaml")
	}
	project = ".clavain/policy.yaml"
	env = ".clavain/policy.env.yaml"
	return
}

// policyResolvePaths applies --global/--project/--env flag overrides over
// defaults. Missing files are skipped (empty path passed to LoadEffective).
func policyResolvePaths(args map[string]string) (global, project, env string) {
	g, p, e := policyDefaultPaths()
	if v, ok := args["global"]; ok {
		g = v
	}
	if v, ok := args["project"]; ok {
		p = v
	}
	if v, ok := args["env"]; ok {
		e = v
	}
	return emptyIfMissing(g), emptyIfMissing(p), emptyIfMissing(e)
}

func emptyIfMissing(path string) string {
	if path == "" {
		return ""
	}
	if _, err := os.Stat(path); err != nil {
		return ""
	}
	return path
}

// parseAuthzArgs parses --key=val pairs and flags into a string map.
// Positional args are stored under "_pos_<N>".
func parseAuthzArgs(args []string) map[string]string {
	out := map[string]string{}
	pos := 0
	for _, a := range args {
		if !strings.HasPrefix(a, "--") {
			out[fmt.Sprintf("_pos_%d", pos)] = a
			pos++
			continue
		}
		a = strings.TrimPrefix(a, "--")
		if eq := strings.IndexByte(a, '='); eq >= 0 {
			out[a[:eq]] = a[eq+1:]
		} else {
			out[a] = "true"
		}
	}
	return out
}

// findIntercoreDB walks up from CWD looking for .clavain/intercore.db.
// Returns the path if found, or empty string.
func findIntercoreDB() string {
	dir, err := os.Getwd()
	if err != nil {
		return ""
	}
	for {
		candidate := filepath.Join(dir, ".clavain", "intercore.db")
		if _, err := os.Stat(candidate); err == nil {
			return candidate
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			break
		}
		dir = parent
	}
	return ""
}

// openIntercoreDB opens the project intercore.db with the required PRAGMAs.
// The caller is responsible for closing.
func openIntercoreDB() (*sql.DB, string, error) {
	path := findIntercoreDB()
	if path == "" {
		return nil, "", fmt.Errorf("intercore.db not found in .clavain/ (walk from CWD)")
	}
	db, err := sql.Open("sqlite", path+"?_busy_timeout=5000")
	if err != nil {
		return nil, "", fmt.Errorf("open intercore.db: %w", err)
	}
	db.SetMaxOpenConns(1)
	return db, path, nil
}

// currentHeadSHA returns `git rev-parse HEAD` or empty string.
func currentHeadSHA() string {
	out, err := exec.Command("git", "rev-parse", "HEAD").Output()
	if err != nil {
		return ""
	}
	return strings.TrimSpace(string(out))
}

// ─── policy check ─────────────────────────────────────────────────────

// cmdPolicyCheck evaluates a CheckInput against merged policy.
//
//	clavain-cli policy check <op> [flags]
//
// Flags:
//
//	--target=<str>             op-specific target (bead id, branch, plugin)
//	--bead=<id>                bead context
//	--agent=<id>               agent identity (required for record; optional here)
//	--vetted-at=<unix>         seconds since epoch
//	--vetted-sha=<sha>
//	--tests-passed             (flag; implies true)
//	--sprint-or-work-flow      (flag; implies true)
//	--head-sha=<sha>           default: `git rev-parse HEAD`
//	--global=<path> --project=<path> --env=<path>  override policy paths
//	--json                     emit JSON (default true in v1)
//
// Exit codes: 0 auto/force_auto, 1 confirm, 2 blocked, 3 malformed.
func cmdPolicyCheck(args []string) error {
	if len(args) < 1 || strings.HasPrefix(args[0], "--") {
		return fmt.Errorf("usage: policy check <op> [flags]")
	}
	op := args[0]
	flags := parseAuthzArgs(args[1:])

	globalPath, projectPath, envPath := policyResolvePaths(flags)
	merged, hash, err := authz.LoadEffective(globalPath, projectPath, envPath)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		return ErrPolicyMalformed
	}
	if merged == nil {
		return fmt.Errorf("no policy configured")
	}

	input := authz.CheckInput{Op: op, Now: time.Now()}
	if v, ok := flags["target"]; ok {
		input.Target = v
	}
	if v, ok := flags["bead"]; ok {
		input.BeadID = v
	}
	if v, ok := flags["head-sha"]; ok {
		input.HeadSHA = v
	} else {
		input.HeadSHA = currentHeadSHA()
	}
	if v, ok := flags["vetted-sha"]; ok {
		input.VettedSHA = v
	}
	if v, ok := flags["vetted-at"]; ok {
		if ts, err := strconv.ParseInt(v, 10, 64); err == nil {
			input.VettedAt = time.Unix(ts, 0)
		}
	}
	if _, ok := flags["tests-passed"]; ok {
		input.TestsPassed = true
	}
	if _, ok := flags["sprint-or-work-flow"]; ok {
		input.SprintOrWorkFlow = true
	}

	result, err := authz.Check(merged, input)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		return ErrPolicyMalformed
	}
	out := PolicyCheckOutput{
		Schema:      policyCheckOutputSchema,
		Mode:        result.Mode,
		PolicyMatch: result.PolicyMatch,
		PolicyHash:  hash,
		Reason:      result.Reason,
	}
	if err := outputJSON(out); err != nil {
		return err
	}

	switch result.Mode {
	case authz.ModeAuto, authz.ModeForceAuto:
		return nil
	case authz.ModeConfirm:
		return ErrPolicyConfirm
	case authz.ModeBlock:
		return ErrPolicyBlocked
	default:
		return fmt.Errorf("unknown mode: %s", result.Mode)
	}
}

// ─── policy record ────────────────────────────────────────────────────

// cmdPolicyRecord inserts one authorizations row.
//
//	clavain-cli policy record --op=<op> --target=<t> --agent=<a> --mode=<m>
//	                          [--bead=<id>] [--policy-match=<s>] [--policy-hash=<h>]
//	                          [--vetted-sha=<sha>] [--cross-project-id=<id>]
func cmdPolicyRecord(args []string) error {
	flags := parseAuthzArgs(args)
	required := []string{"op", "target", "agent", "mode"}
	for _, k := range required {
		if _, ok := flags[k]; !ok {
			return fmt.Errorf("policy record: missing --%s", k)
		}
	}
	db, _, err := openIntercoreDB()
	if err != nil {
		return err
	}
	defer db.Close()

	recArgs := authz.RecordArgs{
		OpType:         flags["op"],
		Target:         flags["target"],
		AgentID:        flags["agent"],
		Mode:           flags["mode"],
		BeadID:         flags["bead"],
		PolicyMatch:    flags["policy-match"],
		PolicyHash:     flags["policy-hash"],
		VettedSHA:      flags["vetted-sha"],
		CrossProjectID: flags["cross-project-id"],
	}
	if err := authz.Record(db, recArgs); err != nil {
		return fmt.Errorf("policy record: %w", err)
	}
	return nil
}

// ─── policy list ──────────────────────────────────────────────────────

// cmdPolicyList prints the merged effective policy as YAML-ish JSON.
//
//	clavain-cli policy list [--global=...] [--project=...] [--env=...]
func cmdPolicyList(args []string) error {
	flags := parseAuthzArgs(args)
	globalPath, projectPath, envPath := policyResolvePaths(flags)
	merged, hash, err := authz.LoadEffective(globalPath, projectPath, envPath)
	if err != nil {
		return fmt.Errorf("policy list: %w", err)
	}
	if merged == nil {
		fmt.Println("{}")
		return nil
	}
	payload := map[string]interface{}{
		"policy":      merged,
		"policy_hash": hash,
		"sources": map[string]string{
			"global":  globalPath,
			"project": projectPath,
			"env":     envPath,
		},
	}
	return outputJSON(payload)
}

// ─── policy explain ───────────────────────────────────────────────────

// cmdPolicyExplain emits human-readable diagnostics for a decision.
// It runs the same eval path as `policy check` but formats plain text.
//
//	clavain-cli policy explain <op> [same flags as check]
func cmdPolicyExplain(args []string) error {
	if len(args) < 1 || strings.HasPrefix(args[0], "--") {
		return fmt.Errorf("usage: policy explain <op> [flags]")
	}
	op := args[0]
	flags := parseAuthzArgs(args[1:])

	globalPath, projectPath, envPath := policyResolvePaths(flags)
	merged, hash, err := authz.LoadEffective(globalPath, projectPath, envPath)
	if err != nil {
		return fmt.Errorf("policy explain: %w", err)
	}
	if merged == nil {
		fmt.Println("no policy configured → default confirm")
		return nil
	}

	input := authz.CheckInput{Op: op, Now: time.Now()}
	if v, ok := flags["bead"]; ok {
		input.BeadID = v
	}
	if v, ok := flags["head-sha"]; ok {
		input.HeadSHA = v
	} else {
		input.HeadSHA = currentHeadSHA()
	}
	if v, ok := flags["vetted-sha"]; ok {
		input.VettedSHA = v
	}
	if v, ok := flags["vetted-at"]; ok {
		if ts, err := strconv.ParseInt(v, 10, 64); err == nil {
			input.VettedAt = time.Unix(ts, 0)
		}
	}
	if _, ok := flags["tests-passed"]; ok {
		input.TestsPassed = true
	}
	if _, ok := flags["sprint-or-work-flow"]; ok {
		input.SprintOrWorkFlow = true
	}

	result, err := authz.Check(merged, input)
	if err != nil {
		return fmt.Errorf("policy explain: %w", err)
	}
	fmt.Printf("op:          %s\n", op)
	fmt.Printf("decision:    %s\n", result.Mode)
	fmt.Printf("rule match:  %s\n", result.PolicyMatch)
	fmt.Printf("reason:      %s\n", result.Reason)
	fmt.Printf("policy hash: %s\n", hash)
	fmt.Printf("sources:     global=%s project=%s env=%s\n", displayPath(globalPath), displayPath(projectPath), displayPath(envPath))
	return nil
}

func displayPath(p string) string {
	if p == "" {
		return "(none)"
	}
	return p
}

// ─── policy audit ─────────────────────────────────────────────────────

// cmdPolicyAudit queries the authorizations table.
//
//	clavain-cli policy audit [--since=<duration>] [--op=<op>] [--agent=<id>]
//	                         [--bead=<id>] [--limit=<n>] [--verify]
//
// `--verify` surfaces cross_project_id groups with missing rows across
// `ic-publish-patch` target projects (best-effort; v1 reports only).
func cmdPolicyAudit(args []string) error {
	flags := parseAuthzArgs(args)
	db, _, err := openIntercoreDB()
	if err != nil {
		return err
	}
	defer db.Close()

	if _, ok := flags["verify"]; ok {
		return maybeAuditVerify(db, flags)
	}

	where := []string{"1=1"}
	params := []interface{}{}
	if v, ok := flags["since"]; ok {
		d, err := time.ParseDuration(v)
		if err != nil {
			return fmt.Errorf("policy audit: invalid --since: %w", err)
		}
		where = append(where, "created_at >= ?")
		params = append(params, time.Now().Add(-d).Unix())
	}
	for _, k := range []string{"op", "agent", "bead"} {
		if v, ok := flags[k]; ok {
			col := map[string]string{"op": "op_type", "agent": "agent_id", "bead": "bead_id"}[k]
			where = append(where, col+" = ?")
			params = append(params, v)
		}
	}
	limit := 200
	if v, ok := flags["limit"]; ok {
		if n, err := strconv.Atoi(v); err == nil && n > 0 {
			limit = n
		}
	}
	q := fmt.Sprintf(`
		SELECT id, op_type, target, agent_id, IFNULL(bead_id,''), mode,
		       IFNULL(policy_match,''), IFNULL(policy_hash,''),
		       IFNULL(vetted_sha,''), IFNULL(cross_project_id,''), created_at
		FROM authorizations
		WHERE %s
		ORDER BY created_at DESC
		LIMIT %d`, strings.Join(where, " AND "), limit)
	rows, err := db.Query(q, params...)
	if err != nil {
		return fmt.Errorf("policy audit: %w", err)
	}
	defer rows.Close()

	type row struct {
		ID             string `json:"id"`
		OpType         string `json:"op_type"`
		Target         string `json:"target"`
		AgentID        string `json:"agent_id"`
		BeadID         string `json:"bead_id"`
		Mode           string `json:"mode"`
		PolicyMatch    string `json:"policy_match"`
		PolicyHash     string `json:"policy_hash"`
		VettedSHA      string `json:"vetted_sha"`
		CrossProjectID string `json:"cross_project_id"`
		CreatedAt      int64  `json:"created_at"`
	}
	var results []row
	for rows.Next() {
		var r row
		if err := rows.Scan(&r.ID, &r.OpType, &r.Target, &r.AgentID, &r.BeadID, &r.Mode, &r.PolicyMatch, &r.PolicyHash, &r.VettedSHA, &r.CrossProjectID, &r.CreatedAt); err != nil {
			return fmt.Errorf("policy audit scan: %w", err)
		}
		results = append(results, r)
	}
	return outputJSON(results)
}

// ─── policy lint ──────────────────────────────────────────────────────

// cmdPolicyLint validates the merged policy against invariants:
//
//  1. MUST have a terminal catchall (op: "*") last in merged order.
//  2. MUST NOT have a child layer loosening a required boolean without
//     parent allow_override — surfaced as a merge error during LoadEffective.
//  3. Every op declared in .clavain/gates/*.gate MUST have a matching rule
//     (or a catchall) in the merged policy.
//
//	clavain-cli policy lint [--global=...] [--project=...] [--env=...]
//	                        [--gates-dir=.clavain/gates]
func cmdPolicyLint(args []string) error {
	flags := parseAuthzArgs(args)
	globalPath, projectPath, envPath := policyResolvePaths(flags)
	merged, _, err := authz.LoadEffective(globalPath, projectPath, envPath)
	if err != nil {
		return fmt.Errorf("policy lint: merge failed: %w", err)
	}
	if merged == nil {
		return fmt.Errorf("policy lint: no policy configured")
	}

	var problems []string

	if len(merged.Rules) == 0 {
		problems = append(problems, "policy has no rules")
	} else {
		last := merged.Rules[len(merged.Rules)-1]
		if last.Op != "*" {
			problems = append(problems, fmt.Sprintf("last rule op=%q; must be \"*\" (terminal catchall)", last.Op))
		}
		for i, r := range merged.Rules[:len(merged.Rules)-1] {
			if r.Op == "*" {
				problems = append(problems, fmt.Sprintf("catchall \"*\" at index %d; must be terminal only", i))
			}
		}
	}

	gatesDir := flags["gates-dir"]
	if gatesDir == "" {
		gatesDir = ".clavain/gates"
	}
	if ops, err := declaredGateOps(gatesDir); err == nil {
		sort.Strings(ops)
		catchallPresent := hasCatchall(merged)
		for _, op := range ops {
			if !ruleCovers(merged, op) && !catchallPresent {
				problems = append(problems, fmt.Sprintf("gate declared for op %q but no matching rule or catchall", op))
			}
		}
	}

	if len(problems) == 0 {
		fmt.Println("policy lint: OK")
		return nil
	}
	for _, p := range problems {
		fmt.Fprintln(os.Stderr, "problem: "+p)
	}
	return fmt.Errorf("policy lint: %d problem(s)", len(problems))
}

func hasCatchall(p *authz.Policy) bool {
	for _, r := range p.Rules {
		if r.Op == "*" {
			return true
		}
	}
	return false
}

func ruleCovers(p *authz.Policy, op string) bool {
	for _, r := range p.Rules {
		if r.Op == op {
			return true
		}
	}
	return false
}

// declaredGateOps reads .clavain/gates/*.gate and extracts the `op=` key from
// each. Files are simple key=value\n\... text; missing dir → empty list.
func declaredGateOps(dir string) ([]string, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	var ops []string
	for _, e := range entries {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".gate") {
			continue
		}
		data, err := os.ReadFile(filepath.Join(dir, e.Name()))
		if err != nil {
			continue
		}
		for _, line := range strings.Split(string(data), "\n") {
			line = strings.TrimSpace(line)
			if strings.HasPrefix(line, "op=") {
				ops = append(ops, strings.TrimPrefix(line, "op="))
				break
			}
		}
	}
	return ops, nil
}

// ─── main.go dispatch hook ────────────────────────────────────────────

// cmdPolicy is the `policy` subcommand dispatcher.
func cmdPolicy(args []string) error {
	if len(args) < 1 {
		return fmt.Errorf("usage: policy <check|record|explain|audit|list|lint|init-key|sign|verify|rotate-key|quarantine|token> [...]")
	}
	sub, rest := args[0], args[1:]
	switch sub {
	case "check":
		return cmdPolicyCheck(rest)
	case "record":
		return cmdPolicyRecord(rest)
	case "explain":
		return cmdPolicyExplain(rest)
	case "audit":
		return cmdPolicyAudit(rest)
	case "list":
		return cmdPolicyList(rest)
	case "lint":
		return cmdPolicyLint(rest)
	case "init-key":
		return cmdPolicyInitKey(rest)
	case "sign":
		return cmdPolicySign(rest)
	case "verify":
		return cmdPolicyVerify(rest)
	case "rotate-key":
		return cmdPolicyRotateKey(rest)
	case "quarantine":
		return cmdPolicyQuarantine(rest)
	case "token":
		return cmdPolicyToken(rest)
	default:
		return fmt.Errorf("unknown policy subcommand: %s (check|record|explain|audit|list|lint|init-key|sign|verify|rotate-key|quarantine|token)", sub)
	}
}

// jsonEncode is a tiny helper for tests that need the canonical encoding.
func jsonEncode(v interface{}) string {
	b, _ := json.Marshal(v)
	return string(b)
}
