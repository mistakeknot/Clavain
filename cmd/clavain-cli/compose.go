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
	SchemaVersion int                         `json:"schema_version"`
	CalibratedAt  string                      `json:"calibrated_at"`
	MinSessions   int                         `json:"min_sessions"`
	Agents        map[string]AgentCalibration `json:"agents"`
}

type AgentCalibration struct {
	RecommendedModel string  `json:"recommended_model"`
	CurrentModel     string  `json:"current_model"`
	HitRate          float64 `json:"hit_rate"`
	EvidenceSessions int     `json:"evidence_sessions"`
	Confidence       float64 `json:"confidence"`
	Reason           string  `json:"reason"`
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

// ─── Compose Output Types ──────────────────────────────────────────

type ComposePlan struct {
	Stage          string      `json:"stage"`
	Sprint         string      `json:"sprint"`
	Budget         int64       `json:"budget"`
	EstimatedTotal int64       `json:"estimated_total"`
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
	// Parse flags
	var sprintID, stage string
	for i := 0; i < len(args); i++ {
		switch {
		case strings.HasPrefix(args[i], "--sprint="):
			sprintID = strings.TrimPrefix(args[i], "--sprint=")
		case strings.HasPrefix(args[i], "--stage="):
			stage = strings.TrimPrefix(args[i], "--stage=")
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

	// 5. Get budget
	budget := computeStageBudget(sprintID, stage, stageSpec)

	// 6. Build plan
	plan := composePlan(stage, sprintID, budget, stageSpec, fleet, cal, overrides)

	// 7. Output JSON
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
	if cal.SchemaVersion != 1 {
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

func composePlan(stage, sprintID string, budget int64, stageSpec StageSpec, fleet *FleetRegistry, cal *InterspectCalibration, overrides *RoutingOverrides) ComposePlan {
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
		model, source := resolveModel(agent, role, cal)
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
		model, source := resolveModel(agent, role, cal)
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

func resolveModel(agent matchedAgent, role AgentRole, cal *InterspectCalibration) (string, string) {
	// Safety floor check first — hard constraint
	if floor, ok := safetyFloorAgents[agent.id]; ok {
		return floor, "safety_floor"
	}

	// Interspect calibration — evidence-driven
	if cal != nil {
		if c, ok := cal.Agents[agent.id]; ok {
			if c.Confidence >= 0.7 && c.EvidenceSessions >= 3 {
				model := c.RecommendedModel
				if model == "haiku" || model == "sonnet" || model == "opus" {
					return model, "interspect_calibration"
				}
			}
		}
	}

	// Fleet preferred model
	if agent.agent.Models.Preferred != "" {
		return agent.agent.Models.Preferred, "fleet_preferred"
	}

	// Role-declared model tier
	if role.ModelTier != "" {
		return role.ModelTier, "routing_fallback"
	}

	return "sonnet", "routing_fallback"
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
func composeSprint(spec *AgencySpec, fleet *FleetRegistry, cal *InterspectCalibration, overrides *RoutingOverrides, sprintID string, totalBudget int64) []ComposePlan {
	var plans []ComposePlan

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
		plan := composePlan(stageName, sprintID, stageBudget, stageSpec, fleet, cal, overrides)
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
	plans := composeSprint(spec, fleet, cal, overrides, beadID, totalBudget)

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
