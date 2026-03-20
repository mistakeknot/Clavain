// Copyright 2025 StrongDM Inc
// SPDX-License-Identifier: Apache-2.0

// Package types defines canonical conversation types for ai-cxdb visualization.
package types

import (
	"os"
	"os/user"
	"runtime"
	"time"

	"github.com/google/uuid"
)

// Provenance captures the origin story of a context.
// Immutable once captured - tells you "where did this context come from?"
//
// This follows OpenTelemetry semantic conventions for attribute naming,
// adapted to snake_case for JSON consistency.
type Provenance struct {
	// === Context Lineage ===
	// How this context relates to others

	// ParentContextID is the context that spawned this one (if any).
	ParentContextID *uint64 `msgpack:"1" json:"parent_context_id,omitempty"`

	// SpawnReason explains why this context was created from a parent.
	// Values: "fork" (branch from turn), "quest" (background task), "delegation", "sub_agent"
	SpawnReason string `msgpack:"2" json:"spawn_reason,omitempty"`

	// RootContextID is the ultimate ancestor context (may equal ParentContextID).
	RootContextID *uint64 `msgpack:"3" json:"root_context_id,omitempty"`

	// === Request Identity (per-interaction) ===
	// Which specific request/interaction created this context

	// TraceID is the W3C trace-id (32 hex chars) for distributed tracing.
	TraceID string `msgpack:"10" json:"trace_id,omitempty"`

	// SpanID is the W3C parent-id (16 hex chars) for distributed tracing.
	SpanID string `msgpack:"11" json:"span_id,omitempty"`

	// CorrelationID is a custom correlation identifier for request tracking.
	CorrelationID string `msgpack:"12" json:"correlation_id,omitempty"`

	// === User Identity (on whose behalf) ===
	// Who is this context serving - the end user

	// OnBehalfOf is the user ID this context is serving.
	OnBehalfOf string `msgpack:"20" json:"on_behalf_of,omitempty"`

	// OnBehalfOfSource is where the user request originated.
	// Values: "slack", "web", "api", "telegram", "sms", "email", "cli", "quest"
	OnBehalfOfSource string `msgpack:"21" json:"on_behalf_of_source,omitempty"`

	// OnBehalfOfEmail is the user's email address (if known).
	OnBehalfOfEmail string `msgpack:"22" json:"on_behalf_of_email,omitempty"`

	// === Writer Identity (authenticated caller) ===
	// Who is writing to CXDB (may differ from "on behalf of")

	// WriterMethod is the authentication method used.
	// Values: "k8s_oidc", "aws_sts", "api_key", "none"
	WriterMethod string `msgpack:"30" json:"writer_method,omitempty"`

	// WriterSubject is the authenticated principal identifier.
	// E.g., "system:serviceaccount:default:my-service" or ARN
	WriterSubject string `msgpack:"31" json:"writer_subject,omitempty"`

	// WriterIssuer is the token issuer URL.
	WriterIssuer string `msgpack:"32" json:"writer_issuer,omitempty"`

	// === Process Identity (compute instance) ===
	// Which running process created this context

	// ServiceName is the logical service name (e.g., "ai-assistant").
	ServiceName string `msgpack:"40" json:"service_name,omitempty"`

	// ServiceVersion is the service version string.
	ServiceVersion string `msgpack:"41" json:"service_version,omitempty"`

	// ServiceInstanceID is a UUID identifying this specific instance.
	// Survives reconnects - identifies a running process.
	ServiceInstanceID string `msgpack:"42" json:"service_instance_id,omitempty"`

	// ProcessPID is the OS process ID.
	ProcessPID int `msgpack:"43" json:"process_pid,omitempty"`

	// ProcessOwner is the OS user running the process.
	ProcessOwner string `msgpack:"44" json:"process_owner,omitempty"`

	// HostName is the machine hostname.
	HostName string `msgpack:"45" json:"host_name,omitempty"`

	// HostArch is the CPU architecture (e.g., "amd64", "arm64").
	HostArch string `msgpack:"46" json:"host_arch,omitempty"`

	// === Network Identity (server-observed) ===
	// What the server sees - injected server-side

	// ClientAddress is the apparent client IP address (set by server).
	ClientAddress string `msgpack:"50" json:"client_address,omitempty"`

	// ClientPort is the client's source port (set by server).
	ClientPort int `msgpack:"51" json:"client_port,omitempty"`

	// === Environment Context ===

	// EnvVars contains selected environment variables (from allowlist).
	EnvVars map[string]string `msgpack:"60" json:"env,omitempty"`

	// === SDK Identity ===

	// SDKName identifies the client SDK (e.g., "ai-agents-sdk", "cxdb-go").
	SDKName string `msgpack:"70" json:"sdk_name,omitempty"`

	// SDKVersion is the SDK version string.
	SDKVersion string `msgpack:"71" json:"sdk_version,omitempty"`

	// === Timestamps ===

	// CapturedAt is when this provenance was captured (Unix milliseconds).
	CapturedAt int64 `msgpack:"80" json:"captured_at,omitempty"`
}

