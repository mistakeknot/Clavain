package main

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestDecideShadowAndEnforce(t *testing.T) {
	root, _ := filepath.Abs("../..")
	for _, mode := range []string{"shadow", "enforce", "off"} {
		t.Run(mode, func(t *testing.T) {
			dir := t.TempDir()
			config := filepath.Join(dir, "routing.yaml")
			os.WriteFile(config, []byte("decision_models:\n  route:\n    backend: heuristic\n    mode: "+mode+"\n"), 0600)
			var out bytes.Buffer
			err := runDecide(strings.NewReader(`{"question":{"id":"route","text":"Choose route","candidates":[{"id":"plan","description":"Plan"}]},"state":{},"native_choice":"plan"}`), &out, []string{"--config", config, "--plugin-root", root, "--project-root", dir})
			if err != nil {
				t.Fatal(err)
			}
			var got map[string]interface{}
			if err := json.Unmarshal(out.Bytes(), &got); err != nil {
				t.Fatal(err)
			}
			if got["fallback"] != true || got["choice"] != "plan" {
				t.Fatalf("unsafe result: %s", out.String())
			}
			if mode == "enforce" && got["reason"] != "enforce_disabled" {
				t.Fatal(got)
			}
		})
	}
}

func TestDecideMissingHelperFallsBack(t *testing.T) {
	var out bytes.Buffer
	err := runDecide(strings.NewReader(`{"native_choice":"plan"}`), &out, []string{"--plugin-root", t.TempDir()})
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(out.String(), `"fallback":true`) {
		t.Fatal(out.String())
	}
}
