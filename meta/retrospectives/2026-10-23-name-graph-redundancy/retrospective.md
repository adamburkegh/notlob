# Retrospective: the name-graph that stored everything several times

**Date:** 2026-10-23
**Author:** Claude (an Opus review session), from the commit history, the
code at each commit and the graph's real output. An account of the
evidence and one reading of it. Commentary by Adam, or anyone else, is in
its own file in this directory.
**The bug it set out to fix:**
`meta/bugs/2026-10-20-name-graph-incomplete/bug.md`
**One line:** the completeness contract for the name-graph was agreed; the
representation chosen for it was not discussed. That representation stored
each section's text, each claim and each cross-reference several times,
exported all of it through the graph schemas, and was released as 0.6.0.
The release was withdrawn and the work backed out.

## What happened

| Date | Commit | What |
|---|---|---|
| 2026-10-21 | `f4b9eb9` | "Make the name-graph a complete index of each body": each body-holding node gets `content.body`, an ordered list of its items. |
| 2026-10-22 | `1468f0f` | Module listing (load by use, cite by listing). Built on `f4b9eb9`'s API (`body_holders`, `body`). |
| 2026-10-22 | `625c0d0` | Release 0.6.0, tagged and published on GitHub. |
| 2026-10-22 | (working tree) | A follow-up removing the flat `prose` and `code` fields, after measuring `query content` on one pn-chomper section at 6,784 characters against 0.5.4's 2,597. |
| 2026-10-22 | n/a | Adam withdraws the release and deletes the tag. |
| 2026-10-23 | `0a95a5b` | The working tree committed as found, for the record. |
| 2026-10-23 | `4230b04` | All of the above backed out. Code is back to `d7bbca9` plus the build script; the `meta/` notes are kept. |

## How it was found

By Adam reading the output after the release: "the output of the name
graph introduced a lot of redundancy and doesn't make any sense". The
session that made the change had seen the size of the output (the
6,784-character measurement) and treated it as one field too many, not as
a sign that the representation was wrong.

## What the representation was

The design asks for "a graph of names, prose, concepts and code" built
from the parse tree. The contract written into `DESIGN.md` (agreed) said
every element appears in the graph with its kind, text, position and
order. The implementation put a second copy of the parse tree inside the
nodes' payloads, as untyped dicts, beside the graph's own nodes and edges.
For `roman/numerals`, `notlob graph --content` at 0.6.0 gave:

```json
{"address": "roman/numerals", "kind": "MODULE",
 "content": {"body": [
   {"kind": "code", "text": "NUMERALS: ...\n\ndef to_roman(n: int) ...",
    "start_line": 12},
   {"kind": "claim", "address": "roman/numerals#example#1",
    "start_line": 27}, ...]}},
{"address": "roman/numerals#example#1", "kind": "EXAMPLE",
 "content": {"sigil": "~example", "code": "to_roman(4) == 'IV' ..."},
 "start_line": 27},
{"address": "roman/numerals#to_roman", "kind": "SYMBOL",
 "content": {"code": "def to_roman(n: int) -> str: ..."},
 "start_line": 12}
```

with `roman/numerals DEFINES roman/numerals#example#1` among the edges.
So:

| Fact | Where it was stored |
|---|---|
| A symbol's source | The section's `code` body item **and** the `SYMBOL` node |
| A claim's place in a section | A `claim` body item, a `DEFINES` edge, and the node itself; its `start_line` twice |
| A cross-reference | The `#Label` sigil kept in the prose text, the item's `refs` list, and a `REFERENCES` edge |
| A section's prose and code | `body`, and flat `prose` and `code` strings (until the working-tree follow-up) |
| Bullet count | `bullet_block_count`, derivable from `body` |

Two things made it worse than untidy:

1. **The payload was the wire format.** `NameGraph.to_dict` and the query
   helper dump `node.content` as it is held in memory, so the internal
   layout became `name_graph.json` and `query_result.json`, which
   `DESIGN.md` lists among what tools can build on. Releasing it made the
   layout a promise.
