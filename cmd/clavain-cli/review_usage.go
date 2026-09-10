package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"
)

// Categories in normalized Claude records exclude each other. Codex's input
// already includes cached input and must not have its cache count added again.
var usageFields = []string{"input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"}

type usageEvidence struct {
	Tokens     int
	Complete   bool
	Terminal   bool
	Normalized bool
}
type usageInvocation struct {
	sequence                                         int
	counts                                           [4]int
	tokens                                           int
	terminal, complete                               bool
	dispatch, session, requested, identity, observed string
	seen                                             map[int]string
}

func usageInteger(row map[string]json.RawMessage, key string) (int, error) {
	raw, ok := row[key]
	var number int
	if !ok || string(raw) == "null" || json.Unmarshal(raw, &number) != nil || number < 0 || number > 1<<53 {
		return 0, fmt.Errorf("invalid or missing usage field %s", key)
	}
	return number, nil
}

func readReviewUsage(path, expectedDispatch string, final bool) (usageEvidence, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return usageEvidence{}, err
	}
	result := usageEvidence{}
	invocations := map[string]*usageInvocation{}
	var problems []error
	codexTurns := 0
	lines := bytes.Split(data, []byte{'\n'})
	if len(data) > 0 && data[len(data)-1] != '\n' {
		// A live writer may not have flushed the last record yet. Never parse it as
		// complete merely because its closing brace happened to arrive first.
		problems = append(problems, errors.New("unterminated usage ledger"))
		lines = lines[:len(lines)-1]
	}
	for i, line := range lines {
		line = bytes.TrimSpace(line)
		if len(line) == 0 || line[0] != '{' {
			continue
		} // documented Codex CLI noise
		var row map[string]json.RawMessage
		if len(line) > 8<<20 || json.Unmarshal(line, &row) != nil {
			problems = append(problems, fmt.Errorf("malformed usage ledger line %d", i+1))
			continue
		}
		var kind string
		_ = json.Unmarshal(row["type"], &kind)
		if kind == "turn.completed" {
			var usage map[string]json.RawMessage
			if json.Unmarshal(row["usage"], &usage) != nil {
				problems = append(problems, errors.New("invalid Codex usage"))
				continue
			}
			input, e1 := usageInteger(usage, "input_tokens")
			output, e2 := usageInteger(usage, "output_tokens")
			if e1 != nil || e2 != nil {
				problems = append(problems, errors.Join(e1, e2))
				continue
			}
			result.Tokens += input + output
			codexTurns++
			continue
		}
		if !strings.HasPrefix(kind, "usage.") {
			continue
		}
		result.Normalized = true
		parse := func() error {
			version, e := usageInteger(row, "schema_version")
			if e != nil || version != 1 || kind != "usage.cumulative" {
				return errors.New("unsupported usage schema")
			}
			var fields struct {
				Dispatch   string `json:"dispatch_id"`
				Invocation string `json:"invocation_id"`
				Session    string `json:"session_id"`
				Requested  string `json:"requested_model"`
				Identity   string `json:"requested_identity"`
				Observed   string `json:"model_identity"`
				Terminal   *bool  `json:"terminal"`
				Complete   *bool  `json:"complete"`
			}
			if json.Unmarshal(line, &fields) != nil || fields.Dispatch == "" || fields.Invocation == "" || fields.Session == "" || fields.Requested == "" || fields.Identity == "" || fields.Terminal == nil || fields.Complete == nil {
				return errors.New("usage record lacks invocation identity/state")
			}
			if expectedDispatch != "" && fields.Dispatch != expectedDispatch {
				return errors.New("usage dispatch binding mismatch")
			}
			seq, e := usageInteger(row, "sequence")
			if e != nil || seq < 1 {
				return errors.New("invalid usage sequence")
			}
			var counts [4]int
			sum := 0
			for j, key := range usageFields {
				n, e := usageInteger(row, key)
				if e != nil {
					return e
				}
				counts[j] = n
				sum += n
			}
			budget, e := usageInteger(row, "budget_tokens")
			if e != nil || budget != sum {
				return errors.New("usage budget total inconsistent with categories")
			}
			for key := range row {
				if strings.HasSuffix(key, "_tokens") && key != "budget_tokens" {
					known := false
					for _, f := range usageFields {
						if key == f {
							known = true
						}
					}
					if !known {
						return fmt.Errorf("unknown usage token field %s", key)
					}
				}
			}
			// Canonical JSON makes an identical replay independent of key order.
			var canonical any
			_ = json.Unmarshal(line, &canonical)
			encoded, _ := json.Marshal(canonical)
			key := fields.Dispatch + ":" + fields.Invocation
			old := invocations[key]
			if old != nil {
				if prior, ok := old.seen[seq]; ok {
					if prior == string(encoded) {
						return nil
					}
					return errors.New("conflicting usage sequence replay")
				}
				if old.terminal || seq != old.sequence+1 {
					return errors.New("usage sequence gap or write after terminal")
				}
				if old.session != fields.Session || old.requested != fields.Requested || old.identity != fields.Identity || (old.observed != "" && fields.Observed != old.observed) {
					return errors.New("usage invocation identity changed")
				}
				for j, n := range counts {
					if n < old.counts[j] {
						return errors.New("cumulative usage regressed")
					}
				}
			} else {
				if seq != 1 {
					return errors.New("usage invocation lacks initial sequence")
				}
				old = &usageInvocation{seen: map[int]string{}}
				invocations[key] = old
			}
			if *fields.Complete && (!*fields.Terminal || fields.Observed == "" || fields.Observed != fields.Identity) {
				return errors.New("complete usage lacks matching observed model identity")
			}
			old.sequence, old.counts, old.tokens = seq, counts, budget
			old.dispatch, old.session, old.requested, old.identity, old.observed = fields.Dispatch, fields.Session, fields.Requested, fields.Identity, fields.Observed
			old.terminal, old.complete = *fields.Terminal, *fields.Complete
			old.seen[seq] = string(encoded)
			return nil
		}
		if e := parse(); e != nil {
			problems = append(problems, fmt.Errorf("usage line %d: %w", i+1, e))
		}
	}
	result.Complete = len(invocations) > 0 || codexTurns > 0
	result.Terminal = result.Complete
	for _, v := range invocations {
		result.Tokens += v.tokens
		result.Terminal = result.Terminal && v.terminal
		result.Complete = result.Complete && v.complete && v.terminal
	}
	if final && !result.Complete {
		problems = append(problems, errors.New("usage accounting incomplete"))
	}
	if len(problems) > 0 {
		result.Complete = false
	}
	return result, errors.Join(problems...)
}

