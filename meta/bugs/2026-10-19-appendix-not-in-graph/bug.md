# `#Appendix` is invisible to the graph and the claim collectors

**Component:** `notlob/graph.py` (`build`, `enrich`, `add_references_edges`),
the claim collectors in all three bindings' runners,
`notlob/bindings/__init__.py` (`collect_run_bodies`), and
`notlob/commands.py` (`_collect_run_claims`, used by `notlob run`).
**Found by:** kamtrinia, notlob 0.5.4, Python binding, 2026-10-19.
**Status:** reopened, 2026-10-23: the fix (`f4b9eb9`) was backed out in
`4230b04` with the name-graph refactor; see
`meta/retrospectives/2026-10-23-name-graph-redundancy/`. Was: fixed,
2026-10-20. Retrospective:
`meta/retrospectives/2026-10-19-appendix-blind-spot/retrospective.md`.
Related core bug: `2026-10-20-name-graph-incomplete`.

## Summary

`notlob check` reported `unused import: Motif imports Typesetting but uses
none of its symbols`. The only use of Typesetting was `Face(...)` inside
`_text_width`, which lived in `#Appendix Width and test support`. Moving
the unchanged function into a body section (`##Text`) made the error
disappear. The grammar defines an Appendix as the same thing as the module
body (`appendix_section: APPENDIX_HEAD body_item*`), and `LANGUAGE.md`
says Appendix code "is assembled exactly like main-body code", and at run
time it was (claims calling it worked); only the checker disagreed.

That was one symptom. The cause was wider.

## Cause

Every consumer of a module walks its parsed tree by hand, and most walked
`module.body` alone, never `module.post_text`'s `AppendixSection`:

| Walk | Saw the Appendix? |
|---|---|
| Assemblers (Python, Haskell, TypeScript) | yes (fixed 2026-08-12, `2b2dd3e`) |
| `validate_refs` (reference validation) | yes (fixed 2026-08-11, `20b9390`) |
| `build`: subheading nodes only | partly |
| `enrich`: symbols and claim nodes | **no** |
| `add_references_edges` | **no** |
| `build`: the module node's own prose and code | **no** |
| Claim collectors: examples and properties, in Python, TypeScript and Haskell | **no** |
| `collect_run_bodies` (build and lint) | **no** |
| `_collect_run_claims` (`notlob run`) | **no** |

So an Appendix symbol was not a graph node and had no `USES` edges, which
is what `[imports]` reads. It also hid Appendix symbols from
`notlob query`, `notlob graph`, and the `typos`, `conventions` and
`titles` checks.

## Extent (verified)

**Claims written inside an `#Appendix` were never run.** An `~example` or
`~property` there was parsed and silently ignored, and a `~run` there was
not executed by `notlob run`. They could not fail, whatever they said.
(kamtrinia has no claims in its appendices, so it was not affected.)
Verified by `tests/test_appendix_graph.py`: the Appendix claim tests
failed before the fix.

## Resolution

**The Appendix is a node.** An `#Appendix` is a section of the document
with its own title, so the graph gets a node for it: kind `APPENDIX`,
address `mod#appendix#N` (N is its 1-based position among the module's
appendices; positional, like a claim, so it cannot collide with the
module's one namespace of symbol and subheading names), label its title
without the `#` (`Appendix Helpers`; a bare `#Appendix` is `Appendix`),
with a source line, and its own prose and code as content.

* The module `CONTAINS` the Appendix node; the Appendix `CONTAINS` its
  subheadings (subheading addresses stay `mod#Name`).
* Symbols and claims written in an Appendix are `DEFINES`-linked from the
  Appendix node, not the module. Symbol addresses stay module-scoped
  (`mod#helper`); claims are numbered within the Appendix, like a
  subheading's: `mod#appendix#1#example#1`.
* The module node's own prose and code are the body's only.

**The graph holds each node's body, and everything reads the graph.** A
module, a subheading and an Appendix each have a body (the grammar's own
term), and each is a node. `build` is now the only place the parse tree is
walked to find bodies: each of those nodes carries its body as an ordered
list of body items (prose, code, bullets, claims), claims become nodes
there (they are structure and need no language binding), and the module
node carries its `#References` lines. `enrich` (symbols), the reference
passes and reference validation read the graph, and so do the claim
collectors in all three bindings, `collect_run_bodies` and `notlob run`'s
entry-point test, through `claims_of(module)`. A claim's address and its
number come from its node, so the graph and the runners cannot disagree
about either. `AppendixSection` gained a `start_line` in the model.

(An earlier version of this fix added a `Region` structure and a flat
`Module.body_items()`: a second description of the hierarchy the graph
already has. Both were removed before they were ever committed; see the
completeness bug, `2026-10-20-name-graph-incomplete`.)

**Schemas and vocabulary.** `APPENDIX` is added to the `kind` enum in
`name_graph.json` and `query_result.json`, and `notlob:Appendix` to the
ontology. Anything that listed a module's `CONTAINS` children now sees the
Appendix node, not its subheadings, directly.

Tests, `tests/test_appendix_graph.py`:

* The Appendix node (address, label, containment, source line, content,
  several appendices), symbols and claims hanging from it, claims running
  (and failing), `~run`, prose references, and `[imports]` (kamtrinia's
  exact case).
* **The consistency property:** for each of the 15 non-empty combinations
  of {body, body subheading, Appendix, Appendix subheading}, the symbols
  the assembler emits equal the graph's symbol nodes, the claims the
  collectors find equal the graph's example, property and run nodes, an
  Appendix node exists iff the module has an Appendix.
* **A guard derived from `grammar.lark`:** the model has a body-holding
  field for exactly the grammar rules that contain a body (`module`,
  `subheading`, `appendix_section`). A body added to the grammar fails a
  test until the graph's `build` and the assemblers are taught about it.
* End to end in the TypeScript and Haskell runners.

The `[imports]` check itself was not changed: it was reporting correctly
what the graph told it.

## Claims in an Appendix: legal, discouraged

The paper (`ref-projects/notlob.tex`, "Bindings") says `~example` blocks
are "restricted to the main body", unit tests belong in the supplemental
material, and a property is "expected in the main section near prose
explaining the concepts and motivation". The grammar and `LANGUAGE.md`
say otherwise: `appendix_section` reuses `body_item*`, so a claim is
legal in an Appendix. Until this fix, claims written there were silently
ignored, which looked like the paper's restriction but was the same blind
spot.

**Decision (Adam, 2026-10-20):** leave the grammar as it is, so claims in
an Appendix stay legal and now run, and add a style-guidance check that
discourages them. It is in the `style` check: an advisory finding for each
`~example` and `~property` in an Appendix (directly or in one of its
subheadings), pointing at the main body, or `#Tests` for a supporting
fact. `~run` is not flagged (the design says nothing about it). Adam may
yet change the grammar and ban them; if so the check becomes a parse
error. He also floated a "lemma" idea, that an Appendix claim might be a
supporting fact with a different standing from an exposition example. Not
designed; recorded here so it is not lost.

## Not done here

The assemblers and the weaver still walk the module themselves (they were
right). The wider fix, making the graph a complete index of the document,
is `2026-10-20-name-graph-incomplete`.
