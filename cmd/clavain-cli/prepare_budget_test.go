package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func requestBudgetMode(t *testing.T, s prepareRequest, mode string, tokens int) prepareRequest {
	t.Helper()
	raw, _ := json.Marshal(s)
	var wire map[string]json.RawMessage
	json.Unmarshal(raw, &wire)
	wire["budget_mode"] = json.RawMessage(mode)
	wire["budget_tokens"], _ = json.Marshal(tokens)
	raw, _ = json.Marshal(wire)
	if err := json.Unmarshal(raw, &s); err != nil {
		t.Fatal(err)
	}
	return s
}

func TestPrepareBudgetModes(t *testing.T) {
	_, original := ratifyFixture(t)
	for _, tc := range []struct {
		mode   string
		tokens int
		valid  bool
	}{
		{`"capped"`, 1, true}, {`"uncapped"`, 0, true},
		{`"capped"`, 0, false}, {`"capped"`, -1, false},
		{`"uncapped"`, 1, false}, {`"uncapped"`, -1, false},
		{`"unknown"`, 1, false}, {`""`, 1, false},
	} {
		s := requestBudgetMode(t, original, tc.mode, tc.tokens)
		if err := validatePrepare(s); (err == nil) != tc.valid {
			t.Errorf("mode=%s tokens=%d valid=%v: %v", tc.mode, tc.tokens, tc.valid, err)
		}
	}
	for _, tokens := range []int{0, -1, 1} {
		s := original
		s.BudgetTokens = tokens
		if err := validatePrepare(s); (err == nil) != (tokens > 0) {
			t.Errorf("legacy budget %d: %v", tokens, err)
		}
	}
}

func TestPrepareBudgetModeImmutableBinding(t *testing.T) {
	for _, mode := range []string{`"capped"`, `"uncapped"`} {
		t.Run(mode, func(t *testing.T) {
			base, s := ratifyFixture(t)
			source, _ := filepath.Abs("../..")
			t.Setenv("CLAVAIN_DIR", source)
			t.Setenv("CLAVAIN_ROUTING_POLICY", filepath.Join(source, "config", "routing.yaml"))
			if _, err := ratifyPrepare(base, s, reviewRun); err != nil {
				t.Fatal(err)
			}
			_, path, err := submitPrepare(base, s)
			if err != nil {
				t.Fatal(err)
			}
			before, _ := os.ReadFile(path)
			tokens := s.BudgetTokens
			if mode == `"uncapped"` {
				tokens = 0
			}
			changed := requestBudgetMode(t, s, mode, tokens)
			if _, err = ratifyPrepare(base, changed, reviewRun); err == nil {
				t.Error("ratification mode mismatch accepted")
			}
			if _, _, err = submitPrepare(base, changed); err == nil {
				t.Error("submission mode mismatch accepted")
			}
			if _, _, err = readPrepare(base, changed); err == nil {
				t.Error("status mode mismatch accepted")
			}
			after, _ := os.ReadFile(path)
			if string(before) != string(after) {
				t.Fatal("historical receipt changed")
			}
		})
	}
}

func TestPrepareLegacyRequestEncoding(t *testing.T) {
	// Frozen pre-budget-mode encoding, including field order, is the hash input.
	want := `{"version":0,"key":"","project":"","actor":"","transcriber":"","budget_tokens":0,"sources":null,"coverage_gaps":null,"proposal":`
	raw, _ := json.Marshal(prepareRequest{})
	proposal, _ := json.Marshal(reviewProposal{})
	if string(raw) != want+string(proposal)+`}` {
		t.Fatalf("legacy hash input changed: %s", raw)
	}
}

func TestPrepareBudgetUncappedBindingCannotRevert(t *testing.T) {
	for _, explicit := range []bool{false, true} {
		base, s := ratifyFixture(t)
		source, _ := filepath.Abs("../..")
		t.Setenv("CLAVAIN_DIR", source)
		t.Setenv("CLAVAIN_ROUTING_POLICY", filepath.Join(source, "config", "routing.yaml"))
		s = requestBudgetMode(t, s, `"uncapped"`, 0)
		if _, err := ratifyPrepare(base, s, reviewRun); err != nil {
			t.Fatal(err)
		}
		_, path, err := submitPrepare(base, s)
		if err != nil {
			t.Fatal(err)
		}
		before, _ := os.ReadFile(path)
		changed := s
		changed.BudgetMode = nil
		changed.BudgetTokens = 1000
		if explicit {
			changed = requestBudgetMode(t, changed, `"capped"`, 1000)
		}
		if _, err := ratifyPrepare(base, changed, reviewRun); err == nil {
			t.Error("uncapped ratification converted to capped")
		}
		if _, _, err := submitPrepare(base, changed); err == nil {
			t.Error("uncapped submission converted to capped")
		}
		if _, _, err := readPrepare(base, changed); err == nil {
			t.Error("uncapped status accepted capped request")
		}
		after, _ := os.ReadFile(path)
		if string(before) != string(after) {
			t.Fatal("uncapped receipt changed")
		}
	}
}
