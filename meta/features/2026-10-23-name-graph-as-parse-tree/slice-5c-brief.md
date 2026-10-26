# Slice 5c brief: Turtle prints the graph, and the layer goes

**For:** an implementing session. **Written by:** the design session,
2026-10-26. **Design:** `design.md` in this directory: section 5 and
slice 5 in section 9; the 5a and 5b briefs for the JSON document and
the queries. Read them first.

## Goal

Turtle is the last output still printed through the temporary layer.
From this slice it prints the graph at the same three levels as the
JSON, and then everything that existed only to reproduce the old shape
is deleted: `legacy_graph` and its helpers, `legacy_dict`, the `DEFINES`
edge kind, `Node.content`, and the snapshot tests.

## Rules

* **May touch:** `notlob/graph.py`, `notlob/schema/notlob.ttl`,
  `notlob/commands.py` (`cmd_graph`), `notlob/cli.py` (the `graph`
  options), `notlob/mcp_server.py` (only to drop its `DEFINES`
  filter), `notlob/docs/LANGUAGE.md` and `DESIGN.md` (their Turtle
  lines only), and tests.
* **Must not touch:** the bindings, `check.py`, `model.py`, the JSON
  schemas (the JSON documents do not change).
* **May be rewritten:** `tests/test_turtle.py` (it pins the old Turtle);
  the tests that build a graph by hand with a `DEFINES` edge or read
  `content` (`tests/test_check.py`'s helper at line 26, which builds a
  graph for the checks, may use `CONTAINS` instead, its assertions
  unchanged; `tests/test_graph.py`'s hand-built edges; the layer tests
  in `tests/test_graph_forest.py` and `tests/test_graph_symbols.py`);
  `tests/test_graph_export.py`'s `TestContent`. Report each, old and new.
* **Delete:** `tests/test_graph_layer.py` and the `graph_*.json`
  snapshots in `tests/data/` (with their part of its README; the
  `claims_*.json` stay). They are the record of the old output and stay
  in the history.
* **Must not change, and must pass:** `tests/test_cli_query_json.py`,
  `tests/test_cli_graph.py`'s JSON tests, `tests/test_graph_levels.py`,
  the claims, collision and one-graph tests, the rest of
  `tests/test_check.py`.
* **Failing test first;** say that you did. Do not commit or stage.
  80-character lines. No phase or slice wording anywhere.

## 1. Turtle at the three levels

```
notlob graph --format turtle                  # outline
notlob graph --format turtle --level full
```

`to_turtle(base=None, level="outline")` writes the same nodes and edges
as `to_dict(level)`, lifting included (reuse `_document_edges` and the
node selection). For each node:

```turtle
<roman/numerals#to_roman> a notlob:Symbol ;
    rdfs:label "to_roman" ;
    notlob:address "roman/numerals#to_roman" ;
    notlob:file "roman/numerals.lob" ;
    notlob:startLine 19 ;
    notlob:endLine 25 .
```

with `notlob:named true` on a named node, `notlob:mode` on a `RUN`; at
`index`, `notlob:size`, and on a `PROSE` leaf each reference as
`notlob:ref [ rdfs:label "..." ; notlob:sub true|false ;
notlob:startLine n ]`; at `full`, `notlob:text` on each node that holds
text. Edges are triples, `notlob:contains`, `notlob:references`,
`notlob:uses`, `notlob:imports`, `notlob:uses_external`, as now without
their lines (RDF has no place for them short of reification; the JSON
carries them).

`--content` goes from the CLI entirely; `--level` works with both
formats.

**Class names.** The ontology names a class by `kind.name.capitalize()`
today, which gives `notlob:Post_text` and `notlob:Test_group`. Use
**UpperCamelCase**, the RDF convention, `notlob:PostText` and
`notlob:TestGroup` (single words unchanged: `notlob:Module`), and change
the emitter, the ontology and the guard test to one function for it.

## 2. The ontology

`notlob/schema/notlob.ttl` declares exactly what the emitter writes: a
class per node kind (UpperCamelCase, with label and comment);
`notlob:address`, `file`, `startLine`, `endLine`, `named`, `mode`,
`size`, `text`, `ref` and the reference's `sub`; the five edge
properties. `notlob:defines`, `notlob:prose` and `notlob:code` go. The
guard tests (every kind a class, every property the emitter writes
declared, and nothing declared that it never writes) run at every level.

## 3. What goes

From `graph.py`: `legacy_graph`, `legacy_dict`, and everything only they
use (`_legacy_content`, `_print_node`, `_print_tests`,
`_print_definitions`, `_reference_holder`, `_group_code`, `_tests_code`,
`_printed_source`, `_earliest_uses`, and any other); `NameGraph._legacy`;
the `DEFINES` member of `EdgeKind` and `add_edge`'s branch that takes a
`DEFINES` edge as a parent; the `content` field of `Node` (and
`_node_content`). `_is_anonymous_test` stays only if something outside
the old printing uses it (`claims_to_run`, `_scanned_text`): if so, it is
`node.kind == NodeKind.TEST and node.name is None` with a docstring that
says what it tells apart and nothing about printing.

Then: the `DEFINES` filters in `commands.py` and `mcp_server.py` become
plain lists of the edge kinds; the module docstring of `graph.py` loses
its sentence about `legacy_graph`; `subtree`'s docstring stops saying
`depth` can leave a symbol without its code block (it cannot: a symbol
is a child of its block, so only asking for the symbol does that).

A test that the names above no longer exist in `notlob.graph`, and that
no `notlob` module imports `legacy`, closes the layer for good.

## 4. Docs

`LANGUAGE.md`'s Turtle sentence and `DESIGN.md`'s `notlob graph` line say
that Turtle comes at the same levels. Nothing else.

## Tests

1. **Turtle at each level** parses (rdflib) for every example project,
   and its nodes, edges and literals agree with `to_dict` at the same
   level (same addresses, kinds, edges after lifting, same text).
2. **The ontology guards** at every level, with the UpperCamelCase class
   names.
3. **Awkward addresses and text** (the existing round-trip cases) at
   `full`.
4. **The layer is gone** (above).

## When to stop

Stop and report if a protected test fails, if something outside the
listed names still needs the layer, if a JSON output changes, or if the
slice grows past this brief.

## When you are done

Report, without committing: a Turtle sample for Roman's `##Decoding` at
`index`; the ontology's classes and properties; what was deleted, with
line counts; that the new tests failed first; the full suite result;
each rewritten or deleted test; `graph.py`'s length before and after; a
line-length check; anything you stopped on.
