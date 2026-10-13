package quarantine

import (
	"errors"
	"math/rand"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func fixed() time.Time { return time.Date(2026, 10, 13, 1, 2, 3, 0, time.UTC) }

func allFiles(t *testing.T, dir string) string {
	var sb strings.Builder
	filepath.Walk(dir, func(p string, i os.FileInfo, err error) error {
		if err == nil && !i.IsDir() {
			b, _ := os.ReadFile(p)
			sb.Write(b)
		}
		return nil
	})
	return sb.String()
}

// Property: no matter the body (including secrets) or the error text, nothing
// on disk contains the body.
func TestNoBodyEverPersisted(t *testing.T) {
	rng := rand.New(rand.NewSource(1))
	secrets := []string{"sk-ant-api03-SECRETSECRET", "ghp_abcdefghijklmnop", "hunter2hunter2", "-----BEGIN " + "PRIVATE KEY-----"}
	for i := 0; i < 300; i++ {
		dir := t.TempDir()
		s := &Store{Dir: dir, Now: fixed}
		body := make([]byte, 20+rng.Intn(200))
		rng.Read(body)
		sec := secrets[rng.Intn(len(secrets))]
		body = append(body, []byte(sec)...)
		verify := func(b []byte) error {
			switch rng.Intn(3) {
			case 0:
				return errors.New("parse error near " + string(b))
			case 1:
				return &Failure{Code: "bad-json"}
			}
			return &Failure{Code: string(b)} // hostile code: must be rejected
		}
		okv, err := s.Handle(int64(i), "", "hook", body, verify)
		if okv {
			t.Fatal("verify should fail")
		}
		if err != nil {
			t.Fatal(err)
		}
		all := allFiles(t, dir)
		if strings.Contains(all, sec) || strings.Contains(all, string(body[:16])) {
			t.Fatalf("body leaked: %s", all)
		}
	}
}

func TestFreeTextFieldsRejected(t *testing.T) {
	s := &Store{Dir: t.TempDir(), Now: fixed}
	for _, bad := range []string{"", "Has Space", "sk-ant-API", strings.Repeat("a", 65), "a\nb"} {
		if _, err := s.Quarantine(Item{Seq: 1, Source: "hook", Reason: bad}); !errors.Is(err, ErrBadToken) {
			t.Errorf("reason %q accepted", bad)
		}
	}
	if _, err := os.Stat(filepath.Join(s.Dir, "1.json")); err == nil {
		t.Error("record written for rejected item")
	}
}

func TestSummaryAndLine(t *testing.T) {
	s := &Store{Dir: t.TempDir(), Now: fixed}
	if Summarize(s.Dir).Line() != "" {
		t.Fatal("empty should render nothing")
	}
	s.Quarantine(Item{Seq: 2, Source: "hook", Reason: "bad-json", BodyLen: 5})
	s.Quarantine(Item{Seq: 10, ID: "m1", Source: "dispatch", Reason: "sig-mismatch", BodyLen: 9})
	s.Quarantine(Item{Seq: 7, Source: "hook", Reason: "truncated"})
	sum := Summarize(s.Dir)
	if sum.Count != 3 || sum.Latest.Seq != 10 || sum.Latest.Reason != "sig-mismatch" {
		t.Fatalf("%+v", sum)
	}
	if sum.Line() != "quarantined:3 latest:sig-mismatch" {
		t.Fatal(sum.Line())
	}
}

// Cursor model: against a reference max-model, over random advance/quarantine/
// handle operations, the cursor is the max seq seen and never decreases; a
// quarantined item never stalls the cursor.
func TestCursorModel(t *testing.T) {
	rng := rand.New(rand.NewSource(7))
	for trial := 0; trial < 50; trial++ {
		s := &Store{Dir: t.TempDir(), Now: fixed}
		model := int64(-1)
		for i := 0; i < 40; i++ {
			seq := int64(rng.Intn(30))
			switch rng.Intn(3) {
			case 0:
				s.Advance(seq)
			case 1:
				s.Quarantine(Item{Seq: seq, Source: "hook", Reason: "bad-json"})
			case 2:
				good := rng.Intn(2) == 0
				s.Handle(seq, "", "hook", []byte("x"), func([]byte) error {
					if good {
						return nil
					}
					return errors.New("no")
				})
			}
			if seq > model {
				model = seq
			}
			if got := s.Cursor(); got != model {
				t.Fatalf("trial %d step %d: cursor %d want %d", trial, i, got, model)
			}
		}
	}
}

func TestFileModes(t *testing.T) {
	s := &Store{Dir: filepath.Join(t.TempDir(), "q"), Now: fixed}
	s.Quarantine(Item{Seq: 1, Source: "hook", Reason: "bad-json"})
	st, _ := os.Stat(filepath.Join(s.Dir, "1.json"))
	if st.Mode().Perm() != 0o600 {
		t.Fatal(st.Mode())
	}
}
