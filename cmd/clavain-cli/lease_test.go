package main

import (
	"errors"
	"math/rand"
	"testing"
)

func TestLeaseTable(t *testing.T) {
	live := Lease{Holder: "a", Gen: 3, ExpiresAt: 1100}
	expired := Lease{Holder: "a", Gen: 3, ExpiresAt: 1000}
	released := Lease{Gen: 3}
	const now = 1000
	tests := []struct {
		name    string
		do      func() (Lease, error)
		wantErr error
		want    Lease
	}{
		{"acquire free", func() (Lease, error) { return leaseAcquire(Lease{}, "a", now, 60) }, nil, Lease{"a", 1, 1060}},
		{"acquire after release bumps gen", func() (Lease, error) { return leaseAcquire(released, "b", now, 60) }, nil, Lease{"b", 4, 1060}},
		{"acquire never steals live", func() (Lease, error) { return leaseAcquire(live, "b", now, 60) }, ErrLeaseHeld, live},
		{"acquire takes expired, new gen", func() (Lease, error) { return leaseAcquire(expired, "b", now, 60) }, nil, Lease{"b", 4, 1060}},
		{"same holder reacquire bumps gen", func() (Lease, error) { return leaseAcquire(live, "a", now, 60) }, nil, Lease{"a", 4, 1060}},
		{"ttl clamped to 5m", func() (Lease, error) { return leaseAcquire(Lease{}, "a", now, 99999) }, nil, Lease{"a", 1, 1300}},
		{"ttl zero -> max", func() (Lease, error) { return leaseAcquire(Lease{}, "a", now, 0) }, nil, Lease{"a", 1, 1300}},
		{"empty holder rejected", func() (Lease, error) { return leaseAcquire(Lease{}, "", now, 60) }, ErrLeaseNotHolder, Lease{}},
		{"renew ok", func() (Lease, error) { return leaseRenew(live, "a", 3, now, 99999) }, nil, Lease{"a", 3, 1300}},
		{"renew wrong fence", func() (Lease, error) { return leaseRenew(live, "a", 2, now, 60) }, ErrLeaseFence, live},
		{"renew wrong holder", func() (Lease, error) { return leaseRenew(live, "b", 3, now, 60) }, ErrLeaseNotHolder, live},
		{"renew expired fails", func() (Lease, error) { return leaseRenew(expired, "a", 3, now, 60) }, ErrLeaseExpired, expired},
		{"renew unheld", func() (Lease, error) { return leaseRenew(released, "a", 3, now, 60) }, ErrLeaseEmpty, released},
		{"release ok keeps gen", func() (Lease, error) { return leaseRelease(live, "a", 3) }, nil, Lease{Gen: 3}},
		{"release wrong fence", func() (Lease, error) { return leaseRelease(live, "a", 9) }, ErrLeaseFence, live},
		{"release wrong holder", func() (Lease, error) { return leaseRelease(live, "b", 3) }, ErrLeaseNotHolder, live},
		{"stale holder cannot release after takeover", func() (Lease, error) {
			l, _ := leaseAcquire(expired, "b", now, 60)
			return leaseRelease(l, "a", 3)
		}, ErrLeaseNotHolder, Lease{"b", 4, 1060}},
		{"stale holder cannot renew after takeover with same name", func() (Lease, error) {
			l, _ := leaseAcquire(expired, "b", now, 60)
			l, _ = leaseRelease(l, "b", 4)
			l, _ = leaseAcquire(l, "a", now, 60)  // a returns with gen 5
			return leaseRenew(l, "a", 3, now, 60) // old fence
		}, ErrLeaseFence, Lease{"a", 5, 1060}},
	}
	for _, tc := range tests {
		got, err := tc.do()
		if !errors.Is(err, tc.wantErr) {
			t.Errorf("%s: err=%v want %v", tc.name, err, tc.wantErr)
			continue
		}
		if got != tc.want {
			t.Errorf("%s: got %+v want %+v", tc.name, got, tc.want)
		}
	}
}

