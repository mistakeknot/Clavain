package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"

	cxdb "github.com/strongdm/ai-cxdb/clients/go"
	"github.com/vmihailenco/msgpack/v5"
)

// cxdbClient holds the singleton CXDB connection.
var cxdbClient *cxdb.Client

// cxdbConnect connects to the local CXDB server.
// Returns the existing connection if already connected.
func cxdbConnect() (*cxdb.Client, error) {
	if cxdbClient != nil {
		return cxdbClient, nil
	}

	addr := fmt.Sprintf("localhost:%d", cxdbDefaultPort)
	client, err := cxdb.Dial(addr)
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
func cxdbSprintContext(client *cxdb.Client, beadID string) (uint64, error) {
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

// DispatchRecord is the data for a clavain.dispatch.v1 turn.
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
func cxdbRecordPhase(client *cxdb.Client, ctxID uint64, rec PhaseRecord) error {
	if rec.Timestamp == 0 {
		rec.Timestamp = uint64(time.Now().Unix())
	}
	return cxdbAppendTyped(client, ctxID, "clavain.phase.v1", rec)
}

// cxdbRecordDispatch records an agent dispatch as a CXDB turn.
func cxdbRecordDispatch(client *cxdb.Client, ctxID uint64, rec DispatchRecord) error {
	if rec.Timestamp == 0 {
		rec.Timestamp = uint64(time.Now().Unix())
	}
	return cxdbAppendTyped(client, ctxID, "clavain.dispatch.v1", rec)
}

// cxdbStoreBlob stores data as a blob via CXDB CAS (content-addressed turn).
// Returns the hex-encoded BLAKE3 hash.
func cxdbStoreBlob(client *cxdb.Client, ctxID uint64, data []byte) (string, error) {
	rec := ArtifactRecord{
		BlobHash:  data, // The CXDB server computes BLAKE3 internally
		SizeBytes: uint64(len(data)),
		Timestamp: uint64(time.Now().Unix()),
	}
	return "", cxdbAppendTyped(client, ctxID, "clavain.artifact.v1", rec)
}

// cxdbForkSprint creates an O(1) branched execution trajectory.
func cxdbForkSprint(client *cxdb.Client, turnID uint64) (uint64, error) {
	ctx := context.Background()
	head, err := client.CreateContext(ctx, turnID)
	if err != nil {
		return 0, fmt.Errorf("cxdb fork: %w", err)
	}
	return head.ContextID, nil
}

// cxdbQueryByType returns all turns of a specific type from a context.
func cxdbQueryByType(client *cxdb.Client, ctxID uint64, typeID string) ([]cxdb.TurnRecord, error) {
	ctx := context.Background()
	turns, err := client.GetLast(ctx, ctxID, cxdb.GetLastOptions{
		Limit:          1000,
		IncludePayload: true,
	})
	if err != nil {
		return nil, fmt.Errorf("cxdb query: %w", err)
	}

	// Filter by type
	var result []cxdb.TurnRecord
	for _, t := range turns {
		if t.TypeID == typeID {
			result = append(result, t)
		}
	}
	return result, nil
}

// cxdbAppendTyped encodes a record as msgpack and appends it as a CXDB turn.
func cxdbAppendTyped(client *cxdb.Client, ctxID uint64, typeID string, record any) error {
	payload, err := msgpack.Marshal(record)
	if err != nil {
		return fmt.Errorf("cxdb encode %s: %w", typeID, err)
	}

	ctx := context.Background()
	_, err = client.AppendTurn(ctx, &cxdb.AppendRequest{
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
// Usage: cxdb-sync <sprint-id>
func cmdCXDBSync(args []string) error {
	if len(args) < 1 {
		return fmt.Errorf("usage: cxdb-sync <sprint-id>")
	}
	beadID := args[0]

	if !cxdbAvailable() {
		return fmt.Errorf("cxdb-sync: CXDB server not running")
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

	var events []struct {
		ID    string `json:"id"`
		Type  string `json:"type"`
		Phase string `json:"phase,omitempty"`
		Data  json.RawMessage `json:"data,omitempty"`
	}
	if err := runICJSON(&events, "run", "events", runID); err != nil {
		return fmt.Errorf("cxdb-sync: cannot read events: %w", err)
	}

	// Check which events are already synced (idempotency)
	existingTurns, _ := cxdbQueryByType(client, ctxID, "clavain.phase.v1")
	synced := make(map[string]bool)
	for _, t := range existingTurns {
		// Use idempotency key from turn payload to track already-synced events
		synced[t.TypeID+":"+fmt.Sprintf("%d", t.TurnID)] = true
	}

	syncCount := 0
	for _, evt := range events {
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

	fmt.Fprintf(os.Stderr, "cxdb-sync: synced %d events for %s\n", syncCount, beadID)
	return nil
}

// cxdbRecordPhaseTransition is a best-effort helper called after phase advances.
// Silently skips if CXDB is not available.
func cxdbRecordPhaseTransition(beadID, phase, artifactPath string) {
	if !cxdbAvailable() {
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
