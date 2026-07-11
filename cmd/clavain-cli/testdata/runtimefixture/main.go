package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"sync"
	"syscall"
	"time"
)

const (
	runtimeSchemaVersion = 1
	maxRequestBytes      = 4 << 10
	maxEventIDBytes      = 512
)

var errDuplicateEvent = errors.New("event already applied")

type observedResource struct {
	Kind       string `json:"kind"`
	Identifier string `json:"identifier"`
}

type endpointDiscovery struct {
	SchemaVersion int                `json:"schema_version"`
	Endpoint      string             `json:"endpoint"`
	Resources     []observedResource `json:"resources"`
}

type verificationObservation struct {
	State    string `json:"state"`
	Evidence string `json:"evidence"`
}

type healthObservation struct {
	SchemaVersion  int                                `json:"schema_version"`
	ObservedNonce  string                             `json:"observed_nonce"`
	Subsystems     map[string]string                  `json:"subsystems"`
	FailureClasses map[string]verificationObservation `json:"failure_classes"`
	Surfaces       []string                           `json:"surfaces"`
	Resources      []observedResource                 `json:"resources"`
	Collisions     []string                           `json:"collisions"`
}

type smokeRequest struct {
	EventID string `json:"event_id"`
}

type assertionObservation struct {
	Name     string `json:"name"`
	State    string `json:"state"`
	Evidence string `json:"evidence"`
}

type smokeObservation struct {
	SchemaVersion   int                    `json:"schema_version"`
	ObservedEventID string                 `json:"observed_event_id"`
	BeforeDigest    string                 `json:"before_digest"`
	AfterDigest     string                 `json:"after_digest"`
	Assertions      []assertionObservation `json:"assertions"`
}

type fixtureState struct {
	mu     sync.Mutex
	events []string
	seen   map[string]struct{}
}

func newFixtureState() *fixtureState {
	return &fixtureState{seen: make(map[string]struct{})}
}

func (s *fixtureState) applyEvent(eventID string) (string, string, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if _, exists := s.seen[eventID]; exists {
		return "", "", errDuplicateEvent
	}
	before, err := digestEvents(s.events)
	if err != nil {
		return "", "", err
	}
	s.events = append(s.events, eventID)
	s.seen[eventID] = struct{}{}
	after, err := digestEvents(s.events)
	if err != nil {
		return "", "", err
	}
	return before, after, nil
}

func digestEvents(events []string) (string, error) {
	payload, err := json.Marshal(struct {
		Events []string `json:"events"`
	}{Events: events})
	if err != nil {
		return "", err
	}
	digest := sha256.Sum256(payload)
	return "sha256:" + hex.EncodeToString(digest[:]), nil
}

func newHandler(nonce string, resources []observedResource, state *fixtureState) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/diag/health", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			w.Header().Set("Allow", http.MethodGet)
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		writeJSON(w, http.StatusOK, healthObservation{
			SchemaVersion: runtimeSchemaVersion,
			ObservedNonce: nonce,
			Subsystems:    map[string]string{"store": "healthy"},
			FailureClasses: map[string]verificationObservation{
				"startup": {
					State:    "VERIFIED",
					Evidence: "fixture HTTP server accepted the health probe",
				},
				"dependency_injection": {
					State:    "NOT_APPLICABLE",
					Evidence: "fixture has no injected dependencies",
				},
				"connection": {
					State:    "VERIFIED",
					Evidence: "fixture accepted a loopback connection",
				},
				"projection_catchup": {
					State:    "NOT_APPLICABLE",
					Evidence: "fixture has no asynchronous projection",
				},
			},
			Surfaces:   []string{"diag/health", "diag/smoke-test"},
			Resources:  resources,
			Collisions: []string{},
		})
	})

	mux.HandleFunc("/diag/smoke-test", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			w.Header().Set("Allow", http.MethodPost)
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		request, err := decodeSmokeRequest(w, r)
		if err != nil {
			http.Error(w, "invalid smoke-test request", http.StatusBadRequest)
			return
		}
		before, after, err := state.applyEvent(request.EventID)
		if errors.Is(err, errDuplicateEvent) {
			http.Error(w, "event already applied", http.StatusConflict)
			return
		}
		if err != nil {
			http.Error(w, "failed to apply event", http.StatusInternalServerError)
			return
		}
		writeJSON(w, http.StatusOK, smokeObservation{
			SchemaVersion:   runtimeSchemaVersion,
			ObservedEventID: request.EventID,
			BeforeDigest:    before,
			AfterDigest:     after,
			Assertions: []assertionObservation{{
				Name:     "state-delta",
				State:    "VERIFIED",
				Evidence: "unique event was committed to the isolated in-memory store",
			}},
		})
	})
	return mux
}

