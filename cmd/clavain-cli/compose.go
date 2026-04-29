package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"

	pkgphase "github.com/mistakeknot/intercore/pkg/phase"
	"gopkg.in/yaml.v3"
)

// ─── Fleet Registry Types ──────────────────────────────────────────

type FleetRegistry struct {
	Version              string                `yaml:"version"`
	CapabilityVocabulary []string              `yaml:"capability_vocabulary"`
	Agents               map[string]FleetAgent `yaml:"agents"`
}

type FleetAgent struct {
	Source          string       `yaml:"source"`
	Category        string       `yaml:"category"`
	Description     string       `yaml:"description"`
	Capabilities    []string     `yaml:"capabilities"`
	Roles           []string     `yaml:"roles"`
	Runtime         AgentRuntime `yaml:"runtime"`
	Models          AgentModels  `yaml:"models"`
	Tools           []string     `yaml:"tools"`
	ColdStartTokens int          `yaml:"cold_start_tokens"`
	Tags            []string     `yaml:"tags"`
	OrphanedAt      string       `yaml:"orphaned_at,omitempty"`
}

type AgentRuntime struct {
	Mode         string `yaml:"mode"`
	SubagentType string `yaml:"subagent_type"`
}

type AgentModels struct {
	Preferred string   `yaml:"preferred"`
	Supported []string `yaml:"supported"`
}

// ─── Agency Spec Types ─────────────────────────────────────────────

type AgencySpec struct {
	Version  string               `yaml:"version"`
	Defaults SpecDefaults         `yaml:"defaults"`
	Stages   map[string]StageSpec `yaml:"stages"`
}

type SpecDefaults struct {
	BudgetAllocation string `yaml:"budget_allocation"`
	GateMode         string `yaml:"gate_mode"`
	ModelRouting     string `yaml:"model_routing"`
	CapabilityMode   string `yaml:"capability_mode"`
}

type StageSpec struct {
	Description string                 `yaml:"description"`
	Phases      []string               `yaml:"phases"`
	Requires    StageRequirements      `yaml:"requires"`
	Budget      StageBudget            `yaml:"budget"`
	Agents      StageAgents            `yaml:"agents"`
	Gates       map[string]interface{} `yaml:"gates,omitempty"`
}

type StageRequirements struct {
	Capabilities []string `yaml:"capabilities"`
	Tools        []string `yaml:"tools"`
}

type StageBudget struct {
	Share         int    `yaml:"share"`
	MinTokens     int    `yaml:"min_tokens"`
	ModelTierHint string `yaml:"model_tier_hint"`
}

type StageAgents struct {
	Required []AgentRole `yaml:"required"`
	Optional []AgentRole `yaml:"optional"`
}

type AgentRole struct {
	Role        string `yaml:"role"`
	Description string `yaml:"description"`
	ModelTier   string `yaml:"model_tier"`
	Count       string `yaml:"count,omitempty"`
	Condition   string `yaml:"condition,omitempty"`
}

// ─── Interspect Calibration Types ──────────────────────────────────

type InterspectCalibration struct {
	SchemaVersion           int                         `json:"schema_version"`
	CalibratedAt            string                      `json:"calibrated_at"`
	MinSessions             int                         `json:"min_sessions"`
	MinNonBootstrapSessions int                         `json:"min_non_bootstrap_sessions,omitempty"`
	SourceWeights           map[string]float64          `json:"source_weights,omitempty"`
	Agents                  map[string]AgentCalibration `json:"agents"`
}

type AgentCalibration struct {
	RecommendedModel    string                      `json:"recommended_model"`
	CurrentModel        string                      `json:"current_model"`
	HitRate             float64                     `json:"hit_rate"`
	WeightedHitRate     float64                     `json:"weighted_hit_rate,omitempty"`
	EvidenceSessions    int                         `json:"evidence_sessions"`
	Confidence          float64                     `json:"confidence"`
	PropagationEligible bool                        `json:"propagation_eligible,omitempty"`
	Reason              string                      `json:"reason"`
	Phases              map[string]AgentCalibration `json:"phases,omitempty"`
}

// ─── Routing Overrides Types ───────────────────────────────────────

type RoutingOverrides struct {
	Version   int               `json:"version"`
	Overrides []RoutingOverride `json:"overrides"`
}

type RoutingOverride struct {
	Agent      string  `json:"agent"`
	Action     string  `json:"action"` // "exclude" or "propose"
	Reason     string  `json:"reason"`
	Confidence float64 `json:"confidence"`
}

