package main

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/zeebo/blake3"
	"gopkg.in/yaml.v3"
	_ "modernc.org/sqlite"
)

// PluginEvidenceOptions identifies local plugin event stores to backfill into CXDB.
type PluginEvidenceOptions struct {
	InterspectDB string
	InterstatDB  string
	InterjectDB  string
}

// PluginEvidenceCursor records the highest consumed row IDs per plugin table.
type PluginEvidenceCursor struct {
	InterspectEvidenceID     int64 `json:"interspect_evidence_id,omitempty"`
	InterstatAgentRunID      int64 `json:"interstat_agent_run_id,omitempty"`
	InterstatToolSelectionID int64 `json:"interstat_tool_selection_id,omitempty"`
	InterjectPromotionID     int64 `json:"interject_promotion_id,omitempty"`
}

// PluginEvidenceItem is a normalized plugin event ready to append as clavain.evidence.v1.
type PluginEvidenceItem struct {
	Record EvidenceRecord
}

// collectPluginEvidenceRecords reads local plugin event stores and normalizes rows
// into clavain.evidence.v1 records without writing to CXDB. Missing databases or
// missing tables are treated as empty so cxdb-sync can run before plugins exist.
func collectPluginEvidenceRecords(beadID string, opts PluginEvidenceOptions, cursor PluginEvidenceCursor) ([]PluginEvidenceItem, PluginEvidenceCursor, error) {
	if strings.TrimSpace(beadID) == "" {
		return nil, cursor, fmt.Errorf("plugin evidence: bead id is required")
	}
	opts = opts.withDefaults()

	var items []PluginEvidenceItem
	if err := collectInterspectEvidence(beadID, opts.InterspectDB, cursor.InterspectEvidenceID, &items, &cursor); err != nil {
		return nil, cursor, err
	}
	if err := collectInterstatAgentRuns(beadID, opts.InterstatDB, cursor.InterstatAgentRunID, &items, &cursor); err != nil {
		return nil, cursor, err
	}
	if err := collectInterstatToolSelections(beadID, opts.InterstatDB, cursor.InterstatToolSelectionID, &items, &cursor); err != nil {
		return nil, cursor, err
	}
	if err := collectInterjectPromotions(beadID, opts.InterjectDB, cursor.InterjectPromotionID, &items, &cursor); err != nil {
		return nil, cursor, err
	}
	return items, cursor, nil
}

func (opts PluginEvidenceOptions) withDefaults() PluginEvidenceOptions {
	if opts.InterspectDB == "" {
		opts.InterspectDB = filepath.Join(projectRoot(), ".clavain", "interspect", "interspect.db")
	}
	if opts.InterstatDB == "" {
		if home, err := os.UserHomeDir(); err == nil {
			opts.InterstatDB = filepath.Join(home, ".claude", "interstat", "metrics.db")
		}
	}
	if opts.InterjectDB == "" {
		opts.InterjectDB = defaultInterjectDBPath()
	}
	return opts
}

func defaultInterjectDBPath() string {
	home, err := os.UserHomeDir()
	if err != nil {
		return ""
	}
	configPath := filepath.Join(home, ".interject", "config.yaml")
	if data, err := os.ReadFile(configPath); err == nil {
		var cfg struct {
			DBPath string `yaml:"db_path"`
		}
		if yaml.Unmarshal(data, &cfg) == nil && strings.TrimSpace(cfg.DBPath) != "" {
			return expandHomePath(strings.TrimSpace(cfg.DBPath))
		}
	}
	return filepath.Join(home, ".interject", "interject.db")
}

func expandHomePath(path string) string {
	if path == "~" {
		if home, err := os.UserHomeDir(); err == nil {
			return home
		}
	}
	if strings.HasPrefix(path, "~/") {
		if home, err := os.UserHomeDir(); err == nil {
			return filepath.Join(home, strings.TrimPrefix(path, "~/"))
		}
	}
	return path
}

func loadPluginEvidenceCursor(beadID string) PluginEvidenceCursor {
	var cursor PluginEvidenceCursor
	if !icAvailable() {
		return cursor
	}
	out, err := runIC("state", "get", pluginEvidenceCursorKey(beadID))
	if err != nil {
		return cursor
	}
	data := strings.TrimSpace(string(out))
	if data == "" {
		return cursor
	}
	_ = json.Unmarshal([]byte(data), &cursor)
	return cursor
}

func savePluginEvidenceCursor(beadID string, cursor PluginEvidenceCursor) error {
	if !icAvailable() {
		return nil
	}
	data, err := json.Marshal(cursor)
	if err != nil {
		return err
	}
	_, err = runIC("state", "set", pluginEvidenceCursorKey(beadID), string(data))
	return err
}