func decodeSmokeRequest(w http.ResponseWriter, r *http.Request) (smokeRequest, error) {
	var request smokeRequest
	r.Body = http.MaxBytesReader(w, r.Body, maxRequestBytes)
	decoder := json.NewDecoder(r.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&request); err != nil {
		return request, err
	}
	if err := ensureJSONEOF(decoder); err != nil {
		return request, err
	}
	if request.EventID == "" || len(request.EventID) > maxEventIDBytes {
		return request, errors.New("event_id must be non-empty and bounded")
	}
	return request, nil
}

func ensureJSONEOF(decoder *json.Decoder) error {
	var extra any
	if err := decoder.Decode(&extra); !errors.Is(err, io.EOF) {
		if err == nil {
			return errors.New("multiple JSON values")
		}
		return err
	}
	return nil
}

func writeJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}

func writeEndpointFile(path string, discovery endpointDiscovery) error {
	return writeEndpointFileBeforePublish(path, discovery, nil)
}

func writeEndpointFileBeforePublish(path string, discovery endpointDiscovery, beforePublish func()) error {
	payload, err := json.Marshal(discovery)
	if err != nil {
		return err
	}
	payload = append(payload, '\n')

	directory := filepath.Dir(path)
	base := filepath.Base(path)
	file, err := os.CreateTemp(directory, "."+base+".tmp-*")
	if err != nil {
		return fmt.Errorf("create endpoint staging file: %w", err)
	}
	stagingPath := file.Name()
	open := true
	defer func() {
		if open {
			_ = file.Close()
		}
		_ = os.Remove(stagingPath)
	}()
	if err := file.Chmod(0o600); err != nil {
		return err
	}
	written, err := file.Write(payload)
	if err != nil {
		return err
	}
	if written != len(payload) {
		return io.ErrShortWrite
	}
	if err := file.Sync(); err != nil {
		return err
	}
	if err := file.Close(); err != nil {
		return err
	}
	open = false
	if beforePublish != nil {
		beforePublish()
	}
	if err := os.Link(stagingPath, path); err != nil {
		return fmt.Errorf("publish fresh endpoint file: %w", err)
	}
	return nil
}

func run(args []string) error {
	flags := flag.NewFlagSet("runtimefixture", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	endpointFile := flags.String("endpoint-file", "", "path for endpoint discovery JSON")
	if err := flags.Parse(args); err != nil {
		return err
	}
	if flags.NArg() != 0 {
		return errors.New("runtimefixture accepts no positional arguments")
	}
	if *endpointFile == "" {
		*endpointFile = os.Getenv("CLAVAIN_RUNTIME_ENDPOINT_FILE")
	}
	if *endpointFile == "" {
		return errors.New("endpoint file is required")
	}
	nonce := os.Getenv("CLAVAIN_RUNTIME_INSTANCE_NONCE")
	if nonce == "" || len(nonce) > maxEventIDBytes {
		return errors.New("CLAVAIN_RUNTIME_INSTANCE_NONCE must be non-empty and bounded")
	}

	listener, err := net.Listen("tcp4", "127.0.0.1:0")
	if err != nil {
		return fmt.Errorf("listen on loopback: %w", err)
	}
	address := listener.Addr().String()
	resources := []observedResource{{Kind: "port", Identifier: address}}
	discovery := endpointDiscovery{
		SchemaVersion: runtimeSchemaVersion,
		Endpoint:      "http://" + address,
		Resources:     resources,
	}
	if err := writeEndpointFile(*endpointFile, discovery); err != nil {
		_ = listener.Close()
		return err
	}

	server := &http.Server{
		Handler:           newHandler(nonce, resources, newFixtureState()),
		ReadHeaderTimeout: time.Second,
		ReadTimeout:       2 * time.Second,
		WriteTimeout:      2 * time.Second,
		IdleTimeout:       5 * time.Second,
		MaxHeaderBytes:    8 << 10,
	}
	serveErrors := make(chan error, 1)
	go func() {
		serveErrors <- server.Serve(listener)
	}()

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	var serveErr error
	select {
	case serveErr = <-serveErrors:
	case <-ctx.Done():
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
		shutdownErr := server.Shutdown(shutdownCtx)
		cancel()
		serveErr = <-serveErrors
		if shutdownErr != nil {
			serveErr = errors.Join(serveErr, shutdownErr)
		}
	}
	removeErr := os.Remove(*endpointFile)
	if removeErr != nil && !errors.Is(removeErr, os.ErrNotExist) {
		serveErr = errors.Join(serveErr, fmt.Errorf("remove endpoint file: %w", removeErr))
	}
	if serveErr != nil && !errors.Is(serveErr, http.ErrServerClosed) {
		return serveErr
	}
	return nil
}

func main() {
	if err := run(os.Args[1:]); err != nil {
		fmt.Fprintf(os.Stderr, "runtimefixture: %v\n", err)
		os.Exit(1)
	}
}
