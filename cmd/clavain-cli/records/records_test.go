package records

import (
	"math/rand"
	"os"
	"path/filepath"
	"strings"
	"sync"
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

func TestFrictionClosedSet(t *testing.T) {
	line := `{"version":"0.1","kind":"friction","session":"s","at":"2026-10-13T09:00:00Z","friction":"hunter2hunter2"}`
	if _, err := Decode([]byte(line)); err == nil {
		t.Fatal("arbitrary friction token accepted")
	}
}

func TestDecodeRejectsTrailingData(t *testing.T) {
	one := `{"version":"0.1","kind":"turn","session":"s","at":"2026-10-13T09:00:00Z","state":"idle"}`
	if _, err := Decode([]byte(one + "\n")); err != nil {
		t.Fatal(err)
	}
	for _, tail := range []string{one, `{"x":1}`, "garbage"} {
		if _, err := Decode([]byte(one + " " + tail)); err == nil {
			t.Errorf("trailing %q accepted", tail)
		}
	}
}

func TestConcurrentEmit(t *testing.T) {
	dir := t.TempDir()
	w := &Writer{Dir: dir, Config: true, Getenv: env(nil), Now: clock()}
	var wg sync.WaitGroup
	for i := 0; i < 50; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			w.Emit(Record{Kind: KindTurn, Session: "a", State: "idle"})
		}()
	}
	wg.Wait()
	b, _ := os.ReadFile(filepath.Join(dir, "records-2026-10-13.jsonl"))
	seen := map[string]bool{}
	for _, l := range strings.Split(strings.TrimSpace(string(b)), "\n") {
		r, err := Decode([]byte(l))
		if err != nil || seen[r.At] {
			t.Fatal(err, r.At)
		}
		seen[r.At] = true
	}
	if len(seen) != 50 {
		t.Fatal(len(seen))
	}
}

// Sub-millisecond clock steps must still persist distinct, increasing stamps.
func TestSubMillisecondTimestamps(t *testing.T) {
	dir := t.TempDir()
	cur := time.Date(2026, 10, 13, 9, 0, 0, 0, time.UTC)
	w := &Writer{Dir: dir, Config: true, Getenv: env(nil), Now: func() time.Time {
		cur = cur.Add(100 * time.Microsecond)
		return cur
	}}
	for i := 0; i < 20; i++ {
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

func TestTurnsDedupedPerSession(t *testing.T) {
	dir := t.TempDir()
	w := &Writer{Dir: dir, Config: true, Getenv: env(nil), Now: clock()}
	w.Emit(Record{Kind: KindTurn, Session: "a", TurnID: "t1", State: "done"})
	w.Emit(Record{Kind: KindTurn, Session: "b", TurnID: "t1", State: "done"})
	d, err := BuildDigest(dir, "2026-10-13")
	if err != nil || d.Turns != 2 {
		t.Fatal(err, d.Turns)
	}
}

func TestWriteDigestCreatesDir(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "new", "r")
	w := &Writer{Dir: dir, Config: true, Getenv: env(nil), Now: clock()}
	if on, err := w.WriteDigest("2026-10-13"); !on || err != nil {
		t.Fatal(on, err)
	}
}

var secretShaped = []string{
	"ghp_abcdefghijklmnop", "gho_abcdefghijklmnop", "sk-abcdefghijklmnop", "xoxb-12345-abcde",
	"AKIAABCDEFGHIJKLMNOP", "0123456789abcdef0123456789abcdef", "eyJhbGciOi.eyJzdWIiOiIx.c2lnbmF0dXJl",
}

func TestSecretShapedSessionAndTurnRejected(t *testing.T) {
	dir := t.TempDir()
	w := &Writer{Dir: dir, Config: true, Getenv: env(nil), Now: clock()}
	for _, v := range secretShaped {
		if ok, err := w.Emit(Record{Kind: KindTurn, Session: v, State: "idle"}); ok || err == nil {
			t.Errorf("session %q accepted", v)
		}
		if ok, err := w.Emit(Record{Kind: KindTurn, Session: "s", TurnID: v, State: "idle"}); ok || err == nil {
			t.Errorf("turn_id %q accepted", v)
		}
		line := `{"version":"0.1","kind":"turn","session":"` + v + `","at":"2026-10-13T09:00:00Z","state":"idle"}`
		if _, err := Decode([]byte(line)); err == nil {
			t.Errorf("decode accepted session %q", v)
		}
	}
	if b, _ := os.ReadFile(filepath.Join(dir, "records-2026-10-13.jsonl")); strings.Contains(string(b), "ghp_") {
		t.Error("secret persisted")
	}
}

func TestNormalIdentifiersAccepted(t *testing.T) {
	w := &Writer{Dir: t.TempDir(), Config: true, Getenv: env(nil), Now: clock()}
	for _, v := range []string{"123e4567-e89b-12d3-a456-426614174000", "01ARZ3NDEKTSV4RRFFQ69G5FAV", "t1", "sess_42"} {
		if ok, err := w.Emit(Record{Kind: KindTurn, Session: v, TurnID: v, State: "idle"}); !ok || err != nil {
			t.Errorf("%q rejected: %v", v, err)
		}
	}
}

func TestMidnightBoundaryPartitionsByObservedDay(t *testing.T) {
	dir := t.TempDir()
	base := time.Date(2026, 10, 13, 23, 59, 59, 999100000, time.UTC)
	w := &Writer{Dir: dir, Config: true, Getenv: env(nil), Now: func() time.Time { return base }}
	// Two events inside the same millisecond: the second is corrected past midnight.
	w.Emit(Record{Kind: KindTurn, Session: "s", TurnID: "t1", State: "done"})
	w.Now = func() time.Time { return base.Add(100 * time.Microsecond) }
	w.Emit(Record{Kind: KindTurn, Session: "s", TurnID: "t2", State: "done"})
	b, err := os.ReadFile(filepath.Join(dir, "records-2026-10-13.jsonl"))
	if err != nil {
		t.Fatal(err)
	}
	lines := strings.Split(strings.TrimSpace(string(b)), "\n")
	if len(lines) != 2 {
		t.Fatalf("want 2 records in observed day, got %d", len(lines))
	}
	r1, _ := Decode([]byte(lines[0]))
	r2, _ := Decode([]byte(lines[1]))
	if r2.At <= r1.At {
		t.Fatalf("timestamps not increasing: %s %s", r1.At, r2.At)
	}
	if _, err := os.Stat(filepath.Join(dir, "records-2026-10-14.jsonl")); err == nil {
		t.Fatal("record leaked into next day file")
	}
	d, _ := BuildDigest(dir, "2026-10-13")
	if d.Turns != 2 {
		t.Fatalf("digest turns = %d, want 2", d.Turns)
	}
}
