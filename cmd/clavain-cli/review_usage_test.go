package main

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func usageRecord(sequence int, terminal bool) map[string]any {
	return map[string]any{"type": "usage.cumulative", "schema_version": 1,
		"dispatch_id": "d", "invocation_id": "i", "session_id": "s",
		"requested_model": "claude-fable-5-1", "requested_identity": "claude-fable-5-1",
		"model_identity": "claude-fable-5-1", "sequence": sequence,
		"input_tokens": 10, "output_tokens": 9, "cache_read_input_tokens": 30,
		"cache_creation_input_tokens": 20, "budget_tokens": 69,
		"terminal": terminal, "complete": terminal, "status": "success"}
}

func TestReviewTerminalAccountingPendingAndRestart(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "receipt.json")
	os.WriteFile(filepath.Join(dir, "usage.jsonl"), []byte(usageLine(usageRecord(1, true))), 0600)
	r := reviewReceipt{Project: dir, DispatchID: "d", Request: reviewSubmission{Proposal: reviewProposal{BudgetTokens: 60}}}
	available := false
	var order []string
	run := func(_ string, _ string, args ...string) ([]byte, error) {
		if strings.Join(args, " ") == "--json dispatch poll d" {
			order = append(order, "collect")
			return []byte(`{"status":"failed","project_dir":` + fmtQuote(dir) + `}`), nil
		}
		if strings.Join(args, " ") == "dispatch tokens d --in=69 --out=0 --cache=0" {
			order = append(order, "report")
			if !available {
				return nil, errors.New("kernel unavailable")
			}
			return nil, nil
		}
		t.Fatalf("unexpected kernel call %v", args)
		return nil, nil
	}
	if finishReviewReceipt(&r, path, "failed", "backend exited 7", run) == nil || r.Status != "kernel_report_pending" {
		t.Fatalf("lost pending accounting: %+v", r)
	}
	data, _ := os.ReadFile(path)
	r = reviewReceipt{}
	json.Unmarshal(data, &r)
	available = true
	if err := finishReviewReceipt(&r, path, r.PendingStatus, r.PendingReason, run); err != nil {
		t.Fatal(err)
	}
	if r.Status != "failed" || r.UsageTokens != 69 || r.BudgetOvershoot != 9 || !r.UsageComplete || r.PendingStatus != "" {
		t.Fatalf("lost failed-spend evidence: %+v", r)
	}
	if strings.Join(order, ",") != "collect,report,collect,report" {
		t.Fatalf("wrong collection/report order %v", order)
	}
}

func fmtQuote(text string) string { b, _ := json.Marshal(text); return string(b) }

func usageLine(record map[string]any) string {
	b, _ := json.Marshal(record)
	return string(b) + "\n"
}

func TestReviewUsageCumulativeReplayAndRetries(t *testing.T) {
	path := filepath.Join(t.TempDir(), "usage.jsonl")
	first, final := usageRecord(1, false), usageRecord(2, true)
	retry := usageRecord(1, true)
	retry["invocation_id"], retry["session_id"] = "retry", "retry-session"
	data := "WARNING provider noise\n{\"type\":\"thread.started\"}\n" +
		usageLine(first) + usageLine(first) + usageLine(final) + usageLine(final) + usageLine(retry) +
		"{\"type\":\"turn.completed\",\"usage\":{\"input_tokens\":10,\"cached_input_tokens\":8,\"output_tokens\":3}}\n"
	os.WriteFile(path, []byte(data), 0600)
	if got, err := reviewUsage(path); err != nil || got != 151 {
		t.Fatalf("usage %d: %v", got, err)
	}
}

func TestReviewUsageInvalidEvidencePreservesLowerBound(t *testing.T) {
	for _, kind := range []string{"malformed", "truncated", "incomplete", "schema", "regression", "identity", "conflict", "missing", "negative", "sum", "after-terminal"} {
		t.Run(kind, func(t *testing.T) {
			path := filepath.Join(t.TempDir(), "usage.jsonl")
			base, next := usageRecord(1, false), usageRecord(2, true)
			data := usageLine(base)
			switch kind {
			case "malformed":
				data += "{garbage}\n"
			case "truncated":
				data += strings.TrimSuffix(usageLine(next), "\n")
			case "incomplete":
			case "schema":
				next["schema_version"] = 22
				data += usageLine(next)
			case "regression":
				next["input_tokens"], next["budget_tokens"] = 0, 59
				data += usageLine(next)
			case "identity":
				next["session_id"] = "someone-else"
				data += usageLine(next)
			case "conflict":
				next["sequence"] = 1
				data += usageLine(next)
			case "missing":
				delete(next, "output_tokens")
				data += usageLine(next)
			case "negative":
				next["input_tokens"] = -1
				data += usageLine(next)
			case "sum":
				next["budget_tokens"] = 9
				data += usageLine(next)
			case "after-terminal":
				data += usageLine(next) + usageLine(usageRecord(3, true))
			}
			os.WriteFile(path, []byte(data), 0600)
			if got, err := reviewUsage(path); err == nil || got != 69 {
				t.Fatalf("usage %d: %v", got, err)
			}
		})
	}
}

func TestReviewUsageCodexRejectsMalformedAndMissingTokens(t *testing.T) {
	for _, data := range []string{"WARNING only\n", "{\"type\":\"turn.completed\",\"usage\":{}}\n", "{\"type\":\"turn.completed\",\"usage\":{\"input_tokens\":-1,\"output_tokens\":3}}\n"} {
		path := filepath.Join(t.TempDir(), "usage.jsonl")
		os.WriteFile(path, []byte(data), 0600)
		if _, err := reviewUsage(path); err == nil {
			t.Fatalf("accepted %s", data)
		}
	}
}
