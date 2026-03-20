package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"github.com/vmihailenco/msgpack/v5"
	"github.com/zeebo/blake3"
)

// cxdbClient holds the singleton CXDB connection.
var cxdbClient *CXDBClient

// cxdbStartAttempted prevents repeated auto-start attempts in the same process.
var cxdbStartAttempted bool

// cxdbEnsureRunning checks if CXDB is available, and if not, attempts to start it.
// Returns true if CXDB is available (either already running or successfully started).
// Returns false if CXDB binary is not installed or start failed.
func cxdbEnsureRunning() bool {
	if cxdbAvailable() {
		return true
	}
	if cxdbStartAttempted {
		return false
	}
	cxdbStartAttempted = true

	// Check if binary exists
	if _, err := os.Stat(cxdbBinaryPath()); os.IsNotExist(err) {
		return false
	}

	// Attempt to start
	if err := cmdCXDBStart(nil); err != nil {
		fmt.Fprintf(os.Stderr, "cxdb: auto-start failed: %v\n", err)
		return false
	}
	return cxdbAvailable()
}

// cxdbConnect connects to the local CXDB server.
// Returns the existing connection if already connected.
func cxdbConnect() (*CXDBClient, error) {
	if cxdbClient != nil {
		return cxdbClient, nil
	}

	addr := fmt.Sprintf("localhost:%d", cxdbDefaultPort)
	client, err := CXDBDial(addr)
	if err != nil {
		return nil, fmt.Errorf("cxdb connect: %w", err)
	}
	cxdbClient = client
	return client, nil
}

// cxdbClose closes the CXDB connection if open.
func cxdbClose() {
	if cxdbClient != nil {
		cxdbClient.Close()
		cxdbClient = nil
	}
}

// cxdbSprintContext gets or creates a CXDB context for a sprint.
// Uses the bead ID to map to a persistent context.
func cxdbSprintContext(client *CXDBClient, beadID string) (uint64, error) {
	// Try to find existing context via ic state
	if icAvailable() {
		out, err := runIC("state", "get", "cxdb_context_"+beadID)
		if err == nil {
			ctxID, parseErr := strconv.ParseUint(strings.TrimSpace(string(out)), 10, 64)
			if parseErr == nil && ctxID > 0 {
				return ctxID, nil
			}
		}
	}

	// Create new context
	ctx := context.Background()
	head, err := client.CreateContext(ctx, 0)
	if err != nil {
		return 0, fmt.Errorf("cxdb create context for %s: %w", beadID, err)
	}

	// Persist context ID in ic state
	if icAvailable() {
		ctxStr := strconv.FormatUint(head.ContextID, 10)
		runIC("state", "set", "cxdb_context_"+beadID, ctxStr)
	}

	return head.ContextID, nil
}

// PhaseRecord is the data for a clavain.phase.v1 turn.
type PhaseRecord struct {
	BeadID           string `msgpack:"1" json:"bead_id"`
	Phase            string `msgpack:"2" json:"phase"`
	PreviousPhase    string `msgpack:"3" json:"previous_phase"`
	ArtifactPath     string `msgpack:"4" json:"artifact_path,omitempty"`
	ArtifactBlobHash []byte `msgpack:"5" json:"artifact_blob_hash,omitempty"`
	Timestamp        uint64 `msgpack:"6" json:"timestamp"`
}

// DispatchRecord is the data for a clavain.dispatch.v2 turn.
type DispatchRecord struct {
	BeadID         string `msgpack:"1" json:"bead_id"`
	AgentName      string `msgpack:"2" json:"agent_name"`
	AgentType      string `msgpack:"3" json:"agent_type,omitempty"`
	Model          string `msgpack:"4" json:"model,omitempty"`
	Status         string `msgpack:"5" json:"status"`
	InputTokens    uint64 `msgpack:"6" json:"input_tokens,omitempty"`
	OutputTokens   uint64 `msgpack:"7" json:"output_tokens,omitempty"`
	ResultBlobHash []byte `msgpack:"8" json:"result_blob_hash,omitempty"`
	Timestamp      uint64 `msgpack:"9" json:"timestamp"`
	DurationMs     uint64 `msgpack:"10" json:"duration_ms,omitempty"`
	ErrorMessage   string `msgpack:"11" json:"error_message,omitempty"`
}

// ArtifactRecord is the data for a clavain.artifact.v1 turn.
type ArtifactRecord struct {
	BeadID       string `msgpack:"1" json:"bead_id"`
	ArtifactType string `msgpack:"2" json:"artifact_type"`
	Path         string `msgpack:"3" json:"path"`
	BlobHash     []byte `msgpack:"4" json:"blob_hash"`
	SizeBytes    uint64 `msgpack:"5" json:"size_bytes,omitempty"`
	Timestamp    uint64 `msgpack:"6" json:"timestamp"`
}

