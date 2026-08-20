# One-Pager Template

> Copy to `docs/onepagers/YYYY-MM-DD-<topic>.md` in the target project.
> One page — ~500 words max. The distilled spine of a design: what a reader
> needs before opening the full brainstorm/PRD, and the artifact reviewers
> and later sessions load FIRST. Written at brainstorm capture (Phase 3 of
> `/clavain:brainstorm`); updated only when rulings land, never as a
> running log. Exemplar: uncrancher `docs/onepagers/2026-08-15-unc-network.md`.

```yaml
---
artifact_type: onepager
distills: docs/brainstorms/<source-brainstorm>.md
bead: <bead id or "none">
stage: discover
---
```

# \<Topic\> — one-pager

**Thesis.** The design's single organizing claim — the sentence that, if
lost, loses the design. 2–4 sentences, no hedging.

**How it works.** 3–6 bullets: the mechanisms that make the thesis real.
Each names the moving part, not the aspiration.

**Lineage / prior art.** What it borrows and from where — one organ per
ancestor, with the refusal attached where one exists ("takes X's chassis,
refuses its Y").

**The refusals.** What the design deliberately does NOT do — the ruled
constraints that bound every future slice. These are load-bearing; a
one-pager without refusals is a wish list.

**Open.** The top open calls, hardest first — max 3, one line each, with a
pointer to the full list in the source doc.

**Status.** Where it sits: horizon (now / next / v2+), what gates it, and
the first shippable slice when its turn comes.
