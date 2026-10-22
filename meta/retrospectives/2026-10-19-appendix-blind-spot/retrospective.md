# Retrospective: the Appendix blind spot

**Date:** 2026-10-19
**Layers:** the first layer (everything above "Second layer") was written
by Claude from the commit history, the fix and the tests. The second
layer, at the end, is Adam's conclusions on top of it. The first layer is
an account of the evidence and one reading of it, not the final word.
**The bug:** `meta/bugs/2026-10-19-appendix-not-in-graph/bug.md`
**One line:** most of the code that reads a module read only its body, so
anything written in an `#Appendix` was invisible to the graph, to
`notlob query`, to several checks, and (worst) to claim collection:
`~example`, `~property` and `~run` blocks in an Appendix were never run.
**Note, 2026-10-23:** the changes under "What changed" were backed out in
`4230b04`; see `meta/retrospectives/2026-10-23-name-graph-redundancy/`.

## What happened

| Date | Commit | What |
|---|---|---|
| 2026-08-11 | `20b9390` | "Allow references to headings in the appendix": 7 lines in `graph.py` (`validate_refs`) and a test. |
| 2026-08-12 | `2b2dd3e` | "Appendix code blocks were out of scope for the rest of the file": the three assemblers, three test files, `LANGUAGE.md` (now promising Appendix code "is assembled exactly like main-body code") and the CHANGELOG. |
| 2026-10-19 | (this fix) | kamtrinia reports `[imports]` flagging an import used only in an Appendix. Ten weeks after the second commit. |

The 08-12 commit is itself a silent-descope bug fix: Appendix code had been
quietly left out of scope. Both August commits fixed the walk that had been
reported broken and nothing else. The graph builder, the claim collectors
and `notlob run` were not touched, so the Appendix stayed out of scope in
those, and nothing was in a position to say so.

## How it was found

By use, not by notlob. kamtrinia moved a helper into an Appendix, `notlob
check` called the import unused, and they moved it back and reported it
with before-and-after evidence. kamtrinia has no claims in its Appendices,
so the worst consequence was not visible to them.

## What the bug actually was

Reading the code found part of it (`enrich` and `add_references_edges`
walk only `module.body`). Writing the tests found the rest: the claim
collectors in all three bindings, `collect_run_bodies`, `notlob run`'s own
collector, and the module node's prose and code. The first version of the
bug note listed the claims question as "verify first"; the consistency
test below settled it in one run. The property found more than the reading
did.

## Why it got through

