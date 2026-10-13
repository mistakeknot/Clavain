// Package asks holds two pure pieces for inter-thread messaging, modeled on
// joelhooks/rat-king pi-ratking asks.ts and attend.ts:
//
//   - Journal: a pending ask lifecycle (pending -> nudged -> answered -> closed)
//     with injected load/save ports and clock. Asks return immediately; no
//     deadline unless DueBy is set.
//   - Attend: a pure decision function from an Arrival to a Verdict.
//
// Neither is wired into live hooks.
package asks

import (
	"encoding/json"
	"errors"
	"fmt"
	"sort"
	"sync"
	"time"
)

// State is an ask lifecycle state.
type State string

const (
	Pending  State = "pending"
	Nudged   State = "nudged"
	Answered State = "answered"
	Closed   State = "closed"
)

// Event drives a transition.
type Event string

const (
	EventDue   Event = "due"
	EventReply Event = "reply"
	EventAck   Event = "ack"
)

// ErrIllegalTransition is returned when an event is not valid in a state.
var ErrIllegalTransition = errors.New("asks: illegal transition")

// ErrUnknownAsk is returned when an id is not in the journal.
var ErrUnknownAsk = errors.New("asks: unknown ask")

var transitions = map[State]map[Event]State{
	Pending:  {EventDue: Nudged, EventReply: Answered, EventAck: Closed},
	Nudged:   {EventReply: Answered, EventAck: Closed},
	Answered: {EventAck: Closed},
	Closed:   {},
}

// Transition returns the state reached from s on e, or ErrIllegalTransition.
func Transition(s State, e Event) (State, error) {
	if t, ok := transitions[s][e]; ok {
		return t, nil
	}
	return s, fmt.Errorf("%w: %s on %s", ErrIllegalTransition, e, s)
}

// Ask is one journal entry. Times are unix milliseconds.
type Ask struct {
	ID      string `json:"id"`
	To      string `json:"to"`
	Did     string `json:"did"` // sender/counterparty identity a reply must carry
	Summary string `json:"summary"`
	SentAt  int64  `json:"sentAt"`
	DueBy   *int64 `json:"dueBy,omitempty"` // nil: no deadline
	State   State  `json:"state"`
}

// clone returns a copy of a that shares no memory with it (DueBy is a pointer),
// so callers and the journal can never mutate each other's deadlines.
func clone(a Ask) Ask {
	if a.DueBy != nil {
		d := *a.DueBy
		a.DueBy = &d
	}
	return a
}

func cloneAll(in []Ask) []Ask {
	out := make([]Ask, len(in))
	for i, a := range in {
		out[i] = clone(a)
	}
	return out
}

// checkIDs rejects empty and duplicate ids: an id must name exactly one ask,
// or Ack and Reply would strand the later entry.
func checkIDs(a []Ask) error {
	seen := make(map[string]struct{}, len(a))
	for _, x := range a {
		if x.ID == "" {
			return errors.New("asks: ask with empty id")
		}
		if _, dup := seen[x.ID]; dup {
			return fmt.Errorf("asks: duplicate ask id %q", x.ID)
		}
		seen[x.ID] = struct{}{}
	}
	return nil
}

// Ports abstract persistence and time.
type Ports struct {
	Load func() ([]Ask, error)
	Save func([]Ask) error
	Now  func() time.Time
}

// Journal is a concurrency-safe ask journal.
type Journal struct {
	mu      sync.Mutex
	ports   Ports
	entries []Ask
}

// Open loads the journal through ports.
func Open(p Ports) (*Journal, error) {
	if p.Load == nil || p.Save == nil || p.Now == nil {
		return nil, errors.New("asks: Ports.Load, Save and Now are required")
	}
	e, err := p.Load()
	if err != nil {
		return nil, err
	}
	if err := validate(e); err != nil {
		return nil, err
	}
	return &Journal{ports: p, entries: cloneAll(e)}, nil
}

func (j *Journal) persist(next []Ask) error {
	// Hand the port its own copy: an adapter that retains its argument must not
	// be able to mutate journal state, even after a failed save.
	if err := j.ports.Save(cloneAll(next)); err != nil {
		return err
	}
	j.entries = next
	return nil
}

func (j *Journal) index(id string) int {
	for i, a := range j.entries {
		if a.ID == id {
			return i
		}
	}
	return -1
}

