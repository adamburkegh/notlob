# Design note: a quantifier check for `notlob check`

**Status:** proposal
**Origin:** the ghost-turn prose/code drift after-action report
(`observations/2026-ghost-turn-prose-drift.md`) — from a different project
than notlob-lab itself; not present in this repo.
**Category:** structural lint, information-only warning — the same tier as
`typos`, `conventions`, `style`. Deterministic, offline, no model calls.

---

## What it does, in one sentence

Warn when a prose block makes a **quantified claim about behaviour** and no
`~example` or `~property` is co-located in the same section to pin it down.

It never decides whether the prose is *true*. It only notices that the prose
has made a checkable-shaped promise that nothing adjacent is checking.

## Why it is in scope (and semantic drift detection is not)

notlob's checks are structural by design, and the paper is explicit that
evaluating whether prose is a true description of code is a semantic judgment
out of scope for a mechanical checker. This check respects that line exactly.
It is a *structural proxy for a semantic smell* — the same move as flagging
more than one bullet list in a section. It asks "is there a quantified
behavioural claim with no runnable claim beside it?", which is answerable by
parsing. It does not ask "is this claim correct?", which is not.

The distinction matters for the paper's consistency: adding this check does
**not** weaken the claim that semantic verification is out of scope. It adds a
check that makes the *absence of verification* visible, which is a different
and mechanical thing.

## The motivating case (ground truth)

From `game/engine.lob`, `##Ghost Turn`, as it actually drifted:

> On the ghost turn, each ghost token fires a randomly chosen enabled
> transition.

The code below fired **one** transition per turn from the union of all
enabled transitions across the ghost marking. The prose says "each … fires";
the code fires one. There was no `~example` in that section pinning the
per-token quantifier. The check would have fired on this exact sentence:
a universal quantifier ("each") + a behavioural verb ("fires"), in a
subsection whose only runnable claims (elsewhere) tested other properties.

This is the test of the design: **does it light up on the real bug without a
semantic model?** It does — the trigger is present in the surface text and
the pinning claim is absent.

## Trigger definition

A warning fires when **all** of these hold for a prose block:

1. **A quantifier token is present.** A closed list, matched case-insensitively
   as whole words:
   `each, every, all, any, always, never, no, none, only, exactly,
   at least, at most, at most one, exactly one, for all, whenever`.
   (Numeric "exactly N", "at most N" via a small number-word/digit pattern.)

2. **A behavioural verb is nearby in the same sentence.** The quantifier must
   govern an *action*, not a static description. Maintain a small lexicon of
   behavioural verbs seeded from the domain and extended over time
   (`fires, moves, returns, produces, consumes, advances, emits, sends,
   writes, updates, fails, throws, retries, resets, increments, flushes,
   blocks, enables, triggers, calls, yields`), plus any verb within N tokens
   of a reference to a code symbol in the same section's name-graph scope.
   The name-graph helps here: a quantifier in a sentence that mentions a
   symbol defined in this section is far more likely to be a behavioural claim
   than one that is not.

3. **No co-located runnable claim.** The enclosing section (the `##`
   subsection, or the module body if no subsection) contains no `~example`
   and no `~property`.

When all three hold, emit an information-only warning naming the file, the
section, and the sentence.

## What it deliberately does NOT do

- **It does not check coverage.** If the section has *any* `~example` or
  `~property`, the check stays silent — even if that claim tests something
  unrelated to the quantifier. This is a real limit and must be documented
  in the warning's own help text, because it is exactly the ghost file's
  situation one step removed: the pre-existing examples near `ghostTurn`
  tested fork-produces-two-tokens and invalid-transition-ignored, both
  satisfiable under either firing interpretation. Had one of those sat in the
  *same subsection*, this check would have stayed quiet. The check catches
  "no check at all beside a quantified claim," not "the check present doesn't
  cover this claim." The latter is semantic and out of scope.

- **It does not judge truth.** A section can have a quantified claim and a
  matching example that are both wrong together; the check has nothing to say
  about that. Only a downstream symptom or a human will.

