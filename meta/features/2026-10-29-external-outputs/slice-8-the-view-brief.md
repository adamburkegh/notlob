# Slice 8 brief: the view

**For:** an implementing session. **Written by:** the design session,
2026-11-03. **Design:** the organising abstraction at the top of
`notlob/docs/DESIGN.md`; `design.md` in this directory, "What a level
is" and the rulings after "How it gets built"; the target,
`notlob/schema/name_graph_next.json` and `tests/test_graph_next.py`. The
third of the stages in `slice-6-the-model-brief.md`, after slices 6 and
7.

## Why

The abstraction: every node, edge and body has a rank, on one scale; a
view is a start, a depth and a rank over the tree; a named level is a
view with a name; a formatter writes a view, and decides nothing. Today
three walks each decide what a level holds (`outline.py`'s, and two in
`graph.py`), with `hidden_at_outline` as their flag. This builds the
one view and the writers of the target beside them. The old path runs
on, untouched, until the swap.

## The change

**Rank** (Adam, 2026-11-02). One scale of natural numbers, with names
for the common ranks: `STRUCTURE` 1, `REFERENCES` 2, `BLOCK` 3, `BODY`
4. It is defined once, in `graph.py`: a `rank` column in `KINDS`, and
the same for the edge kinds. Nothing else decides it.

* **1:** `MODULE`, `SUBHEADING`, `SYMBOL`, `PROPERTY`, `EXAMPLE`,
  `RUN`, `TEST`, `APPENDIX`, `TESTS`, `TEST_GROUP`, `REFERENCES`,
  `BINDING`; the edges `CONTAINS` and `CONTAINS_INDIRECTLY`.
* **2:** `DECLARATION`, `EXTERNAL`; the edges `USES`, `CITES`,
  `IMPORTS` and `USES_EXTERNAL`.
* **3:** `PROSE`, `CODE`, `BULLETS`, `TEST_LINES`, `LISTING`, `IMPORT`,
  `POST_TEXT`.
* **4:** every body.

**Named levels are presets** (Adam, 2026-11-02): `outline` (rank 1),
`index` (2), `block` (3), `full` (4), each the whole tree by default
(Adam, 2026-11-03: "not sure if that will be the final form"). A table
beside `KINDS` holds them, and the view never sees a level's name.
There is no `--rank`, but the view takes a rank so there is room for
one.

**The view.** One function takes a graph, a start (the whole project by
default), a depth and a rank, and gives the nodes, edges and bodies of
that rank or lower:

* **Containment.** A `CONTAINS` edge is always one of the tree's. Where
  the view hides what holds a node, it gives `CONTAINS_INDIRECTLY` from
  the nearest node above that it shows (Adam, 2026-11-03).
* **References.** An edge's source is the nearest node at or above
  where it is written that an `outline` shows, the same at every level;
  references merge on source, target and kind, and their `lines` join,
  in order, each once (Adam, 2026-11-02).
* **Ends.** An edge is in the view only if both its ends are.
* **Depth** counts the steps the view shows (Adam, 2026-11-02). Only
  the whole tree is tested here; what a start and a depth do to an edge
  whose end they leave out may be revisited.

**The writers write the view and decide nothing.** Each takes the view
alone and never asks a kind's rank or branches on a level. A view made
from a preset carries the preset's name, which the JSON writes as
`level`, and nothing else reads (the design session):

* **JSON:** the target document, `name_graph_next.json`. A field is
  named once, in snake_case; a value is spelled as the language spells
  it. `name` where a node has one, `body` at rank 4, no `label`, `size`,
  `refs`, `text` or `named`.
* **Turtle** (Adam, 2026-11-03): a node's kind as its class, as now
  (`notlob:TestLines`; the design session), and its fields as literals,
  named in camelCase from the JSON's; every edge a triple, its kind in camelCase
  the predicate; an edge with lines also an `rdf:Statement` about that
  triple, carrying them as `notlob:lines`, one value a line. RDF 1.2's
  annotation would say the same, but rdflib 7.6 cannot read it.
* **Text** (Adam, 2026-11-03), as slice 3's form for a reader: each
  file's path on a line alone, its lines under it, a blank line between
  files; a line's words on the left, indented two spaces a step, its
  line numbers right aligned in a column. A heading, group, module or
  symbol says its name; a claim or test its sigil and name; a
  declaration `~language python`; a positional node the end of its
  address (`prose#1`, `test#1`). A reference is `uses <name>`, `cites
  <name>`, `imports <name>` under its source, in line order among what
  else is there, with every line it is on. At `full`, each file's path
  and then its bodies in order, and nothing else: a symbol or a
  reference is written in a body. `var/block_text_sketch.py` draws
  `block` from the scratch target; read it, do not import it.

`var/target_doc.py` is a scratch stand-in for the view and the JSON and
Turtle writers, and passes every test of `test_graph_next.py`. Read it
for the rules; do not import or copy its shape.

**The target tests run the view.** `test_graph_next.py`'s `_output` is
the one place they run notlob. Point it at the new writers, still in a
fresh process (the determinism test sets `PYTHONHASHSEED`; the design
session), and take off the `not_yet` marks. At the swap it goes back
to `notlob graph`.

**The old path is untouched:** the commands, MCP, `query`,
`hidden_at_outline`, the old writers and walks, `name_graph.json`,
`notlob.ttl`. The swap moves them. The new Turtle uses terms the
ontology does not declare yet (`notlob:body`, `notlob:lines`,
`notlob:containsIndirectly`); the swap adds them, with the guard that
holds the ontology to the writer (the design session).

## Rules

* **May touch:** `notlob/graph.py` (the rank column, the edge kinds'
  ranks, the presets), new modules for the view and its writers (their
  names and layout are yours; say what you chose), tests.
  `test_graph_next.py`: `_output` and the marks only.
* **Must not touch:** `name_graph_next.json`, the rest of
  `test_graph_next.py`, `DESIGN.md`, the old path above, the grammar,
  the bindings, what any command prints.
* **No rank, level name or kind list outside the rank column and the
  presets.** If a writer seems to need one, stop: it is a missing rank
  or a missing node.
* **Failing tests first;** say that you did. Do not commit or stage.
  80-character lines. No slice wording. One shell command per call; use
  `-C`, not `cd`. Plain `pytest` and `ruff` calls.

## Tests

1. `test_graph_next.py` passes whole, unmarked, against the new writers.
2. Break the writers three ways, one at a time, and show the target
   tests catch each: an indirect edge written as `CONTAINS`; references
   left where they are written; Turtle without its statements.
3. The rank column covers every `NodeKind` and `EdgeKind`, and the
   presets are the four above.
4. Roman's `numerals.lob` as text at each of the four levels, exactly.
   At `full`, the text of every example is its files, each under its
   path.
5. Retail as text at `index` and `block`, exactly.
6. The old documents of every example are as they were
   (`var/test_baseline_s7.py`).

## When to stop

Stop and report if the target schema or a target test seems wrong, if a
writer needs a rank or a level's name, if the view needs a kind list,
if anything in the old path would change, or if this grows past the
brief.

## When you are done

Report: roman at `block` as text; one reference edge with several lines
in JSON and in Turtle; where the view and the writers live; the three
breaks and what caught each; that the new tests failed first; the full
suite; a line-length check; anything you stopped on.
