package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestCollectObservationsReturnsOnlyObservedState(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch r.URL.Path {
		case "/diag/health":
			_, _ = w.Write([]byte(`{"schema_version":1,"observed_nonce":"nonce-123","subsystems":{"store":"healthy"},"failure_classes":{"startup":{"state":"VERIFIED","evidence":"started"},"dependency_injection":{"state":"NOT_APPLICABLE","evidence":"no injected dependencies"},"connection":{"state":"VERIFIED","evidence":"loopback request accepted"},"projection_catchup":{"state":"NOT_APPLICABLE","evidence":"no projection"}},"surfaces":["diag/health","diag/smoke-test"],"resources":[{"kind":"port","identifier":"127.0.0.1:43210"}],"collisions":[]}`))
		case "/diag/smoke-test":
			var request smokeRequest
			if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
				t.Fatal(err)
			}
			if request.EventID != "event-123" {
				t.Fatalf("event ID = %q", request.EventID)
			}
			_, _ = w.Write([]byte(`{"schema_version":1,"observed_event_id":"event-123","before_digest":"sha256:before","after_digest":"sha256:after","assertions":[{"name":"state-delta","state":"VERIFIED","evidence":"event applied"}]}`))
		default:
			http.NotFound(w, r)
		}
	}))
	defer server.Close()

	discovery := endpointDiscovery{SchemaVersion: 1, Endpoint: server.URL}
	client := &http.Client{Timeout: time.Second}
	observation, err := collectObservations(context.Background(), client, discovery, "event-123")
	if err != nil {
		t.Fatalf("collectObservations: %v", err)
	}
	if observation.ObservedNonce != "nonce-123" || observation.ObservedEventID != "event-123" {
		t.Fatalf("identity observations = %#v", observation)
	}
	if observation.Subsystems["store"] != "healthy" || len(observation.Resources) != 1 {
		t.Fatalf("health observations = %#v", observation)
	}

	encoded, err := json.Marshal(observation)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(encoded), `"observed_surfaces"`) {
		t.Fatalf("probe output omitted observed_surfaces: %s", encoded)
	}
	for _, forbidden := range []string{"expected", "ownership", "build_digest", "installed_digest", "runtime_digest"} {
		if strings.Contains(string(encoded), forbidden) {
			t.Fatalf("probe output contains collector-owned field %q: %s", forbidden, encoded)
		}
	}
}

func TestReadEndpointDiscoveryRejectsNonLoopbackEndpoint(t *testing.T) {
	path := filepath.Join(t.TempDir(), "endpoint.json")
	if err := os.WriteFile(path, []byte(`{"schema_version":1,"endpoint":"http://example.com:80","resources":[]}`), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := readEndpointDiscovery(path); err == nil {
		t.Fatal("non-loopback endpoint unexpectedly accepted")
	}
}
