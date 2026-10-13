package asks

import (
	"fmt"
	"time"
)

// Kind of an inbound message.
type Kind string

const (
	KindAsk   Kind = "ask"
	KindReply Kind = "reply"
	KindInfo  Kind = "info"
)

// Arrival is one inbound message as seen by the attention decision.
type Arrival struct {
	Copy          bool // addressed as cc rather than to
	Kind          Kind
	Relay         string // non-empty when the message is relayed
	DigestMinutes *int   // nil: no digest window configured
}

// Fact explains a verdict.
type Fact string

const (
	FactTo     Fact = "to"
	FactCC     Fact = "cc"
	FactAsk    Fact = "ask"
	FactReply  Fact = "reply"
	FactRelay  Fact = "relay"
	FactDigest Fact = "digest"
)

// Reason carries the facts behind a verdict.
type Reason struct{ Facts []Fact }

func (r Reason) Has(f Fact) bool {
	for _, x := range r.Facts {
		if x == f {
			return true
		}
	}
	return false
}

// Disposition is the verdict class.
type Disposition string

const (
	Now   Disposition = "Now"
	Next  Disposition = "Next"
	Later Disposition = "Later"
	Never Disposition = "Never"
)

// Verdict is the attention decision. Window is set only for Later.
type Verdict struct {
	Disposition Disposition
	Reason      Reason
	Window      time.Duration
}

// Attend decides how to treat an arrival. Pure. Copies that are neither asks
// nor relayed are quiet: Next, or Later(window) when a digest is configured.
// Everything else wakes now. (Never is reserved for callers' suppression
// rules; the base intent never yields it.)
func Attend(a Arrival) Verdict {
	facts := []Fact{FactTo}
	if a.Copy {
		facts[0] = FactCC
	}
	if a.Kind == KindAsk || a.Kind == KindReply {
		facts = append(facts, Fact(a.Kind))
	}
	if a.Relay != "" {
		facts = append(facts, FactRelay)
	}
	quiet := a.Copy && a.Kind != KindAsk && a.Relay == ""
	if quiet && a.DigestMinutes != nil {
		facts = append(facts, FactDigest)
		return Verdict{Disposition: Later, Reason: Reason{facts}, Window: time.Duration(*a.DigestMinutes) * time.Minute}
	}
	if quiet {
		return Verdict{Disposition: Next, Reason: Reason{facts}}
	}
	return Verdict{Disposition: Now, Reason: Reason{facts}}
}

// Tone classifies a reason as held, quiet or woken.
func Tone(r Reason) string {
	if r.Has(FactDigest) {
		return "held"
	}
	if r.Has(FactCC) && !r.Has(FactAsk) && !r.Has(FactRelay) {
		return "quiet"
	}
	return "woken"
}

// FormatReason renders a short human label.
func FormatReason(r Reason) string {
	switch Tone(r) {
	case "held":
		return "held: cc digest"
	case "quiet":
		return "quiet: cc"
	}
	if r.Has(FactAsk) {
		return "woken: ask"
	}
	if r.Has(FactReply) {
		return "woken: reply"
	}
	return "woken: to"
}

func (v Verdict) String() string {
	if v.Disposition == Later {
		return fmt.Sprintf("Later(%s) %s", v.Window, FormatReason(v.Reason))
	}
	return fmt.Sprintf("%s %s", v.Disposition, FormatReason(v.Reason))
}
