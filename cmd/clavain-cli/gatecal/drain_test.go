package gatecal

import (
	"context"
	"path/filepath"
	"sync"
	"testing"
	"time"
)

// helper: build a signal with sane defaults
func sig(eventID int64, ct, pf, pt, signal string, ageDays int) GateSignal {
	return GateSignal{
		EventID:   eventID,
		RunID:     "run1",
		CheckType: ct,
		FromPhase: pf,
		ToPhase:   pt,
		Signal:    signal,
		CreatedAt: time.Now().Unix() - int64(ageDays)*86400,
	}
}

func TestDrainEmptyIsNoOp(t *testing.T) {
	s, _ := Open(filepath.Join(t.TempDir(), "gate.db"))
	defer s.Close()
	now := time.Now().Unix()
	res, err := s.Drain(context.Background(), now, "auto", nil)
	if err != nil {
		t.Fatal(err)
	}
	if res.SignalsProcessed != 0 || res.StateChanges != 0 {
		t.Errorf("expected empty result, got %+v", res)
	}
	// drain_log should still record the attempt with drain_committed set
	var n int
	_ = s.DB().QueryRow(`SELECT COUNT(*) FROM drain_log WHERE drain_committed IS NOT NULL`).Scan(&n)
	if n != 1 {
		t.Errorf("expected 1 committed drain row, got %d", n)
	}
}

func TestDrainSmallNNoPromotion(t *testing.T) {
	s, _ := Open(filepath.Join(t.TempDir(), "gate.db"))
	defer s.Close()
	now := time.Now().Unix()
	// 5 fn signals on safety_secrets — weighted_n ~ 5, below threshold of 10.
	signals := []GateSignal{}
	for i := int64(1); i <= 5; i++ {
		signals = append(signals, sig(i, "safety_secrets", "design", "plan", "fn", 0))
	}
	_, err := s.Drain(context.Background(), now, "auto", signals)
	if err != nil {
		t.Fatal(err)
	}
	var tier string
	_ = s.DB().QueryRow(`SELECT tier FROM tier_state WHERE check_type='safety_secrets'`).Scan(&tier)
	if tier != "soft" {
		t.Errorf("expected soft (small-n guard), got %q", tier)
	}
}

func TestDrainZeroFNRSmallSampleNoPromotion(t *testing.T) {
	s, _ := Open(filepath.Join(t.TempDir(), "gate.db"))
	defer s.Close()
	now := time.Now().Unix()
	// 12 tn signals, 0 fn — weighted_n=12 (>=10) but fnr=0 with n<20 → no promote.
	signals := []GateSignal{}
	for i := int64(1); i <= 12; i++ {
		signals = append(signals, sig(i, "safety_secrets", "design", "plan", "tn", 0))
	}
	_, err := s.Drain(context.Background(), now, "auto", signals)
	if err != nil {
		t.Fatal(err)
	}
	var tier string
	_ = s.DB().QueryRow(`SELECT tier FROM tier_state WHERE check_type='safety_secrets'`).Scan(&tier)
	if tier != "soft" {
		t.Errorf("expected soft (zero-FNR small-sample guard), got %q", tier)
	}
}

func TestDrainConsecutiveStablePromotes(t *testing.T) {
	s, _ := Open(filepath.Join(t.TempDir(), "gate.db"))
	defer s.Close()
	now := time.Now().Unix()

	build := func(eventBase int64) []GateSignal {
		out := []GateSignal{}
		// 7 tn + 4 fn → fnr > 0.3 and weighted_n safely above 10 after decay.
		for i := int64(0); i < 7; i++ {
			out = append(out, sig(eventBase+i, "safety_secrets", "design", "plan", "tn", 0))
		}
		for i := int64(0); i < 4; i++ {
			out = append(out, sig(eventBase+7+i, "safety_secrets", "design", "plan", "fn", 0))
		}
		return out
	}

	// Drain 1: counter → 1, still soft
	_, _ = s.Drain(context.Background(), now, "auto", build(100))
	assertTier(t, s, "safety_secrets", "soft", 1)

	// Drain 2: counter → 2, still soft
	_, _ = s.Drain(context.Background(), now+1, "auto", build(200))
	assertTier(t, s, "safety_secrets", "soft", 2)

	// Drain 3: counter → 3, promote → hard, counter resets to 0, last_changed_at set
	_, _ = s.Drain(context.Background(), now+2, "auto", build(300))
	assertTier(t, s, "safety_secrets", "hard", 0)
}