1. **Nothing said which bodies a module has, and the graph, the one
   structure meant to, did not hold them.** Every consumer walked the
   parsed tree by hand: about ten walks (assemblers, graph build and
   enrich, reference edges, reference validation, claim collectors per
   binding, `notlob run`, the weaver). Each decided for itself where to
   look. The Appendix was handled in some and not in others, and nothing
   recorded which. A module, a subheading and an appendix each have a
   body (the grammar's `body`, `_sub_item*`, `body_item*`); the graph
   knew the nodes but not their bodies.
2. **Fixes were scoped to the symptom.** Each August fix touched one
   walker and added a test for that walker. Neither asked "what else
   walks a module?". The `LANGUAGE.md` promise was widened in the same
   commit, which made the gap a documented-behaviour bug instead of a
   known limitation, but no consumer was checked against the new promise.
3. **The tests were per walker; none compared views.** A test of the
   assembler can pass forever while the graph disagrees with it. No test
   asked whether two views of the same module contain the same things.
   A completeness test did exist: `tests/test_graph_completeness.py`
   (since 2026-06-20) says "every structural element in a parsed Module
   should be represented in the name graph". But its fixture has no
   Appendix, and it finds the module's claims by iterating `module.body`
   and the body's subheadings: the same hand-written walk, with the same
   blind spot, so the test of completeness shared the bug it was meant to
   catch. It checks a hand-listed registry of sigils, not the grammar.
4. **The failure was silent, and silent in the worst direction.** A body
   a walker does not know about produces no error: the code is just not
   there. For claims this means a check that cannot fail. "A missing
   checker is never reported as a pass" is a rule `LANGUAGE.md` already
   states for linters; the same rule was not applied to claim collection.
5. **The grammar already said the answer, and nothing read it.**
   `appendix_section: APPENDIX_HEAD body_item*` reuses the body rule. The
   formal definition of the syntax was right; the code derived from it was
   hand-written and unchecked against it.
6. **The way work is sliced.** This project is built in small slices of
   time, largely by agents, and a small slice naturally fixes the reported
   instance. That is a fine way to work only if something spans the
   slices. Here nothing did: no invariant held across the walkers, so no
   slice could notice another's omission.
7. **Few users of the feature.** Helper code in an Appendix is recent and
   unusual; the first heavy user found it within weeks.

None of this is a lapse of one person or one session. It is the shape of
the code: ten independent walks over one structure, with a silent default.

## What changed

* **The Appendix is a node,** and **the graph holds each node's body.**
  `build` is the only place the parse tree is walked to find bodies;
  symbol extraction, the reference edges, reference validation, the claim
  collectors in all three bindings, `collect_run_bodies` and `notlob run`
  read the graph, so a claim's address and number have one owner.
* **How it got there, which is part of the lesson.** The first version of
  the fix added a flat `Module.body_items()` that every consumer
  iterated. Adam's point that the Appendix "should surely have its own
  node" gave the Appendix a node, and with it the ability to say where a
  claim was written (the style check below needed that). I then added a
  `Region` structure and a `module_regions()` to give consumers addresses.
  Adam pointed out it duplicated the hierarchy the graph already has,
  that it was a day old and uncommitted, and that fidgeting was how the
  project got here; he also objected to the word, which I had made up.
  Both were removed before they were committed. The reason `Region` had
  seemed necessary was that the graph did not carry what the collectors
  needed; making the graph complete removed the need. Caution about
  adding a second structure beside the first is the same failure as the
  bug.
* **A style check:** an advisory `style` finding for an `~example` or
  `~property` in an Appendix, since the paper restricts them to the main
  body but the grammar allows them (Adam's decision, 2026-10-20).
* **A contract test** (`tests/test_graph_body.py`): an oracle walks the
  parse tree independently and, for every combination of places code can
  be written (body, body subheading, Appendix, Appendix subheading), what
  the graph holds for each node's body equals what the tree says, in
  order, with source positions.
* **A consistency property** (`tests/test_appendix_graph.py`): the symbols
  the assembler emits equal the graph's symbols, and the claims the
  collectors find equal the graph's claim nodes, wherever the code is
  written. This is the test that would have failed on 2026-08-12.
* **A guard derived from the grammar:** the model has a body-holding field
  for exactly the grammar rules that contain a body. A new body in
  `grammar.lark` fails a test until the graph's `build` and the assemblers
  are taught about it.
* Reference tests fail against the old walk (checked by reverting it), so
  they test what they claim.

## What is still open

1. **The rest of the completeness bug.** The name-graph being the complete
   graph the design describes was a bug in a core idea, not a feature
   (`meta/bugs/2026-10-20-name-graph-incomplete/bug.md`). Bodies are
   done. Still open: `#Tests` assertions and their order, binding
   declarations, the Turtle export of bodies, and the assemblers and
   weaver, which still read the parse tree (correctly, and tied to the
   graph by tests).
2. **The same property for other pairs of views.** Lint's source should
   equal the assembler's. The weaver's code blocks should equal the
   assembled code. Each is a cheap invariant of the same kind.
3. **Audit the other post-text sections** for the same second-class
   treatment: `#Tests` is in the graph in part; check `#References`,
   `#Binding` and `~external` against what each consumer does with them.
4. **A habit, written down:** a bug in one consumer of the model is a
   question about all of them. Before closing it, grep for the others
   (`grep '\.body\b'` found them here in a minute) and ask whether they
   agree. This could go in `AGENTS.md`.
5. **A principle for `DESIGN.md`:** what the language defines once (the
   grammar) is derived once, and anything hand-written against it has a
   test that reads the definition. This is the same premise as the rest of
   notlob (an agent does better against a hard formal check than against
   prose), applied to notlob's own internals.

## Lessons, short

* Silent skipping is a design smell: an unhandled body should be an
  error, or the walk should not exist.
* Before adding a structure beside the one that exists, ask what the
  existing one lacks, and add that to it.
* When the same structure is read in ten places, the consistency between
  the reads is a property worth testing in its own right.
* The formal definition is a test oracle. Use it.
* The cheapest way to find the extent of a bug like this was to write the
  invariant, not to read the code.

---

## Second layer: Adam's conclusions

*(to be written by Adam)*