func pluginEvidenceCursorKey(beadID string) string {
	return "cxdb_plugin_evidence_cursor_" + beadID
}

func collectInterspectEvidence(beadID, dbPath string, afterID int64, items *[]PluginEvidenceItem, cursor *PluginEvidenceCursor) error {
	db, ok, err := openPluginSQLite(dbPath)
	if err != nil || !ok {
		return err
	}
	defer db.Close()
	if exists, err := sqliteTableExists(db, "evidence"); err != nil || !exists {
		return err
	}

	rows, err := db.Query(`SELECT id, ts, session_id, event, COALESCE(context, ''), COALESCE(source_event_id, ''), COALESCE(source_table, ''), COALESCE(override_reason, ''), COALESCE(raw_override_reason, '')
		FROM evidence
		WHERE id > ?
		ORDER BY id`, afterID)
	if err != nil {
		return fmt.Errorf("plugin evidence: read interspect evidence: %w", err)
	}
	defer rows.Close()

	for rows.Next() {
		var id int64
		var ts, sessionID, event, contextRaw, sourceEventID, upstreamTable, overrideReason, rawOverride string
		if err := rows.Scan(&id, &ts, &sessionID, &event, &contextRaw, &sourceEventID, &upstreamTable, &overrideReason, &rawOverride); err != nil {
			return fmt.Errorf("plugin evidence: scan interspect evidence: %w", err)
		}
		if id > cursor.InterspectEvidenceID {
			cursor.InterspectEvidenceID = id
		}

		contextMap := parsePluginContext(contextRaw)
		contextBead := pluginString(contextMap, "bead_id")
		if contextBead != "" && contextBead != beadID {
			continue
		}
		phase := pluginString(contextMap, "phase")
		summary := pluginString(contextMap, "summary")
		if summary == "" {
			summary = event
		}
		if overrideReason != "" || rawOverride != "" {
			summary = strings.TrimSpace(summary + " " + strings.TrimSpace(overrideReason+" "+rawOverride))
		}
		if upstreamTable != "" {
			summary = strings.TrimSpace(summary + " [upstream=" + upstreamTable + "]")
		}
		if sourceEventID == "" {
			sourceEventID = fmt.Sprintf("%d", id)
		}

		rec := EvidenceRecord{
			BeadID:        beadID,
			SourcePlugin:  "interspect",
			EvidenceType:  pluginNonEmpty(event, "interspect_event"),
			SessionID:     sessionID,
			Phase:         phase,
			BlobHash:      pluginEvidenceBlobHash("interspect", "evidence", id, map[string]any{"ts": ts, "session_id": sessionID, "event": event, "context": contextMap, "source_event_id": sourceEventID}),
			Timestamp:     parsePluginEvidenceTimestamp(ts),
			SourceID:      fmt.Sprintf("interspect:evidence:%d", id),
			SourceTable:   "evidence",
			SourceEventID: sourceEventID,
			Summary:       truncate(summary, 240),
		}
		*items = append(*items, PluginEvidenceItem{Record: rec})
	}
	return rows.Err()
}

func collectInterstatAgentRuns(beadID, dbPath string, afterID int64, items *[]PluginEvidenceItem, cursor *PluginEvidenceCursor) error {
	db, ok, err := openPluginSQLite(dbPath)
	if err != nil || !ok {
		return err
	}
	defer db.Close()
	if exists, err := sqliteTableExists(db, "agent_runs"); err != nil || !exists {
		return err
	}

	rows, err := db.Query(`SELECT id, timestamp, session_id, agent_name, COALESCE(invocation_id, ''), COALESCE(subagent_type, ''), COALESCE(description, ''), COALESCE(total_tokens, 0), COALESCE(input_tokens, 0), COALESCE(output_tokens, 0), COALESCE(model, ''), COALESCE(phase, '')
		FROM agent_runs
		WHERE id > ? AND bead_id = ?
		ORDER BY id`, afterID, beadID)
	if err != nil {
		return fmt.Errorf("plugin evidence: read interstat agent_runs: %w", err)
	}
	defer rows.Close()

	for rows.Next() {
		var id, totalTokens, inputTokens, outputTokens int64
		var ts, sessionID, agentName, invocationID, subagentType, description, model, phase string
		if err := rows.Scan(&id, &ts, &sessionID, &agentName, &invocationID, &subagentType, &description, &totalTokens, &inputTokens, &outputTokens, &model, &phase); err != nil {
			return fmt.Errorf("plugin evidence: scan interstat agent_runs: %w", err)
		}
		if id > cursor.InterstatAgentRunID {
			cursor.InterstatAgentRunID = id
		}
		summary := description
		if summary == "" {
			summary = strings.TrimSpace(agentName + " " + subagentType)
		}
		if model != "" || totalTokens > 0 {
			summary = strings.TrimSpace(fmt.Sprintf("%s [model=%s tokens=%d/%d/%d]", summary, model, inputTokens, outputTokens, totalTokens))
		}

		rec := EvidenceRecord{
			BeadID:        beadID,
			SourcePlugin:  "interstat",
			EvidenceType:  "agent_run",
			SessionID:     sessionID,
			Phase:         phase,
			BlobHash:      pluginEvidenceBlobHash("interstat", "agent_runs", id, map[string]any{"timestamp": ts, "session_id": sessionID, "agent_name": agentName, "invocation_id": invocationID, "model": model, "tokens": totalTokens}),
			Timestamp:     parsePluginEvidenceTimestamp(ts),
			SourceID:      fmt.Sprintf("interstat:agent_runs:%d", id),
			SourceTable:   "agent_runs",
			SourceEventID: invocationID,
			Summary:       truncate(summary, 240),
		}
		*items = append(*items, PluginEvidenceItem{Record: rec})
	}
	return rows.Err()
}

