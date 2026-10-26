# Design note: keep phases and obsolete material out of `DESIGN.md`

**Status:** bookmarked 2026-10-24, not started.
**Origin:** Adam, reviewing slice 1 of the name-graph redesign
(`2026-10-23-name-graph-as-parse-tree`): `DESIGN.md` is one of the key
theory documents and should stay tight. Phase and slice numbering, and
progress on getting there, belong in `meta/features/`; so does the
history of designs that have been dropped. ("Later Features" is a
long-standing section of the document and stays.)

## What to look for

* Phase, slice or step numbering ("phase 1", "slice 2"), and progress
  notes ("being brought into line", "until ... lands").
* Obsolete elements: descriptions of designs that were dropped or
  superseded, and statements about the code that are no longer true.

## Found so far (search on 2026-10-24, after slice 1)

No phase or slice numbering. Candidates:

**Progress note**, "Structured output has a schema" (line 631):

```
Outputs that predate the rule are being brought into line;
`meta/features/2026-10-18-output-schemas` lists them.
```

**A dropped design, with its history**, before the binding's testing
libraries (lines 480-486):

```
**The binding — not a per-project declaration — selects the
property-testing and unit-testing library.** An earlier design had
authors write `~property-testing hypothesis` / `~unit-testing pytest`
in `binding.lob`; this was never actually part of the grammar
(...) and was removed as a documented breaking change
in 0.5.2. Each binding now provides one fixed choice, ...
```

The rule ("the binding selects the library") is theory; the earlier
design and its removal are history (the CHANGELOG has it).

**Minor**, under "Later Features" (line 722): "this is not yet
implemented" restates what the section heading already says.

## When picked up

A full read of `DESIGN.md` for the two kinds above, rather than a word
search: obsolete statements about the code do not share a vocabulary.
For each, cut it, or keep the design and move the history or progress to
the feature note or CHANGELOG entry it belongs to.
