// Package quarantine records metadata-only evidence that a hook or dispatch
// input could not be parsed or verified, then lets the caller skip the item
// and advance a cursor. Modeled on joelhooks/rat-king pi-ratking quarantine.ts.
//
// Safety by construction: the API never accepts a body. Callers hand over only
// the body length; Source and ID are restricted to short code tokens and Reason
// to a closed set of codes, so free text (and therefore payload content) cannot
// enter a record. Not wired
// into live hooks.
package quarantine

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"time"
)

var token = regexp.MustCompile(`^[a-z0-9][a-z0-9_.:-]{0,63}$`)

// ErrBadToken is returned when Source or ID is not a short code token, or
// Reason is not one of the known reason codes.
var ErrBadToken = errors.New("quarantine: field must match [a-z0-9][a-z0-9_.:-]{0,63}, and reason must be a known code")

// reasons is the closed set of Reason codes. Token syntax cannot tell metadata
// from a secret-shaped string, so only these values are ever persisted.
var reasons = map[string]bool{
	"unverifiable": true, "bad-json": true, "truncated": true, "sig-mismatch": true,
	"schema-mismatch": true, "oversize": true, "empty": true, "unauthorized": true,
}

// Record is the only thing ever written. There is deliberately no body field.
type Record struct {
	Seq    int64  `json:"seq"`
	ID     string `json:"id,omitempty"`
	Source string `json:"source"`
	Reason string `json:"reason"`
	Bytes  int    `json:"bytes"`
	At     string `json:"at"`
}

// Item describes a rejected input. BodyLen is the length only.
type Item struct {
	Seq     int64
	ID      string
	Source  string
	Reason  string
	BodyLen int
}

// Store keeps records as <dir>/<seq>.json and the cursor as <dir>/cursor.json.
type Store struct {
	Dir string
	Now func() time.Time
}

func (s *Store) now() time.Time {
	if s.Now != nil {
		return s.Now().UTC()
	}
	return time.Now().UTC()
}

func ok(v string) bool { return token.MatchString(v) }

func okReason(v string) bool { return reasons[v] }

// Quarantine writes a record for it and advances the cursor to it.Seq.
func (s *Store) Quarantine(it Item) (Record, error) {
	if !ok(it.Source) || !okReason(it.Reason) || (it.ID != "" && !ok(it.ID)) || it.Seq < 0 {
		return Record{}, ErrBadToken
	}
	r := Record{Seq: it.Seq, ID: it.ID, Source: it.Source, Reason: it.Reason,
		Bytes: it.BodyLen, At: s.now().Format(time.RFC3339Nano)}
	b, err := json.Marshal(r)
	if err != nil {
		return Record{}, err
	}
	if err := os.MkdirAll(s.Dir, 0o700); err != nil {
		return Record{}, err
	}
	if err := writeFile(filepath.Join(s.Dir, strconv.FormatInt(it.Seq, 10)+".json"), b); err != nil {
		return Record{}, err
	}
	if _, err := s.Advance(it.Seq); err != nil {
		return Record{}, err
	}
	return r, nil
}

func writeFile(path string, b []byte) error {
	f, err := os.CreateTemp(filepath.Dir(path), filepath.Base(path)+".*.tmp")
	if err != nil {
		return err
	}
	tmp := f.Name()
	_, err = f.Write(b)
	if cerr := f.Close(); err == nil {
		err = cerr
	}
	if err == nil {
		err = os.Rename(tmp, path)
	}
	if err != nil {
		os.Remove(tmp)
	}
	return err
}

// Cursor returns the highest sequence number processed (-1 when none).
func (s *Store) Cursor() int64 {
	b, err := os.ReadFile(filepath.Join(s.Dir, "cursor.json"))
	if err != nil {
		return -1
	}
	var c struct {
		Seq int64 `json:"seq"`
	}
	if json.Unmarshal(b, &c) != nil {
		return -1
	}
	return c.Seq
}

// Advance moves the cursor to seq, never backwards. It returns the new cursor.
func (s *Store) Advance(seq int64) (int64, error) {
	cur := s.Cursor()
	if seq <= cur {
		return cur, nil
	}
	if err := os.MkdirAll(s.Dir, 0o700); err != nil {
		return cur, err
	}
	lock, err := os.OpenFile(filepath.Join(s.Dir, "cursor.lock"), os.O_CREATE|os.O_RDWR, 0o600)
	if err != nil {
		return cur, err
	}
	defer lock.Close()
	// Read-modify-write under an exclusive file lock so concurrent writers
	// cannot lose progress.
	err = withFileLock(lock, func() error {
		cur = s.Cursor()
		if seq <= cur {
			return nil
		}
		b, _ := json.Marshal(struct {
			Seq int64 `json:"seq"`
		}{seq})
		if err := writeFile(filepath.Join(s.Dir, "cursor.json"), b); err != nil {
			return err
		}
		cur = seq
		return nil
	})
	return cur, err
}

// Failure lets a verifier name a safe reason code. Other errors map to
// "unverifiable" because arbitrary error text may echo the input.
type Failure struct{ Code string }

func (f *Failure) Error() string { return "quarantine failure: " + f.Code }

// Handle verifies one input. On success it advances the cursor and returns
// true. On failure it quarantines (metadata only), advances, and returns false:
// the caller skips the item either way.
func (s *Store) Handle(seq int64, id, source string, body []byte, verify func([]byte) error) (bool, error) {
	err := verify(body)
	if err == nil {
		_, aerr := s.Advance(seq)
		return true, aerr
	}
	code := "unverifiable"
	var f *Failure
	if errors.As(err, &f) && okReason(f.Code) {
		code = f.Code
	}
	_, qerr := s.Quarantine(Item{Seq: seq, ID: id, Source: source, Reason: code, BodyLen: len(body)})
	return false, qerr
}

// Summary is the status-line view.
type Summary struct {
	Count  int
	Latest *Record
}

var entry = regexp.MustCompile(`^(\d+)\.json$`)

// Summarize counts records and decodes the highest-seq one. Unreadable
// directories yield an empty summary; a corrupt latest record yields nil Latest.
func Summarize(dir string) Summary {
	es, err := os.ReadDir(dir)
	if err != nil {
		return Summary{}
	}
	var seqs []int64
	for _, e := range es {
		if m := entry.FindStringSubmatch(e.Name()); m != nil {
			n, _ := strconv.ParseInt(m[1], 10, 64)
			seqs = append(seqs, n)
		}
	}
	sum := Summary{Count: len(seqs)}
	if len(seqs) == 0 {
		return sum
	}
	sort.Slice(seqs, func(i, j int) bool { return seqs[i] > seqs[j] })
	b, err := os.ReadFile(filepath.Join(dir, strconv.FormatInt(seqs[0], 10)+".json"))
	if err != nil {
		return sum
	}
	var r Record
	if json.Unmarshal(b, &r) == nil && ok(r.Source) && okReason(r.Reason) {
		sum.Latest = &r
	}
	return sum
}

// Line renders a status-line fragment, empty when nothing is quarantined.
func (s Summary) Line() string {
	if s.Count == 0 {
		return ""
	}
	l := fmt.Sprintf("quarantined:%d", s.Count)
	if s.Latest != nil {
		l += " latest:" + strings.TrimSpace(s.Latest.Reason)
	}
	return l
}
