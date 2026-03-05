package main

import (
	"bufio"
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"unicode"

	"gopkg.in/yaml.v3"
)

// ─── Handoff Contract Types ──────────────────────────────────────

// HandoffContracts is the top-level config/handoff-contracts.yaml.
type HandoffContracts struct {
	Version   string                      `yaml:"version"`
	Contracts map[string]ArtifactContract `yaml:"contracts"`
}

// ArtifactContract defines validation rules for a single artifact type.
type ArtifactContract struct {
	Description string              `yaml:"description"`
	ProducedBy  string              `yaml:"produced_by"`
	ConsumedBy  []string            `yaml:"consumed_by"`
	Frontmatter FrontmatterContract `yaml:"frontmatter"`
	Content     ContentContract     `yaml:"content"`
}

// FrontmatterContract defines required fields in YAML frontmatter.
type FrontmatterContract struct {
	RequiredFields []string `yaml:"required_fields"`
}

// ContentContract defines content validation rules.
type ContentContract struct {
	RequiredSections []SectionContract `yaml:"required_sections"`
	OptionalSections []SectionContract `yaml:"optional_sections"`
	MinTotalWords    int               `yaml:"min_total_words"`
	RequiredPatterns []PatternContract `yaml:"required_patterns"`
	OptionalPatterns []PatternContract `yaml:"optional_patterns"`
}

// SectionContract defines a required or optional markdown section.
type SectionContract struct {
	ID             string `yaml:"id"`
	HeadingPattern string `yaml:"heading_pattern"`
	MinWords       int    `yaml:"min_words"`
	MinCount       int    `yaml:"min_count"`
}

// PatternContract defines a required or optional content pattern.
type PatternContract struct {
	Pattern     string `yaml:"pattern"`
	Description string `yaml:"description"`
}

// ─── Validation Result Types ─────────────────────────────────────

// HandoffResult is the JSON output of validate-handoff.
type HandoffResult struct {
	ArtifactType    string         `json:"artifact_type"`
	ArtifactPath    string         `json:"artifact_path"`
	ContractVersion string         `json:"contract_version"`
	Result          string         `json:"result"` // "pass", "fail", "warn"
	Checks          []HandoffCheck `json:"checks"`
	Warnings        []string       `json:"warnings"`
}

// HandoffCheck is a single validation check result.
type HandoffCheck struct {
	Check    string `json:"check"`
	Result   string `json:"result"` // "pass", "fail", "skip"
	Heading  string `json:"heading,omitempty"`
	Line     int    `json:"line,omitempty"`
	Actual   int    `json:"actual,omitempty"`
	Required int    `json:"required,omitempty"`
	Detail   string `json:"detail,omitempty"`
}

// ─── Frontmatter Parsing ─────────────────────────────────────────

// parseFrontmatter extracts YAML frontmatter delimited by "---" from markdown.
// Returns the frontmatter as a raw map, the body after the closing "---", and any error.
// Returns nil map and full content if no frontmatter found.
func parseFrontmatter(content []byte) (map[string]interface{}, []byte, error) {
	scanner := bufio.NewScanner(bytes.NewReader(content))

	// First line must be "---"
	if !scanner.Scan() {
		return nil, content, nil
	}
	if strings.TrimSpace(scanner.Text()) != "---" {
		return nil, content, nil
	}

	// Collect lines until closing "---"
	var fmLines []string
	found := false
	lineCount := 1 // Already read the opening ---
	for scanner.Scan() {
		lineCount++
		line := scanner.Text()
		if strings.TrimSpace(line) == "---" {
			found = true
			break
		}
		fmLines = append(fmLines, line)
	}
	if !found {
		return nil, content, nil
	}

	// Parse YAML
	fmData := strings.Join(fmLines, "\n")
	var fm map[string]interface{}
	if err := yaml.Unmarshal([]byte(fmData), &fm); err != nil {
		return nil, content, fmt.Errorf("parse frontmatter: %w", err)
	}

	// Body is everything after the closing ---
	// Calculate byte offset: count bytes up to and including the closing ---
	bodyStart := 0
	linesSeen := 0
	for i := 0; i < len(content); i++ {
		if content[i] == '\n' {
			linesSeen++
			if linesSeen == lineCount {
				bodyStart = i + 1
				break
			}
		}
	}
	if bodyStart >= len(content) {
		return fm, nil, nil
	}
	return fm, content[bodyStart:], nil
}

