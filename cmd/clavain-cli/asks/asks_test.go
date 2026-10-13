package asks

import (
	"errors"
	"math/rand"
	"reflect"
	"testing"
	"time"
)

type fakeStore struct {
	data    []Ask
	saves   int
	failing bool
	now     time.Time
}

func (f *fakeStore) ports() Ports {
	return Ports{
		Load: func() ([]Ask, error) { return append([]Ask(nil), f.data...), nil },
		Save: func(a []Ask) error {
			if f.failing {
				return errors.New("disk full")
			}
			f.data = append([]Ask(nil), a...)
			f.saves++
			return nil
		},
		Now: func() time.Time { return f.now },
	}
}

func TestNoDeadlineNeverNudges(t *testing.T) {
	f := &fakeStore{now: time.UnixMilli(1000)}
	j, _ := Open(f.ports())
	if _, err := j.Record(Ask{ID: "a", To: "x", Did: "d"}); err != nil {
		t.Fatal(err)
	}
	f.now = f.now.Add(1000 * time.Hour)
	n, _ := j.Nudges()
	if len(n) != 0 || j.Open()[0].State != Pending {
		t.Fatal("ask without deadline must stay pending")
	}
}

func TestNudgeOnDueOnceThenReplyAck(t *testing.T) {
	f := &fakeStore{now: time.UnixMilli(1000)}
	j, _ := Open(f.ports())
	due := int64(2000)
	j.Record(Ask{ID: "a", Did: "d", DueBy: &due})
	if n, _ := j.Nudges(); len(n) != 0 {
		t.Fatal("not due yet")
	}
	f.now = time.UnixMilli(2000)
	n, _ := j.Nudges()
	if len(n) != 1 || n[0].State != Nudged {
		t.Fatalf("want nudged, got %v", n)
	}
	if n, _ := j.Nudges(); len(n) != 0 {
		t.Fatal("nudge must fire once")
	}
	if _, ok, _ := j.Reply("a", "other"); ok {
		t.Fatal("wrong sender must not match")
	}
	if a, ok, _ := j.Reply("a", "d"); !ok || a.State != Answered {
		t.Fatal("reply should answer")
	}
	if _, ok, _ := j.Reply("a", "d"); ok {
		t.Fatal("double reply must not match")
	}
	j.Ack("a")
	if len(j.Open()) != 0 {
		t.Fatal("closed ask must leave open set")
	}
	if err := j.Ack("a"); err != nil || j.Ack("nope") != nil {
		t.Fatal("ack idempotent")
	}
}

func TestSaveFailureLeavesStateUnchanged(t *testing.T) {
	f := &fakeStore{now: time.UnixMilli(1)}
	j, _ := Open(f.ports())
	j.Record(Ask{ID: "a", Did: "d"})
	f.failing = true
	if err := j.Ack("a"); err == nil {
		t.Fatal("want error")
	}
	if j.Open()[0].State != Pending {
		t.Fatal("state must not advance when save fails")
	}
	if _, err := j.Record(Ask{ID: "a"}); err == nil {
		t.Fatal("duplicate or failing record must error")
	}
}

func TestJSONRoundTripAndValidation(t *testing.T) {
	d := int64(5)
	in := []Ask{{ID: "a", To: "t", Did: "d", Summary: "s", SentAt: 1, DueBy: &d, State: Nudged}}
	b, _ := Marshal(in)
	out, err := Unmarshal(b)
	if err != nil || !reflect.DeepEqual(in, out) {
		t.Fatalf("roundtrip: %v %v", err, out)
	}
	if _, err := Unmarshal([]byte(`[{"id":"a","state":"bogus"}]`)); err == nil {
		t.Fatal("invalid state accepted")
	}
}

// Model-based: random event sequences against an independent oracle table.
func TestStateMachineModel(t *testing.T) {
	states := []State{Pending, Nudged, Answered, Closed}
	events := []Event{EventDue, EventReply, EventAck}
	legal := map[[2]string]State{
		{"pending", "due"}: Nudged, {"pending", "reply"}: Answered, {"pending", "ack"}: Closed,
		{"nudged", "reply"}: Answered, {"nudged", "ack"}: Closed,
		{"answered", "ack"}: Closed,
	}
	for _, s := range states {
		for _, e := range events {
			want, ok := legal[[2]string{string(s), string(e)}]
			got, err := Transition(s, e)
			if ok && (err != nil || got != want) {
				t.Fatalf("%s+%s: got %s,%v want %s", s, e, got, err, want)
			}
			if !ok && !errors.Is(err, ErrIllegalTransition) {
				t.Fatalf("%s+%s must be illegal", s, e)
			}
		}
	}
	rng := rand.New(rand.NewSource(7))
	for run := 0; run < 500; run++ {
		s := Pending
		for step := 0; step < 12; step++ {
			e := events[rng.Intn(len(events))]
			want, ok := legal[[2]string{string(s), string(e)}]
			got, err := Transition(s, e)
			if ok != (err == nil) {
				t.Fatalf("legality mismatch %s+%s", s, e)
			}
			if ok {
				s = want
				if got != want {
					t.Fatal("transition mismatch")
				}
			}
			if s == Closed && len(transitions[s]) != 0 {
				t.Fatal("closed must be terminal")
			}
		}
	}
}

