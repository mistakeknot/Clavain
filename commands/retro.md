---
name: retro
description: Read a session, a PR with its session, or a week of merged PRs and propose ranked changes to the environment that would have stopped repeated mistakes
argument-hint: "[session id | PR URL | week OWNER/REPO [YYYY-MM-DD]]"
---

# Retro

Look back at finished work and propose changes to the environment (checks,
standards, steering files) that would have stopped a mistake from repeating.
`/clavain:reflect` captures what a sprint learned. This asks what to change so
the next session does not need to learn it again.

Target: `$ARGUMENTS`. One of:

- a session id, or no argument for the current session;
- a PR URL: the PR's review comments, follow-up fix commits and the session
  that produced it;
- `week OWNER/REPO [date]`: every PR merged in the seven days up to the date
  (default today), with their review comments and fix-up commits.

## This command only proposes

It edits no instruction file, hook, setting, workflow or test. It writes one
report. Anything adopted afterwards goes through the normal route for that
file: instruction files reach their owner as a pull request, and a new check
is built and reviewed like any other change.

## Steps

1. **Collect the mistakes.** A mistake is something that had to be corrected
   after the author thought the work was done: a review finding that was
   fixed, a fix-up commit, a reverted change, a failed gate that a later change
   cured, a user correction in the session. Record each with its source (PR
   and comment, commit, or session line). Skip taste and one-off slips.
2. **Group repeats.** Merge mistakes that share a cause. A mistake that
   appears once stays in the report as a single instance; do not propose
   changes for it unless it was expensive.
3. **Classify each group.**
   - **Mechanical:** a program could have caught it from the code or the
     change alone (a forbidden pattern, a missing field, a wrong path, a
     missing test for a new command, a hostname in a public file).
   - **Judgement:** it needed someone to weigh a trade-off or know the
     domain (design choice, naming, scope, what to ask the user).
4. **Propose one change per group.**
   - Mechanical: a deterministic check. Name where it would run (a lint, a
     guard test in the repo, or a job on the independent CI service), what it
     fails on, and one concrete past instance it would have failed. Never
     propose a GitHub Actions workflow.
   - Judgement: one line for a standards file that a reviewer reads, not the
     always-loaded steering file, with the instance it comes from.
5. **Audit the steering lines.** Read the steering files in scope (global and
   project instruction files). For each line that matches no mistake in the
   window, say whether it is untested rather than useless. Flag a line as
   *changes nothing* only when you can show a case in the window where the
   line applied and behaviour did not change, or when a deterministic check
   already enforces it. Never call a line dead without that evidence.
6. **Rank.** Order proposals by mistakes prevented times cost per mistake,
   then by how cheap the change is. Put mechanical checks above standards
   lines at equal rank. Cap the report at ten proposals; drop the rest.
7. **Write the report** to the thread or project scratch directory, not into
   the repository under review:

   ```markdown
   # Retro: <target>, <window>
   ## Proposals (ranked)
   1. <mechanical|judgement> - <change> - prevents: <instances with links> - cost: <S|M|L> - where: <check location or standards file>
   ## Single instances (no proposal)
   ## Steering lines that changed nothing (with evidence)
   ## Not examined
   ```

   End with `## Not examined`: what the window did not cover (PRs without
   review comments, sessions that were unreadable). Do not present the
   absence of proposals as proof the environment is sound.

## Success

A retro run succeeded if at least one proposed check, once built, would have
failed on a real earlier mistake you cite. A report that only adds standards
lines is a weak result; say so.