func collectInterstatToolSelections(beadID, dbPath string, afterID int64, items *[]PluginEvidenceItem, cursor *PluginEvidenceCursor) error {
	db, ok, err := openPluginSQLite(dbPath)
	if err != nil || !ok {
		return err
	}
	defer db.Close()
	if exists, err := sqliteTableExists(db, "tool_selection_events"); err != nil || !exists {
		return err
	}

	rows, err := db.Query(`SELECT id, timestamp, session_id, seq, tool_name, COALESCE(tool_input_summary, ''), COALESCE(outcome, ''), COALESCE(preceding_tool, ''), COALESCE(retry_of_seq, 0), COALESCE(phase, '')
		FROM tool_selection_events
		WHERE id > ? AND bead_id = ?
		ORDER BY id`, afterID, beadID)
	if err != nil {
		return fmt.Errorf("plugin evidence: read interstat tool_selection_events: %w", err)
	}
	defer rows.Close()

	for rows.Next() {
		var id, seq, retryOfSeq int64
		var ts, sessionID, toolName, inputSummary, outcome, precedingTool, phase string
		if err := rows.Scan(&id, &ts, &sessionID, &seq, &toolName, &inputSummary, &outcome, &precedingTool, &retryOfSeq, &phase); err != nil {
			return fmt.Errorf("plugin evidence: scan interstat tool_selection_events: %w", err)
		}
		if id > cursor.InterstatToolSelectionID {
			cursor.InterstatToolSelectionID = id
		}
		summary := strings.TrimSpace(toolName + " " + outcome)
		if inputSummary != "" {
			summary = strings.TrimSpace(summary + ": " + inputSummary)
		}
		if precedingTool != "" || retryOfSeq > 0 {
			summary = strings.TrimSpace(fmt.Sprintf("%s [prev=%s retry_of=%d]", summary, precedingTool, retryOfSeq))
		}

		rec := EvidenceRecord{
			BeadID:        beadID,
			SourcePlugin:  "interstat",
			EvidenceType:  "tool_selection",
			SessionID:     sessionID,
			Phase:         phase,
			BlobHash:      pluginEvidenceBlobHash("interstat", "tool_selection_events", id, map[string]any{"timestamp": ts, "session_id": sessionID, "seq": seq, "tool_name": toolName, "outcome": outcome}),
			Timestamp:     parsePluginEvidenceTimestamp(ts),
			SourceID:      fmt.Sprintf("interstat:tool_selection_events:%d", id),
			SourceTable:   "tool_selection_events",
			SourceEventID: fmt.Sprintf("%s:%d", sessionID, seq),
			Summary:       truncate(summary, 240),
		}
		*items = append(*items, PluginEvidenceItem{Record: rec})
	}
	return rows.Err()
}

