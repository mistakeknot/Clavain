package main

import (
	"fmt"
	"os"
	"time"

	"github.com/mistakeknot/intercore/pkg/authz"
)

// ─── ExitCode propagation ─────────────────────────────────────────────

// tokenExit wraps an authz-token error with the 5-class CLI exit code
// produced by authz.ExitCode. main.go extracts the code via errors.As on
// the ExitCoder interface and translates it to os.Exit. The library error
// remains unwrapped so errors.Is checks still match on sentinel identity.
type tokenExit struct {
	err  error
	code int
}

func (e *tokenExit) Error() string { return e.err.Error() }
func (e *tokenExit) Unwrap() error { return e.err }
func (e *tokenExit) ExitCode() int { return e.code }

// reportTokenErr prints "ERROR <class>: <reason>" to stderr (per plan Task 4
// Step 3) and wraps the error with its authz exit-code class. main.go must
// NOT print the wrapped error a second time — the errors.As(ExitCoder) branch
// exits without re-emitting.
func reportTokenErr(err error) error {
	if err == nil {
		return nil
	}
	code := authz.ExitCode(err)
	class := authz.ErrClass(err)
	fmt.Fprintf(os.Stderr, "ERROR %s: %s\n", class, err.Error())
	return &tokenExit{err: err, code: code}
}

// requireAgentID reads $CLAVAIN_AGENT_ID. The library never reads env vars;
// the CLI composition root passes agent id in by value.
func requireAgentID() (string, error) {
	if v := os.Getenv("CLAVAIN_AGENT_ID"); v != "" {
		return v, nil
	}
	return "", fmt.Errorf("CLAVAIN_AGENT_ID not set (required for policy token ops)")
}

// ─── Dispatcher ───────────────────────────────────────────────────────

// cmdPolicyToken dispatches `clavain-cli policy token <sub> [flags]`.
// All subcommands share the flag-parse (--key=val) and DB-lookup conventions
// of the rest of the policy surface.
func cmdPolicyToken(args []string) error {
	if len(args) < 1 {
		return usagePolicyToken()
	}
	sub, rest := args[0], args[1:]
	switch sub {
	case "issue":
		return cmdPolicyTokenIssue(rest)
	case "consume":
		return cmdPolicyTokenConsume(rest)
	case "delegate":
		return cmdPolicyTokenDelegate(rest)
	case "revoke":
		return cmdPolicyTokenRevoke(rest)
	case "list":
		return cmdPolicyTokenList(rest)
	case "show":
		return cmdPolicyTokenShow(rest)
	case "verify":
		return cmdPolicyTokenVerify(rest)
	default:
		return usagePolicyToken()
	}
}

func usagePolicyToken() error {
	return fmt.Errorf("Usage: policy token <issue|consume|delegate|revoke|list|show|verify> [flags]")
}

// parseTTL accepts Go duration strings ("60m", "24h", "5m"). The library
// rejects TTL <= 0, so "0s" is surfaced as a library error rather than here.
func parseTTL(s string) (time.Duration, error) {
	if s == "" {
		return 0, fmt.Errorf("--ttl required")
	}
	return time.ParseDuration(s)
}

// ─── issue ────────────────────────────────────────────────────────────

