package main

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestWriteEndpointFileIsFreshAndPrivate(t *testing.T) {
	path := filepath.Join(t.TempDir(), "endpoint.json")
	discovery := endpointDiscovery{
		SchemaVersion: 1,
		Endpoint:      "http://127.0.0.1:43210",
		Resources: []observedResource{{
			Kind:       "port",
			Identifier: "127.0.0.1:43210",
		}},
	}

	if err := writeEndpointFile(path, discovery); err != nil {
		t.Fatalf("writeEndpointFile: %v", err)
	}
	info, err := os.Stat(path)
	if err != nil {
		t.Fatal(err)
	}
	if got := info.Mode().Perm(); got != 0o600 {
		t.Fatalf("mode = %o, want 600", got)
	}
	if err := writeEndpointFile(path, discovery); err == nil {
		t.Fatal("second write unexpectedly replaced a stale endpoint file")
	}
}

func TestWriteEndpointFileIsInvisibleUntilPayloadIsComplete(t *testing.T) {
	path := filepath.Join(t.TempDir(), "endpoint.json")
	discovery := endpointDiscovery{
		SchemaVersion: 1,
		Endpoint:      "http://127.0.0.1:43210",
		Resources:     []observedResource{{Kind: "port", Identifier: "127.0.0.1:43210"}},
	}
	ready := make(chan struct{})
	release := make(chan struct{})
	done := make(chan error, 1)
	go func() {
		done <- writeEndpointFileBeforePublish(path, discovery, func() {
			close(ready)
			<-release
		})
	}()

	<-ready
	if _, err := os.Lstat(path); !os.IsNotExist(err) {
		close(release)
		t.Fatalf("endpoint was visible before atomic publication: %v", err)
	}
	close(release)
	if err := <-done; err != nil {
		t.Fatalf("publish endpoint: %v", err)
	}
	payload, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var got endpointDiscovery
	decodeJSON(t, payload, &got)
	if got.Endpoint != discovery.Endpoint || len(got.Resources) != 1 || got.Resources[0] != discovery.Resources[0] {
		t.Fatalf("published discovery = %#v", got)
	}
}

func TestHandlerReportsHealthAndAppliesUniqueEvent(t *testing.T) {
	resource := observedResource{Kind: "port", Identifier: "127.0.0.1:43210"}
	handler := newHandler("nonce-123", []observedResource{resource}, newFixtureState())

	healthRequest := httptest.NewRequest(http.MethodGet, "/diag/health", nil)
	healthResponse := httptest.NewRecorder()
	handler.ServeHTTP(healthResponse, healthRequest)
	if healthResponse.Code != http.StatusOK {
		t.Fatalf("health status = %d, body = %s", healthResponse.Code, healthResponse.Body.String())
	}
	var health healthObservation
	decodeJSON(t, healthResponse.Body.Bytes(), &health)
	if health.ObservedNonce != "nonce-123" {
		t.Fatalf("observed nonce = %q", health.ObservedNonce)
	}
	if health.Subsystems["store"] != "healthy" {
		t.Fatalf("store state = %q", health.Subsystems["store"])
	}
	for name, want := range map[string]string{
		"startup":              "VERIFIED",
		"dependency_injection": "NOT_APPLICABLE",
		"connection":           "VERIFIED",
		"projection_catchup":   "NOT_APPLICABLE",
	} {
		got, ok := health.FailureClasses[name]
		if !ok || got.State != want || got.Evidence == "" {
			t.Fatalf("failure class %q = %#v, want state %s with evidence", name, got, want)
		}
	}

	body := bytes.NewBufferString(`{"event_id":"event-123"}`)
	smokeRequest := httptest.NewRequest(http.MethodPost, "/diag/smoke-test", body)
	smokeRequest.Header.Set("Content-Type", "application/json")
	smokeResponse := httptest.NewRecorder()
	handler.ServeHTTP(smokeResponse, smokeRequest)
	if smokeResponse.Code != http.StatusOK {
		t.Fatalf("smoke status = %d, body = %s", smokeResponse.Code, smokeResponse.Body.String())
	}
	var smoke smokeObservation
	decodeJSON(t, smokeResponse.Body.Bytes(), &smoke)
	if smoke.ObservedEventID != "event-123" {
		t.Fatalf("observed event = %q", smoke.ObservedEventID)
	}
	if smoke.BeforeDigest == smoke.AfterDigest || !strings.HasPrefix(smoke.BeforeDigest, "sha256:") || !strings.HasPrefix(smoke.AfterDigest, "sha256:") {
		t.Fatalf("state digests did not prove a transition: %q -> %q", smoke.BeforeDigest, smoke.AfterDigest)
	}
	if len(smoke.Assertions) != 1 || smoke.Assertions[0].Name != "state-delta" || smoke.Assertions[0].State != "VERIFIED" || smoke.Assertions[0].Evidence == "" {
		t.Fatalf("assertions = %#v", smoke.Assertions)
	}

	duplicateRequest := httptest.NewRequest(http.MethodPost, "/diag/smoke-test", bytes.NewBufferString(`{"event_id":"event-123"}`))
	duplicateResponse := httptest.NewRecorder()
	handler.ServeHTTP(duplicateResponse, duplicateRequest)
	if duplicateResponse.Code != http.StatusConflict {
		t.Fatalf("duplicate event status = %d, want %d", duplicateResponse.Code, http.StatusConflict)
	}
}

func decodeJSON(t *testing.T, data []byte, target any) {
	t.Helper()
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		t.Fatalf("decode response: %v\n%s", err, data)
	}
}
