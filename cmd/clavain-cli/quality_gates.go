package main

import (
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
)

// GateCheck represents a single quality gate check result.
type GateCheck struct {
	Language string `json:"language"`
	Check    string `json:"check"`
	Pass     bool   `json:"pass"`
	Duration int64  `json:"duration_ms"`
	Output   string `json:"output,omitempty"`
}

// GateResult represents the overall gate result.
type GateResultOutput struct {
	Pass   bool        `json:"pass"`
	Checks []GateCheck `json:"checks"`
}

// cmdQualityGateRun runs deterministic quality gates for the project.
// Detects languages and runs compile/test/lint checks.
// Args: [project_dir] (defaults to cwd)
// Exit 1 if any check fails.
func cmdQualityGateRun(args []string) error {
	dir := "."
	if len(args) > 0 && args[0] != "" {
		dir = args[0]
	}
	dir, err := filepath.Abs(dir)
	if err != nil {
		return fmt.Errorf("quality-gate-run: %w", err)
	}

	languages := detectLanguages(dir)
	if len(languages) == 0 {
		fmt.Println("quality-gate-run: no supported languages detected, skipping")
		return nil
	}

	var checks []GateCheck
	allPass := true

	for _, lang := range languages {
		langChecks := runLanguageGates(dir, lang)
		for _, c := range langChecks {
			checks = append(checks, c)
			if !c.Pass {
				allPass = false
			}
		}
	}

	result := GateResultOutput{Pass: allPass, Checks: checks}

	// Print summary table
	fmt.Println()
	fmt.Println("Quality Gate Results")
	fmt.Println("────────────────────────────────────────────")
	for _, c := range checks {
		status := "PASS"
		if !c.Pass {
			status = "FAIL"
		}
		fmt.Printf("  %-8s %-20s %s  (%dms)\n", c.Language, c.Check, status, c.Duration)
	}
	fmt.Println("────────────────────────────────────────────")
	if allPass {
		fmt.Println("  Overall: PASS")
	} else {
		fmt.Println("  Overall: FAIL")
		// Print failure details
		for _, c := range checks {
			if !c.Pass && c.Output != "" {
				fmt.Printf("\n--- %s/%s FAILURE ---\n", c.Language, c.Check)
				// Truncate long output
				out := c.Output
				if len(out) > 2000 {
					out = out[:2000] + "\n... (truncated)"
				}
				fmt.Println(out)
			}
		}
	}

	// JSON output to stderr for machine consumption
	if jsonBytes, err := json.Marshal(result); err == nil {
		fmt.Fprintln(os.Stderr, string(jsonBytes))
	}

	if !allPass {
		return fmt.Errorf("quality gates failed")
	}
	return nil
}

// detectLanguages checks for language markers in the project directory.
func detectLanguages(dir string) []string {
	var langs []string

	markers := map[string]string{
		"go.mod":           "go",
		"Cargo.toml":       "rust",
		"pyproject.toml":   "python",
		"setup.py":         "python",
		"requirements.txt": "python",
	}

	for file, lang := range markers {
		if _, err := os.Stat(filepath.Join(dir, file)); err == nil {
			// Deduplicate
			found := false
			for _, l := range langs {
				if l == lang {
					found = true
					break
				}
			}
			if !found {
				langs = append(langs, lang)
			}
		}
	}

	// Check for shell scripts
	if hasShellScripts(dir) {
		langs = append(langs, "shell")
	}

	return langs
}

// hasShellScripts checks if there are .sh files in common locations.
func hasShellScripts(dir string) bool {
	patterns := []string{"*.sh", "hooks/*.sh", "scripts/*.sh"}
	for _, p := range patterns {
		matches, _ := filepath.Glob(filepath.Join(dir, p))
		if len(matches) > 0 {
			return true
		}
	}
	return false
}

// runLanguageGates runs all gates for a specific language.
func runLanguageGates(dir, lang string) []GateCheck {
	switch lang {
	case "go":
		return runGoGates(dir)
	case "rust":
		return runRustGates(dir)
	case "python":
		return runPythonGates(dir)
	case "shell":
		return runShellGates(dir)
	default:
		return nil
	}
}

func runGoGates(dir string) []GateCheck {
	var checks []GateCheck
	checks = append(checks, runGate(dir, "go", "build", "go", "build", "./..."))
	checks = append(checks, runGate(dir, "go", "test", "go", "test", "./..."))
	if commandExists("golangci-lint") {
		checks = append(checks, runGate(dir, "go", "lint", "golangci-lint", "run", "--timeout=120s"))
	}
	return checks
}

func runRustGates(dir string) []GateCheck {
	var checks []GateCheck
	checks = append(checks, runGate(dir, "rust", "check", "cargo", "check"))
	checks = append(checks, runGate(dir, "rust", "test", "cargo", "test"))
	checks = append(checks, runGate(dir, "rust", "clippy", "cargo", "clippy", "--", "-D", "warnings"))
	return checks
}

func runPythonGates(dir string) []GateCheck {
	var checks []GateCheck
	if commandExists("ruff") {
		checks = append(checks, runGate(dir, "python", "lint", "ruff", "check", "."))
	}
	// Try pytest, uv run pytest, or python -m pytest
	if commandExists("uv") {
		checks = append(checks, runGate(dir, "python", "test", "uv", "run", "pytest", "--tb=short", "-q"))
	} else if commandExists("pytest") {
		checks = append(checks, runGate(dir, "python", "test", "pytest", "--tb=short", "-q"))
	}
	return checks
}

func runShellGates(dir string) []GateCheck {
	if !commandExists("shellcheck") {
		return nil
	}
	// Find .sh files in common locations
	var shFiles []string
	for _, pattern := range []string{"*.sh", "hooks/*.sh", "scripts/*.sh"} {
		matches, _ := filepath.Glob(filepath.Join(dir, pattern))
		shFiles = append(shFiles, matches...)
	}
	if len(shFiles) == 0 {
		return nil
	}
	args := append([]string{"-S", "warning"}, shFiles...)
	return []GateCheck{runGate(dir, "shell", "shellcheck", "shellcheck", args...)}
}

// runGate executes a single gate check and returns the result.
func runGate(dir, lang, check, command string, args ...string) GateCheck {
	start := time.Now()
	cmd := exec.Command(command, args...)
	cmd.Dir = dir

	out, err := cmd.CombinedOutput()
	duration := time.Since(start).Milliseconds()

	gc := GateCheck{
		Language: lang,
		Check:    check,
		Pass:     err == nil,
		Duration: duration,
	}

	if err != nil {
		// Capture output on failure (truncated)
		output := strings.TrimSpace(string(out))
		if len(output) > 4000 {
			output = output[:4000]
		}
		gc.Output = output
	}

	return gc
}

// commandExists checks if a command is available on PATH.
func commandExists(name string) bool {
	_, err := exec.LookPath(name)
	return err == nil
}