// cxdbRecordPhase records a phase transition as a CXDB turn.
func cxdbRecordPhase(client *CXDBClient, ctxID uint64, rec PhaseRecord) error {
	if rec.Timestamp == 0 {
		rec.Timestamp = uint64(time.Now().Unix())
	}
	return cxdbAppendTyped(client, ctxID, "clavain.phase.v1", rec)
}

// cxdbRecordDispatch records an agent dispatch as a CXDB turn.
func cxdbRecordDispatch(client *CXDBClient, ctxID uint64, rec DispatchRecord) error {
	if rec.Timestamp == 0 {
		rec.Timestamp = uint64(time.Now().Unix())
	}
	return cxdbAppendTyped(client, ctxID, "clavain.dispatch.v2", rec)
}

// cxdbStoreBlob stores data as a blob via CXDB CAS (content-addressed turn).
// Returns the hex-encoded BLAKE3 hash.
func cxdbStoreBlob(client *CXDBClient, ctxID uint64, data []byte) (string, error) {
	rec := ArtifactRecord{
		BlobHash:  data, // The CXDB server computes BLAKE3 internally
		SizeBytes: uint64(len(data)),
		Timestamp: uint64(time.Now().Unix()),
	}
	return "", cxdbAppendTyped(client, ctxID, "clavain.artifact.v1", rec)
}

// cxdbForkSprint creates an O(1) branched execution trajectory.
func cxdbForkSprint(client *CXDBClient, turnID uint64) (uint64, error) {
	ctx := context.Background()
	head, err := client.CreateContext(ctx, turnID)
	if err != nil {
		return 0, fmt.Errorf("cxdb fork: %w", err)
	}
	return head.ContextID, nil
}

// cxdbQueryByType returns all turns of a specific type from a context.
func cxdbQueryByType(client *CXDBClient, ctxID uint64, typeID string) ([]CXDBTurnRecord, error) {
	ctx := context.Background()
	turns, err := client.GetLast(ctx, ctxID, CXDBGetLastOptions{
		Limit:          1000,
		IncludePayload: true,
	})
	if err != nil {
		return nil, fmt.Errorf("cxdb query: %w", err)
	}

	// Filter by type
	var result []CXDBTurnRecord
	for _, t := range turns {
		if t.TypeID == typeID {
			result = append(result, t)
		}
	}
	return result, nil
}

// cxdbAppendTyped encodes a record as msgpack and appends it as a CXDB turn.
func cxdbAppendTyped(client *CXDBClient, ctxID uint64, typeID string, record any) error {
	payload, err := msgpack.Marshal(record)
	if err != nil {
		return fmt.Errorf("cxdb encode %s: %w", typeID, err)
	}

	ctx := context.Background()
	_, err = client.AppendTurn(ctx, &CXDBAppendRequest{
		ContextID:   ctxID,
		TypeID:      typeID,
		TypeVersion: 1,
		Payload:     payload,
	})
	if err != nil {
		return fmt.Errorf("cxdb append %s: %w", typeID, err)
	}
	return nil
}