// RoutingConfig captures the production routing.yaml fields the composer needs.
// B2 complexity routing is intentionally scoped here to model selection; shell
// dispatch-tier routing remains owned by scripts/lib-routing.sh.
type RoutingConfig struct {
	Complexity ComplexityRoutingConfig `json:"complexity" yaml:"complexity"`
}

type ComplexityRoutingConfig struct {
	Mode      string                          `json:"mode" yaml:"mode"`
	Tiers     map[string]ComplexityTierConfig `json:"tiers" yaml:"tiers"`
	Overrides map[string]ComplexityOverride   `json:"overrides" yaml:"overrides"`
}

type ComplexityTierConfig struct {
	Description    string `json:"description" yaml:"description"`
	PromptTokens   int    `json:"prompt_tokens" yaml:"prompt_tokens"`
	FileCount      int    `json:"file_count" yaml:"file_count"`
	ReasoningDepth int    `json:"reasoning_depth" yaml:"reasoning_depth"`
}

type ComplexityOverride struct {
	SubagentModel string `json:"subagent_model" yaml:"subagent_model"`
	DispatchTier  string `json:"dispatch_tier" yaml:"dispatch_tier"`
}

// ─── Compose Output Types ──────────────────────────────────────────

type ComposePlan struct {
	Stage          string      `json:"stage"`
	Sprint         string      `json:"sprint"`
	Budget         int64       `json:"budget"`
	EstimatedTotal int64       `json:"estimated_total"`
	ComplexityTier string      `json:"complexity_tier,omitempty"`
	Warnings       []string    `json:"warnings"`
	Agents         []PlanAgent `json:"agents"`
}

type PlanAgent struct {
	AgentID         string `json:"agent_id"`
	SubagentType    string `json:"subagent_type"`
	Model           string `json:"model"`
	EstimatedTokens int    `json:"estimated_tokens"`
	Role            string `json:"role"`
	Required        bool   `json:"required"`
	ModelSource     string `json:"model_source"` // interspect_calibration | fleet_preferred | safety_floor | routing_fallback
}

// Safety floor agents: never downgraded below sonnet.
var safetyFloorAgents = map[string]string{
	"fd-safety":      "sonnet",
	"fd-correctness": "sonnet",
}

func cmdCompose(args []string) error {
	// Parse flags. --phase is accepted as an alias for --stage so flux-drive
	// handoffs can pass their native phase terminology through unchanged.
	var sprintID, stage, complexityTier string
	var promptTokens, fileCount, reasoningDepth int
	for i := 0; i < len(args); i++ {
		switch {
		case strings.HasPrefix(args[i], "--sprint="):
			sprintID = strings.TrimPrefix(args[i], "--sprint=")
		case strings.HasPrefix(args[i], "--stage="):
			stage = strings.TrimPrefix(args[i], "--stage=")
		case strings.HasPrefix(args[i], "--phase="):
			stage = strings.TrimPrefix(args[i], "--phase=")
		case strings.HasPrefix(args[i], "--complexity-tier="):
			complexityTier = strings.TrimPrefix(args[i], "--complexity-tier=")
		case strings.HasPrefix(args[i], "--complexity="):
			complexityTier = strings.TrimPrefix(args[i], "--complexity=")
		case strings.HasPrefix(args[i], "--prompt-tokens="):
			promptTokens = parseIntArg(strings.TrimPrefix(args[i], "--prompt-tokens="))
		case strings.HasPrefix(args[i], "--file-count="):
			fileCount = parseIntArg(strings.TrimPrefix(args[i], "--file-count="))
		case strings.HasPrefix(args[i], "--reasoning-depth="):
			reasoningDepth = parseIntArg(strings.TrimPrefix(args[i], "--reasoning-depth="))
		}
	}
	if stage == "" {
		return fmt.Errorf("compose: --stage is required")
	}

	// 1. Load fleet registry
	fleet, err := loadFleetRegistry()
	if err != nil {
		return fmt.Errorf("compose: load fleet: %w", err)
	}

	// 2. Load agency spec (with project override merge)
	spec, err := loadAgencySpec()
	if err != nil {
		return fmt.Errorf("compose: load spec: %w", err)
	}

	stageSpec, ok := spec.Stages[stage]
	if !ok {
		return fmt.Errorf("compose: unknown stage %q (valid: %s)", stage, stageKeys(spec))
	}

	// 3. Load Interspect calibration (optional — missing is OK)
	cal := loadInterspectCalibration()

	// 4. Load routing overrides (optional — missing is OK)
	overrides := loadRoutingOverrides()

	// 5. Load calibrated confidence thresholds (optional — missing is OK)
	ct := loadCalibratedThresholds()

	// 6. Load B2 routing config and derive complexity tier from caller signals.
	routing := loadRoutingConfig()
	applyComposeComplexityModeDefault(routing)
	if complexityTier == "" {
		complexityTier = classifyRoutingComplexity(routing, promptTokens, fileCount, reasoningDepth)
	}

	// 7. Get budget
	budget := computeStageBudget(sprintID, stage, stageSpec)

	// 8. Build plan
	plan := composePlanWithRouting(stage, sprintID, budget, complexityTier, stageSpec, fleet, cal, overrides, ct, routing)

	// 9. Output JSON
	data, err := json.MarshalIndent(plan, "", "  ")
	if err != nil {
		return fmt.Errorf("compose: marshal: %w", err)
	}
	fmt.Println(string(data))
	return nil
}