// DefaultEnvAllowlist contains environment variables that are generally safe
// and useful to capture for debugging and tracing purposes.
var DefaultEnvAllowlist = []string{
	// Kubernetes
	"K8S_NAMESPACE",
	"K8S_POD_NAME",
	"K8S_NODE_NAME",
	"KUBERNETES_SERVICE_HOST",

	// AWS
	"AWS_REGION",
	"AWS_DEFAULT_REGION",
	"AWS_EXECUTION_ENV",

	// GCP
	"GOOGLE_CLOUD_PROJECT",
	"GCP_PROJECT",

	// Deployment/environment indicators
	"DEPLOYMENT",
	"ENVIRONMENT",
	"ENV",
	"STAGE",
	"REGION",

	// Host identification
	"HOSTNAME",
	"USER",
	"HOME",

	// Runtime
	"GOVERSION",
	"GO_VERSION",

	// Common service identifiers
	"SERVICE_NAME",
	"SERVICE_VERSION",
	"APP_NAME",
	"APP_VERSION",
}

// ProvenanceOption configures provenance capture.
type ProvenanceOption func(*Provenance)

// CaptureProcessProvenance creates a Provenance populated with process-level
// information. Call this once at startup and reuse for all contexts.
//
// The returned Provenance includes:
//   - ServiceInstanceID: a new UUID for this process instance
//   - ProcessPID: current process ID
//   - ProcessOwner: current user
//   - HostName: machine hostname
//   - HostArch: CPU architecture
//   - CapturedAt: current timestamp
func CaptureProcessProvenance(serviceName, serviceVersion string, opts ...ProvenanceOption) *Provenance {
	p := &Provenance{
		ServiceName:       serviceName,
		ServiceVersion:    serviceVersion,
		ServiceInstanceID: uuid.New().String(),
		ProcessPID:        os.Getpid(),
		ProcessOwner:      getCurrentUser(),
		HostName:          getHostname(),
		HostArch:          runtime.GOARCH,
		CapturedAt:        time.Now().UnixMilli(),
	}

	for _, opt := range opts {
		opt(p)
	}

	return p
}

// NewProvenance creates a new Provenance by cloning base process provenance
// and applying additional options for this specific context.
func NewProvenance(base *Provenance, opts ...ProvenanceOption) *Provenance {
	p := &Provenance{}
	if base != nil {
		*p = *base // shallow copy
		// Deep copy the map
		if base.EnvVars != nil {
			p.EnvVars = make(map[string]string, len(base.EnvVars))
			for k, v := range base.EnvVars {
				p.EnvVars[k] = v
			}
		}
	}

	// Update timestamp for this specific capture
	p.CapturedAt = time.Now().UnixMilli()

	for _, opt := range opts {
		opt(p)
	}

	return p
}

// WithParentContext sets the parent and root context IDs.
// If rootID is 0, it defaults to parentID.
func WithParentContext(parentID, rootID uint64) ProvenanceOption {
	return func(p *Provenance) {
		p.ParentContextID = &parentID
		if rootID == 0 {
			p.RootContextID = &parentID
		} else {
			p.RootContextID = &rootID
		}
	}
}

// WithSpawnReason sets the reason this context was spawned.
func WithSpawnReason(reason string) ProvenanceOption {
	return func(p *Provenance) {
		p.SpawnReason = reason
	}
}

// WithTraceContext sets W3C trace context fields.
func WithTraceContext(traceID, spanID string) ProvenanceOption {
	return func(p *Provenance) {
		p.TraceID = traceID
		p.SpanID = spanID
	}
}

// WithCorrelationID sets a custom correlation identifier.
func WithCorrelationID(id string) ProvenanceOption {
	return func(p *Provenance) {
		p.CorrelationID = id
	}
}

// WithOnBehalfOf sets the user identity this context serves.
func WithOnBehalfOf(userID, source, email string) ProvenanceOption {
	return func(p *Provenance) {
		p.OnBehalfOf = userID
		p.OnBehalfOfSource = source
		p.OnBehalfOfEmail = email
	}
}

// WithWriterIdentity sets the authenticated writer identity.
func WithWriterIdentity(method, subject, issuer string) ProvenanceOption {
	return func(p *Provenance) {
		p.WriterMethod = method
		p.WriterSubject = subject
		p.WriterIssuer = issuer
	}
}

// WithEnvVars captures environment variables from the given allowlist.
// Pass nil to use DefaultEnvAllowlist.
func WithEnvVars(allowlist []string) ProvenanceOption {
	return func(p *Provenance) {
		if allowlist == nil {
			allowlist = DefaultEnvAllowlist
		}
		p.EnvVars = captureEnvVars(allowlist)
	}
}

// WithSDK sets the SDK name and version.
func WithSDK(name, version string) ProvenanceOption {
	return func(p *Provenance) {
		p.SDKName = name
		p.SDKVersion = version
	}
}

// WithService sets service identification fields.
func WithService(name, version, instanceID string) ProvenanceOption {
	return func(p *Provenance) {
		p.ServiceName = name
		p.ServiceVersion = version
		if instanceID != "" {
			p.ServiceInstanceID = instanceID
		}
	}
}

// captureEnvVars reads environment variables from the allowlist.
func captureEnvVars(allowlist []string) map[string]string {
	vars := make(map[string]string)
	for _, key := range allowlist {
		if val := os.Getenv(key); val != "" {
			vars[key] = val
		}
	}
	if len(vars) == 0 {
		return nil
	}
	return vars
}

// getCurrentUser returns the current OS username, or empty string on error.
func getCurrentUser() string {
	u, err := user.Current()
	if err != nil {
		return ""
	}
	return u.Username
}

// getHostname returns the machine hostname, or empty string on error.
func getHostname() string {
	h, err := os.Hostname()
	if err != nil {
		return ""
	}
	return h
}
