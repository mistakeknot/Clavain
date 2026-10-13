package main

import (
	"errors"
	"fmt"
	"strconv"
	"strings"
)

// Generation-fenced leases (design choice, bead mk-u3bu2; modelled on the
// rat-king mailbox lease).
//
// Rules:
//   - acquire never steals a live lease (different holder, not yet expired);
//   - every successful acquire increments Gen, the fence token;
//   - expiry is clamped to maxLeaseTTLSeconds (5 minutes) from "now";
//   - renew and release require the current holder AND the current fence,
//     and renew additionally requires the lease to be unexpired, so a stale
//     holder can never act.
//
// The functions are pure (no I/O, explicit clock) so they can be tested
// against a model. Persistence is additive: bead claims keep their existing
// claimed_by/claimed_at labels and gain one new label, claim_gen:N. Claims
// written before this change have no claim_gen and are read as Gen 0.

const (
	// maxLeaseTTLSeconds is the hard ceiling on any lease granted or renewed.
	maxLeaseTTLSeconds = 300
	// leaseGenLabel is the additive bd label carrying the fence token.
	leaseGenLabel = "claim_gen"
)

var (
	ErrLeaseHeld      = errors.New("lease held by another live holder")
	ErrLeaseFence     = errors.New("fence token does not match current lease")
	ErrLeaseNotHolder = errors.New("caller is not the lease holder")
	ErrLeaseExpired   = errors.New("lease expired")
	ErrLeaseEmpty     = errors.New("no lease is held")
)

// Lease is the persisted ownership state. A zero Holder means unheld; Gen is
// retained across release so fence tokens never repeat.
type Lease struct {
	Holder    string
	Gen       int64
	ExpiresAt int64 // unix seconds; meaningful only when Holder != ""
}

// clampLeaseTTL bounds a requested TTL to (0, maxLeaseTTLSeconds].
// Non-positive requests get the maximum rather than an instantly-dead lease.
func clampLeaseTTL(ttl int64) int64 {
	if ttl <= 0 || ttl > maxLeaseTTLSeconds {
		return maxLeaseTTLSeconds
	}
	return ttl
}

// Live reports whether the lease is held and unexpired at now.
func (l Lease) Live(now int64) bool {
	return l.Holder != "" && now < l.ExpiresAt
}

// leaseAcquire grants the lease to holder. The same holder re-acquiring a live
// lease also gets a new generation (a re-acquire is a new epoch of ownership).
func leaseAcquire(l Lease, holder string, now, ttl int64) (Lease, error) {
	if holder == "" {
		return l, ErrLeaseNotHolder
	}
	if l.Live(now) && l.Holder != holder {
		return l, ErrLeaseHeld
	}
	return Lease{Holder: holder, Gen: l.Gen + 1, ExpiresAt: now + clampLeaseTTL(ttl)}, nil
}

func leaseCheckCurrent(l Lease, holder string, fence int64) error {
	if l.Holder == "" {
		return ErrLeaseEmpty
	}
	if l.Holder != holder {
		return ErrLeaseNotHolder
	}
	if l.Gen != fence {
		return ErrLeaseFence
	}
	return nil
}

// leaseRenew extends the current holder's unexpired lease. Gen is unchanged.
func leaseRenew(l Lease, holder string, fence, now, ttl int64) (Lease, error) {
	if err := leaseCheckCurrent(l, holder, fence); err != nil {
		return l, err
	}
	if !l.Live(now) {
		return l, ErrLeaseExpired
	}
	l.ExpiresAt = now + clampLeaseTTL(ttl)
	return l, nil
}

// leaseRelease frees the lease. The holder+fence must match; an expired lease
// may still be released by its (still current) holder, since nobody else has
// taken it. Gen is preserved so the next acquire gets Gen+1.
func leaseRelease(l Lease, holder string, fence int64) (Lease, error) {
	if err := leaseCheckCurrent(l, holder, fence); err != nil {
		return l, err
	}
	return Lease{Holder: "", Gen: l.Gen, ExpiresAt: 0}, nil
}

// parseLeaseGen validates a raw claim_gen label. Absent ("" or a bd "(no ...)"
// sentinel) is generation 0; a present value must be a non-negative integer.
// Malformed values are an error so they can never reset the fence to 1.
func parseLeaseGen(raw string) (int64, error) {
	raw = strings.TrimSpace(raw)
	if raw == "" || strings.HasPrefix(raw, "(no ") {
		return 0, nil
	}
	n, err := strconv.ParseInt(raw, 10, 64)
	if err != nil || n < 0 {
		return 0, fmt.Errorf("malformed claim generation %q", raw)
	}
	return n, nil
}

// leaseFromLegacy reads pre-existing claim labels into a Lease without
// migrating them. claimedBy/claimedAt/gen are the raw label values ("" or
// "(no ...)" when absent).
//
// Regression guard: a claimed_at of 0 (or unparseable/negative) is "unknown",
// NOT "epoch". Treating it as a real timestamp made age ~56 years, so every
// such claim looked stale and could be stolen. Unknown-age claims by a named
// holder are read as live for one max TTL from now, so they are never stolen
// on the strength of a missing timestamp.
func leaseFromLegacy(claimedBy, claimedAt, gen string, now int64) Lease {
	l := Lease{}
	if g, err := strconv.ParseInt(strings.TrimSpace(gen), 10, 64); err == nil && g > 0 {
		l.Gen = g
	}
	claimedBy = strings.TrimSpace(claimedBy)
	if claimedBy == "" || strings.HasPrefix(claimedBy, "(no ") || claimedBy == "released" {
		return l
	}
	l.Holder = claimedBy
	ts, err := strconv.ParseInt(strings.TrimSpace(claimedAt), 10, 64)
	if err != nil || ts <= 0 {
		l.ExpiresAt = now + maxLeaseTTLSeconds
		return l
	}
	// Claims written before fencing (no claim_gen) keep their historical
	// staleness window; fenced claims use the clamped 5-minute window.
	if l.Gen > 0 {
		l.ExpiresAt = ts + maxLeaseTTLSeconds
	} else {
		l.ExpiresAt = ts + beadClaimStaleSeconds
	}
	return l
}

// ageSecondsOrUnknown returns the age of an epoch timestamp, or -1 when the
// timestamp is unknown (<= 0). Callers must treat -1 as "not provably stale".
func ageSecondsOrUnknown(createdAt, now int64) int64 {
	if createdAt <= 0 {
		return -1
	}
	return now - createdAt
}
