package gatecal

import (
	"path/filepath"
	"testing"
)

func TestOpenCreatesSchema(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "gate.db")

	s, err := Open(path)
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer s.Close()

	expectTables := []string{"tier_state", "drain_log", "signals_cache"}
	for _, tbl := range expectTables {
		var name string
		err := s.DB().QueryRow(`SELECT name FROM sqlite_master WHERE type='table' AND name=?`, tbl).Scan(&name)
		if err != nil {
			t.Errorf("missing table %s: %v", tbl, err)
		}
	}
}

func TestOpenIsIdempotent(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "gate.db")

	s1, err := Open(path)
	if err != nil {
		t.Fatalf("first Open: %v", err)
	}
	s1.Close()

	s2, err := Open(path)
	if err != nil {
		t.Fatalf("second Open (re-init): %v", err)
	}
	defer s2.Close()
}

func TestTierStateColumns(t *testing.T) {
	dir := t.TempDir()
	s, err := Open(filepath.Join(dir, "gate.db"))
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer s.Close()

	rows, err := s.DB().Query(`PRAGMA table_info(tier_state)`)
	if err != nil {
		t.Fatalf("PRAGMA: %v", err)
	}
	defer rows.Close()

	want := map[string]bool{
		"theme": true, "check_type": true, "phase_from": true, "phase_to": true,
		"tier": true, "fpr": true, "fnr": true, "weighted_n": true,
		"consecutive_windows_above_threshold": true, "locked": true,
		"change_count_90d": true, "last_changed_at": true,
		"fnr_threshold": true, "origin_key": true, "theme_source": true, "updated_at": true,
	}
	got := map[string]bool{}
	for rows.Next() {
		var cid int
		var name, typ string
		var notnull, pk int
		var dflt interface{}
		if err := rows.Scan(&cid, &name, &typ, &notnull, &dflt, &pk); err != nil {
			t.Fatalf("scan pragma row: %v", err)
		}
		got[name] = true
	}
	for col := range want {
		if !got[col] {
			t.Errorf("tier_state missing column %s", col)
		}
	}
}
