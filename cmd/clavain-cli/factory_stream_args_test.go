package main

import (
	"strconv"
	"strings"
	"testing"
	"time"
)

func TestParseFactoryStreamArgsDefaults(t *testing.T) {
	opts, err := parseFactoryStreamArgs(nil)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if opts.port != 8401 || opts.interval != 5*time.Second || opts.corsOrigins != "*" {
		t.Fatalf("defaults = %+v", opts)
	}
}

func TestParseFactoryStreamArgsValid(t *testing.T) {
	opts, err := parseFactoryStreamArgs([]string{
		"--port", "9000", "--interval", "250ms", "--cors-origins", "https://example.com",
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if opts.port != 9000 {
		t.Errorf("port = %d, want 9000", opts.port)
	}
	if opts.interval != 250*time.Millisecond {
		t.Errorf("interval = %s, want 250ms", opts.interval)
	}
	if opts.corsOrigins != "https://example.com" {
		t.Errorf("corsOrigins = %q", opts.corsOrigins)
	}
}

func TestParseFactoryStreamArgsPortBounds(t *testing.T) {
	for _, port := range []string{"0", "65535"} {
		opts, err := parseFactoryStreamArgs([]string{"--port", port})
		if err != nil {
			t.Fatalf("port %s: unexpected error: %v", port, err)
		}
		if strconv.Itoa(opts.port) != port {
			t.Errorf("port = %d, want %s", opts.port, port)
		}
	}
}

// A zero or negative interval used to reach time.NewTicker and panic; an
// unparsable value used to be dropped without a word.
func TestParseFactoryStreamArgsRejectsBadValues(t *testing.T) {
	cases := []struct {
		name string
		args []string
		want string
	}{
		{"zero interval", []string{"--interval", "0s"}, "greater than zero"},
		{"negative interval", []string{"--interval", "-5s"}, "greater than zero"},
		{"interval without unit", []string{"--interval", "5"}, "must be a duration"},
		{"interval missing value", []string{"--interval"}, "--interval needs a value"},
		{"port not a number", []string{"--port", "http"}, "--port must be a number"},
		{"port out of range", []string{"--port", "70000"}, "--port must be a number"},
		{"negative port", []string{"--port", "-1"}, "--port must be a number"},
		{"port missing value", []string{"--port"}, "--port needs a value"},
		{"cors missing value", []string{"--cors-origins"}, "--cors-origins needs a value"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			_, err := parseFactoryStreamArgs(tc.args)
			if err == nil {
				t.Fatalf("expected an error for %v", tc.args)
			}
			if !strings.Contains(err.Error(), tc.want) {
				t.Fatalf("error %q does not mention %q", err, tc.want)
			}
		})
	}
}

// The command must return the parse error instead of starting the server.
func TestCmdFactoryStreamReturnsParseError(t *testing.T) {
	err := cmdFactoryStream([]string{"--interval", "0s"})
	if err == nil || !strings.Contains(err.Error(), "greater than zero") {
		t.Fatalf("err = %v, want the interval error", err)
	}
}