// cmdCXDBSync backfills the CXDB Turn DAG from Intercore events.
// Supports incremental sync via cursor stored in ic state.
// Usage: cxdb-sync <sprint-id>
func cmdCXDBSync(args []string) error {
	if len(args) < 1 {
		return fmt.Errorf("usage: cxdb-sync <sprint-id>")
	}
	beadID := args[0]

	if !cxdbEnsureRunning() {
		return fmt.Errorf("cxdb-sync: CXDB not available")
	}

	client, err := cxdbConnect()
	if err != nil {
		return err
	}
	defer cxdbClose()

	ctxID, err := cxdbSprintContext(client, beadID)
	if err != nil {
		return err
	}

	// Get ic run events
	runID, err := resolveRunID(beadID)
	if err != nil {
		return fmt.Errorf("cxdb-sync: cannot resolve run for %s: %w", beadID, err)
	}

	// Read sync cursor for incremental sync
	cursorKey := "cxdb_sync_cursor_" + beadID
	var cursor string
	if icAvailable() {
		if out, err := runIC("state", "get", cursorKey); err == nil {
			cursor = strings.TrimSpace(string(out))
		}
	}

	var events []struct {
		ID    string          `json:"id"`
		Type  string          `json:"type"`
		Phase string          `json:"phase,omitempty"`
		Data  json.RawMessage `json:"data,omitempty"`
	}
	if err := runICJSON(&events, "run", "events", runID); err != nil {
		return fmt.Errorf("cxdb-sync: cannot read events: %w", err)
	}

	// Filter events after cursor
	startIdx := 0
	if cursor != "" {
		for i, evt := range events {
			if evt.ID == cursor {
				startIdx = i + 1
				break
			}
		}
	}

	syncCount := 0
	var lastID string
	for _, evt := range events[startIdx:] {
		lastID = evt.ID
		// Record phase transitions
		if evt.Type == "phase_change" || evt.Type == "advance" {
			rec := PhaseRecord{
				BeadID:    beadID,
				Phase:     evt.Phase,
				Timestamp: uint64(time.Now().Unix()),
			}
			if err := cxdbRecordPhase(client, ctxID, rec); err != nil {
				fmt.Fprintf(os.Stderr, "cxdb-sync: warning: %v\n", err)
				continue
			}
			syncCount++
		}
	}

	// Update cursor
	if lastID != "" && icAvailable() {
		runIC("state", "set", cursorKey, lastID)
	}

	fmt.Fprintf(os.Stderr, "cxdb-sync: synced %d events for %s (cursor: %s)\n", syncCount, beadID, lastID)
	return nil
}

// cxdbRecordPhaseTransition is a best-effort helper called after phase advances.
// Auto-starts CXDB if the binary is installed. Silently skips otherwise.
func cxdbRecordPhaseTransition(beadID, phase, artifactPath string) {
	if !cxdbEnsureRunning() {
		return
	}
	client, err := cxdbConnect()
	if err != nil {
		fmt.Fprintf(os.Stderr, "cxdb: phase record skipped: %v\n", err)
		return
	}
	ctxID, err := cxdbSprintContext(client, beadID)
	if err != nil {
		fmt.Fprintf(os.Stderr, "cxdb: phase record skipped: %v\n", err)
		return
	}
	rec := PhaseRecord{
		BeadID:       beadID,
		Phase:        phase,
		ArtifactPath: artifactPath,
	}
	if err := cxdbRecordPhase(client, ctxID, rec); err != nil {
		fmt.Fprintf(os.Stderr, "cxdb: phase record warning: %v\n", err)
	}
}

// cxdbRecordArtifact records a file artifact with its BLAKE3 hash as a CXDB turn.
// Silently skips if the file doesn't exist or CXDB is not available.
func cxdbRecordArtifact(beadID, artifactType, path string) {
	if !cxdbEnsureRunning() {
		return
	}

	// Read file and compute hash
	data, err := os.ReadFile(path)
	if err != nil {
		return // File doesn't exist yet — skip silently
	}
	hash := blake3.Sum256(data)

	client, err := cxdbConnect()
	if err != nil {
		return
	}
	ctxID, err := cxdbSprintContext(client, beadID)
	if err != nil {
		return
	}

	rec := ArtifactRecord{
		BeadID:       beadID,
		ArtifactType: artifactType,
		Path:         path,
		BlobHash:     hash[:],
		SizeBytes:    uint64(len(data)),
	}
	if err := cxdbAppendTyped(client, ctxID, "clavain.artifact.v1", rec); err != nil {
		fmt.Fprintf(os.Stderr, "cxdb: artifact record warning: %v\n", err)
	}
}

// VerdictFile is the JSON structure of a verdict file in .clavain/verdicts/.
type VerdictFile struct {
	Type          string `json:"type"`
	Status        string `json:"status"`
	Model         string `json:"model"`
	TokensSpent   int    `json:"tokens_spent"`
	FindingsCount int    `json:"findings_count"`
	Summary       string `json:"summary"`
	Timestamp     string `json:"timestamp"`
}

