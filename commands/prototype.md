---
name: prototype
description: Build disposable code to answer one design question, record the evidence and answer, then remove or quarantine the experiment
argument-hint: '"<one design question>" or <prototype-ticket-id>'
disable-model-invocation: true
---

# Prototype

Use running code to settle one named design question. The deliverable is an
answer supported by observations; the code is temporary.

Inspired by the prototype workflow in mattpocock/skills (MIT License,
Copyright (c) 2026 Matt Pocock). These instructions are written for Clavain.

Target: `$ARGUMENTS`. Read the supplied ticket and its parent decision map,
or use the question supplied directly. If neither names a single question,
clarify that before building.

## Bound the experiment

Write down the question, the alternatives, the observations that would
distinguish them, and a time limit. Identify who decides and where the answer
will be kept. Stop and record an inconclusive result if the limit is reached;
a plausible demo alone does not settle the question.

Choose the smallest useful shape:

- **Behaviour:** one HTML file with controls to drive a state model through
  ordinary and awkward sequences. Display the complete current state after
  every action and provide a reset control.
- **Presentation:** contrasting UI variants switchable in one screen, all
  showing the same sample data and states so the owner can compare them.
- **Technical feasibility:** a tiny script or harness that exercises the
  uncertain operation and prints its inputs and observed result.

## Build and observe

1. **Isolate it.** Use a disposable directory outside the production tree or
   a dedicated local experiment branch. Mark the entry file and any README
   `THROWAWAY PROTOTYPE`, with the question and limits. Keep a list of files
   you create so cleanup cannot touch unrelated work.
2. **Make it easy to run.** Supply one exact launch command from a named
   working directory, including any required setup. Prefer a self-contained
   file and existing tools. Use dummy data and in-memory state; restarting
   resets the experiment. Keep it disconnected from credentials, production
   services and durable storage.
3. **Build only what supplies evidence.** Skip automated tests, production
   integration and cosmetic polish for this disposable code. Existing repo
   checks and safety gates still apply. Do not broaden the experiment into
   feature implementation.
4. **Run it.** Execute the launch command and exercise the distinguishing
   cases, including the awkward states named earlier. Record actual inputs,
   actions and observations, plus anything the model leaves out. A launch
   failure or untested case stays an explicit limitation.
5. **Present the evidence.** Give the owner the run command or preview,
   describe the alternatives and recommend an answer. A preference question
   remains pending until the owner chooses. Use the project's decision
   channel; an agent recommendation does not count as the owner's pick.

## Keep the answer, retire the code

Record the following in the prototype ticket, or in
`docs/decisions/<question-slug>.md` when there is no ticket:

- Question and alternatives explored.
- Cases exercised and observations (with evidence references).
- Answer, its source and who made the decision, or `inconclusive` / `pending`.
- Limits: what the experiment did not establish.
- Next step and code disposition.

For a wayfind ticket, return the answer and evidence to `/clavain:wayfind`.
Its `resolve` step records the authoritative answer with the owner's pick as
`--source`; do not close it from an agent recommendation or change the map's
destination. A pending pick leaves the ticket open.

After recording the outcome, remove only the experiment files you created,
or quarantine them outside the production tree/on the dedicated experiment
branch and record that location. Stop any preview process you started. Keep
only the decision record in the delivery branch; do not merge prototype code
into main. Follow repository guards and publication permissions for any
branch operations. Quarantine is sufficient when deletion is not authorized.

## Done when

One question has a recorded answer and evidence, or an explicit unresolved
status with a next step; the code is removed or quarantined and its location
is recorded. An unresolved result does not clear a wayfind decision ticket.
