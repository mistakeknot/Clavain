package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"os"
	"strconv"
	"strings"
	"time"
)

const (
	runtimeSchemaVersion = 1
	maxDiscoveryBytes    = 4 << 10
	maxResponseBytes     = 64 << 10
	maxEventIDBytes      = 512
)

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

type probeObservation struct {
	SchemaVersion    int                                `json:"schema_version"`
	ObservedNonce    string                             `json:"observed_nonce"`
	Subsystems       map[string]string                  `json:"subsystems"`
	FailureClasses   map[string]verificationObservation `json:"failure_classes"`
	ObservedEventID  string                             `json:"observed_event_id"`
	BeforeDigest     string                             `json:"before_digest"`
	AfterDigest      string                             `json:"after_digest"`
	Assertions       []assertionObservation             `json:"assertions"`
	ObservedSurfaces []string                           `json:"observed_surfaces"`
	Resources        []observedResource                 `json:"resources"`
	Collisions       []string                           `json:"collisions"`
}

func readEndpointDiscovery(path string) (endpointDiscovery, error) {
	var discovery endpointDiscovery
	info, err := os.Lstat(path)
	if err != nil {
		return discovery, fmt.Errorf("inspect endpoint file: %w", err)
	}
	if !info.Mode().IsRegular() {
		return discovery, errors.New("endpoint file must be a regular file")
	}
	if info.Size() > maxDiscoveryBytes {
		return discovery, errors.New("endpoint file exceeds size limit")
	}
	file, err := os.Open(path)
	if err != nil {
		return discovery, fmt.Errorf("open endpoint file: %w", err)
	}
	defer file.Close()
	payload, err := io.ReadAll(io.LimitReader(file, maxDiscoveryBytes+1))
	if err != nil {
		return discovery, fmt.Errorf("read endpoint file: %w", err)
	}
	if len(payload) > maxDiscoveryBytes {
		return discovery, errors.New("endpoint file exceeds size limit")
	}
	if err := decodeStrictJSON(payload, &discovery); err != nil {
		return discovery, fmt.Errorf("decode endpoint file: %w", err)
	}
	if discovery.SchemaVersion != runtimeSchemaVersion {
		return discovery, fmt.Errorf("unsupported endpoint schema version %d", discovery.SchemaVersion)
	}
	parsed, err := validateLoopbackEndpoint(discovery.Endpoint)
	if err != nil {
		return discovery, err
	}
	if len(discovery.Resources) != 1 || discovery.Resources[0].Kind != "port" || discovery.Resources[0].Identifier != parsed.Host {
		return discovery, errors.New("endpoint discovery must name its loopback port resource")
	}
	return discovery, nil
}

func validateLoopbackEndpoint(raw string) (*url.URL, error) {
	parsed, err := url.Parse(raw)
	if err != nil {
		return nil, fmt.Errorf("parse endpoint: %w", err)
	}
	if parsed.Scheme != "http" || parsed.User != nil || parsed.RawQuery != "" || parsed.Fragment != "" || (parsed.Path != "" && parsed.Path != "/") {
		return nil, errors.New("endpoint must be an unadorned HTTP loopback URL")
	}
	host, portText, err := net.SplitHostPort(parsed.Host)
	if err != nil {
		return nil, fmt.Errorf("endpoint host must include a port: %w", err)
	}
	ip := net.ParseIP(host)
	if ip == nil || !ip.IsLoopback() {
		return nil, errors.New("endpoint host must be a loopback IP")
	}
	port, err := strconv.Atoi(portText)
	if err != nil || port < 1 || port > 65535 {
		return nil, errors.New("endpoint port is invalid")
	}
	return parsed, nil
}