// cmdPolicyTokenIssue emits a fresh root token. Opaque string goes to stdout
// (only line on success). A v1.5 authorization row is also recorded describing
// the issue event — distinct from the consume-audit row that ConsumeToken
// writes inside its transaction.
//
//	clavain-cli policy token issue --op=<o> --target=<t> --for=<agent>
//	                               --ttl=<dur> [--bead=<id>]
func cmdPolicyTokenIssue(args []string) error {
	flags := parseAuthzArgs(args)
	op := flags["op"]
	target := flags["target"]
	forAgent := flags["for"]
	ttlStr := flags["ttl"]
	bead := flags["bead"]
	if op == "" || target == "" || forAgent == "" || ttlStr == "" {
		return fmt.Errorf("usage: policy token issue --op=<o> --target=<t> --for=<agent> --ttl=<dur> [--bead=<id>]")
	}
	ttl, err := parseTTL(ttlStr)
	if err != nil {
		return fmt.Errorf("--ttl: %w", err)
	}
	agentID, err := requireAgentID()
	if err != nil {
		return err
	}

	db, _, root, err := openIntercoreDBAndRoot()
	if err != nil {
		return err
	}
	defer db.Close()

	kp, err := authz.LoadPrivKey(root)
	if err != nil {
		return fmt.Errorf("load priv key: %w", err)
	}

	now := time.Now().Unix()
	spec := authz.IssueSpec{
		OpType:   op,
		Target:   target,
		AgentID:  forAgent,
		BeadID:   bead,
		IssuedBy: agentID,
		TTL:      ttl,
	}
	tok, opaque, err := authz.IssueToken(db, kp.Priv, spec, now)
	if err != nil {
		return reportTokenErr(err)
	}

	vetting := map[string]interface{}{
		"via":         "token-issue",
		"token_id":    tok.ID,
		"delegate_to": forAgent,
		"expires_at":  tok.ExpiresAt,
	}
	if err := authz.Record(db, authz.RecordArgs{
		OpType:    "authz.token-issue",
		Target:    tok.ID,
		AgentID:   agentID,
		BeadID:    bead,
		Mode:      "auto",
		Vetting:   vetting,
		CreatedAt: now,
	}); err != nil {
		return fmt.Errorf("audit issue: %w", err)
	}

	fmt.Println(opaque)
	return nil
}

// ─── consume ──────────────────────────────────────────────────────────

// cmdPolicyTokenConsume atomically claims a single-use token. The audit
// record is written inside ConsumeToken's transaction; this handler only
// emits the sentinel-wrapped unset-env payload for `eval`-consumption.
//
//	clavain-cli policy token consume [--token=<str>] --expect-op=<o>
//	                                 --expect-target=<t>
//
// If --token is omitted, $CLAVAIN_AUTHZ_TOKEN is read. --expect-op /
// --expect-target are optional but wrappers always pass them; an empty value
// produces a scope-skipped warning to stderr for observability (r3 P2).
func cmdPolicyTokenConsume(args []string) error {
	flags := parseAuthzArgs(args)
	tokenStr := flags["token"]
	if tokenStr == "" {
		tokenStr = os.Getenv("CLAVAIN_AUTHZ_TOKEN")
	}
	if tokenStr == "" {
		return fmt.Errorf("usage: policy token consume --token=<str> --expect-op=<o> --expect-target=<t> (or set $CLAVAIN_AUTHZ_TOKEN)")
	}
	expectOp := flags["expect-op"]
	expectTarget := flags["expect-target"]
	if expectOp == "" || expectTarget == "" {
		fmt.Fprintln(os.Stderr, "warn: scope check skipped (pass --expect-op and --expect-target to enforce)")
	}
	agentID, err := requireAgentID()
	if err != nil {
		return err
	}

	db, _, root, err := openIntercoreDBAndRoot()
	if err != nil {
		return err
	}
	defer db.Close()

	pub, err := authz.LoadPubKey(root)
	if err != nil {
		return fmt.Errorf("load pub key: %w", err)
	}

	now := time.Now().Unix()
	if _, err := authz.ConsumeToken(db, pub, tokenStr, agentID, expectOp, expectTarget, now); err != nil {
		return reportTokenErr(err)
	}

	// Sentinel-wrapped unset so `eval "$(clavain-cli policy token consume …)"`
	// can clear the env var, and a paranoid caller can grep the block and
	// reject stdout that emits anything between the begin/end markers.
	fmt.Println("# authz-unset-begin")
	fmt.Println("unset CLAVAIN_AUTHZ_TOKEN")
	fmt.Println("# authz-unset-end")
	return nil
}

// ─── delegate ─────────────────────────────────────────────────────────