// ─── Content Analysis ────────────────────────────────────────────

// countWords counts whitespace-separated words in a byte slice.
func countWords(b []byte) int {
	count := 0
	inWord := false
	for _, r := range string(b) {
		if unicode.IsSpace(r) {
			inWord = false
		} else if !inWord {
			inWord = true
			count++
		}
	}
	return count
}

// sectionMatch records a matched heading.
type sectionMatch struct {
	heading string
	line    int
	words   int // word count from this heading to the next h2
}

// matchSections scans markdown body for h2 headings matching section contracts.
// Returns a map of section ID → match info.
func matchSections(body []byte, sections []SectionContract) map[string]sectionMatch {
	results := make(map[string]sectionMatch)

	// Parse all h2 headings with their line numbers and content ranges
	type heading struct {
		text     string
		line     int
		startOff int // byte offset of line after heading
		endOff   int // byte offset of next heading (or end)
	}
	var headings []heading

	scanner := bufio.NewScanner(bytes.NewReader(body))
	lineNum := 0
	offset := 0
	for scanner.Scan() {
		lineNum++
		line := scanner.Text()
		lineLen := len(line) + 1 // +1 for newline

		if strings.HasPrefix(line, "## ") && !strings.HasPrefix(line, "### ") {
			headings = append(headings, heading{
				text:     strings.TrimPrefix(line, "## "),
				line:     lineNum,
				startOff: offset + lineLen,
			})
		}
		offset += lineLen
	}

	// Set endOff for each heading (to the start of the next heading or EOF)
	for i := range headings {
		if i+1 < len(headings) {
			headings[i].endOff = headings[i+1].startOff - len(headings[i+1].text) - 4 // "## " + text + "\n"
		} else {
			headings[i].endOff = len(body)
		}
		// Clamp
		if headings[i].endOff > len(body) {
			headings[i].endOff = len(body)
		}
		if headings[i].startOff > headings[i].endOff {
			headings[i].startOff = headings[i].endOff
		}
	}

	// Match each section contract against headings
	for _, sec := range sections {
		re, err := regexp.Compile(sec.HeadingPattern)
		if err != nil {
			continue
		}
		matchCount := 0
		for _, h := range headings {
			if re.MatchString(h.text) {
				matchCount++
				if _, exists := results[sec.ID]; !exists {
					sectionContent := body[h.startOff:h.endOff]
					results[sec.ID] = sectionMatch{
						heading: h.text,
						line:    h.line,
						words:   countWords(sectionContent),
					}
				}
			}
		}
		// For min_count, store the count in the match
		if sec.MinCount > 0 && matchCount >= sec.MinCount {
			if _, exists := results[sec.ID]; !exists {
				results[sec.ID] = sectionMatch{
					heading: fmt.Sprintf("(%d matches)", matchCount),
					line:    0,
				}
			}
		}
	}
	return results
}

// ─── Contract Validation ─────────────────────────────────────────

