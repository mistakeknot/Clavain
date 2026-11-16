package main

import (
	"bytes"
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"time"

	"gopkg.in/yaml.v3"
)

// decide never applies a choice. The native answer stays with the caller.
func cmdDecide(args []string) error { return runDecide(os.Stdin, os.Stdout, args) }

func runDecide(in io.Reader, out io.Writer, args []string) error {
	fs := flag.NewFlagSet("decide", flag.ContinueOnError)
	root := fs.String("plugin-root", os.Getenv("CLAVAIN_DIR"), "Clavain installation root")
	config := fs.String("config", "", "routing.yaml path")
	project := fs.String("project-root", ".", "project root for egress and shadow records")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if fs.NArg() != 0 {
		return fmt.Errorf("decide accepts JSON on stdin")
	}
	if *root == "" {
		*root = os.Getenv("CLAUDE_PLUGIN_ROOT")
	}
	if *root == "" {
		*root = "."
	}
	if *config == "" {
		*config = filepath.Join(*root, "config", "routing.yaml")
	}
	var req struct {
		Question struct {
			ID string `json:"id"`
		} `json:"question"`
		NativeChoice string `json:"native_choice"`
	}
	raw, err := io.ReadAll(io.LimitReader(in, 90001))
	fallback := func(reason string) error {
		return json.NewEncoder(out).Encode(map[string]interface{}{"choice": req.NativeChoice, "probs": map[string]float64{}, "confidence": 0, "fallback": true, "reason": reason})
	}
	if err != nil || len(raw) > 90000 || json.Unmarshal(raw, &req) != nil {
		return fallback("invalid_input")
	}
	var routing struct {
		Decisions map[string]map[string]interface{} `yaml:"decision_models"`
	}
	data, err := os.ReadFile(*config)
	if err != nil || yaml.Unmarshal(data, &routing) != nil {
		return fallback("config_unavailable")
	}
	policy := routing.Decisions[req.Question.ID]
	if policy == nil {
		return fallback("off")
	}
	absProject, err := filepath.Abs(*project)
	if err != nil {
		return fallback("invalid_input")
	}
	envelope, err := json.Marshal(map[string]interface{}{"request": json.RawMessage(raw), "policy": policy, "project_root": absProject})
	if err != nil {
		return fallback("invalid_input")
	}
	// The Python client has its own shorter deadline. Bound startup and all I/O
	// too, so a broken installation cannot stall a sprint.
	ctx, cancel := context.WithTimeout(context.Background(), 6*time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, "python3", filepath.Join(*root, "scripts", "clavain_selector", "decide.py"))
	cmd.Env = append(os.Environ(), "PYTHONPATH="+filepath.Join(*root, "scripts"))
	cmd.Stdin = bytes.NewReader(envelope)
	response, err := cmd.Output()
	if err != nil {
		return fallback("backend_unavailable")
	}
	var result map[string]interface{}
	if json.Unmarshal(response, &result) != nil || result["fallback"] != true {
		return fallback("invalid_response")
	}
	return json.NewEncoder(out).Encode(result)
}
