# Slice 2c brief: the forest, behind today's outputs

**For:** an implementing session. **Written by:** the design session,
2026-10-24. **Design:** `design.md` in this directory: read sections 1, 2
and 7, and slice 2c in section 9, before starting.

## Goal

Make the name-graph the parse tree: every element of a module a node, in
one tree per file joined by `CONTAINS`, with text held on the leaves.
Today the graph holds named things and claims, with a section's prose
and code as concatenated strings on its node and `DEFINES` edges from a
section to what is written in it.

Every output keeps **today's shape** in this slice. A temporary layer
produces the old shape from the new graph; slice 5 replaces the outputs
and deletes it. The guard that nothing was lost:

* the CLI-level tests and the check tests do not change, and pass;
* the six accessors from slice 2b keep their tests, unchanged;
* a new oracle test compares the graph with an independent walk of the
  model.

This is the largest slice. Stop early and report rather than improvise:
see "When to stop".

## Rules

* **May touch:** `notlob/graph.py`, `notlob/project.py`,
  `notlob/commands.py` (the query commands only, as below), and the tests
  listed under "Tests".
* **Must not touch:** `model.py`, `check.py` (it already reads only the
  accessors; its guard test must still pass), the bindings, the runners,
  the assemblers, the weaver, `cli.py`, `mcp_server.py`, the schemas, the
  docs.
* **Failing test first** for the oracle and forest tests; say in your
  report that you did.
* **Do not commit or stage.** 80-character lines. No phase or slice
  wording in code, comments or docstrings: describe what the code is.
  The temporary layer's docstring says what it produces ("the graph in
  the shape `notlob graph` and `notlob query` print"), not when it goes.

## The graph

### Nodes

`Node` gains `end_line`, `file`, `text` and `refs`, all defaulting to
`None` (or an empty tuple for `refs`). `content` stays on the dataclass,
because the temporary layer builds old-shape nodes with it; nodes of the
new graph never set it.

New `NodeKind` members: `PROSE`, `CODE`, `BULLETS`, `APPENDIX`, `TESTS`.
`TEST` now means a test group, an assertion block or a `~test`.

What each element of the model becomes (positions from the 2a fields;
`file` is the module's path relative to the project root, POSIX
separators, `None` for a module built on its own):

| Model | Node kind | Address | Label | `text` |
|---|---|---|---|---|
| `Module` | `MODULE` | as now | as now | none |
| `Subheading` | `SUBHEADING` | as now (`mod#Title`), in the body or an Appendix | as now | none |
| `AppendixSection` | `APPENDIX` | `mod#appendix#n` (n from 1, in order) | its title without `#` | none |
| `TestsSection` | `TESTS` | `mod#Tests` | `Tests` | none |
| `TestGroup` | `TEST` | as now (`mod#Tests#title`) | as now | none |
| a run of bare assertion lines | `TEST` | `parent#test#n` | `test#n` | the lines as written, joined with `\n` |
| `NamedTest` | `TEST` | as now (`group#name`) | as now | its lines as now |
| `ProseBlock` | `PROSE` | `parent#prose#n` | `prose#n` | the spans joined, references with their sigils |
| `CodeBlock` | `CODE` | `parent#code#n` | `code#n` | dedented, as `_code_text` does per block |
| `BulletBlock` | `BULLETS` | `parent#bullets#n` | `bullets#n` | the items joined with `\n` |
| `Claim` | `EXAMPLE`, `PROPERTY` or `RUN` | as now (`claim_address`, the same counters) | as now | dedented lines (see "Values that must not move") |

A run of bare assertion lines is consecutive bare lines (blank ones
included) in `#Tests` or a group, ended by anything else. Ordinals count
per parent and per kind, from 1. A `PROSE` leaf's `refs` holds its `Ref`s.

**A claim's kind follows its sigil:** every `~run` (bare, `on-load`,
`on-invocation`) is a `RUN`; only `~property` is a `PROPERTY`. Today
`~run on-load` becomes a `PROPERTY` named "on-load". If a CLI-level test
pins the old behaviour, that test may change: list it.