// validateContract validates artifact content against a contract.
func validateContract(artifactPath string, content []byte, contract ArtifactContract, contractVersion string) HandoffResult {
	result := HandoffResult{
		ArtifactPath:    artifactPath,
		ContractVersion: contractVersion,
		Checks:          []HandoffCheck{},
		Warnings:        []string{},
	}

	// Parse frontmatter
	fm, body, fmErr := parseFrontmatter(content)

	// Only check frontmatter presence when the contract requires frontmatter fields
	hasFrontmatterRequirements := len(contract.Frontmatter.RequiredFields) > 0
	if hasFrontmatterRequirements {
		if fm == nil {
			result.Checks = append(result.Checks, HandoffCheck{
				Check:  "frontmatter_present",
				Result: "fail",
				Detail: "no YAML frontmatter found",
			})
			if fmErr != nil {
				result.Checks = append(result.Checks, HandoffCheck{
					Check:  "frontmatter_valid",
					Result: "fail",
					Detail: fmErr.Error(),
				})
			}
			body = content // Use full content for section checks
		} else {
			result.Checks = append(result.Checks, HandoffCheck{
				Check:  "frontmatter_present",
				Result: "pass",
			})
		}
	} else if fm == nil {
		body = content // Use full content for section checks
	}

	// Infer artifact type from frontmatter if present
	if fm != nil && result.ArtifactType == "" {
		if at, ok := fm["artifact_type"].(string); ok {
			result.ArtifactType = at
		}
	}

	// Check required frontmatter fields
	for _, field := range contract.Frontmatter.RequiredFields {
		check := HandoffCheck{
			Check: "frontmatter_field:" + field,
		}
		if fm == nil {
			check.Result = "skip"
			check.Detail = "no frontmatter"
		} else if val, ok := fm[field]; !ok || val == nil || val == "" {
			check.Result = "fail"
			check.Detail = fmt.Sprintf("missing required field %q", field)
		} else {
			check.Result = "pass"
		}
		result.Checks = append(result.Checks, check)
	}

	// Check required sections
	if len(contract.Content.RequiredSections) > 0 {
		matches := matchSections(body, contract.Content.RequiredSections)
		for _, sec := range contract.Content.RequiredSections {
			check := HandoffCheck{
				Check: "section:" + sec.ID,
			}
			if m, found := matches[sec.ID]; found {
				check.Result = "pass"
				check.Heading = m.heading
				check.Line = m.line
				// Check min_words for this section
				if sec.MinWords > 0 && m.words < sec.MinWords {
					check.Result = "fail"
					check.Actual = m.words
					check.Required = sec.MinWords
					check.Detail = fmt.Sprintf("section %q has %d words, need %d", sec.ID, m.words, sec.MinWords)
				}
			} else {
				check.Result = "fail"
				check.Detail = fmt.Sprintf("required section %q not found (pattern: %s)", sec.ID, sec.HeadingPattern)
			}
			result.Checks = append(result.Checks, check)
		}
	}

	// Check optional sections (pass/skip, never fail)
	if len(contract.Content.OptionalSections) > 0 {
		matches := matchSections(body, contract.Content.OptionalSections)
		for _, sec := range contract.Content.OptionalSections {
			check := HandoffCheck{
				Check: "section:" + sec.ID,
			}
			if m, found := matches[sec.ID]; found {
				check.Result = "pass"
				check.Heading = m.heading
				check.Line = m.line
			} else {
				check.Result = "skip"
				check.Detail = "optional section not found"
			}
			result.Checks = append(result.Checks, check)
		}
	}

	// Check min total words
	if contract.Content.MinTotalWords > 0 {
		wc := countWords(body)
		check := HandoffCheck{
			Check:    "min_total_words",
			Actual:   wc,
			Required: contract.Content.MinTotalWords,
		}
		if wc >= contract.Content.MinTotalWords {
			check.Result = "pass"
		} else {
			check.Result = "fail"
			check.Detail = fmt.Sprintf("%d words, need %d", wc, contract.Content.MinTotalWords)
		}
		result.Checks = append(result.Checks, check)
	}

	// Check required content patterns
	for _, pat := range contract.Content.RequiredPatterns {
		check := HandoffCheck{
			Check: "pattern:" + pat.Description,
		}
		re, err := regexp.Compile(pat.Pattern)
		if err != nil {
			check.Result = "fail"
			check.Detail = fmt.Sprintf("invalid pattern %q: %v", pat.Pattern, err)
		} else if re.Match(content) { // Match against full content (including frontmatter area for verdicts)
			check.Result = "pass"
		} else {
			check.Result = "fail"
			check.Detail = fmt.Sprintf("pattern not found: %s", pat.Description)
		}
		result.Checks = append(result.Checks, check)
	}

	// Determine overall result
	hasFail := false
	for _, c := range result.Checks {
		if c.Result == "fail" {
			hasFail = true
			break
		}
	}
	if hasFail {
		result.Result = "fail"
	} else {
		result.Result = "pass"
	}

	return result
}

// ─── Contract Loading ────────────────────────────────────────────

// loadHandoffContracts loads config/handoff-contracts.yaml using the same
// config directory resolution as loadAgencySpec.
func loadHandoffContracts() (*HandoffContracts, error) {
	for _, dir := range configDirs() {
		p := filepath.Join(dir, "handoff-contracts.yaml")
		data, err := os.ReadFile(p)
		if err != nil {
			continue
		}
		var contracts HandoffContracts
		if err := yaml.Unmarshal(data, &contracts); err != nil {
			return nil, fmt.Errorf("parse %s: %w", p, err)
		}
		return &contracts, nil
	}
	return nil, fmt.Errorf("handoff-contracts.yaml not found")
}

// loadHandoffContractsFromPath loads contracts from a specific path.
func loadHandoffContractsFromPath(path string) (*HandoffContracts, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var contracts HandoffContracts
	if err := yaml.Unmarshal(data, &contracts); err != nil {
		return nil, fmt.Errorf("parse %s: %w", path, err)
	}
	return &contracts, nil
}