func (j *Journal) advance(i int, e Event) (Ask, error) {
	a := j.entries[i]
	s, err := Transition(a.State, e)
	if err != nil {
		return a, err
	}
	a.State = s
	next := append([]Ask(nil), j.entries...)
	next[i] = a
	if err := j.persist(next); err != nil {
		return clone(a), err
	}
	return clone(a), nil
}

// Record adds a new pending ask and returns immediately. SentAt is stamped
// from the clock when zero; State is forced to pending. A duplicate id is
// rejected (an ask cannot be re-opened by re-recording).
func (j *Journal) Record(a Ask) (Ask, error) {
	j.mu.Lock()
	defer j.mu.Unlock()
	if a.ID == "" {
		return a, errors.New("asks: ask id required")
	}
	if j.index(a.ID) >= 0 {
		return a, fmt.Errorf("asks: duplicate ask id %q", a.ID)
	}
	if a.SentAt == 0 {
		a.SentAt = j.ports.Now().UnixMilli()
	}
	a = clone(a)
	a.State = Pending
	next := append(append([]Ask(nil), j.entries...), a)
	if err := j.persist(next); err != nil {
		return clone(a), err
	}
	return clone(a), nil
}

// Reply matches an inbound reply (replyTo id from sender did) to an open ask
// and marks it answered. ok is false when nothing matches (unknown id, wrong
// sender, or already closed). An already-answered ask is not re-answered.
func (j *Journal) Reply(replyTo, did string) (ask Ask, ok bool, err error) {
	j.mu.Lock()
	defer j.mu.Unlock()
	i := j.index(replyTo)
	if i < 0 || j.entries[i].Did != did {
		return Ask{}, false, nil
	}
	if s := j.entries[i].State; s == Closed || s == Answered {
		return Ask{}, false, nil
	}
	ask, err = j.advance(i, EventReply)
	return ask, err == nil, err
}

// Ack closes an ask. Unknown or already-closed ids are a no-op (nil).
func (j *Journal) Ack(id string) error {
	j.mu.Lock()
	defer j.mu.Unlock()
	i := j.index(id)
	if i < 0 || j.entries[i].State == Closed {
		return nil
	}
	_, err := j.advance(i, EventAck)
	return err
}

// Nudges moves every pending ask whose DueBy has passed to nudged and returns
// them. Asks without a deadline are never nudged.
func (j *Journal) Nudges() ([]Ask, error) {
	j.mu.Lock()
	defer j.mu.Unlock()
	now := j.ports.Now().UnixMilli()
	var out []Ask
	for i := range j.entries {
		a := j.entries[i]
		if a.State == Pending && a.DueBy != nil && *a.DueBy <= now {
			n, err := j.advance(i, EventDue)
			if err != nil {
				return out, err
			}
			out = append(out, n)
		}
	}
	return out, nil
}

// Open returns asks that are not closed, ordered by SentAt then ID.
func (j *Journal) Open() []Ask {
	j.mu.Lock()
	defer j.mu.Unlock()
	var out []Ask
	for _, a := range j.entries {
		if a.State != Closed {
			out = append(out, clone(a))
		}
	}
	sort.SliceStable(out, func(x, y int) bool {
		if out[x].SentAt != out[y].SentAt {
			return out[x].SentAt < out[y].SentAt
		}
		return out[x].ID < out[y].ID
	})
	return out
}

// Age renders whole minutes since the ask was sent, never negative.
func Age(a Ask, now time.Time) string {
	m := (now.UnixMilli() - a.SentAt) / 60000
	if m < 0 {
		m = 0
	}
	return fmt.Sprintf("%d min", m)
}

// Marshal / Unmarshal give the JSON journal format ([]Ask array).
func Marshal(a []Ask) ([]byte, error) {
	if a == nil {
		a = []Ask{}
	}
	return json.MarshalIndent(a, "", "  ")
}

func Unmarshal(b []byte) ([]Ask, error) {
	var a []Ask
	if err := json.Unmarshal(b, &a); err != nil {
		return nil, err
	}
	if err := validate(a); err != nil {
		return nil, err
	}
	return a, nil
}

// validate rejects persisted entries with an unknown state or a bad id.
func validate(a []Ask) error {
	for _, x := range a {
		if _, ok := transitions[x.State]; !ok {
			return fmt.Errorf("asks: invalid state %q for %q", x.State, x.ID)
		}
	}
	return checkIDs(a)
}
