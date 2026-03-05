package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"gopkg.in/yaml.v3"
)

// ─── Tool Composition Types ──────────────────────────────────────
// Go-only parser for config/tool-composition.yaml.
// No bash-side parser exists — unlike routing.yaml which has two implementations.

type ToolComposition struct {
	Version         int                        `yaml:"version" json:"version"`
	Domains         map[string]Domain          `yaml:"domains" json:"domains"`
	CurationGroups  map[string]CurationGroup   `yaml:"curation_groups" json:"curation_groups"`
	SequencingHints     []SequencingHint     `yaml:"sequencing_hints" json:"sequencing_hints"`
	DisambiguationHints []DisambiguationHint `yaml:"disambiguation_hints" json:"disambiguation_hints"`
}

type Domain struct {
	Description string   `yaml:"description" json:"description"`
	Plugins     []string `yaml:"plugins" json:"plugins"`
}

type CurationGroup struct {
	Plugins []string `yaml:"plugins" json:"plugins"`
	Context string   `yaml:"context" json:"context"`
}

type SequencingHint struct {
	First string `yaml:"first" json:"first"`
	Then  string `yaml:"then" json:"then"`
	Hint  string `yaml:"hint" json:"hint"`
}

type DisambiguationHint struct {
	Plugins []string `yaml:"plugins" json:"plugins"`
	Domain  string   `yaml:"domain" json:"domain"`
	Hint    string   `yaml:"hint" json:"hint"`
}

// ─── Command ──────────────────────────────────────────────────────

func cmdToolSurface(args []string) error {
	jsonMode := false
	for _, a := range args {
		if a == "--json" {
			jsonMode = true
		}
	}

	comp, err := loadToolComposition()
	if err != nil {
		// Missing file → empty output, not error
		if jsonMode {
			fmt.Println("{}")
		}
		return nil
	}

	if jsonMode {
		data, err := json.MarshalIndent(comp, "", "  ")
		if err != nil {
			return fmt.Errorf("tool-surface: marshal: %w", err)
		}
		fmt.Println(string(data))
		return nil
	}

	// Plain text output for hook injection
	fmt.Println(formatToolSurface(comp))
	return nil
}

// ─── Loader ───────────────────────────────────────────────────────

func loadToolComposition() (*ToolComposition, error) {
	path := findToolCompositionPath()
	if path == "" {
		return nil, fmt.Errorf("tool-composition.yaml not found")
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var comp ToolComposition
	if err := yaml.Unmarshal(data, &comp); err != nil {
		return nil, fmt.Errorf("parse %s: %w", path, err)
	}
	// Ensure slices are non-nil so JSON serializes as [] not null
	if comp.SequencingHints == nil {
		comp.SequencingHints = []SequencingHint{}
	}
	if comp.DisambiguationHints == nil {
		comp.DisambiguationHints = []DisambiguationHint{}
	}
	return &comp, nil
}

func findToolCompositionPath() string {
	for _, dir := range configDirs() {
		p := filepath.Join(dir, "tool-composition.yaml")
		if _, err := os.Stat(p); err == nil {
			return p
		}
	}
	return ""
}

// ─── Formatter ────────────────────────────────────────────────────

func formatToolSurface(comp *ToolComposition) string {
	var b strings.Builder

	// Domains
	b.WriteString("## Tool Composition\n")
	domainNames := sortedKeys(comp.Domains)
	for _, name := range domainNames {
		d := comp.Domains[name]
		b.WriteString(fmt.Sprintf("%s: %s — %s\n",
			capitalize(name), strings.Join(d.Plugins, ", "), d.Description))
	}

	// Curation groups
	b.WriteString("\n### Workflow Groups\n")
	groupNames := sortedKeys(comp.CurationGroups)
	for _, name := range groupNames {
		g := comp.CurationGroups[name]
		b.WriteString(fmt.Sprintf("- %s: %s — %s\n",
			name, strings.Join(g.Plugins, " + "), g.Context))
	}

	// Sequencing hints
	if len(comp.SequencingHints) > 0 {
		b.WriteString("\n### Sequencing\n")
		for _, h := range comp.SequencingHints {
			b.WriteString(fmt.Sprintf("- %s before %s (%s)\n", h.First, h.Then, h.Hint))
		}
	}

	// Disambiguation hints
	if len(comp.DisambiguationHints) > 0 {
		b.WriteString("\n### Disambiguation\n")
		for _, h := range comp.DisambiguationHints {
			b.WriteString(fmt.Sprintf("- %s: %s\n",
				strings.Join(h.Plugins, " vs "), h.Hint))
		}
	}

	return strings.TrimRight(b.String(), "\n")
}

func sortedKeys[V any](m map[string]V) []string {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	return keys
}

func capitalize(s string) string {
	if s == "" {
		return s
	}
	return strings.ToUpper(s[:1]) + s[1:]
}