func collectInterjectPromotions(beadID, dbPath string, afterID int64, items *[]PluginEvidenceItem, cursor *PluginEvidenceCursor) error {
	db, ok, err := openPluginSQLite(dbPath)
	if err != nil || !ok {
		return err
	}
	defer db.Close()
	if exists, err := sqliteTableExists(db, "promotions"); err != nil || !exists {
		return err
	}
	if exists, err := sqliteTableExists(db, "discoveries"); err != nil || !exists {
		return err
	}

	rows, err := db.Query(`SELECT p.id, COALESCE(CAST(p.discovery_id AS TEXT), ''), COALESCE(CAST(p.bead_priority AS TEXT), ''), COALESCE(p.promoted_at, ''), COALESCE(d.source, ''), COALESCE(d.source_id, ''), COALESCE(d.title, ''), COALESCE(d.summary, ''), COALESCE(d.url, ''), COALESCE(d.relevance_score, 0), COALESCE(d.confidence_tier, '')
		FROM promotions p
		LEFT JOIN discoveries d ON CAST(d.id AS TEXT) = CAST(p.discovery_id AS TEXT)
		WHERE p.id > ? AND p.bead_id = ?
		ORDER BY p.id`, afterID, beadID)
	if err != nil {
		return fmt.Errorf("plugin evidence: read interject promotions: %w", err)
	}
	defer rows.Close()

	for rows.Next() {
		var id int64
		var relevanceScore float64
		var discoveryID, beadPriority, promotedAt, source, sourceID, title, summaryText, url, confidenceTier string
		if err := rows.Scan(&id, &discoveryID, &beadPriority, &promotedAt, &source, &sourceID, &title, &summaryText, &url, &relevanceScore, &confidenceTier); err != nil {
			return fmt.Errorf("plugin evidence: scan interject promotions: %w", err)
		}
		if id > cursor.InterjectPromotionID {
			cursor.InterjectPromotionID = id
		}
		summary := title
		if summaryText != "" {
			summary = strings.TrimSpace(summary + ": " + summaryText)
		}
		if source != "" || confidenceTier != "" || beadPriority != "" {
			summary = strings.TrimSpace(fmt.Sprintf("%s [source=%s confidence=%s priority=%s]", summary, source, confidenceTier, beadPriority))
		}
		eventID := discoveryID
		if sourceID != "" {
			eventID = sourceID
		}

		rec := EvidenceRecord{
			BeadID:        beadID,
			SourcePlugin:  "interject",
			EvidenceType:  "promotion",
			BlobHash:      pluginEvidenceBlobHash("interject", "promotions", id, map[string]any{"promoted_at": promotedAt, "discovery_id": discoveryID, "source": source, "source_id": sourceID, "title": title, "summary": summaryText, "url": url, "relevance_score": relevanceScore}),
			Timestamp:     parsePluginEvidenceTimestamp(promotedAt),
			SourceID:      fmt.Sprintf("interject:promotions:%d", id),
			SourceTable:   "promotions",
			SourceEventID: eventID,
			Summary:       truncate(summary, 240),
		}
		*items = append(*items, PluginEvidenceItem{Record: rec})
	}
	return rows.Err()
}

func openPluginSQLite(path string) (*sql.DB, bool, error) {
	path = strings.TrimSpace(path)
	if path == "" {
		return nil, false, nil
	}
	if _, err := os.Stat(path); err != nil {
		if os.IsNotExist(err) {
			return nil, false, nil
		}
		return nil, false, fmt.Errorf("plugin evidence: stat sqlite %s: %w", path, err)
	}
	db, err := sql.Open("sqlite", path+"?_busy_timeout=5000")
	if err != nil {
		return nil, false, fmt.Errorf("plugin evidence: open sqlite %s: %w", path, err)
	}
	db.SetMaxOpenConns(1)
	return db, true, nil
}

func sqliteTableExists(db *sql.DB, table string) (bool, error) {
	var name string
	err := db.QueryRow(`SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?`, table).Scan(&name)
	if err == sql.ErrNoRows {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	return name == table, nil
}

func parsePluginContext(raw string) map[string]any {
	m := map[string]any{}
	if strings.TrimSpace(raw) == "" {
		return m
	}
	_ = json.Unmarshal([]byte(raw), &m)
	return m
}

func pluginString(m map[string]any, key string) string {
	v, ok := m[key]
	if !ok || v == nil {
		return ""
	}
	switch typed := v.(type) {
	case string:
		return typed
	case fmt.Stringer:
		return typed.String()
	case float64:
		return strings.TrimRight(strings.TrimRight(fmt.Sprintf("%.6f", typed), "0"), ".")
	default:
		return fmt.Sprint(typed)
	}
}

func pluginNonEmpty(value, fallback string) string {
	if strings.TrimSpace(value) == "" {
		return fallback
	}
	return value
}

func parsePluginEvidenceTimestamp(raw string) uint64 {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return uint64(time.Now().Unix())
	}
	layouts := []string{
		time.RFC3339Nano,
		time.RFC3339,
		"2006-01-02 15:04:05",
		"2006-01-02T15:04:05",
	}
	for _, layout := range layouts {
		if parsed, err := time.Parse(layout, raw); err == nil {
			return uint64(parsed.Unix())
		}
	}
	return uint64(time.Now().Unix())
}

func pluginEvidenceBlobHash(plugin, table string, id int64, raw any) []byte {
	payload := map[string]any{
		"plugin": plugin,
		"table":  table,
		"id":     id,
		"raw":    raw,
	}
	data, _ := json.Marshal(payload)
	hash := blake3.Sum256(data)
	out := make([]byte, len(hash))
	copy(out, hash[:])
	return out
}
