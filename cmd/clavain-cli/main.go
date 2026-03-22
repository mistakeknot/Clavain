package main

import (
	"fmt"
	"os"
)

func main() {
	if len(os.Args) < 2 {
		printHelp()
		os.Exit(0)
	}

	cmd := os.Args[1]
	args := os.Args[2:]

	var err error
	switch cmd {
	// Sprint CRUD
	case "sprint-init":
		err = cmdSprintInit(args)
	case "sprint-create":
		err = cmdSprintCreate(args)
	case "sprint-find-active":
		err = cmdSprintFindActive(args)
	case "sprint-read-state":
		err = cmdSprintReadState(args)

	// Budget
	case "sprint-budget-remaining":
		err = cmdBudgetRemaining(args)
	case "budget-total":
		err = cmdBudgetTotal(args)
	case "sprint-budget-stage":
		err = cmdBudgetStage(args)
	case "sprint-budget-stage-remaining":
		err = cmdBudgetStageRemaining(args)
	case "sprint-budget-stage-check":
		err = cmdBudgetStageCheck(args)
	case "sprint-stage-tokens-spent":
		err = cmdStageTokensSpent(args)
	case "sprint-record-phase-tokens":
		err = cmdRecordPhaseTokens(args)
	case "record-cost-actuals":
		err = cmdRecordCostActuals(args)
	case "record-cost-estimate":
		err = cmdRecordCostEstimate(args)
	case "calibrate-phase-costs":
		err = cmdCalibratePhaseCosts(args)

	// Phase transitions
	case "sprint-advance":
		err = cmdSprintAdvance(args)
	case "sprint-next-step":
		err = cmdSprintNextStep(args)
	case "sprint-should-pause":
		err = cmdSprintShouldPause(args)
	case "enforce-gate":
		err = cmdEnforceGate(args)
	case "advance-phase":
		err = cmdAdvancePhase(args)
	case "record-phase":
		err = cmdRecordPhase(args)
	case "set-artifact":
		err = cmdSetArtifact(args)
	case "get-artifact":
		err = cmdGetArtifact(args)
	case "infer-action":
		err = cmdInferAction(args)
	case "infer-bead":
		err = cmdInferBead(args)

	// Checkpoints
	case "checkpoint-write":
		err = cmdCheckpointWrite(args)
	case "checkpoint-read":
		err = cmdCheckpointRead(args)
	case "checkpoint-validate":
		err = cmdCheckpointValidate(args)
	case "checkpoint-clear":
		err = cmdCheckpointClear(args)
	case "checkpoint-completed-steps":
		err = cmdCheckpointCompletedSteps(args)
	case "checkpoint-step-done":
		err = cmdCheckpointStepDone(args)

	// Claiming
	case "sprint-claim":
		err = cmdSprintClaim(args)
	case "sprint-release":
		err = cmdSprintRelease(args)
	case "bead-claim":
		err = cmdBeadClaim(args)
	case "bead-release":
		err = cmdBeadRelease(args)
	case "bead-heartbeat":
		err = cmdBeadHeartbeat(args)

	// Complexity
	case "classify-complexity":
		err = cmdClassifyComplexity(args)
	case "complexity-label":
		err = cmdComplexityLabel(args)

	// Children
	case "close-children":
		err = cmdCloseChildren(args)
	case "close-parent-if-done":
		err = cmdCloseParentIfDone(args)

	// Stats
	case "sprint-stats":
		err = cmdSprintStats(args)
	case "recent-reflect-learnings":
		err = cmdRecentReflectLearnings(args)

	// Agent tracking
	case "sprint-track-agent":
		err = cmdSprintTrackAgent(args)
	case "sprint-complete-agent":
		err = cmdSprintCompleteAgent(args)
	case "sprint-invalidate-caches":
		err = cmdSprintInvalidateCaches(args)

	// Compose
	case "compose":
		err = cmdCompose(args)
	case "sprint-compose":
		err = cmdSprintCompose(args)
	case "sprint-plan-phase":
		err = cmdSprintPlanPhase(args)
	case "sprint-env-vars":
		err = cmdSprintEnvVars(args)

	// Tool Composition
	case "tool-surface":
		err = cmdToolSurface(args)

	// CXDB
	case "cxdb-start":
		err = cmdCXDBStart(args)
	case "cxdb-stop":
		err = cmdCXDBStop(args)
	case "cxdb-status":
		err = cmdCXDBStatus(args)
	case "cxdb-setup":
		err = cmdCXDBSetup(args)
	case "cxdb-sync":
		err = cmdCXDBSync(args)
	case "cxdb-fork":
		err = cmdCXDBFork(args)
	case "cxdb-sync-verdicts":
		err = cmdCXDBSyncVerdicts(args)
	case "cxdb-history":
		err = cmdCXDBHistory(args)

	// Scenarios
	case "scenario-create":
		err = cmdScenarioCreate(args)
	case "scenario-list":
		err = cmdScenarioList(args)
	case "scenario-validate":
		err = cmdScenarioValidate(args)
	case "scenario-run":
		err = cmdScenarioRun(args)
	case "scenario-score":
		err = cmdScenarioScore(args)
	case "scenario-calibrate":
		err = cmdScenarioCalibrate(args)

	// Evidence
	case "evidence-to-scenario":
		err = cmdEvidenceToScenario(args)
	case "evidence-pack":
		err = cmdEvidencePack(args)
	case "evidence-list":
		err = cmdEvidenceList(args)

	// Policy
	case "policy-check":
		err = cmdPolicyCheck(args)
	case "policy-show":
		err = cmdPolicyShow(args)

	// Handoff
	case "validate-handoff":
		err = cmdValidateHandoff(args)
	case "validate-linkage":
		err = cmdValidateLinkage(args)

	// Quality Gates
	case "quality-gate-run":
		err = cmdQualityGateRun(args)

	// Watchdog
	case "watchdog":
		err = cmdWatchdog(args)
	case "factory-paused":
		err = cmdFactoryPaused(args)
	case "agent-paused":
		err = cmdAgentPaused(args)
	case "factory-status":
		err = cmdFactoryStatus(args)

	// Daemon
	case "daemon":
		err = cmdDaemon(args)

	// Intent contract
	case "intent":
		if len(args) > 0 && args[0] == "submit" {
			err = cmdIntentSubmit(args[1:])
		} else {
			fmt.Fprintf(os.Stderr, "clavain-cli intent: unknown subcommand (use 'intent submit')\n")
			os.Exit(1)
		}

	case "help", "--help", "-h":
		printHelp()

	default:
		fmt.Fprintf(os.Stderr, "clavain-cli: unknown command '%s'\n", cmd)
		fmt.Fprintf(os.Stderr, "Run 'clavain-cli help' for usage.\n")
		os.Exit(1)
	}

	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func printHelp() {
	fmt.Print(`Usage: clavain-cli <command> [args...]

Gate / Phase:
  advance-phase       <bead_id> <phase> <reason> <artifact_path>
  enforce-gate        <bead_id> <target_phase> <artifact_path>
  infer-bead          <artifact_path>

Sprint State:
  sprint-init         <bead_id>                            Bootstrap + formatted status banner
  set-artifact        <bead_id> <type> <path>              Store artifact (ic + bd fallback)
  get-artifact        <bead_id> <type>                     Retrieve artifact path by type
  record-phase        <bead_id> <phase>
  sprint-advance      <bead_id> <current_phase> [artifact_path]
  sprint-find-active
  sprint-create       <title>
  sprint-claim        <bead_id> <session_id>
  sprint-release      <bead_id>
  sprint-read-state   <bead_id>
  sprint-next-step    <phase>
  sprint-budget-remaining <bead_id>
  sprint-stats        [--complexity=N] [--since=DURATION] [--json] [--project=DIR]

Budget:
  budget-total            <bead_id>
  sprint-budget-stage     <bead_id> <stage>
  sprint-budget-stage-remaining <bead_id> <stage>
  sprint-budget-stage-check     <bead_id> <stage>
  sprint-stage-tokens-spent     <bead_id> <stage>
  sprint-record-phase-tokens    <bead_id> <phase>
  record-cost-actuals           <bead_id>
  record-cost-estimate          <bead_id> <phase>
  calibrate-phase-costs         (reads interstat history, writes calibration file)

Complexity:
  classify-complexity <bead_id> <description>
  complexity-label    <score>

Children:
  close-children           <bead_id> <reason>
  close-parent-if-done     <bead_id> [reason]

Bead Claiming:
  bead-claim              <bead_id> [session_id]
  bead-release            <bead_id> [--failure-class=<class>]
  bead-heartbeat          <bead_id>     Refresh claimed_at timestamp

Quality Gates:
  quality-gate-run        [project_dir]   Run deterministic gates (build/test/lint)

Watchdog:
  watchdog                [flags]  Sweep stale beads and escalate failures
                  --once  --dry-run  --stale-ttl=600s  --interval=60s  --max-unclaims=2

Factory:
  factory-status          [--json]   Fleet health dashboard (utilization, queue, WIP, dispatches)

Checkpoints:
  checkpoint-write    <bead_id> <phase> <step> <plan_path>
  checkpoint-read
  checkpoint-validate
  checkpoint-clear
  checkpoint-completed-steps
  checkpoint-step-done <step_name>

Agent Tracking:
  sprint-track-agent     <bead_id> <agent_name> [agent_type] [dispatch_id]
  sprint-complete-agent  <agent_id> [status]
  sprint-invalidate-caches

Compose:
  compose             --sprint=<bead_id> --stage=<stage>  Generate dispatch plan
  sprint-compose      <bead_id>                             Compose all stages for sprint
  sprint-plan-phase   <bead_id> <phase>                    Get model+budget for phase from compose plan
  sprint-env-vars     <bead_id> <phase>                    Output export statements for sprint env vars

Tool Composition:
  tool-surface        [--json]                             Output tool composition context (domains, groups, hints)

CXDB:
  cxdb-start          Start CXDB server (creates data dir, registers types)
  cxdb-stop           Stop CXDB server
  cxdb-status         Show CXDB server status as JSON
  cxdb-setup          Download and install cxdb-server binary [--version=<ver>]
  cxdb-sync           <sprint-id>           Backfill CXDB turns from Intercore events
  cxdb-fork           <sprint-id> <turn-id> Create branched execution trajectory

Scenarios:
  scenario-create     <name> [--holdout]     Scaffold scenario YAML
  scenario-list       [--holdout] [--dev]    List scenarios with metadata
  scenario-validate                          Validate all scenarios against schema
  scenario-run        <pattern> [--sprint=<id>]  Execute scenarios
  scenario-score      <run-id> [--summary]  Score scenario run with satisfaction rubrics
  scenario-calibrate                         Calibrate satisfaction threshold from history

Evidence:
  evidence-to-scenario <finding-id> [--bead=<id>]  Convert finding to dev scenario
  evidence-pack        <bead-id> [--type=<type>]   Create evidence pack from sprint data
  evidence-list        [bead-id]                    List evidence packs

Policy:
  policy-check         <agent> <action> [--path=<p>] [--bead=<id>]  Check action against policy
  policy-show                                        Display current policy

Handoff:
  validate-handoff    <artifact_path> [--type=<type>]     Validate artifact against handoff contract
  validate-linkage    [--contracts=<path>] [--spec=<path>] Check contract-to-spec consistency

Daemon:
  daemon          [flags]  Run continuous dispatch loop
                  --poll=30s  --max-concurrent=3  --max-complexity=3
                  --min-priority=3  --label=<filter>  --project-dir=.
                  --dry-run  --once

Intent Contract:
  intent submit   Submit a typed intent (JSON on stdin preferred; flags: --type, --bead, --session, --key)
`)
}