// ─── Loaders ───────────────────────────────────────────────────────

func loadFleetRegistry() (*FleetRegistry, error) {
	path := findFleetRegistryPath()
	if path == "" {
		return nil, fmt.Errorf("fleet-registry.yaml not found")
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var reg FleetRegistry
	if err := yaml.Unmarshal(data, &reg); err != nil {
		return nil, fmt.Errorf("parse %s: %w", path, err)
	}
	return &reg, nil
}

func loadAgencySpec() (*AgencySpec, error) {
	// Load default spec
	defaultPath := findDefaultSpecPath()
	if defaultPath == "" {
		return nil, fmt.Errorf("agency-spec.yaml not found")
	}
	data, err := os.ReadFile(defaultPath)
	if err != nil {
		return nil, err
	}
	var spec AgencySpec
	if err := yaml.Unmarshal(data, &spec); err != nil {
		return nil, fmt.Errorf("parse %s: %w", defaultPath, err)
	}

	// Load project override and merge (if exists)
	overridePath := findProjectSpecPath()
	if overridePath != "" {
		oData, err := os.ReadFile(overridePath)
		if err == nil {
			var override AgencySpec
			if err := yaml.Unmarshal(oData, &override); err == nil {
				mergeSpec(&spec, &override)
			}
		}
	}
	return &spec, nil
}

func loadInterspectCalibration() *InterspectCalibration {
	projectDir := projectRoot()
	path := filepath.Join(projectDir, ".clavain", "interspect", "routing-calibration.json")
	data, err := os.ReadFile(path)
	if err != nil {
		return nil // File missing — expected
	}
	var cal InterspectCalibration
	if err := json.Unmarshal(data, &cal); err != nil {
		fmt.Fprintf(os.Stderr, "compose: warning: corrupt %s: %v\n", path, err)
		return nil
	}
	if cal.SchemaVersion != 1 && cal.SchemaVersion != 2 {
		fmt.Fprintf(os.Stderr, "compose: warning: unsupported schema version %d in %s\n", cal.SchemaVersion, path)
		return nil
	}
	return &cal
}

func loadRoutingOverrides() *RoutingOverrides {
	projectDir := projectRoot()
	path := filepath.Join(projectDir, ".claude", "routing-overrides.json")
	data, err := os.ReadFile(path)
	if err != nil {
		return nil // File missing — expected
	}
	var ov RoutingOverrides
	if err := json.Unmarshal(data, &ov); err != nil {
		fmt.Fprintf(os.Stderr, "compose: warning: corrupt %s: %v\n", path, err)
		return nil
	}
	return &ov
}

func loadRoutingConfig() *RoutingConfig {
	path := findRoutingConfigPath()
	if path == "" {
		return nil // routing.yaml missing — expected in minimal fixtures
	}
	data, err := os.ReadFile(path)
	if err != nil {
		fmt.Fprintf(os.Stderr, "compose: warning: read %s: %v\n", path, err)
		return nil
	}
	var cfg RoutingConfig
	if err := yaml.Unmarshal(data, &cfg); err != nil {
		fmt.Fprintf(os.Stderr, "compose: warning: corrupt %s: %v\n", path, err)
		return nil
	}
	return &cfg
}

// ─── Path Resolution ───────────────────────────────────────────────

func findFleetRegistryPath() string {
	// 1. CLAVAIN_CONFIG_DIR
	if dir := os.Getenv("CLAVAIN_CONFIG_DIR"); dir != "" {
		p := filepath.Join(dir, "fleet-registry.yaml")
		if _, err := os.Stat(p); err == nil {
			return p
		}
	}
	// 2. CLAVAIN_DIR/config
	if dir := os.Getenv("CLAVAIN_DIR"); dir != "" {
		p := filepath.Join(dir, "config", "fleet-registry.yaml")
		if _, err := os.Stat(p); err == nil {
			return p
		}
	}
	// 3. CLAVAIN_SOURCE_DIR/config
	if dir := os.Getenv("CLAVAIN_SOURCE_DIR"); dir != "" {
		p := filepath.Join(dir, "config", "fleet-registry.yaml")
		if _, err := os.Stat(p); err == nil {
			return p
		}
	}
	// 4. CLAUDE_PLUGIN_ROOT/../config (plugin cache)
	if dir := os.Getenv("CLAUDE_PLUGIN_ROOT"); dir != "" {
		p := filepath.Join(dir, "config", "fleet-registry.yaml")
		if _, err := os.Stat(p); err == nil {
			return p
		}
	}
	return ""
}

func findRoutingConfigPath() string {
	if path := os.Getenv("CLAVAIN_ROUTING_CONFIG"); path != "" {
		if _, err := os.Stat(path); err == nil {
			return path
		}
		return ""
	}
	for _, dir := range configDirs() {
		p := filepath.Join(dir, "routing.yaml")
		if _, err := os.Stat(p); err == nil {
			return p
		}
	}
	return ""
}

func findDefaultSpecPath() string {
	// Same resolution as fleet registry but for agency-spec.yaml
	for _, dir := range configDirs() {
		p := filepath.Join(dir, "agency-spec.yaml")
		if _, err := os.Stat(p); err == nil {
			return p
		}
	}
	return ""
}

func findProjectSpecPath() string {
	projectDir := projectRoot()
	p := filepath.Join(projectDir, ".clavain", "agency-spec.yaml")
	if _, err := os.Stat(p); err == nil {
		return p
	}
	return ""
}

func configDirs() []string {
	var dirs []string
	if d := os.Getenv("CLAVAIN_CONFIG_DIR"); d != "" {
		dirs = append(dirs, d)
	}
	if d := os.Getenv("CLAVAIN_DIR"); d != "" {
		dirs = append(dirs, filepath.Join(d, "config"))
	}
	if d := os.Getenv("CLAVAIN_SOURCE_DIR"); d != "" {
		dirs = append(dirs, filepath.Join(d, "config"))
	}
	if d := os.Getenv("CLAUDE_PLUGIN_ROOT"); d != "" {
		dirs = append(dirs, filepath.Join(d, "config"))
	}
	return dirs
}

func projectRoot() string {
	if d := os.Getenv("SPRINT_LIB_PROJECT_DIR"); d != "" {
		return d
	}
	return "."
}

// ─── Merge Logic ───────────────────────────────────────────────────

// mergeSpec applies override fields on top of base.
// Arrays replace, non-zero scalars replace, zero values are skipped.
func mergeSpec(base, override *AgencySpec) {
	if base.Stages == nil {
		base.Stages = make(map[string]StageSpec)
	}
	for stageName, oStage := range override.Stages {
		if bStage, ok := base.Stages[stageName]; ok {
			if len(oStage.Requires.Capabilities) > 0 {
				bStage.Requires.Capabilities = oStage.Requires.Capabilities
			}
			if oStage.Budget.Share > 0 {
				bStage.Budget.Share = oStage.Budget.Share
			}
			if oStage.Budget.MinTokens > 0 {
				bStage.Budget.MinTokens = oStage.Budget.MinTokens
			}
			if oStage.Budget.ModelTierHint != "" {
				bStage.Budget.ModelTierHint = oStage.Budget.ModelTierHint
			}
			if len(oStage.Agents.Required) > 0 {
				bStage.Agents.Required = oStage.Agents.Required
			}
			if len(oStage.Agents.Optional) > 0 {
				bStage.Agents.Optional = oStage.Agents.Optional
			}
			base.Stages[stageName] = bStage
		} else {
			base.Stages[stageName] = oStage
		}
	}
}

// ─── Budget ────────────────────────────────────────────────────────

func computeStageBudget(sprintID, stage string, stageSpec StageSpec) int64 {
	if sprintID == "" {
		return int64(stageSpec.Budget.MinTokens)
	}
	// Try ic run tokens for total budget
	out, err := runIC("run", "budget", sprintID)
	if err != nil || len(out) == 0 {
		return int64(stageSpec.Budget.MinTokens)
	}
	var br BudgetResult
	if err := json.Unmarshal(out, &br); err != nil {
		return int64(stageSpec.Budget.MinTokens)
	}
	total := br.TokenBudget
	if total == 0 {
		return int64(stageSpec.Budget.MinTokens)
	}
	stageBudget := total * int64(stageSpec.Budget.Share) / 100
	if stageBudget < int64(stageSpec.Budget.MinTokens) {
		stageBudget = int64(stageSpec.Budget.MinTokens)
	}
	return stageBudget
}

// ─── Core Compose Algorithm ────────────────────────────────────────

// roleIndex partitions the active fleet by role once, with each role's
// candidates pre-sorted by ColdStartTokens (cheapest first, stable ID tiebreak).
// Lookups are O(1) map access + a linear skip over any excluded agents.
type roleIndex struct {
	byRole map[string][]matchedAgent
}

func buildRoleIndex(fleet map[string]FleetAgent, excluded map[string]bool) roleIndex {
	idx := roleIndex{byRole: make(map[string][]matchedAgent, len(fleet)/2)}
	for id, agent := range fleet {
		if agent.OrphanedAt != "" || excluded[id] {
			continue
		}
		for _, r := range agent.Roles {
			idx.byRole[r] = append(idx.byRole[r], matchedAgent{id: id, agent: agent})
		}
	}
	// Pre-sort each role's candidates: cheapest ColdStartTokens first, ID tiebreak.
	for _, candidates := range idx.byRole {
		sort.Slice(candidates, func(i, j int) bool {
			if candidates[i].agent.ColdStartTokens == candidates[j].agent.ColdStartTokens {
				return candidates[i].id < candidates[j].id
			}
			return candidates[i].agent.ColdStartTokens < candidates[j].agent.ColdStartTokens
		})
	}
	return idx
}

// match returns the cheapest agent for the given role.
// Because candidates are pre-sorted, we just return the first one.
func (idx *roleIndex) match(role string) (matchedAgent, bool) {
	candidates := idx.byRole[role]
	if len(candidates) == 0 {
		return matchedAgent{}, false
	}
	return candidates[0], true
}

// precomputeCapabilities builds a set of all capabilities provided by
// the selected agents, so checkCapabilityCoverage can do a simple lookup.
func precomputeCapabilities(agents []PlanAgent, fleet *FleetRegistry) map[string]bool {
	provided := make(map[string]bool, len(agents)*2)
	for _, a := range agents {
		if fleetAgent, ok := fleet.Agents[a.AgentID]; ok {
			for _, cap := range fleetAgent.Capabilities {
				provided[cap] = true
			}
		}
	}
	return provided
}

func composePlan(stage, sprintID string, budget int64, stageSpec StageSpec, fleet *FleetRegistry, cal *InterspectCalibration, overrides *RoutingOverrides, ct *CalibratedThresholds) ComposePlan {
	plan := ComposePlan{
		Stage:    stage,
		Sprint:   sprintID,
		Budget:   budget,
		Warnings: []string{},
		Agents:   []PlanAgent{},
	}

	// Build exclusion set from routing overrides
	excluded := map[string]bool{}
	if overrides != nil {
		for _, o := range overrides.Overrides {
			if o.Action == "exclude" {
				excluded[o.Agent] = true
				if _, isFloor := safetyFloorAgents[o.Agent]; isFloor {
					plan.Warnings = append(plan.Warnings, fmt.Sprintf("WARNING:safety_floor_excluded:%s:%s", o.Agent, o.Reason))
				}
				plan.Warnings = append(plan.Warnings, fmt.Sprintf("excluded:%s:%s", o.Agent, o.Reason))
			}
		}
	}

	// Build role index: partition fleet by role, pre-sort candidates once
	idx := buildRoleIndex(fleet.Agents, excluded)

	// Match required roles
	for _, role := range stageSpec.Agents.Required {
		agent, found := idx.match(role.Role)
		if !found {
			plan.Warnings = append(plan.Warnings, fmt.Sprintf("unmatched_role:%s", role.Role))
			continue
		}
		model, source := resolveModelForStage(stage, agent, role, cal, ct)
		plan.Agents = append(plan.Agents, PlanAgent{
			AgentID:         agent.id,
			SubagentType:    agent.agent.Runtime.SubagentType,
			Model:           model,
			EstimatedTokens: agent.agent.ColdStartTokens,
			Role:            role.Role,
			Required:        true,
			ModelSource:     source,
		})
	}

	// Match optional roles
	for _, role := range stageSpec.Agents.Optional {
		agent, found := idx.match(role.Role)
		if !found {
			continue // Optional roles are silently skipped
		}
		model, source := resolveModelForStage(stage, agent, role, cal, ct)
		plan.Agents = append(plan.Agents, PlanAgent{
			AgentID:         agent.id,
			SubagentType:    agent.agent.Runtime.SubagentType,
			Model:           model,
			EstimatedTokens: agent.agent.ColdStartTokens,
			Role:            role.Role,
			Required:        false,
			ModelSource:     source,
		})
	}

	// Sort agents by ID for deterministic output (learnings: go-map-hash-determinism)
	sort.Slice(plan.Agents, func(i, j int) bool {
		return plan.Agents[i].AgentID < plan.Agents[j].AgentID
	})

	// Sum estimated tokens
	var total int64
	for _, a := range plan.Agents {
		total += int64(a.EstimatedTokens)
	}
	plan.EstimatedTotal = total

	// Budget check (warn, don't optimize)
	if total > budget && budget > 0 {
		plan.Warnings = append(plan.Warnings, "budget_exceeded")
	}

	// Capability coverage check using pre-computed set
	capSet := precomputeCapabilities(plan.Agents, fleet)
	var missing []string
	for _, req := range stageSpec.Requires.Capabilities {
		if !capSet[req] {
			missing = append(missing, req)
		}
	}
	sort.Strings(missing)
	for _, cap := range missing {
		plan.Warnings = append(plan.Warnings, fmt.Sprintf("missing_capability:%s", cap))
	}

	return plan
}

func composePlanWithRouting(stage, sprintID string, budget int64, complexityTier string, stageSpec StageSpec, fleet *FleetRegistry, cal *InterspectCalibration, overrides *RoutingOverrides, ct *CalibratedThresholds, routing *RoutingConfig) ComposePlan {
	plan := composePlan(stage, sprintID, budget, stageSpec, fleet, cal, overrides, ct)
	applyB2ComplexityRouting(&plan, normalizeComplexityTier(complexityTier), fleet, routing)
	return plan
}

func applyB2ComplexityRouting(plan *ComposePlan, tier string, fleet *FleetRegistry, routing *RoutingConfig) {
	if plan == nil || tier == "" {
		return
	}
	plan.ComplexityTier = tier
	if routing == nil {
		return
	}
	mode := strings.ToLower(strings.TrimSpace(routing.Complexity.Mode))
	if mode == "" || mode == "off" {
		return
	}
	override, ok := routing.Complexity.Overrides[tier]
	if !ok {
		return
	}
	target := strings.TrimSpace(override.SubagentModel)
	if target == "" || target == "inherit" {
		return
	}
	for i := range plan.Agents {
		baseModel := plan.Agents[i].Model
		baseSource := plan.Agents[i].ModelSource
		candidateModel, candidateSource := target, "b2_complexity"
		if !agentSupportsModel(plan.Agents[i].AgentID, candidateModel, fleet) {
			continue
		}
		candidateModel, candidateSource = applySafetyFloor(plan.Agents[i].AgentID, candidateModel, candidateSource)
		switch mode {
		case "shadow":
			if candidateModel != baseModel {
				plan.Warnings = append(plan.Warnings, fmt.Sprintf("b2_shadow:%s:%s->%s:%s", plan.Agents[i].AgentID, baseModel, candidateModel, tier))
			}
		case "enforce":
			if candidateModel != baseModel || candidateSource != baseSource {
				plan.Agents[i].Model = candidateModel
				plan.Agents[i].ModelSource = candidateSource
			}
		}
	}
}

func applySafetyFloor(agentID, model, source string) (string, string) {
	if floor, ok := safetyFloorAgents[agentID]; ok {
		if pkgphase.ModelTier(model) < pkgphase.ModelTier(floor) || pkgphase.ModelTier(model) == 0 {
			return floor, "safety_floor"
		}
	}
	return model, source
}

func agentSupportsModel(agentID, model string, fleet *FleetRegistry) bool {
	if fleet == nil || model == "" {
		return true
	}
	agent, ok := fleet.Agents[agentID]
	if !ok || len(agent.Models.Supported) == 0 {
		return true
	}
	for _, supported := range agent.Models.Supported {
		if supported == model {
			return true
		}
	}
	return false
}

func normalizeComplexityTier(tier string) string {
	t := strings.ToUpper(strings.TrimSpace(tier))
	if t == "" {
		return ""
	}
	if strings.HasPrefix(t, "C") {
		return t
	}
	if n, err := strconv.Atoi(t); err == nil && n >= 1 && n <= 5 {
		return fmt.Sprintf("C%d", n)
	}
	return t
}

func classifyRoutingComplexity(routing *RoutingConfig, promptTokens, fileCount, reasoningDepth int) string {
	if routing == nil || (promptTokens == 0 && fileCount == 0 && reasoningDepth == 0) {
		return ""
	}
	order := []string{"C5", "C4", "C3", "C2", "C1"}
	for _, tier := range order {
		cfg, ok := routing.Complexity.Tiers[tier]
		if !ok {
			continue
		}
		if promptTokens >= cfg.PromptTokens || fileCount >= cfg.FileCount || reasoningDepth >= cfg.ReasoningDepth {
			return tier
		}
	}
	return "C1"
}

func applyComposeComplexityModeDefault(routing *RoutingConfig) {
	if routing == nil {
		return
	}
	if mode := strings.TrimSpace(os.Getenv("CLAVAIN_COMPOSE_COMPLEXITY_MODE")); mode != "" {
		routing.Complexity.Mode = mode
		return
	}
	if routing.Complexity.Mode != "" && routing.Complexity.Mode != "off" {
		// Production compose activation is a shadow rollout. Config may already be
		// enforce for lower-level routing; compose callers observe before enforcing.
		routing.Complexity.Mode = "shadow"
	}
}

func parseIntArg(value string) int {
	n, err := strconv.Atoi(strings.TrimSpace(value))
	if err != nil || n < 0 {
		return 0
	}
	return n
}

type matchedAgent struct {
	id    string
	agent FleetAgent
}

// matchRole is the original per-call linear-scan matcher, retained for
// backward compatibility with tests and callers outside composePlan.
// composePlan uses roleIndex.match() instead.
func matchRole(role AgentRole, fleet map[string]FleetAgent) (matchedAgent, bool) {
	var candidates []matchedAgent
	for id, agent := range fleet {
		for _, r := range agent.Roles {
			if r == role.Role {
				candidates = append(candidates, matchedAgent{id: id, agent: agent})
				break
			}
		}
	}
	if len(candidates) == 0 {
		return matchedAgent{}, false
	}
	// Pick cheapest candidate (by cold_start_tokens)
	sort.Slice(candidates, func(i, j int) bool {
		if candidates[i].agent.ColdStartTokens == candidates[j].agent.ColdStartTokens {
			return candidates[i].id < candidates[j].id // Stable tiebreak
		}
		return candidates[i].agent.ColdStartTokens < candidates[j].agent.ColdStartTokens
	})
	return candidates[0], true
}

func resolveModel(agent matchedAgent, role AgentRole, cal *InterspectCalibration, ct *CalibratedThresholds) (string, string) {
	return resolveModelForStage("", agent, role, cal, ct)
}

func resolveModelForStage(stage string, agent matchedAgent, role AgentRole, cal *InterspectCalibration, ct *CalibratedThresholds) (string, string) {
	var model, source string

	// Interspect calibration — evidence-driven. Schema v2 can carry
	// phase-specific recommendations; prefer those for the compose stage and
	// fall back to the global agent recommendation when no phase has enough
	// evidence/confidence.
	if cal != nil {
		if c, ok := cal.Agents[agent.id]; ok {
			threshold := 0.7
			if ct != nil {
				if at, ok := ct.Agents[agent.id]; ok {
					threshold = at.ConfidenceThreshold
				}
			}
			if pc, ok := phaseCalibration(c, stage); ok && calibrationUsable(pc, threshold) {
				if m := pc.RecommendedModel; m == "haiku" || m == "sonnet" || m == "opus" {
					model, source = m, "interspect_calibration"
				}
			}
			if model == "" && calibrationUsable(c, threshold) {
				if m := c.RecommendedModel; m == "haiku" || m == "sonnet" || m == "opus" {
					model, source = m, "interspect_calibration"
				}
			}
		}
	}

	// Fleet preferred model
	if model == "" && agent.agent.Models.Preferred != "" {
		model, source = agent.agent.Models.Preferred, "fleet_preferred"
	}

	// Role-declared model tier
	if model == "" && role.ModelTier != "" {
		model, source = role.ModelTier, "routing_fallback"
	}

	// Ultimate fallback
	if model == "" {
		model, source = "sonnet", "routing_fallback"
	}

	// Safety floor clamp — unconditional final step
	if floor, ok := safetyFloorAgents[agent.id]; ok {
		if pkgphase.ModelTier(model) < pkgphase.ModelTier(floor) || pkgphase.ModelTier(model) == 0 {
			model, source = floor, "safety_floor"
		}
	}

	return model, source
}

func calibrationUsable(c AgentCalibration, threshold float64) bool {
	return c.Confidence >= threshold && c.EvidenceSessions >= 3
}

func phaseCalibration(c AgentCalibration, stage string) (AgentCalibration, bool) {
	if len(c.Phases) == 0 || stage == "" {
		return AgentCalibration{}, false
	}
	for _, key := range phaseCalibrationKeys(stage) {
		if pc, ok := c.Phases[key]; ok {
			return pc, true
		}
	}
	return AgentCalibration{}, false
}

func phaseCalibrationKeys(stage string) []string {
	keys := []string{stage}
	switch stage {
	case "ship":
		keys = append(keys, "shipping", "quality-gates", "quality_gates")
	case "plan":
		keys = append(keys, "planning")
	case "build":
		keys = append(keys, "implementation", "implement")
	}
	return keys
}

func checkCapabilityCoverage(required []string, agents []PlanAgent, fleet *FleetRegistry) []string {
	provided := map[string]bool{}
	for _, a := range agents {
		if fleetAgent, ok := fleet.Agents[a.AgentID]; ok {
			for _, cap := range fleetAgent.Capabilities {
				provided[cap] = true
			}
		}
	}
	var missing []string
	for _, req := range required {
		if !provided[req] {
			missing = append(missing, req)
		}
	}
	sort.Strings(missing)
	return missing
}

// composeSprint runs compose for ALL stages in the agency spec.
// Returns a slice of ComposePlan — one per stage.
func composeSprint(spec *AgencySpec, fleet *FleetRegistry, cal *InterspectCalibration, overrides *RoutingOverrides, ct *CalibratedThresholds, sprintID string, totalBudget int64) []ComposePlan {
	var plans []ComposePlan
	routing := loadRoutingConfig()
	applyComposeComplexityModeDefault(routing)
	complexityTier := ""
	if sprintID != "" {
		complexityTier = tryComplexityOverride(sprintID)
	}

	// Sort stage names for deterministic output
	var stageNames []string
	for name := range spec.Stages {
		stageNames = append(stageNames, name)
	}
	sort.Strings(stageNames)

	for _, stageName := range stageNames {
		stageSpec := spec.Stages[stageName]
		stageBudget := totalBudget * int64(stageSpec.Budget.Share) / 100
		if stageBudget < int64(stageSpec.Budget.MinTokens) {
			stageBudget = int64(stageSpec.Budget.MinTokens)
		}
		plan := composePlanWithRouting(stageName, sprintID, stageBudget, complexityTier, stageSpec, fleet, cal, overrides, ct, routing)
		plans = append(plans, plan)
	}
	return plans
}

// cmdSprintCompose runs compose for all stages and stores the result as an ic artifact.
// Usage: sprint-compose <bead_id>
// Outputs: JSON array of ComposePlan on stdout.
func cmdSprintCompose(args []string) error {
	if len(args) < 1 || args[0] == "" {
		return fmt.Errorf("usage: sprint-compose <bead_id>")
	}
	beadID := args[0]

	// Load inputs
	fleet, err := loadFleetRegistry()
	if err != nil {
		return fmt.Errorf("sprint-compose: %w", err)
	}
	spec, err := loadAgencySpec()
	if err != nil {
		return fmt.Errorf("sprint-compose: %w", err)
	}
	cal := loadInterspectCalibration()
	overrides := loadRoutingOverrides()
	ct := loadCalibratedThresholds()

	// Get total budget from ic run
	var totalBudget int64 = 1000000 // default 1M
	runID, runErr := resolveRunID(beadID)
	if runErr == nil {
		var run Run
		if err := runICJSON(&run, "run", "status", runID); err == nil && run.TokenBudget > 0 {
			totalBudget = run.TokenBudget
		}
	}

	// Compose all stages
	plans := composeSprint(spec, fleet, cal, overrides, ct, beadID, totalBudget)

	// Output JSON
	data, err := json.MarshalIndent(plans, "", "  ")
	if err != nil {
		return fmt.Errorf("sprint-compose: marshal: %w", err)
	}
	fmt.Println(string(data))

	// Store as ic artifact (best-effort)
	if runErr == nil && runID != "" {
		tmpPath := filepath.Join(os.TempDir(), fmt.Sprintf("clavain-compose-%s.json", beadID))
		if err := os.WriteFile(tmpPath, data, 0644); err == nil {
			runIC("run", "artifact", "add", runID, "--phase=brainstorm", "--path="+tmpPath, "--type=compose_plan")
		}
	}

	return nil
}

func stageKeys(spec *AgencySpec) string {
	var keys []string
	for k := range spec.Stages {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	return strings.Join(keys, ", ")
}
