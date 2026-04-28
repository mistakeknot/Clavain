package main

import (
	"database/sql"
	"path/filepath"
	"testing"

	"github.com/vmihailenco/msgpack/v5"
	_ "modernc.org/sqlite"
)

type evidenceRecordSchemaProbe struct {
	BeadID        string `msgpack:"1"`
	SourcePlugin  string `msgpack:"2"`
	EvidenceType  string `msgpack:"3"`
	SessionID     string `msgpack:"4"`
	Phase         string `msgpack:"5"`
	BlobHash      []byte `msgpack:"6"`
	Timestamp     uint64 `msgpack:"7"`
	FindingID     string `msgpack:"8"`
	Severity      string `msgpack:"9"`
	SourceID      string `msgpack:"10"`
	SourceTable   string `msgpack:"11"`
	SourceEventID string `msgpack:"12"`
	Summary       string `msgpack:"13"`
}

func TestEvidenceRecordMsgpackMatchesCXDBEvidenceSchema(t *testing.T) {
	rec := EvidenceRecord{
		BeadID:        "sylveste-xcn4",
		SourcePlugin:  "interspect",
		EvidenceType:  "route_outcome",
		SessionID:     "session-1",
		Phase:         "green",
		BlobHash:      []byte{1, 2, 3},
		Timestamp:     1777406400,
		FindingID:     "finding-1",
		Severity:      "warning",
		SourceID:      "interspect:evidence:7",
		SourceTable:   "evidence",
		SourceEventID: "evt-7",
		Summary:       "kernel route outcome",
	}

	data, err := msgpack.Marshal(rec)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	var decoded evidenceRecordSchemaProbe
	if err := msgpack.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("unmarshal into schema probe: %v", err)
	}

	if decoded.SessionID != "session-1" {
		t.Fatalf("tag 4 should be session_id, got %q", decoded.SessionID)
	}
	if decoded.Phase != "green" {
		t.Fatalf("tag 5 should be phase, got %q", decoded.Phase)
	}
	if decoded.Timestamp != 1777406400 {
		t.Fatalf("tag 7 should be timestamp, got %d", decoded.Timestamp)
	}
	if decoded.SourceID != "interspect:evidence:7" || decoded.SourceTable != "evidence" || decoded.SourceEventID != "evt-7" {
		t.Fatalf("source lineage tags did not round-trip: %#v", decoded)
	}
}

func TestCollectPluginEvidenceRecordsReadsPluginDatabases(t *testing.T) {
	tmpDir := t.TempDir()
	interspectDB := filepath.Join(tmpDir, "interspect.db")
	interstatDB := filepath.Join(tmpDir, "interstat.db")
	interjectDB := filepath.Join(tmpDir, "interject.db")

	createInterspectFixture(t, interspectDB)
	createInterstatFixture(t, interstatDB)
	createInterjectFixture(t, interjectDB)

	items, cursor, err := collectPluginEvidenceRecords("sylveste-xcn4", PluginEvidenceOptions{
		InterspectDB: interspectDB,
		InterstatDB:  interstatDB,
		InterjectDB:  interjectDB,
	}, PluginEvidenceCursor{})
	if err != nil {
		t.Fatalf("collect plugin evidence: %v", err)
	}

	wantBySourceID := map[string]struct {
		plugin       string
		evidenceType string
		sessionID    string
		phase        string
	}{
		"interspect:evidence:7":              {"interspect", "route_outcome", "session-1", "green"},
		"interstat:agent_runs:11":            {"interstat", "agent_run", "session-1", "green"},
		"interstat:tool_selection_events:12": {"interstat", "tool_selection", "session-1", "green"},
		"interject:promotions:4":             {"interject", "promotion", "", ""},
	}
	if len(items) != len(wantBySourceID) {
		t.Fatalf("got %d records, want %d: %#v", len(items), len(wantBySourceID), items)
	}
	seen := map[string]bool{}
	for _, item := range items {
		rec := item.Record
		want, ok := wantBySourceID[rec.SourceID]
		if !ok {
			t.Fatalf("unexpected source id %q in record %#v", rec.SourceID, rec)
		}
		seen[rec.SourceID] = true
		if rec.BeadID != "sylveste-xcn4" {
			t.Errorf("%s bead_id got %q", rec.SourceID, rec.BeadID)
		}
		if rec.SourcePlugin != want.plugin || rec.EvidenceType != want.evidenceType {
			t.Errorf("%s source got %s/%s want %s/%s", rec.SourceID, rec.SourcePlugin, rec.EvidenceType, want.plugin, want.evidenceType)
		}
		if rec.SessionID != want.sessionID || rec.Phase != want.phase {
			t.Errorf("%s session/phase got %q/%q want %q/%q", rec.SourceID, rec.SessionID, rec.Phase, want.sessionID, want.phase)
		}
		if len(rec.BlobHash) != 32 {
			t.Errorf("%s blob hash length got %d, want 32", rec.SourceID, len(rec.BlobHash))
		}
	}
	for sourceID := range wantBySourceID {
		if !seen[sourceID] {
			t.Errorf("missing source id %s", sourceID)
		}
	}
	if cursor.InterspectEvidenceID != 7 || cursor.InterstatAgentRunID != 11 || cursor.InterstatToolSelectionID != 12 || cursor.InterjectPromotionID != 4 {
		t.Fatalf("cursor did not advance to max row ids: %#v", cursor)
	}
}

