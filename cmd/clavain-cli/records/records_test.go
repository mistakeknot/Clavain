package records

import (
	"math/rand"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func env(m map[string]string) func(string) string { return func(k string) string { return m[k] } }

func clock() func() time.Time {
	t := time.Date(2026, 10, 13, 9, 0, 0, 0, time.UTC)
	return func() time.Time { return t }
}

func TestDefaultOff(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "r")
	w := &Writer{Dir: dir, Getenv: env(nil), Now: clock()}
	wrote, err := w.Emit(Record{Kind: KindTurn, Session: "s1", State: "working"})
	if wrote || err != nil {
		t.Fatal(wrote, err)
	}
	if on, _ := w.WriteDigest("2026-10-13"); on {
		t.Fatal("digest written while off")
	}
	if _, err := os.Stat(dir); err == nil {
		t.Fatal("directory created while off")
	}
}

func TestSwitches(t *testing.T) {
	cases := []struct {
		env  string
		cfg  bool
		want bool
	}{{"", false, false}, {"1", false, true}, {"", true, true}, {"0", true, false}, {"false", true, false}, {"junk", false, false}, {"junk", true, true}}
	for _, c := range cases {
		if got := Enabled(env(map[string]string{EnvVar: c.env}), c.cfg); got != c.want {
			t.Errorf("%+v got %v", c, got)
		}
	}
}

func TestSchemaRejectsContent(t *testing.T) {
	bad := []string{
		`{"version":"0.1","kind":"turn","session":"s","at":"2026-10-13T09:00:00Z","state":"working","prompt":"hi"}`,
		`{"version":"0.1","kind":"turn","session":"s","at":"2026-10-13T09:00:00Z","state":"thinking"}`,
		`{"version":"0.1","kind":"friction","session":"s","at":"2026-10-13T09:00:00Z","friction":"sk-ant secret value"}`,
		`{"version":"0.1","kind":"turn","session":"has space","at":"2026-10-13T09:00:00Z","state":"idle"}`,
		`{"version":"0.2","kind":"turn","session":"s","at":"2026-10-13T09:00:00Z","state":"idle"}`,
	}
	for _, b := range bad {
		if _, err := Decode([]byte(b)); err == nil {
			t.Errorf("accepted %s", b)
		}
	}
	if _, err := Decode([]byte(`{"version":"0.1","kind":"turn","session":"s","turn_id":"s:1","at":"2026-10-13T09:00:00Z","state":"done","stop_reason":"stop"}`)); err != nil {
		t.Fatal(err)
	}
}

// Property: fuzz bodies containing secrets into every string field the API
// accepts; whatever lands on disk (records and digest) never contains the body.
func TestNoBodyEverPersisted(t *testing.T) {
	rng := rand.New(rand.NewSource(3))
	secret := "sk-ant-api03-TOPSECRET value with spaces"
	for i := 0; i < 200; i++ {
		dir := t.TempDir()
		w := &Writer{Dir: dir, Config: true, Getenv: env(nil), Now: clock()}
		body := make([]byte, 10+rng.Intn(80))
		rng.Read(body)
		hostile := string(body) + secret
		for _, r := range []Record{
			{Kind: KindTurn, Session: hostile, State: "working"},
			{Kind: KindTurn, Session: "s", TurnID: hostile, State: "done"},
			{Kind: KindTurn, Session: "s", State: hostile},
			{Kind: KindTurn, Session: "s", State: "done", StopReason: hostile},
			{Kind: KindFriction, Session: "s", Friction: hostile},
			{Kind: hostile, Session: "s"},
			{Kind: KindFriction, Session: "s", Friction: "retry-loop"},
		} {
			w.Emit(r)
		}
		w.WriteDigest("2026-10-13")
		var all strings.Builder
		filepath.Walk(dir, func(p string, in os.FileInfo, err error) error {
			if err == nil && !in.IsDir() {
				b, _ := os.ReadFile(p)
				all.Write(b)
			}
			return nil
		})
		if strings.Contains(all.String(), "TOPSECRET") || strings.Contains(all.String(), string(body[:8])) {
			t.Fatalf("leak: %s", all.String())
		}
		if !strings.Contains(all.String(), "retry-loop") {
			t.Fatal("valid record missing")
		}
	}
}

func TestDigestCounts(t *testing.T) {
	dir := t.TempDir()
	w := &Writer{Dir: dir, Config: true, Getenv: env(nil), Now: clock()}
	w.Emit(Record{Kind: KindTurn, Session: "a", TurnID: "a:1", State: "working"})
	w.Emit(Record{Kind: KindTurn, Session: "a", TurnID: "a:1", State: "done", StopReason: "stop"})
	w.Emit(Record{Kind: KindTurn, Session: "b", TurnID: "b:1", State: "blocked"})
	w.Emit(Record{Kind: KindFriction, Session: "b", Friction: "approval-wait"})
	w.Emit(Record{Kind: KindFriction, Session: "b", Friction: "approval-wait"})
	d, err := BuildDigest(dir, "2026-10-13")
	if err != nil {
		t.Fatal(err)
	}
	if d.Sessions != 2 || d.Turns != 2 || d.States["done"] != 1 || d.Stops["stop"] != 1 || d.Friction["approval-wait"] != 2 {
		t.Fatalf("%+v", d)
	}
	if _, err := BuildDigest(dir, "../x"); err == nil {
		t.Fatal("bad day accepted")
	}
	if on, err := w.WriteDigest("2026-10-13"); !on || err != nil {
		t.Fatal(on, err)
	}
}

func TestTimestampsStrictlyIncrease(t *testing.T) {
	dir := t.TempDir()
	w := &Writer{Dir: dir, Config: true, Getenv: env(nil), Now: clock()}
	for i := 0; i < 5; i++ {
		w.Emit(Record{Kind: KindTurn, Session: "a", State: "idle"})
	}
	b, _ := os.ReadFile(filepath.Join(dir, "records-2026-10-13.jsonl"))
	prev := ""
	for _, l := range strings.Split(strings.TrimSpace(string(b)), "\n") {
		r, err := Decode([]byte(l))
		if err != nil || r.At <= prev {
			t.Fatal(err, r.At, prev)
		}
		prev = r.At
	}
}
