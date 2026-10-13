// Package records writes opt-in, metadata-only turn and friction records and a
// daily usage digest. Modeled on joelhooks/rat-king pi-ratking turn-record.ts.
//
// Off by default: nothing is written unless CLAVAIN_TURN_RECORDS is truthy or
// the config switch is set (an explicit falsey env value wins). Records have
// no content fields; every string is a short code token and decoding rejects
// unknown fields, so a record that carries content fails validation.
// Not wired into live hooks.
package records

import (
	"bufio"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"time"
)

// EnvVar is the opt-in environment switch.
const EnvVar = "CLAVAIN_TURN_RECORDS"

// Enabled reports whether records may be written. getenv is injected.
func Enabled(getenv func(string) string, cfg bool) bool {
	switch strings.ToLower(strings.TrimSpace(getenv(EnvVar))) {
	case "0", "false", "off", "no":
		return false
	case "1", "true", "on", "yes":
		return true
	}
	return cfg
}

var token = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$`)

// Turn states and stop reasons are closed sets.
var (
	states      = map[string]bool{"working": true, "idle": true, "blocked": true, "done": true}
	stopReasons = map[string]bool{"": true, "stop": true, "aborted": true, "error": true, "length": true}
)

// Kinds.
const (
	KindTurn     = "turn"
	KindFriction = "friction"
)

// Record is a turn or friction record. There are no content fields.
type Record struct {
	Version    string `json:"version"`
	Kind       string `json:"kind"`
	Session    string `json:"session"`
	TurnID     string `json:"turn_id,omitempty"`
	At         string `json:"at"`
	State      string `json:"state,omitempty"`       // turn only
	StopReason string `json:"stop_reason,omitempty"` // turn only
	Friction   string `json:"friction,omitempty"`    // friction only: code token
}

// Validate checks the schema.
func (r Record) Validate() error {
	if r.Version != "0.1" {
		return errors.New("records: bad version")
	}
	if !token.MatchString(r.Session) {
		return errors.New("records: bad session")
	}
	if _, err := time.Parse(time.RFC3339Nano, r.At); err != nil {
		return errors.New("records: bad at")
	}
	if r.TurnID != "" && !token.MatchString(r.TurnID) {
		return errors.New("records: bad turn_id")
	}
	switch r.Kind {
	case KindTurn:
		if !states[r.State] || !stopReasons[r.StopReason] || r.Friction != "" {
			return errors.New("records: bad turn fields")
		}
	case KindFriction:
		if !token.MatchString(r.Friction) || r.State != "" || r.StopReason != "" {
			return errors.New("records: bad friction fields")
		}
	default:
		return errors.New("records: bad kind")
	}
	return nil
}

// Decode parses one JSON record strictly (unknown fields rejected) and validates it.
func Decode(b []byte) (Record, error) {
	var r Record
	d := json.NewDecoder(strings.NewReader(string(b)))
	d.DisallowUnknownFields()
	if err := d.Decode(&r); err != nil {
		return Record{}, errors.New("records: undecodable")
	}
	return r, r.Validate()
}

// Writer appends validated records to <Dir>/records-YYYY-MM-DD.jsonl.
type Writer struct {
	Dir    string
	Config bool
	Getenv func(string) string
	Now    func() time.Time
	lastAt time.Time
}

func (w *Writer) now() time.Time {
	if w.Now != nil {
		return w.Now().UTC()
	}
	return time.Now().UTC()
}

func (w *Writer) getenv(k string) string {
	if w.Getenv != nil {
		return w.Getenv(k)
	}
	return os.Getenv(k)
}

// Emit writes r (At and Version are filled in). It is a no-op when disabled,
// and returns whether anything was written. Timestamps are strictly increasing.
func (w *Writer) Emit(r Record) (bool, error) {
	if !Enabled(w.getenv, w.Config) {
		return false, nil
	}
	r.Version = "0.1"
	t := w.now()
	if !t.After(w.lastAt) {
		t = w.lastAt.Add(time.Millisecond)
	}
	w.lastAt = t
	r.At = t.Format("2006-01-02T15:04:05.000Z07:00")
	if err := r.Validate(); err != nil {
		return false, err
	}
	b, _ := json.Marshal(r)
	if err := os.MkdirAll(w.Dir, 0o700); err != nil {
		return false, err
	}
	p := filepath.Join(w.Dir, "records-"+t.Format("2006-01-02")+".jsonl")
	f, err := os.OpenFile(p, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o600)
	if err != nil {
		return false, err
	}
	defer f.Close()
	_, err = f.Write(append(b, '\n'))
	return err == nil, err
}

// Digest is the metadata-only daily usage summary: counts only.
type Digest struct {
	Version  string         `json:"version"`
	Day      string         `json:"day"`
	Sessions int            `json:"sessions"`
	Turns    int            `json:"turns"`
	States   map[string]int `json:"states"`
	Stops    map[string]int `json:"stops"`
	Friction map[string]int `json:"friction"`
}

// BuildDigest reads the day's JSONL file in dir. Invalid lines are skipped and
// counted in no bucket. A missing file gives an empty digest.
func BuildDigest(dir, day string) (Digest, error) {
	d := Digest{Version: "0.1", Day: day, States: map[string]int{}, Stops: map[string]int{}, Friction: map[string]int{}}
	if _, err := time.Parse("2006-01-02", day); err != nil {
		return d, fmt.Errorf("records: bad day")
	}
	f, err := os.Open(filepath.Join(dir, "records-"+day+".jsonl"))
	if err != nil {
		if os.IsNotExist(err) {
			return d, nil
		}
		return d, err
	}
	defer f.Close()
	sessions := map[string]bool{}
	turns := map[string]bool{}
	sc := bufio.NewScanner(f)
	for sc.Scan() {
		r, err := Decode(sc.Bytes())
		if err != nil {
			continue
		}
		sessions[r.Session] = true
		if r.Kind == KindFriction {
			d.Friction[r.Friction]++
			continue
		}
		d.States[r.State]++
		if r.StopReason != "" {
			d.Stops[r.StopReason]++
		}
		if r.TurnID != "" {
			turns[r.TurnID] = true
		}
	}
	d.Sessions, d.Turns = len(sessions), len(turns)
	return d, sc.Err()
}

// Marshal renders the digest deterministically (maps sort by key).
func (d Digest) Marshal() []byte {
	b, _ := json.MarshalIndent(d, "", "  ")
	return append(b, '\n')
}

// WriteDigest builds and writes <dir>/digest-<day>.json when enabled.
func (w *Writer) WriteDigest(day string) (bool, error) {
	if !Enabled(w.getenv, w.Config) {
		return false, nil
	}
	d, err := BuildDigest(w.Dir, day)
	if err != nil {
		return false, err
	}
	return true, os.WriteFile(filepath.Join(w.Dir, "digest-"+day+".json"), d.Marshal(), 0o600)
}