func TestDrainConsecutiveCounterResetsOnDrop(t *testing.T) {
	s, _ := Open(filepath.Join(t.TempDir(), "gate.db"))
	defer s.Close()
	now := time.Now().Unix()

	above := func(base int64) []GateSignal {
		out := []GateSignal{}
		for i := int64(0); i < 7; i++ {
			out = append(out, sig(base+i, "safety_secrets", "design", "plan", "tn", 0))
		}
		for i := int64(0); i < 4; i++ {
			out = append(out, sig(base+7+i, "safety_secrets", "design", "plan", "fn", 0))
		}
		return out
	}
	below := func(base int64) []GateSignal {
		out := []GateSignal{}
		// Same volume but mostly tn -> fnr below threshold.
		for i := int64(0); i < 10; i++ {
			out = append(out, sig(base+i, "safety_secrets", "design", "plan", "tn", 0))
		}
		out = append(out, sig(base+10, "safety_secrets", "design", "plan", "fn", 0))
		return out
	}

	_, _ = s.Drain(context.Background(), now, "auto", above(100))
	assertTier(t, s, "safety_secrets", "soft", 1)
	_, _ = s.Drain(context.Background(), now+1, "auto", below(200))
	assertTier(t, s, "safety_secrets", "soft", 0) // reset
}

func TestDrainEmptyDoesNotResetCounter(t *testing.T) {
	s, _ := Open(filepath.Join(t.TempDir(), "gate.db"))
	defer s.Close()
	now := time.Now().Unix()

	above := func(base int64) []GateSignal {
		out := []GateSignal{}
		for i := int64(0); i < 7; i++ {
			out = append(out, sig(base+i, "safety_secrets", "design", "plan", "tn", 0))
		}
		for i := int64(0); i < 4; i++ {
			out = append(out, sig(base+7+i, "safety_secrets", "design", "plan", "fn", 0))
		}
		return out
	}

	_, _ = s.Drain(context.Background(), now, "auto", above(100))
	assertTier(t, s, "safety_secrets", "soft", 1)
	// Empty drain — counter should NOT reset.
	_, _ = s.Drain(context.Background(), now+1, "auto", nil)
	assertTier(t, s, "safety_secrets", "soft", 1)
}

func TestDrainConcurrentSafe(t *testing.T) {
	path := filepath.Join(t.TempDir(), "gate.db")
	s, _ := Open(path)
	defer s.Close()

	now := time.Now().Unix()
	mk := func(base int64, n int) []GateSignal {
		out := []GateSignal{}
		for i := int64(0); i < int64(n); i++ {
			out = append(out, sig(base+i, "safety_secrets", "design", "plan", "tn", 0))
		}
		return out
	}

	var wg sync.WaitGroup
	errs := make(chan error, 2)
	for i := 0; i < 2; i++ {
		wg.Add(1)
		go func(idx int) {
			defer wg.Done()
			s2, err := Open(path)
			if err != nil {
				errs <- err
				return
			}
			defer s2.Close()
			_, err = s2.Drain(context.Background(), now, "auto", mk(int64(idx*1000), 5))
			if err != nil {
				errs <- err
			}
		}(i)
	}
	wg.Wait()
	close(errs)
	for err := range errs {
		t.Errorf("concurrent drain error: %v", err)
	}
	// Both should have committed; tier_state should be coherent (not corrupted).
	var n int
	_ = s.DB().QueryRow(`SELECT COUNT(*) FROM drain_log WHERE drain_committed IS NOT NULL`).Scan(&n)
	if n != 2 {
		t.Errorf("expected 2 committed drains, got %d", n)
	}
}

// assertTier checks tier and consecutive counter for a given check_type.
func assertTier(t *testing.T, s *Store, ct, wantTier string, wantCounter int) {
	t.Helper()
	var tier string
	var counter int
	err := s.DB().QueryRow(
		`SELECT tier, consecutive_windows_above_threshold FROM tier_state WHERE check_type=? ORDER BY updated_at DESC LIMIT 1`, ct,
	).Scan(&tier, &counter)
	if err != nil {
		t.Fatalf("query tier_state: %v", err)
	}
	if tier != wantTier {
		t.Errorf("tier = %q, want %q", tier, wantTier)
	}
	if counter != wantCounter {
		t.Errorf("counter = %d, want %d", counter, wantCounter)
	}
}