func createInterspectFixture(t *testing.T, path string) {
	t.Helper()
	db := mustOpenSQLite(t, path)
	defer db.Close()
	mustExec(t, db, `CREATE TABLE evidence (
		id INTEGER PRIMARY KEY AUTOINCREMENT,
		ts TEXT NOT NULL,
		session_id TEXT NOT NULL,
		seq INTEGER NOT NULL,
		source TEXT NOT NULL,
		source_version TEXT,
		event TEXT NOT NULL,
		override_reason TEXT,
		context TEXT NOT NULL,
		project TEXT NOT NULL,
		project_lang TEXT,
		project_type TEXT,
		source_event_id TEXT,
		source_table TEXT,
		raw_override_reason TEXT,
		quarantine_until INTEGER DEFAULT 0
	)`)
	mustExec(t, db, `INSERT INTO evidence (id, ts, session_id, seq, source, source_version, event, override_reason, context, project, source_event_id, source_table, raw_override_reason, quarantine_until)
		VALUES (7, '2026-04-28T20:00:00Z', 'session-1', 2, 'kernel-route', 'abc123', 'route_outcome', '', '{"bead_id":"sylveste-xcn4","phase":"green","summary":"kernel route outcome"}', 'Sylveste', 'evt-7', 'events', '', 0)`)
}

func createInterstatFixture(t *testing.T, path string) {
	t.Helper()
	db := mustOpenSQLite(t, path)
	defer db.Close()
	mustExec(t, db, `CREATE TABLE agent_runs (
		id INTEGER PRIMARY KEY AUTOINCREMENT,
		timestamp TEXT NOT NULL,
		session_id TEXT NOT NULL,
		agent_name TEXT NOT NULL,
		invocation_id TEXT,
		subagent_type TEXT,
		description TEXT,
		wall_clock_ms INTEGER,
		result_length INTEGER,
		total_tokens INTEGER,
		input_tokens INTEGER,
		output_tokens INTEGER,
		model TEXT,
		parsed_at TEXT,
		bead_id TEXT,
		phase TEXT
	)`)
	mustExec(t, db, `INSERT INTO agent_runs (id, timestamp, session_id, agent_name, invocation_id, subagent_type, description, wall_clock_ms, result_length, total_tokens, input_tokens, output_tokens, model, bead_id, phase)
		VALUES (11, '2026-04-28T20:01:00Z', 'session-1', 'Claude Code', 'inv-1', 'coder', 'implemented wiring', 1200, 44, 100, 60, 40, 'gpt-5.5', 'sylveste-xcn4', 'green')`)
	mustExec(t, db, `CREATE TABLE tool_selection_events (
		id INTEGER PRIMARY KEY AUTOINCREMENT,
		timestamp TEXT NOT NULL,
		session_id TEXT NOT NULL,
		seq INTEGER NOT NULL,
		tool_name TEXT NOT NULL,
		tool_input_summary TEXT,
		outcome TEXT,
		preceding_tool TEXT,
		retry_of_seq INTEGER,
		bead_id TEXT,
		phase TEXT
	)`)
	mustExec(t, db, `INSERT INTO tool_selection_events (id, timestamp, session_id, seq, tool_name, tool_input_summary, outcome, preceding_tool, retry_of_seq, bead_id, phase)
		VALUES (12, '2026-04-28T20:02:00Z', 'session-1', 3, 'terminal', 'go test', 'success', 'read_file', NULL, 'sylveste-xcn4', 'green')`)
}

func createInterjectFixture(t *testing.T, path string) {
	t.Helper()
	db := mustOpenSQLite(t, path)
	defer db.Close()
	mustExec(t, db, `CREATE TABLE discoveries (
		id INTEGER PRIMARY KEY AUTOINCREMENT,
		source TEXT NOT NULL,
		source_id TEXT,
		title TEXT NOT NULL,
		summary TEXT,
		url TEXT,
		raw_metadata TEXT,
		embedding BLOB,
		relevance_score REAL,
		confidence_tier TEXT,
		status TEXT,
		discovered_at TEXT,
		reviewed_at TEXT
	)`)
	mustExec(t, db, `CREATE TABLE promotions (
		id INTEGER PRIMARY KEY AUTOINCREMENT,
		discovery_id INTEGER NOT NULL,
		bead_id TEXT NOT NULL,
		bead_priority TEXT,
		promoted_at TEXT
	)`)
	mustExec(t, db, `INSERT INTO discoveries (id, source, source_id, title, summary, url, raw_metadata, relevance_score, confidence_tier, status, discovered_at)
		VALUES (3, 'paper', 'arxiv:1234', 'Routing paper', 'Useful route/outcome method', 'https://example.test/paper', '{"topic":"routing"}', 0.92, 'high', 'promoted', '2026-04-28T19:59:00+00:00')`)
	mustExec(t, db, `INSERT INTO promotions (id, discovery_id, bead_id, bead_priority, promoted_at)
		VALUES (4, 3, 'sylveste-xcn4', 'P1', '2026-04-28T20:03:00+00:00')`)
}

func mustOpenSQLite(t *testing.T, path string) *sql.DB {
	t.Helper()
	db, err := sql.Open("sqlite", path)
	if err != nil {
		t.Fatalf("open sqlite %s: %v", path, err)
	}
	return db
}

func mustExec(t *testing.T, db *sql.DB, stmt string) {
	t.Helper()
	if _, err := db.Exec(stmt); err != nil {
		t.Fatalf("exec %s: %v", stmt, err)
	}
}