// ─── Cross-Stage Linkage Validation ──────────────────────────────

// validateLinkage checks that handoff contracts are consistent with agency spec stages.
func validateLinkage(contracts *HandoffContracts, spec *AgencySpec) []HandoffCheck {
	var checks []HandoffCheck

	// Sort contract keys for deterministic output
	var types []string
	for t := range contracts.Contracts {
		types = append(types, t)
	}
	sort.Strings(types)

	for _, typeName := range types {
		contract := contracts.Contracts[typeName]

		// Check produced_by is a valid stage
		if contract.ProducedBy != "" {
			check := HandoffCheck{
				Check: "linkage:produced_by:" + typeName,
			}
			if _, ok := spec.Stages[contract.ProducedBy]; ok {
				check.Result = "pass"
			} else {
				check.Result = "fail"
				check.Detail = fmt.Sprintf("produced_by stage %q not found in agency spec", contract.ProducedBy)
			}
			checks = append(checks, check)
		}

		// Check consumed_by stages are valid
		for _, stage := range contract.ConsumedBy {
			check := HandoffCheck{
				Check: "linkage:consumed_by:" + typeName + ":" + stage,
			}
			if _, ok := spec.Stages[stage]; ok {
				check.Result = "pass"
			} else {
				check.Result = "fail"
				check.Detail = fmt.Sprintf("consumed_by stage %q not found in agency spec", stage)
			}
			checks = append(checks, check)
		}

		// Warn on terminal contracts (no consumers) that aren't reflection
		if len(contract.ConsumedBy) == 0 && typeName != "reflection" {
			checks = append(checks, HandoffCheck{
				Check:  "linkage:orphan:" + typeName,
				Result: "fail",
				Detail: fmt.Sprintf("contract %q has no consumers (consumed_by is empty)", typeName),
			})
		}
	}

	return checks
}

// ─── CLI Commands ────────────────────────────────────────────────

// cmdValidateHandoff validates an artifact against its handoff contract.
// Usage: validate-handoff <artifact_path> [--type=<artifact_type>] [--contracts=<path>]
func cmdValidateHandoff(args []string) error {
	if len(args) < 1 {
		return fmt.Errorf("usage: validate-handoff <artifact_path> [--type=<type>] [--contracts=<path>]")
	}

	artifactPath := args[0]
	var artifactType, contractsPath string
	for _, arg := range args[1:] {
		switch {
		case strings.HasPrefix(arg, "--type="):
			artifactType = strings.TrimPrefix(arg, "--type=")
		case strings.HasPrefix(arg, "--contracts="):
			contractsPath = strings.TrimPrefix(arg, "--contracts=")
		}
	}

	// Load artifact content
	content, err := os.ReadFile(artifactPath)
	if err != nil {
		return fmt.Errorf("read artifact: %w", err)
	}

	// Load contracts
	var contracts *HandoffContracts
	if contractsPath != "" {
		contracts, err = loadHandoffContractsFromPath(contractsPath)
	} else {
		contracts, err = loadHandoffContracts()
	}
	if err != nil {
		return fmt.Errorf("load contracts: %w", err)
	}

	// Infer artifact type from frontmatter if not specified
	if artifactType == "" {
		fm, _, _ := parseFrontmatter(content)
		if fm != nil {
			if at, ok := fm["artifact_type"].(string); ok {
				artifactType = at
			}
		}
	}
	if artifactType == "" {
		return fmt.Errorf("cannot determine artifact type: use --type= or add artifact_type to frontmatter")
	}

	// Find contract
	contract, ok := contracts.Contracts[artifactType]
	if !ok {
		return fmt.Errorf("no contract defined for artifact type %q", artifactType)
	}

	// Validate
	result := validateContract(artifactPath, content, contract, contracts.Version)
	result.ArtifactType = artifactType

	// Output JSON
	data, err := json.MarshalIndent(result, "", "  ")
	if err != nil {
		return fmt.Errorf("marshal result: %w", err)
	}
	fmt.Println(string(data))
	return nil
}