func TestLeaseFromLegacy(t *testing.T) {
	const now = 100000
	tests := []struct {
		name        string
		by, at, gen string
		wantHolder  string
		wantGen     int64
		wantLive    bool
	}{
		{"no claim", "", "", "", "", 0, false},
		{"bd sentinel", "(no claimed_by state set)", "", "", "", 0, false},
		{"released", "released", "0", "4", "", 4, false},
		{"fresh legacy", "s1", "99900", "", "s1", 0, true},
		{"legacy within 10m", "s1", "99500", "", "s1", 0, true},
		{"legacy older than 10m", "s1", "99000", "", "s1", 0, false},
		{"fenced uses 5m window", "s1", "99500", "2", "s1", 2, false},
		{"fenced fresh", "s1", "99900", "2", "s1", 2, true},
		// Regression: epoch/zero created_at made every claim look ~56y stale.
		{"REGRESSION epoch claimed_at is unknown not stale", "s1", "0", "", "s1", 0, true},
		{"REGRESSION negative claimed_at", "s1", "-5", "", "s1", 0, true},
		{"REGRESSION garbage claimed_at", "s1", "abc", "", "s1", 0, true},
		{"REGRESSION empty claimed_at", "s1", "", "", "s1", 0, true},
	}
	for _, tc := range tests {
		l := leaseFromLegacy(tc.by, tc.at, tc.gen, now)
		if l.Holder != tc.wantHolder || l.Gen != tc.wantGen || l.Live(now) != tc.wantLive {
			t.Errorf("%s: got %+v live=%v", tc.name, l, l.Live(now))
		}
	}
	// Unknown-age claim must not be stealable.
	l := leaseFromLegacy("s1", "0", "", now)
	if _, err := leaseAcquire(l, "s2", now, 60); !errors.Is(err, ErrLeaseHeld) {
		t.Errorf("epoch claim was stolen: %v", err)
	}
}

func TestAgeSecondsOrUnknown(t *testing.T) {
	if got := ageSecondsOrUnknown(0, 1_800_000_000); got != -1 {
		t.Errorf("epoch created_at must be unknown, got age %d", got)
	}
	if got := ageSecondsOrUnknown(-1, 5); got != -1 {
		t.Errorf("negative must be unknown, got %d", got)
	}
	if got := ageSecondsOrUnknown(100, 160); got != 60 {
		t.Errorf("age=%d want 60", got)
	}
}

// TestLeaseModelSequence drives random interleavings of acquire/renew/release/
// clock-advance by several actors against a deliberately simple model and
// checks they agree on every outcome and on the invariants.
func TestLeaseModelSequence(t *testing.T) {
	actors := []string{"a", "b", "c"}
	for seed := int64(0); seed < 300; seed++ {
		rng := rand.New(rand.NewSource(seed))
		var l Lease
		// model
		var mHolder string
		var mGen, mExp, now int64 = 0, 0, 1000
		// each actor's last-known fence
		fences := map[string]int64{}
		for step := 0; step < 200; step++ {
			who := actors[rng.Intn(len(actors))]
			ttl := int64(rng.Intn(900)) - 50
			eff := ttl
			if eff <= 0 || eff > 300 {
				eff = 300
			}
			live := mHolder != "" && now < mExp
			// half the time use a stale/random fence
			fence := fences[who]
			if rng.Intn(4) == 0 {
				fence = int64(rng.Intn(int(mGen) + 3))
			}
			switch op := rng.Intn(5); op {
			case 0: // acquire
				nl, err := leaseAcquire(l, who, now, ttl)
				if live && mHolder != who {
					if !errors.Is(err, ErrLeaseHeld) || nl != l {
						t.Fatalf("seed %d step %d: stole live lease: %v", seed, step, err)
					}
					break
				}
				if err != nil {
					t.Fatalf("seed %d step %d: acquire failed: %v", seed, step, err)
				}
				mHolder, mGen, mExp = who, mGen+1, now+eff
				fences[who] = mGen
				l = nl
			case 1: // renew
				nl, err := leaseRenew(l, who, fence, now, ttl)
				ok := mHolder == who && fence == mGen && live
				if ok != (err == nil) {
					t.Fatalf("seed %d step %d: renew ok=%v err=%v model=%+v", seed, step, ok, err, [3]int64{mGen, mExp, now})
				}
				if ok {
					mExp = now + eff
					l = nl
				} else if nl != l {
					t.Fatalf("seed %d step %d: failed renew mutated lease", seed, step)
				}
			case 2: // release
				nl, err := leaseRelease(l, who, fence)
				ok := mHolder != "" && mHolder == who && fence == mGen
				if ok != (err == nil) {
					t.Fatalf("seed %d step %d: release ok=%v err=%v", seed, step, ok, err)
				}
				if ok {
					mHolder = ""
					l = nl
				} else if nl != l {
					t.Fatalf("seed %d step %d: failed release mutated lease", seed, step)
				}
			default: // advance clock
				now += int64(rng.Intn(200))
			}
			// invariants
			if l.Holder != mHolder || l.Gen != mGen {
				t.Fatalf("seed %d step %d: state %+v model holder=%q gen=%d", seed, step, l, mHolder, mGen)
			}
			if l.Holder != "" && l.ExpiresAt != mExp {
				t.Fatalf("seed %d step %d: exp %d model %d", seed, step, l.ExpiresAt, mExp)
			}
			if l.Holder != "" && l.ExpiresAt-now > maxLeaseTTLSeconds {
				t.Fatalf("seed %d step %d: expiry exceeds clamp", seed, step)
			}
		}
	}
}
