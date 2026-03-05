package main

import (
	"testing"

	"github.com/vmihailenco/msgpack/v5"
)

func TestPhaseRecordMsgpack(t *testing.T) {
	rec := PhaseRecord{
		BeadID:        "iv-abc123",
		Phase:         "executing",
		PreviousPhase: "plan-reviewed",
		ArtifactPath:  "docs/plans/test.md",
		Timestamp:     1709654400,
	}

	data, err := msgpack.Marshal(rec)
	if err != nil {
		t.Fatalf("marshal PhaseRecord: %v", err)
	}

	var decoded PhaseRecord
	if err := msgpack.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("unmarshal PhaseRecord: %v", err)
	}

	if decoded.BeadID != rec.BeadID {
		t.Errorf("BeadID: got %q, want %q", decoded.BeadID, rec.BeadID)
	}
	if decoded.Phase != rec.Phase {
		t.Errorf("Phase: got %q, want %q", decoded.Phase, rec.Phase)
	}
	if decoded.PreviousPhase != rec.PreviousPhase {
		t.Errorf("PreviousPhase: got %q, want %q", decoded.PreviousPhase, rec.PreviousPhase)
	}
	if decoded.ArtifactPath != rec.ArtifactPath {
		t.Errorf("ArtifactPath: got %q, want %q", decoded.ArtifactPath, rec.ArtifactPath)
	}
	if decoded.Timestamp != rec.Timestamp {
		t.Errorf("Timestamp: got %d, want %d", decoded.Timestamp, rec.Timestamp)
	}
}

func TestDispatchRecordMsgpack(t *testing.T) {
	rec := DispatchRecord{
		BeadID:       "iv-xyz789",
		AgentName:    "fd-architecture",
		AgentType:    "review",
		Model:        "claude-opus-4-6",
		Status:       "completed",
		InputTokens:  50000,
		OutputTokens: 12000,
		Timestamp:    1709654500,
	}

	data, err := msgpack.Marshal(rec)
	if err != nil {
		t.Fatalf("marshal DispatchRecord: %v", err)
	}

	var decoded DispatchRecord
	if err := msgpack.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("unmarshal DispatchRecord: %v", err)
	}

	if decoded.AgentName != rec.AgentName {
		t.Errorf("AgentName: got %q, want %q", decoded.AgentName, rec.AgentName)
	}
	if decoded.InputTokens != rec.InputTokens {
		t.Errorf("InputTokens: got %d, want %d", decoded.InputTokens, rec.InputTokens)
	}
	if decoded.OutputTokens != rec.OutputTokens {
		t.Errorf("OutputTokens: got %d, want %d", decoded.OutputTokens, rec.OutputTokens)
	}
}

func TestArtifactRecordMsgpack(t *testing.T) {
	rec := ArtifactRecord{
		BeadID:       "iv-art456",
		ArtifactType: "plan",
		Path:         "docs/plans/test.md",
		BlobHash:     []byte{0xde, 0xad, 0xbe, 0xef},
		SizeBytes:    4096,
		Timestamp:    1709654600,
	}

	data, err := msgpack.Marshal(rec)
	if err != nil {
		t.Fatalf("marshal ArtifactRecord: %v", err)
	}

	var decoded ArtifactRecord
	if err := msgpack.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("unmarshal ArtifactRecord: %v", err)
	}

	if decoded.ArtifactType != rec.ArtifactType {
		t.Errorf("ArtifactType: got %q, want %q", decoded.ArtifactType, rec.ArtifactType)
	}
	if decoded.SizeBytes != rec.SizeBytes {
		t.Errorf("SizeBytes: got %d, want %d", decoded.SizeBytes, rec.SizeBytes)
	}
	if string(decoded.BlobHash) != string(rec.BlobHash) {
		t.Errorf("BlobHash mismatch")
	}
}

func TestMsgpackNumericTags(t *testing.T) {
	// Verify that numeric msgpack tags produce string-keyed encoding
	// matching CXDB's expected format
	rec := PhaseRecord{
		BeadID: "test",
		Phase:  "executing",
	}

	data, err := msgpack.Marshal(rec)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}

	// Decode as generic map — vmihailenco/msgpack uses string tag values as keys
	var raw map[string]interface{}
	if err := msgpack.Unmarshal(data, &raw); err != nil {
		t.Fatalf("unmarshal to map[string]: %v", err)
	}

	// Tag "1" = BeadID, Tag "2" = Phase
	if raw["1"] != "test" {
		t.Errorf("tag '1' (BeadID): got %v, want 'test'", raw["1"])
	}
	if raw["2"] != "executing" {
		t.Errorf("tag '2' (Phase): got %v, want 'executing'", raw["2"])
	}
}

func TestCXDBConnectNoServer(t *testing.T) {
	// With no server, cxdbConnect should fail
	// Reset singleton
	oldClient := cxdbClient
	cxdbClient = nil
	defer func() { cxdbClient = oldClient }()

	_, err := cxdbConnect()
	if err == nil {
		t.Error("expected error connecting to non-existent server")
	}
}

func TestCXDBRecordPhaseTransitionNoServer(t *testing.T) {
	// Should silently return when CXDB is not available
	tmpDir := t.TempDir()
	t.Setenv("SPRINT_LIB_PROJECT_DIR", tmpDir)

	// This should not panic or return an error
	cxdbRecordPhaseTransition("iv-test", "executing", "test.md")
}