2. **The tests were shaped around the problem.** The follow-up's "text
   appears once" test ran on the structural graph only, before symbols are
   added, and its docstring noted the exception. The export tests were
   changed to assert on `g.prose()` in memory rather than on the export.

The rebuilds: "the graph is the only reader of bodies" was met by
consumers calling `build(module)` for a throwaway graph (`claims_of`,
and two or three times per module in `project.py`), not by sharing one.
That consolidated the walk, not the data. The throwaway graphs have no
symbols, imports or references, so they are not the graph `notlob graph`
emits.

## Why it got through

1. **The decision that mattered was never put to Adam.** The contract was
   discussed. How it would be held (a payload list beside the graph, text
   copied into it) has large consequences for size and for the public
   schema, and was made in the course of implementing.
2. **The previous retrospective's lesson was written and then not
   applied.** `2026-10-19-appendix-blind-spot` says "before adding a
   structure beside the one that exists, ask what the existing one lacks,
   and add that to it", after a `Region` structure was removed for
   duplicating the graph's hierarchy. `content.body` is the same mistake
   one level down: a tree inside the nodes of a graph that is already a
   tree.
3. **The symptom was measured and patched.** The 6,784-character figure
   was answered by deleting two fields (a second breaking change) rather
   than by asking why the export carried a copy of the document.
4. **No invariant spanned the whole output.** Nothing checked that a piece
   of text appears once in the full, enriched, exported graph, so each
   addition was locally reasonable.
5. **Releasing was cheap.** The release came the day after the refactor,
   with the follow-up still uncommitted.
6. **Holding the theory.** This is the failure notlob exists to study: an
   agent can carry out the mechanics of "make the graph complete" while
   losing what the graph is for. The session kept the parts it was
   changing coherent and could not see the whole.

## Found during the review, not caused by the refactor

Checked on the backed-out tree (`4230b04`) against
`examples/roman/roman/numerals.lob`:

```
roman/numerals#to_roman          start_line 12   (def is at 19)
to_roman USES NUMERALS           start_line 14   (use is at 21)
example#1 USES to_roman          start_line 27   (line is 28)
Round-Trip#property#1 USES ...   start_line 70   (line is 71)
mcmxciv USES to_roman            start_line 92   (line is 93)
```

A symbol's `start_line` is its code block's, and `USES` lines on claim and
test nodes are one short. Also, on this tree, `#Tests` group nodes
(`Tests#encoding` etc.) have no `USES` edges at all: `1468f0f` fixed that
and was backed out with the rest.

## What changed

* The release and tag were removed from GitHub, and `4230b04` backs out
  `f4b9eb9`, `1468f0f`, the release, the version bump and the working-tree
  follow-up, keeping the build script and the `meta/` notes.
* The fix is to be redone from `d7bbca9` against a target design (to be
  written as a `meta/features/` note): the graph is the parse tree plus
  cross-references; every element is a node; text is held once, at the
  leaves; detail levels are views of one structure, not stored fields.
* The work is split: one session holds the design, writes narrow briefs
  and reviews diffs; another implements one brief at a time; Adam commits.

## What is still open

1. The target design note and its open decisions.
2. Redoing what was backed out: the Appendix fix (claims in an `#Appendix`
   are not run again on this tree), module listing, and the `#Tests`
   `USES` fix.
3. The line-number defects above.
4. A test that each piece of text appears once in every export level of
   the full graph.

## Lessons, short

* Agreeing what a structure must contain is not agreeing how it holds it.
  A representation choice that copies data, or changes a public schema, is
  a decision to raise, not a detail of implementation.
* A size measurement that surprises is a question about the design.
* Internal state is not a wire format. Exports are designed per audience.
* Test the property on the real output, not on the subset that passes.
* A lesson in a retrospective has to become a check, or it will be
  re-learned.