func collectObservations(ctx context.Context, client *http.Client, discovery endpointDiscovery, eventID string) (probeObservation, error) {
	var observation probeObservation
	if eventID == "" || len(eventID) > maxEventIDBytes {
		return observation, errors.New("event ID must be non-empty and bounded")
	}
	baseURL := strings.TrimRight(discovery.Endpoint, "/")
	var health healthObservation
	if err := requestJSON(ctx, client, http.MethodGet, baseURL+"/diag/health", nil, &health); err != nil {
		return observation, fmt.Errorf("health probe: %w", err)
	}
	if health.SchemaVersion != runtimeSchemaVersion {
		return observation, fmt.Errorf("unsupported health schema version %d", health.SchemaVersion)
	}
	var smoke smokeObservation
	if err := requestJSON(ctx, client, http.MethodPost, baseURL+"/diag/smoke-test", smokeRequest{EventID: eventID}, &smoke); err != nil {
		return observation, fmt.Errorf("smoke probe: %w", err)
	}
	if smoke.SchemaVersion != runtimeSchemaVersion {
		return observation, fmt.Errorf("unsupported smoke schema version %d", smoke.SchemaVersion)
	}
	return probeObservation{
		SchemaVersion:    runtimeSchemaVersion,
		ObservedNonce:    health.ObservedNonce,
		Subsystems:       health.Subsystems,
		FailureClasses:   health.FailureClasses,
		ObservedEventID:  smoke.ObservedEventID,
		BeforeDigest:     smoke.BeforeDigest,
		AfterDigest:      smoke.AfterDigest,
		Assertions:       smoke.Assertions,
		ObservedSurfaces: health.Surfaces,
		Resources:        health.Resources,
		Collisions:       health.Collisions,
	}, nil
}

func requestJSON(ctx context.Context, client *http.Client, method, endpoint string, requestBody any, responseBody any) error {
	var body io.Reader
	if requestBody != nil {
		payload, err := json.Marshal(requestBody)
		if err != nil {
			return err
		}
		body = bytes.NewReader(payload)
	}
	request, err := http.NewRequestWithContext(ctx, method, endpoint, body)
	if err != nil {
		return err
	}
	request.Header.Set("Accept", "application/json")
	if requestBody != nil {
		request.Header.Set("Content-Type", "application/json")
	}
	response, err := client.Do(request)
	if err != nil {
		return err
	}
	defer response.Body.Close()
	payload, err := io.ReadAll(io.LimitReader(response.Body, maxResponseBytes+1))
	if err != nil {
		return err
	}
	if len(payload) > maxResponseBytes {
		return errors.New("response exceeds size limit")
	}
	if response.StatusCode != http.StatusOK {
		return fmt.Errorf("server returned HTTP %d", response.StatusCode)
	}
	if err := decodeStrictJSON(payload, responseBody); err != nil {
		return fmt.Errorf("decode response: %w", err)
	}
	return nil
}

func decodeStrictJSON(payload []byte, target any) error {
	decoder := json.NewDecoder(bytes.NewReader(payload))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		return err
	}
	var extra any
	if err := decoder.Decode(&extra); !errors.Is(err, io.EOF) {
		if err == nil {
			return errors.New("multiple JSON values")
		}
		return err
	}
	return nil
}

func run(args []string, stdout io.Writer) error {
	flags := flag.NewFlagSet("runtimeprobe", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	endpointFile := flags.String("endpoint-file", "", "path to endpoint discovery JSON")
	if err := flags.Parse(args); err != nil {
		return err
	}
	if flags.NArg() != 0 {
		return errors.New("runtimeprobe accepts no positional arguments")
	}
	if *endpointFile == "" {
		*endpointFile = os.Getenv("CLAVAIN_RUNTIME_ENDPOINT_FILE")
	}
	if *endpointFile == "" {
		return errors.New("endpoint file is required")
	}
	eventID := os.Getenv("CLAVAIN_RUNTIME_EVENT_ID")
	discovery, err := readEndpointDiscovery(*endpointFile)
	if err != nil {
		return err
	}
	client := &http.Client{
		Timeout: 2 * time.Second,
		CheckRedirect: func(_ *http.Request, _ []*http.Request) error {
			return http.ErrUseLastResponse
		},
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	observation, err := collectObservations(ctx, client, discovery, eventID)
	if err != nil {
		return err
	}
	encoder := json.NewEncoder(stdout)
	encoder.SetEscapeHTML(false)
	return encoder.Encode(observation)
}

func main() {
	if err := run(os.Args[1:], os.Stdout); err != nil {
		fmt.Fprintf(os.Stderr, "runtimeprobe: %v\n", err)
		os.Exit(1)
	}
}