Claims are made by `build`, not `enrich` (they need no binding). `enrich`
adds `SYMBOL` nodes as now (addresses, labels, `text` = `info.source`,
`start_line` = the block's, all unchanged) but contained by their `CODE`
leaf, and a property's functions by the `PROPERTY` node.

`#Binding` and `#References` sections are **not** nodes in this slice
(`design.md` D11 is open). `IMPORTS`, `EXTERNAL` nodes and
`USES_EXTERNAL` edges stay as `build_package` makes them now.

### Edges

* `CONTAINS` from each node to each of its children, in document order.
  It is the only edge `build` and `enrich` make. Keep a parent index so a
  node's parent is found without a scan.
* `REFERENCES` come from the `PROSE` leaf that holds the reference
  (`design.md` D3). `add_references_edges(graph)` reads the `PROSE`
  leaves' `refs` from the graph instead of walking the model, so it no
  longer takes the modules; one edge per (leaf, target), carrying the
  reference's line. Resolution is unchanged.
* `USES`, `IMPORTS`, `USES_EXTERNAL`: made as now.

### The accessors

Their tests in `tests/test_graph.py` (from 2b) do not change. Their
answers come from the tree now:

| Method | From |
|---|---|
| `module_of` | the root of the node's tree, along `CONTAINS`; `None` for `EXTERNAL` or unknown |
| `edges` | unchanged |
| `sections` | the `SUBHEADING` and `APPENDIX` nodes in the module's tree, in document order |
| `prose` | the module's or section's own `PROSE` and `BULLETS` children, as `_prose_text` joins them today |
| `bullet_list_count` | its own `BULLETS` children |
| `claims` | its own `EXAMPLE`, `PROPERTY` and `RUN` children, in document order |

`sections` now includes Appendices, so `check_references` reads Appendix
prose. That is the intended fix; if a check test pins the old behaviour,
stop and report.

## The temporary output layer

One function in `graph.py`, `legacy_graph(graph) -> NameGraph`, builds a
graph in today's shape from the forest:

* the node kinds of today only (`MODULE`, `SUBHEADING`, `SYMBOL`,
  `PROPERTY`, `EXAMPLE`, `RUN`, `TEST`, `EXTERNAL`), with today's
  `content` dicts (`prose`, `code`, `bullet_block_count` on a module or
  subheading, `code` on the rest) and today's `start_line`; no `end_line`,
  `file`, `text` or `refs`;
* today's edges: `CONTAINS` from a module to its subheadings (an
  Appendix's subheadings included, as now), `DEFINES` from a section to
  its symbols, claims and test nodes, from a group to its named tests and
  from a property to its functions, and `REFERENCES` from the section
  that holds the paragraph (one per section and target, the first line
  kept), plus `IMPORTS`, `USES` and `USES_EXTERNAL` as they are;
* today's `#Tests` shape: a `TEST` node at `mod#Tests` only when there
  are bare assertions directly in `#Tests`, carrying them all; a group's
  node carrying all its bare lines; no `TESTS` node, no assertion-block
  nodes.

Where the old graph left something out (anything written directly in an
`#Appendix` rather than in one of its subheadings), the layer may include
it, attached to the module. List any test that changes because of it.

Wiring: `NameGraph.to_dict`, `to_json` and `to_turtle` produce their
output from `legacy_graph(self)`, so `notlob graph` and the MCP graph tool
do not change. In `commands.py`, the query commands (`children`,
`resolve`, `search`, `imports`, `imported-by`, `callers`, `callees`,
`references`, `referenced-by`, `content`) query `legacy_graph` of the
package graph; `notlob check` keeps the new graph.

### Values that must not move

The CLI tests compare text, so the layer must reproduce today's strings,
and `add_uses_edges` today's lines. What `build` stores on a leaf may
differ from what the layer prints, as long as the layer gets back to it:

* a section's `code` is its code blocks and its bare-`~run` claims,
  dedented, a blank line apart (`_code_text`); with the `~run` fix, any
  `~run` counts;
* an `EXAMPLE`'s or `RUN`'s `code` is its dedented lines stripped; a
  `PROPERTY`'s is dedented, not stripped;
* a test node's `code` is its bare lines joined with `\n`, then
  stripped, not dedented;
* `add_uses_edges` scans the same strings as today, so its lines do not
  move (slice 3 fixes the line numbers; do not fix them here).

If a value cannot be reproduced from what the forest holds, store what is
needed on the leaf rather than reading the model in the layer. If that
seems wrong, stop and report.

## Tests

**Must not change, and must pass:** `tests/test_check.py` (its guard
included), every `tests/test_cli_*.py`, `tests/test_address_collision.py`,
`tests/test_graph_export.py`, `tests/test_turtle.py`, and the accessor
classes in `tests/test_graph.py` (`TestModuleOf` to `TestClaims`).

**May be rewritten to the new graph**, because they test the in-memory
structure that is changing: the rest of `tests/test_graph.py`,
`tests/test_graph_completeness.py`, `tests/test_graph_package.py`,
`tests/test_graph_symbols.py`, `tests/test_graph_property.py`. Rewrite,
do not delete: an assertion about `DEFINES` or `content` becomes the
same assertion about `CONTAINS`, a leaf's `text`, or an accessor. For
each rewritten test, the report gives the old assertion and the new.

**New:**

1. **Oracle.** A walk of the model written in the test (not reusing
   `build`) lists every element (module, subheading, Appendix, `#Tests`,
   group, assertion run, named test, paragraph, code block, bullet
   list, claim) with its kind, parent, start and end line, in order. For
   every `.lob` file under `examples/`, and for sources covering every
   place an element can be written (body, subheading, Appendix, Appendix
   subheading, `#Tests`, a group), the graph has exactly those nodes,
   with those kinds, parents, positions and order.
2. **Forest.** For every `.lob` file under `examples/`: each node from
   the file except its `MODULE` has exactly one `CONTAINS` parent;
   following parents from any node reaches the `MODULE` with no cycle;
   `CONTAINS` is the only edge between nodes of one tree other than
   `USES` and `REFERENCES`; `EXTERNAL` nodes have no `CONTAINS` edge.
3. **The layer.** For the Roman example, `legacy_graph` of the new graph
   has the same nodes (with `content` and `start_line`) and the same
   edges as `notlob graph --content` printed before this slice, compared
   as sets. Capture that output from the current code into the test as
   data before you change `graph.py`. If the order of nodes or edges in
   the output differs from today's, say so in the report.
4. **The `~run` kinds:** `~run`, `~run on-load` and `~run on-invocation`
   are each a `RUN`, and an unnamed `~property` after them is still
   `property#1`.

## When to stop

Stop and report, with what you have, if:

* a test outside "May be rewritten" fails and the fix is not in the layer;
* a value under "Values that must not move" cannot be reproduced;
* anything needs `model.py`, `check.py`, a binding or a schema;
* the slice is growing past what the brief describes.

## When you are done

Report, without committing:

1. The new `Node` fields and `NodeKind` members, and `legacy_graph`'s
   signature and docstring.
2. That the new tests failed first, and why; then the full suite result
   (`notlobenv/Scripts/pytest`, through Bash).
3. Each rewritten test, old assertion and new.
4. Any CLI-level or check test that changed (the `~run` fix or the
   Appendix), with the reason.
5. A line-length check on the files you changed.
6. Anything you stopped on, and anything outside these files that needs
   changing.

The design session reviews the diff against this brief before it goes to
Adam.

## Amendments, 2026-10-24 (Adam)

After the implementing session stopped on 17 protected tests, all caused
by this brief rather than the work:

1. **Schemas and ontology.** Add `PROSE`, `CODE`, `BULLETS`, `APPENDIX`
   and `TESTS` to the `kind` enum of `name_graph.json` and
   `query_result.json`, and a class for each to `notlob.ttl`, with label
   and comment like the others. Additive: nothing prints them yet. Do
   not narrow the guard tests.
2. **The Turtle tests that compare in-memory nodes with the printed
   Turtle** (`TestEmittedTurtle::test_awkward_titles_and_prose_parse_and_round_trip`,
   `TestGraphFidelity`) may be rewritten to iterate
   `legacy_graph(graph)`. Report the change as for the others.
3. **`TestEdgesAccessor`** (the two tests comparing `edges()` with
   `to_dict()`): rewrite them to test what `edges()` promises (every
   edge, in the order added; filtered by kind) on a small graph built
   with `add_node` and `add_edge`, independent of `build` and the
   output.
4. **A name defined twice in one scope** (two `def f` in a module):
   keep today's behaviour, where the last definition wins: one node,
   contained by the leaf of its last definition only, so the forest
   test holds. Do not give the second one another address. Whether
   redefinition should become an error is open (`design.md` D10).