// Keep the historical caller interface, now requiring final evidence.
func reviewUsage(path string) (int, error) {
	evidence, err := readReviewUsage(path, "", true)
	return evidence.Tokens, err
}

// Kernel status can become terminal before the adapter finishes its drain.
// A missing terminal receipt remains explicit after this bounded wait.
func finalReviewUsage(path, dispatch string) (usageEvidence, error) {
	deadline := time.Now().Add(8 * time.Second)
	for {
		evidence, err := readReviewUsage(path, dispatch, true)
		if evidence.Terminal || time.Now().After(deadline) {
			return evidence, err
		}
		time.Sleep(100 * time.Millisecond)
	}
}

// Collection can replace the kernel's mid-run counts from a summary sidecar.
// Always collect terminal state first and then overwrite it with validated
// cumulative accounting, including partial spend on failed/cancelled calls.
func settleReviewUsage(r *reviewReceipt, dir string, run reviewRunner) error {
	data, err := run(r.Project, "ic", "--json", "dispatch", "poll", r.DispatchID)
	if err != nil {
		return err
	}
	var dispatch struct {
		Status  string `json:"status"`
		Project string `json:"project_dir"`
	}
	if json.Unmarshal(data, &dispatch) != nil || dispatch.Project != r.Project {
		return errors.New("kernel accounting project binding unavailable")
	}
	if dispatch.Status == "running" || dispatch.Status == "spawned" || dispatch.Status == "" {
		return errors.New("kernel accounting awaits terminal dispatch")
	}
	evidence, evidenceErr := finalReviewUsage(filepath.Join(dir, "usage.jsonl"), r.DispatchID)
	r.UsageTokens = evidence.Tokens
	r.BudgetOvershoot = max(0, evidence.Tokens-r.Request.Proposal.BudgetTokens)
	r.UsageComplete = evidenceErr == nil && evidence.Complete
	_, err = run(r.Project, "ic", "dispatch", "tokens", r.DispatchID, "--in="+fmt.Sprint(evidence.Tokens), "--out=0", "--cache=0")
	return err
}

func finishReviewReceipt(r *reviewReceipt, path, status, reason string, run reviewRunner) error {
	if r.DispatchID != "" {
		if err := settleReviewUsage(r, filepath.Dir(path), run); err != nil {
			r.Status = "kernel_report_pending"
			r.PendingStatus, r.PendingReason = status, reason
			r.Reason = "Final token report awaits kernel reconciliation: " + err.Error()
			r.UpdatedAt = time.Now().UTC()
			if writeErr := reviewWrite(path, r); writeErr != nil {
				return writeErr
			}
			return err
		}
		if status == "ready_for_retest" && !r.UsageComplete {
			status, reason = "blocked", "Final usage evidence incomplete; no success or further dispatch is authorized"
		}
	}
	r.Status, r.Reason = status, reason
	r.PendingStatus, r.PendingReason = "", ""
	r.UpdatedAt = time.Now().UTC()
	return reviewWrite(path, r)
}
