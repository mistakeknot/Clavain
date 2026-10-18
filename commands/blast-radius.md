---
name: blast-radius
description: Find what a change could break somewhere else before it ships, and prove the one fact it is safe because of by running real code
argument-hint: "[PR number, commit range or file path; defaults to the current diff]"
disable-model-invocation: true
---

# Blast radius

Find what a change breaks somewhere else, before it ships. Use it for "blast
radius of X", "what could this break", or a small diff you don't trust yet.

Adapted from the blast-radius skill in pstack (cursor/plugins, MIT License,
Copyright (c) 2026 Lauren Tan; see THIRD-PARTY-NOTICES.md).

Listing the callers is not the job; grep does that in a second. The job is the
breakage grep won't show you. `/clavain:verify` checks that the work does what
it claims. This command asks what the work does to everything else.

Target: `$ARGUMENTS`. With no argument, use the current diff against the default
branch.

## Don't trust your own writeup

A blast-radius writeup that sounds right is worthless: it reads as convincing
whether or not it is true. So don't hand back the writeup. Find the one or two
facts the whole thing depends on and prove them by running code.

For each fact the change's safety depends on, get it as far down this list as is
cheap, and say where it stopped:

1. You said so. Worthless on its own.
2. You pointed at the line: a real `file:line`, or the library's own source.
3. You showed the bad case can't happen, by walking the failure step by step.
4. You ran it: a script or test that calls the real code and fails loudly if you
   are wrong.
5. You reproduced it in the running system.

Step 4 is usually one small script that imports what ships and calls the exact
function you are worried about.

## Steps

1. **Read the change.** The diff, the symbols it adds, changes and deletes, and
   what it now does differently, including the part the diff doesn't spell out.
   Pull the PR and its commits for intent.
2. **Find the one fact it is safe because of.** Most risky-looking changes are
   safe because of a single fact, such as "this call only drops entries that
   are already dead". Find it; if it holds, most risky cases clear at once.
   Spend your time here, not on a long list of maybes.
3. **Look where grep stops.** Read the source of the library you call, and check
   its pinned version and any local patch. Work out when things run: ordering,
   teardown, retries, concurrency. Follow what a symbol search misses: JSON an
   API returns, a database column, a wire format, another language reading the
   same bytes, a feature flag, a hook or script three hops downstream.
4. **Be honest about each risk.** Give it a real chance of happening and a real
   cost if it does. Cite a real `file:line`; a search that finds nothing is
   still an answer; never invent a caller or an API. Keep confirmed risks apart
   from the ones you checked and cleared.
5. **Prove the one fact.** Write a script or test that runs the real code, run
   it, and paste what happened.
6. **For a big or wide change,** ask an independent reviewer the same question
   through `/clavain:interserve` or packaged `scripts/dispatch.sh --role
   cross-lab-review`, and merge the answers. Different models catch different
   real bugs.

## What to hand back

- **What it does.** What changed, including the part that isn't obvious.
- **The one fact it is safe because of.** State it, say which step of the list
  you got it to, and show the proof. If you couldn't prove it, write
  `unproven`.
- **Risks.** Each names how it breaks, the `file:line`, how likely and how bad,
  and how to check. Paste the proof for the ones that matter.
- **Cleared.** What you checked and why it is fine.
- **Before you merge.** The cheapest test or repro that catches the real bug,
  including the script you wrote.