// Journal-level model: drive a journal and a simple model with random ops.
func TestJournalAgainstModel(t *testing.T) {
	rng := rand.New(rand.NewSource(11))
	for run := 0; run < 200; run++ {
		f := &fakeStore{now: time.UnixMilli(0)}
		j, _ := Open(f.ports())
		model := map[string]State{}
		due := map[string]bool{}
		for step := 0; step < 30; step++ {
			id := string(rune('a' + rng.Intn(3)))
			switch rng.Intn(4) {
			case 0:
				d := f.now.UnixMilli() + int64(rng.Intn(3))
				_, err := j.Record(Ask{ID: id, Did: "d", DueBy: &d})
				if _, exists := model[id]; exists != (err != nil) {
					t.Fatal("duplicate handling mismatch")
				}
				if err == nil {
					model[id] = Pending
					due[id] = true
					_ = d
				}
			case 1:
				f.now = f.now.Add(time.Millisecond * time.Duration(rng.Intn(3)))
				j.Nudges()
				for _, a := range j.entries {
					model[a.ID] = a.State // nudge timing checked in dedicated test
				}
			case 2:
				_, ok, _ := j.Reply(id, "d")
				s, exists := model[id]
				wantOK := exists && (s == Pending || s == Nudged)
				if ok != wantOK {
					t.Fatalf("reply ok=%v want %v (state %s)", ok, wantOK, s)
				}
				if ok {
					model[id] = Answered
				}
			case 3:
				j.Ack(id)
				if _, exists := model[id]; exists {
					model[id] = Closed
				}
			}
			for _, a := range j.entries {
				if model[a.ID] != a.State {
					t.Fatalf("model %s != journal %s for %s", model[a.ID], a.State, a.ID)
				}
			}
		}
	}
}

func ptr(i int) *int { return &i }

// Property tests over the full arrival space.
func TestAttendProperties(t *testing.T) {
	kinds := []Kind{KindAsk, KindReply, KindInfo}
	for _, copy := range []bool{false, true} {
		for _, k := range kinds {
			for _, relay := range []string{"", "bob"} {
				for _, dg := range []*int{nil, ptr(0), ptr(30)} {
					a := Arrival{Copy: copy, Kind: k, Relay: relay, DigestMinutes: dg}
					v := Attend(a)
					if !reflect.DeepEqual(v, Attend(a)) {
						t.Fatal("not deterministic")
					}
					if v.Disposition == Never {
						t.Fatal("base intent never yields Never")
					}
					quiet := copy && k != KindAsk && relay == ""
					switch {
					case !quiet && v.Disposition != Now:
						t.Fatalf("%+v: non-quiet must be Now, got %s", a, v)
					case quiet && dg == nil && v.Disposition != Next:
						t.Fatalf("%+v: quiet no digest must be Next", a)
					case quiet && dg != nil:
						if v.Disposition != Later || v.Window != time.Duration(*dg)*time.Minute || !v.Reason.Has(FactDigest) {
							t.Fatalf("%+v: quiet+digest must be Later(window), got %s", a, v)
						}
					}
					if v.Disposition != Later && v.Window != 0 {
						t.Fatal("window only on Later")
					}
					if v.Reason.Has(FactCC) == v.Reason.Has(FactTo) {
						t.Fatal("exactly one of to/cc")
					}
					if v.Reason.Has(FactCC) != copy || v.Reason.Has(FactRelay) != (relay != "") {
						t.Fatal("facts must mirror arrival")
					}
					if (k == KindAsk) != v.Reason.Has(FactAsk) || (k == KindReply) != v.Reason.Has(FactReply) {
						t.Fatal("ask/reply facts")
					}
					if (Tone(v.Reason) == "held") != (v.Disposition == Later) {
						t.Fatal("held tone iff Later")
					}
					if Tone(v.Reason) == "quiet" && v.Disposition != Next {
						t.Fatal("quiet tone iff Next")
					}
				}
			}
		}
	}
}

func TestFormatReason(t *testing.T) {
	cases := map[string]Arrival{
		"woken: ask":      {Kind: KindAsk},
		"woken: reply":    {Kind: KindReply},
		"woken: to":       {Kind: KindInfo},
		"quiet: cc":       {Kind: KindInfo, Copy: true},
		"held: cc digest": {Kind: KindInfo, Copy: true, DigestMinutes: ptr(10)},
	}
	for want, a := range cases {
		if got := FormatReason(Attend(a).Reason); got != want {
			t.Errorf("%+v: got %q want %q", a, got, want)
		}
	}
	if Attend(Arrival{Kind: KindInfo, Copy: true, Relay: "x"}).Disposition != Now {
		t.Fatal("relayed copy wakes")
	}
}

func TestDeadlinePointersAreNotShared(t *testing.T) {
	f := &fakeStore{now: time.UnixMilli(1000)}
	j, _ := Open(f.ports())
	due := int64(5000)
	got, _ := j.Record(Ask{ID: "a", Did: "d", DueBy: &due})
	due = 0        // caller mutates its input
	*got.DueBy = 0 // and the returned snapshot
	*j.Open()[0].DueBy = 0
	f.now = time.UnixMilli(2000)
	if n, _ := j.Nudges(); len(n) != 0 {
		t.Fatalf("journal deadline changed through a caller pointer: %v", n)
	}
	f.now = time.UnixMilli(5000)
	if n, _ := j.Nudges(); len(n) != 1 {
		t.Fatal("ask must nudge at its original deadline")
	}
}

func TestDuplicateAndEmptyPersistedIDsRejected(t *testing.T) {
	dup := []Ask{{ID: "a", State: Pending}, {ID: "a", State: Pending}}
	f := &fakeStore{data: dup, now: time.UnixMilli(1)}
	if _, err := Open(f.ports()); err == nil {
		t.Fatal("Open must reject duplicate ids")
	}
	b, _ := Marshal(dup)
	if _, err := Unmarshal(b); err == nil {
		t.Fatal("Unmarshal must reject duplicate ids")
	}
	b, _ = Marshal([]Ask{{ID: "", State: Pending}})
	if _, err := Unmarshal(b); err == nil {
		t.Fatal("Unmarshal must reject an empty id")
	}
}
