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
	dir := t.TempDir()
	config := filepath.Join(dir, "routing.yaml")
	os.WriteFile(config, []byte("decision_models:\n  route: {mode: shadow, backend: heuristic}\n"), 0600)
	var out bytes.Buffer
	err := runDecide(strings.NewReader(`{"question":{"id":"route"},"native_choice":"plan"}`), &out, []string{"--plugin-root", dir, "--config", config})
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(out.String(), `"reason":"backend_unavailable"`) {
		t.Fatal(out.String())
	}
}

func TestDecideEnvelopeAndCase(t *testing.T) {
	root, _ := filepath.Abs("../..")
	dir := t.TempDir()
	config := filepath.Join(dir, "routing.yaml")
	os.WriteFile(config, []byte("decision_models:\n  route: {mode: shadow, backend: heuristic}\n"), 0600)
	for index, raw := range []string{
		`{"question":{"id":"route","text":"Choose","candidates":[{"id":"plan","description":"Plan"}]},"state":{},"native_choice":"plan","padding":"` + strings.Repeat("x", 89800) + `"}`,
		`{"question":{"id":"route"},"Question":{"ID":"unknown"},"native_choice":"plan"}`,
	} {
		var out bytes.Buffer
		if err := runDecide(strings.NewReader(raw), &out, []string{"--plugin-root", root, "--config", config, "--project-root", dir}); err != nil {
			t.Fatal(err)
		}
		var got map[string]interface{}
		json.Unmarshal(out.Bytes(), &got)
		if got["choice"] != "plan" || got["reason"] == "off" {
			t.Fatal(out.String())
		}
		if index == 0 && got["reason"] != "shadow_mode" {
			t.Fatal(out.String())
		}
	}
}

func TestDecideHelperTimeout(t *testing.T) {
	dir := t.TempDir()
	os.MkdirAll(filepath.Join(dir, "scripts", "clavain_selector"), 0700)
	os.WriteFile(filepath.Join(dir, "scripts", "clavain_selector", "decide.py"), []byte("import time\ntime.sleep(60)\n"), 0600)
	config := filepath.Join(dir, "routing.yaml")
	os.WriteFile(config, []byte("decision_models:\n  route: {mode: shadow, backend: heuristic}\n"), 0600)
	var out bytes.Buffer
	if err := runDecide(strings.NewReader(`{"question":{"id":"route"},"native_choice":"plan"}`), &out, []string{"--plugin-root", dir, "--config", config}); err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(out.String(), `"reason":"backend_unavailable"`) {
		t.Fatal(out.String())
	}
}

func TestDecideForcesNativeChoice(t *testing.T) {
	dir := t.TempDir()
	os.MkdirAll(filepath.Join(dir, "scripts", "clavain_selector"), 0700)
	os.WriteFile(filepath.Join(dir, "scripts", "clavain_selector", "decide.py"), []byte(`print('{"choice":"build","shadow_choice":"build","fallback":true}')`), 0600)
	config := filepath.Join(dir, "routing.yaml")
	os.WriteFile(config, []byte("decision_models:\n  route: {mode: shadow, backend: heuristic}\n"), 0600)
	var out bytes.Buffer
	if err := runDecide(strings.NewReader(`{"question":{"id":"route"},"native_choice":"plan"}`), &out, []string{"--plugin-root", dir, "--config", config}); err != nil {
		t.Fatal(err)
	}
	var got map[string]interface{}
	json.Unmarshal(out.Bytes(), &got)
	if got["choice"] != "plan" || got["shadow_choice"] != "build" {
		t.Fatal(out.String())
	}
}