// cmdCXDBSyncVerdicts reads verdict files and writes dispatch turns.
// Usage: cxdb-sync-verdicts <bead-id>
func cmdCXDBSyncVerdicts(args []string) error {
	if len(args) < 1 {
		return fmt.Errorf("usage: cxdb-sync-verdicts <bead-id>")
	}
	beadID := args[0]

	if !cxdbEnsureRunning() {
		return fmt.Errorf("cxdb-sync-verdicts: CXDB not available")
	}

	client, err := cxdbConnect()
	if err != nil {
		return err
	}
	defer cxdbClose()

	ctxID, err := cxdbSprintContext(client, beadID)
	if err != nil {
		return err
	}

	// Find verdict files
	projectDir := os.Getenv("SPRINT_LIB_PROJECT_DIR")
	if projectDir == "" {
		projectDir = "."
	}
	verdictDir := filepath.Join(projectDir, ".clavain", "verdicts")
	entries, err := os.ReadDir(verdictDir)
	if err != nil {
		return fmt.Errorf("cxdb-sync-verdicts: no verdict dir: %w", err)
	}

	syncCount := 0
	for _, entry := range entries {
		if entry.IsDir() || !strings.HasSuffix(entry.Name(), ".json") {
			continue
		}

		data, err := os.ReadFile(filepath.Join(verdictDir, entry.Name()))
		if err != nil {
			continue
		}
		var verdict VerdictFile
		if err := json.Unmarshal(data, &verdict); err != nil {
			continue
		}
		if verdict.Type != "verdict" {
			continue
		}

		// Agent name from filename (e.g., "fd-architecture.json" → "fd-architecture")
		agentName := strings.TrimSuffix(entry.Name(), ".json")

		// Parse timestamp
		var ts uint64
		if t, err := time.Parse(time.RFC3339, verdict.Timestamp); err == nil {
			ts = uint64(t.Unix())
		} else {
			ts = uint64(time.Now().Unix())
		}

		rec := DispatchRecord{
			BeadID:    beadID,
			AgentName: agentName,
			AgentType: "flux-drive-reviewer",
			Model:     verdict.Model,
			Status:    strings.ToLower(verdict.Status),
		}
		if verdict.TokensSpent > 0 {
			rec.OutputTokens = uint64(verdict.TokensSpent)
		}
		rec.Timestamp = ts

		if err := cxdbRecordDispatch(client, ctxID, rec); err != nil {
			fmt.Fprintf(os.Stderr, "cxdb-sync-verdicts: warning: %v\n", err)
			continue
		}
		syncCount++
	}

	fmt.Fprintf(os.Stderr, "cxdb-sync-verdicts: synced %d verdicts for %s\n", syncCount, beadID)
	return nil
}

// cmdCXDBHistory outputs a JSON timeline of all turns for a sprint.
// Usage: cxdb-history <bead-id>
func cmdCXDBHistory(args []string) error {
	if len(args) < 1 {
		return fmt.Errorf("usage: cxdb-history <bead-id>")
	}
	beadID := args[0]

	if !cxdbAvailable() {
		return fmt.Errorf("cxdb-history: CXDB not available")
	}

	client, err := cxdbConnect()
	if err != nil {
		return err
	}
	defer cxdbClose()

	ctxID, err := cxdbSprintContext(client, beadID)
	if err != nil {
		return err
	}

	ctx := context.Background()
	turns, err := client.GetLast(ctx, ctxID, CXDBGetLastOptions{
		Limit:          10000,
		IncludePayload: true,
	})
	if err != nil {
		return fmt.Errorf("cxdb-history: query failed: %w", err)
	}

	type HistoryEntry struct {
		TurnID  uint64         `json:"turn_id"`
		TypeID  string         `json:"type_id"`
		Payload map[string]any `json:"payload"`
		Depth   uint32         `json:"depth"`
	}

	var entries []HistoryEntry
	for _, t := range turns {
		entry := HistoryEntry{
			TurnID: t.TurnID,
			TypeID: t.TypeID,
			Depth:  t.Depth,
		}

		// Decode msgpack payload to generic map
		var payload map[string]any
		if len(t.Payload) > 0 {
			if err := msgpack.Unmarshal(t.Payload, &payload); err != nil {
				// Fallback: store raw hex
				payload = map[string]any{"_raw": fmt.Sprintf("%x", t.Payload)}
			}
		}
		entry.Payload = payload
		entries = append(entries, entry)
	}

	enc := json.NewEncoder(os.Stdout)
	enc.SetIndent("", "  ")
	return enc.Encode(entries)
}

// cmdCXDBFork creates a branched execution trajectory.
// Usage: cxdb-fork <sprint-id> <turn-id>
func cmdCXDBFork(args []string) error {
	if len(args) < 2 {
		return fmt.Errorf("usage: cxdb-fork <sprint-id> <turn-id>")
	}

	turnID, err := strconv.ParseUint(args[1], 10, 64)
	if err != nil {
		return fmt.Errorf("invalid turn-id: %w", err)
	}

	if !cxdbAvailable() {
		return fmt.Errorf("cxdb-fork: CXDB server not running")
	}

	client, err := cxdbConnect()
	if err != nil {
		return err
	}
	defer cxdbClose()

	newCtxID, err := cxdbForkSprint(client, turnID)
	if err != nil {
		return err
	}

	fmt.Printf("%d\n", newCtxID)
	return nil
}