// cmdPolicyTokenDelegate issues a child token narrower than or equal to the
// parent. POP is enforced: $CLAVAIN_AGENT_ID must match the parent's AgentID
// (else exit 4, pop-mismatch).
//
//	clavain-cli policy token delegate --from=<parent-ulid> --to=<agent>
//	                                  --ttl=<dur>
func cmdPolicyTokenDelegate(args []string) error {
	flags := parseAuthzArgs(args)
	parentID := flags["from"]
	toAgent := flags["to"]
	ttlStr := flags["ttl"]
	if parentID == "" || toAgent == "" || ttlStr == "" {
		return fmt.Errorf("usage: policy token delegate --from=<parent-ulid> --to=<agent> --ttl=<dur>")
	}
	ttl, err := parseTTL(ttlStr)
	if err != nil {
		return fmt.Errorf("--ttl: %w", err)
	}
	agentID, err := requireAgentID()
	if err != nil {
		return err
	}

	db, _, root, err := openIntercoreDBAndRoot()
	if err != nil {
		return err
	}
	defer db.Close()

	kp, err := authz.LoadPrivKey(root)
	if err != nil {
		return fmt.Errorf("load priv key: %w", err)
	}

	now := time.Now().Unix()
	spec := authz.DelegateSpec{
		ParentID:      parentID,
		CallerAgentID: agentID,
		ToAgentID:     toAgent,
		RequestedTTL:  ttl,
	}
	_, opaque, err := authz.DelegateToken(db, kp.Priv, spec, now)
	if err != nil {
		return reportTokenErr(err)
	}
	fmt.Println(opaque)
	return nil
}

// ─── revoke ───────────────────────────────────────────────────────────

// cmdPolicyTokenRevoke marks a token (and optionally its descendants) as
// revoked. --cascade is refused for non-root tokens (ErrCascadeOnNonRoot);
// see docs/canon/authz-token-model.md §Revoke for why mid-chain cascade is a
// v2.x concern.
//
//	clavain-cli policy token revoke --token=<id> [--cascade]
//	clavain-cli policy token revoke --issued-since=<duration>  # bulk
func cmdPolicyTokenRevoke(args []string) error {
	flags := parseAuthzArgs(args)
	tokenID := flags["token"]
	_, cascade := flags["cascade"]
	issuedSince := flags["issued-since"]
	if tokenID == "" && issuedSince == "" {
		return fmt.Errorf("usage: policy token revoke --token=<id> [--cascade] | --issued-since=<duration>")
	}

	db, _, _, err := openIntercoreDBAndRoot()
	if err != nil {
		return err
	}
	defer db.Close()

	now := time.Now().Unix()

	if issuedSince != "" {
		d, err := time.ParseDuration(issuedSince)
		if err != nil {
			return fmt.Errorf("--issued-since: %w", err)
		}
		cutoff := time.Now().Add(-d).Unix()
		toks, err := authz.ListTokens(db, authz.ListFilter{Status: "consumable", Now: now})
		if err != nil {
			return fmt.Errorf("list for bulk revoke: %w", err)
		}
		total := 0
		for _, t := range toks {
			if t.CreatedAt < cutoff {
				continue
			}
			n, err := authz.RevokeToken(db, t.ID, false, now)
			if err != nil {
				return reportTokenErr(err)
			}
			total += n
		}
		return outputJSON(map[string]int{"revoked": total})
	}

	n, err := authz.RevokeToken(db, tokenID, cascade, now)
	if err != nil {
		return reportTokenErr(err)
	}
	return outputJSON(map[string]interface{}{
		"token_id": tokenID,
		"cascade":  cascade,
		"revoked":  n,
	})
}

// ─── list ─────────────────────────────────────────────────────────────

// cmdPolicyTokenList dumps matching token rows as JSON.
//
//	clavain-cli policy token list [--root=<id>] [--agent=<id>] [--op=<o>]
//	                              [--status=consumable|consumed|revoked|expired]
func cmdPolicyTokenList(args []string) error {
	flags := parseAuthzArgs(args)
	filter := authz.ListFilter{
		RootToken: flags["root"],
		AgentID:   flags["agent"],
		OpType:    flags["op"],
		Status:    flags["status"],
	}
	if filter.Status == "consumable" || filter.Status == "expired" {
		filter.Now = time.Now().Unix()
	}

	db, _, _, err := openIntercoreDBAndRoot()
	if err != nil {
		return err
	}
	defer db.Close()

	tokens, err := authz.ListTokens(db, filter)
	if err != nil {
		return fmt.Errorf("list tokens: %w", err)
	}
	return outputJSON(tokensToJSONRows(tokens))
}

// ─── show ─────────────────────────────────────────────────────────────