// cmdValidateLinkage checks contract-to-spec consistency.
// Usage: validate-linkage [--contracts=<path>] [--spec=<path>]
func cmdValidateLinkage(args []string) error {
	var contractsPath, specPath string
	for _, arg := range args {
		switch {
		case strings.HasPrefix(arg, "--contracts="):
			contractsPath = strings.TrimPrefix(arg, "--contracts=")
		case strings.HasPrefix(arg, "--spec="):
			specPath = strings.TrimPrefix(arg, "--spec=")
		}
	}

	// Load contracts
	var contracts *HandoffContracts
	var err error
	if contractsPath != "" {
		contracts, err = loadHandoffContractsFromPath(contractsPath)
	} else {
		contracts, err = loadHandoffContracts()
	}
	if err != nil {
		return fmt.Errorf("load contracts: %w", err)
	}

	// Load spec
	var spec *AgencySpec
	if specPath != "" {
		data, err := os.ReadFile(specPath)
		if err != nil {
			return fmt.Errorf("read spec: %w", err)
		}
		spec = &AgencySpec{}
		if err := yaml.Unmarshal(data, spec); err != nil {
			return fmt.Errorf("parse spec: %w", err)
		}
	} else {
		spec, err = loadAgencySpec()
		if err != nil {
			return fmt.Errorf("load spec: %w", err)
		}
	}

	checks := validateLinkage(contracts, spec)

	// Determine overall result
	overallResult := "pass"
	for _, c := range checks {
		if c.Result == "fail" {
			overallResult = "fail"
			break
		}
	}

	output := struct {
		Result string         `json:"result"`
		Checks []HandoffCheck `json:"checks"`
	}{
		Result: overallResult,
		Checks: checks,
	}

	data, err := json.MarshalIndent(output, "", "  ")
	if err != nil {
		return fmt.Errorf("marshal: %w", err)
	}
	fmt.Println(string(data))
	return nil
}

// ─── Gate Integration ────────────────────────────────────────────

// checkHandoffContracts validates artifacts for the current phase against contracts.
// Returns nil if no contracts loaded or no artifacts to check.
func checkHandoffContracts(beadID, targetPhase string) []HandoffResult {
	contracts, err := loadHandoffContracts()
	if err != nil {
		return nil // No contracts = nothing to check
	}

	// Get artifacts from ic
	runID, err := resolveRunID(beadID)
	if err != nil {
		return nil
	}

	var artifacts []Artifact
	if err := runICJSON(&artifacts, "run", "artifact", "list", runID); err != nil {
		return nil
	}

	var results []HandoffResult
	for _, art := range artifacts {
		contract, ok := contracts.Contracts[art.Type]
		if !ok {
			continue // No contract for this type
		}

		content, err := os.ReadFile(art.Path)
		if err != nil {
			results = append(results, HandoffResult{
				ArtifactType: art.Type,
				ArtifactPath: art.Path,
				Result:       "fail",
				Checks: []HandoffCheck{{
					Check:  "file_readable",
					Result: "fail",
					Detail: err.Error(),
				}},
			})
			continue
		}

		result := validateContract(art.Path, content, contract, contracts.Version)
		result.ArtifactType = art.Type
		results = append(results, result)
	}
	return results
}

// getGateMode reads the gate_mode from agency-spec defaults.
// Returns "shadow" if not found or on error.
func getGateMode() string {
	spec, err := loadAgencySpec()
	if err != nil {
		return "shadow"
	}
	if spec.Defaults.GateMode != "" {
		return spec.Defaults.GateMode
	}
	return "shadow"
}

// getGateModeForPhase checks for per-stage gate_mode override, falling back to spec defaults.
// Maps the target phase to a stage via phaseToStage, then checks the stage's gates.
func getGateModeForPhase(spec *AgencySpec, targetPhase string) string {
	stage := phaseToStage(targetPhase)
	if stage != "" && stage != "unknown" && stage != "done" {
		if stageSpec, ok := spec.Stages[stage]; ok {
			if stageSpec.Gates != nil {
				if gm, ok := stageSpec.Gates["gate_mode"]; ok {
					if mode, ok := gm.(string); ok && mode != "" {
						return mode
					}
				}
			}
		}
	}
	// Fall back to spec defaults
	if spec.Defaults.GateMode != "" {
		return spec.Defaults.GateMode
	}
	return "shadow"
}

// summarizeFailures returns a one-line summary of failed checks.
func summarizeFailures(r HandoffResult) string {
	var fails []string
	for _, c := range r.Checks {
		if c.Result == "fail" {
			fails = append(fails, c.Check)
		}
	}
	return strings.Join(fails, ", ")
}