- **It does not fire on non-behavioural quantifiers.** "Every place has a
  dot", "all arcs are bipartite" (structural descriptions) should not trigger
  unless they govern an action verb. This is the hardest part to tune (see
  Risks).

## Output

Information-only, consistent with `style`/`conventions` tier. Example:

```
notlob check  (warnings)

  game/engine.lob
    ~quantifier  ##Ghost Turn
      "each ghost token fires a randomly chosen enabled transition"
      Universal claim about behaviour with no ~example or ~property in this
      section. Consider pinning the quantifier with a runnable claim.
      (This check verifies presence, not coverage — see `notlob check
      --explain quantifier`.)
```

Never fails the build. Suppressible per-section with an inline marker if
notlob has a suppression convention (and if it does not, this check is a
reason to add one — a sentence a human has deliberately judged unpinnable
should be silenceable, the way the bullet threshold should be).

## Tuning and rollout

The whole engineering risk is **false-positive rate**, exactly as with the
bullet-list check. A lint that fires on ordinary descriptive prose gets muted
within a day and is then worse than nothing. Mitigations:

- **Behavioural-verb gating** (requirement 2) is the main precision lever.
  Start narrow — quantifier + known behavioural verb + same-section symbol
  reference — and widen only if it misses real cases. Prefer false negatives
  to false positives at first; a check people trust and act on beats a
  thorough one they suppress.
- **Calibrate against the corpus.** Run it across the existing example
  projects (roman, retail, gutenberg, pn-chomper, pleiades, patches-dsp) and
  count fires. The ghost-turn sentence *must* fire (true positive). Anything
  else that fires is a precision test: is it a real unpinned behavioural
  claim, or noise? Tune the verb lexicon and the quantifier list until the
  corpus is quiet except where a human agrees the warning is fair.
- **Frequency, not instance, may be the right unit** — as with bullets. One
  unpinned quantified claim in a file is probably fine; a file full of them
  is a prose layer asserting behaviour it never checks. Consider firing on
  density above a threshold rather than on every instance, if per-instance
  proves too chatty. (Open question — resolve by corpus calibration.)

## Risks and honest limits

1. **The coverage blind spot** (above) is the big one. State it loudly. The
   check narrows the gap where drift hides; it does not close it. The honest
   framing in docs: "This finds quantified behavioural claims that nothing
   nearby checks. It cannot tell whether a check that *is* present actually
   covers the claim — that is a semantic judgment notlob leaves to you and to
   downstream symptoms."

2. **Behavioural vs structural quantifiers** is a genuine NLP-ish
   discrimination problem being approximated with a word list. It will
   misclassify. Accept that, keep the list small and curated, and lean on the
   name-graph symbol-reference signal to raise precision. Do not reach for a
   parser-of-English here; that is scope creep toward the semantic tool this
   check exists to *avoid* being.

3. **The familiar trap:** this check must not become the project's own
   instance of the §4.3 pattern — a declarative artifact (the verb lexicon,
   the quantifier list) that rots because nobody maintains it. Keep both lists
   small, version them in the repo, and treat additions as deliberate. A
   quantifier check whose lexicon has drifted from real usage would be a
   quietly perfect irony and a real failure.

## What success looks like

The check fires on the ghost-turn sentence and on genuinely analogous
unpinned behavioural claims across the corpus, stays silent on structural
description and on sections that already carry a claim, and is quiet enough
overall that a developer reads its output rather than suppressing it
wholesale. It manufactures a cheap *upstream* symptom — "nothing checks this
quantified claim" surfaced at authoring time — in a domain where the report
showed that symptoms, not review, are what catch drift. That is the modest,
honest, shippable win the ghost report actually earns.

## Explicitly out of scope (the other feature)

LLM-backed "is this prose true of this code?" semantic drift detection is a
different tool: non-deterministic, token-costing, network-dependent, and
recursively using LLM judgment to verify LLM-written prose — the very step
the ghost report documents an LLM failing. If it is built at all, it belongs
as a separate, opt-in, explicitly-advisory command (`notlob audit` /
`review`, a "second reader"), never inside `check`, never in the build gate,
so the paper's "deterministic structural checks" claim stays intact. The
name-graph is the right substrate for it; `check` is not the right home.