// cmdPolicyTokenShow prints one token's full row, signature verification
// status, and the whole chain it belongs to (ordered by created_at).
//
//	clavain-cli policy token show --token=<id>
func cmdPolicyTokenShow(args []string) error {
	flags := parseAuthzArgs(args)
	tokenID := flags["token"]
	if tokenID == "" {
		return fmt.Errorf("usage: policy token show --token=<id>")
	}

	db, _, root, err := openIntercoreDBAndRoot()
	if err != nil {
		return err
	}
	defer db.Close()

	t, err := authz.GetToken(db, tokenID)
	if err != nil {
		return reportTokenErr(err)
	}

	verified := false
	if pub, pubErr := authz.LoadPubKey(root); pubErr == nil {
		verified = authz.VerifyToken(pub, t, t.Signature)
	}

	// The chain root is t itself for root tokens, else t.RootToken. This
	// surfaces the full subtree even when show is called on a leaf.
	chainRoot := t.ID
	if t.RootToken != "" {
		chainRoot = t.RootToken
	}
	chain, _ := authz.ListTokens(db, authz.ListFilter{RootToken: chainRoot})

	return outputJSON(map[string]interface{}{
		"token":        tokenToJSON(t),
		"sig_verified": verified,
		"chain":        tokensToJSONRows(chain),
	})
}

// ─── verify ───────────────────────────────────────────────────────────

// cmdPolicyTokenVerify checks an opaque token string's signature without
// consuming it. Exits 0 iff the signature verifies against the stored row
// under the project pub key; otherwise exits via reportTokenErr.
//
//	clavain-cli policy token verify --token=<opaque>
func cmdPolicyTokenVerify(args []string) error {
	flags := parseAuthzArgs(args)
	opaque := flags["token"]
	if opaque == "" {
		return fmt.Errorf("usage: policy token verify --token=<opaque-string>")
	}

	id, sig, err := authz.ParseTokenString(opaque)
	if err != nil {
		return reportTokenErr(err)
	}

	db, _, root, err := openIntercoreDBAndRoot()
	if err != nil {
		return err
	}
	defer db.Close()

	pub, err := authz.LoadPubKey(root)
	if err != nil {
		return fmt.Errorf("load pub key: %w", err)
	}

	t, err := authz.GetToken(db, id)
	if err != nil {
		return reportTokenErr(err)
	}

	if !authz.VerifyToken(pub, t, sig) {
		return reportTokenErr(authz.ErrSigVerify)
	}
	return outputJSON(map[string]interface{}{
		"id":           t.ID,
		"op_type":      t.OpType,
		"target":       t.Target,
		"agent_id":     t.AgentID,
		"sig_verified": true,
	})
}

// ─── JSON projection ──────────────────────────────────────────────────

// tokenJSON is the wire shape for token output. Signature bytes are elided
// from JSON output (the opaque token string carries the sig; stored sig is
// only relevant for server-side verify). Fields marked omitempty are the
// nullable ones, matching Token's zero-value-as-NULL convention.
type tokenJSON struct {
	ID          string `json:"id"`
	OpType      string `json:"op_type"`
	Target      string `json:"target"`
	AgentID     string `json:"agent_id"`
	BeadID      string `json:"bead_id,omitempty"`
	DelegateTo  string `json:"delegate_to,omitempty"`
	ExpiresAt   int64  `json:"expires_at"`
	ConsumedAt  int64  `json:"consumed_at,omitempty"`
	RevokedAt   int64  `json:"revoked_at,omitempty"`
	IssuedBy    string `json:"issued_by"`
	ParentToken string `json:"parent_token,omitempty"`
	RootToken   string `json:"root_token,omitempty"`
	Depth       int    `json:"depth"`
	SigVersion  int    `json:"sig_version"`
	CreatedAt   int64  `json:"created_at"`
}

func tokenToJSON(t authz.Token) tokenJSON {
	return tokenJSON{
		ID:          t.ID,
		OpType:      t.OpType,
		Target:      t.Target,
		AgentID:     t.AgentID,
		BeadID:      t.BeadID,
		DelegateTo:  t.DelegateTo,
		ExpiresAt:   t.ExpiresAt,
		ConsumedAt:  t.ConsumedAt,
		RevokedAt:   t.RevokedAt,
		IssuedBy:    t.IssuedBy,
		ParentToken: t.ParentToken,
		RootToken:   t.RootToken,
		Depth:       t.Depth,
		SigVersion:  t.SigVersion,
		CreatedAt:   t.CreatedAt,
	}
}

func tokensToJSONRows(tokens []authz.Token) []tokenJSON {
	out := make([]tokenJSON, 0, len(tokens))
	for _, t := range tokens {
		out = append(out, tokenToJSON(t))
	}
	return out
}
