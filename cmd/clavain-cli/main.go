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

	// Agent tracking
	case "sprint-track-agent":
		err = cmdSprintTrackAgent(args)
	case "sprint-complete-agent":
		err = cmdSprintCompleteAgent(args)
	case "sprint-invalidate-caches":
		err = cmdSprintInvalidateCaches(args)

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
  set-artifact        <bead_id> <type> <path>
  record-phase        <bead_id> <phase>
  sprint-advance      <bead_id> <current_phase> [artifact_path]
  sprint-find-active
  sprint-create       <title>
  sprint-claim        <bead_id> <session_id>
  sprint-release      <bead_id>
  sprint-read-state   <bead_id>
  sprint-next-step    <phase>
  sprint-budget-remaining <bead_id>

Budget:
  budget-total            <bead_id>
  sprint-budget-stage     <bead_id> <stage>
  sprint-budget-stage-remaining <bead_id> <stage>
  sprint-budget-stage-check     <bead_id> <stage>
  sprint-stage-tokens-spent     <bead_id> <stage>
  sprint-record-phase-tokens    <bead_id> <phase>

Complexity:
  classify-complexity <bead_id> <description>
  complexity-label    <score>

Children:
  close-children           <bead_id> <reason>
  close-parent-if-done     <bead_id> [reason]

Bead Claiming:
  bead-claim              <bead_id> [session_id]
  bead-release            <bead_id>

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
`)
}
