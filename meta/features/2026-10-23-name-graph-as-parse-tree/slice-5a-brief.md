# Slice 5a brief: `notlob graph` prints the graph

**For:** an implementing session. **Written by:** the design session,
2026-10-25. **Design:** `design.md` in this directory: sections 1, 2 and
5, D18, and slice 5 in section 9. Read them first.

## Goal

`notlob graph` still prints the old shape, through the temporary layer
(`legacy_graph`). From this slice it prints the graph itself, at one of
three levels of detail, and the JSON schema says so. Only the JSON
export of `notlob graph` (and the MCP tool that calls it) changes here:
`notlob query` (5b) and Turtle (5c) stay on the layer for now, so the
layer stays.

## Rules

* **May touch:** `notlob/graph.py`, `notlob/commands.py` (`cmd_graph`),
  `notlob/cli.py` (the `graph` subcommand), `notlob/mcp_server.py` (the
  `notlob_graph` tool), `notlob/schema/name_graph.json`,
  `notlob/docs/LANGUAGE.md` (its `notlob graph` lines and the paragraph
  on the graph's schema), `notlob/docs/DESIGN.md` (the one `notlob
  graph` line in its command list), and tests.
* **Must not touch:** `notlob query` and its schema, Turtle and
  `notlob.ttl`, the bindings, `check.py`, `model.py`.
* **May be rewritten:** `tests/test_cli_graph.py`,
  `tests/test_graph_export.py`, and the schema tests of the graph, since
  what they pin is the output this slice replaces. Report each, old and
  new. `tests/test_graph_layer.py` changes only to print the layer with
  the old serialiser (below).
* **Must not change, and must pass:** `tests/test_cli_query_json.py`,
  `tests/test_turtle.py`, `tests/test_check.py`, the other CLI tests,
  the collision and one-graph tests.
* **Failing test first;** say that you did. Do not commit or stage.
  80-character lines. No phase or slice wording in code, comments,
  docstrings or docs.

## The document

```json
{"version": 2, "level": "outline",
 "nodes": [{"address": "roman/numerals#to_roman", "label": "to_roman",
            "kind": "SYMBOL", "file": "roman/numerals.lob",
            "start_line": 19, "end_line": 25}, ...],
 "edges": [{"source": "roman/numerals#Decoding",
            "target": "roman/numerals#from_roman", "kind": "CONTAINS"},
           ...]}
```

Every node has `address`, `label`, `kind`, and `file`, `start_line`,
`end_line` when known. A node with a document name also has `name`; a
`RUN` has `mode` (D18: what the graph holds, it prints). Edges are as the
graph holds them: `CONTAINS`, `REFERENCES`, `USES`, `IMPORTS`,
`USES_EXTERNAL`, each with `start_line` when it has one. No `DEFINES`,
no `content`.

| Level | Nodes | Adds |
|---|---|---|
| 1 `outline` (default) | every node but the anonymous leaves (`PROSE`, `CODE`, `BULLETS`) | |
| 2 `index` | every node | `refs` on a `PROSE` leaf; `size` on every node |
| 3 `full` | every node | `text` on each node that holds text |

* **Lifting** (`design.md` section 5): at `outline`, an edge to or from a
  hidden leaf is attached to the leaf's nearest shown ancestor along
  `CONTAINS`; edges that then repeat (same source, target, kind) are
  merged, keeping the earliest `start_line`; `CONTAINS` edges to hidden
  leaves are dropped. A symbol's `CONTAINS` from its `CODE` leaf becomes
  one from the section; a `REFERENCES` from a paragraph becomes one from
  its section.
* **`size`:** the characters of text held at or under the node (each
  leaf's `text` counted once; a symbol holds none of its own, so it adds
  nothing to its section and its own `size` is the length of
  `graph.text()`). An agent reads it to budget before asking for `full`.
* **`text` at `full`:** the leaves' text, each piece once; a symbol has
  none (its lines are in its `CODE` leaf).

## The command

```
notlob graph                      # outline
notlob graph --level index        # or --level 2
notlob graph --level full         # or --level 3
```

`--content` goes; `--level` takes the name or the number, and an error
names the choices. `--format turtle` is unchanged and still prints the
layer's Turtle (and still takes `--content` for that) until 5c: keep
whatever the Turtle path needs, but only there. The MCP `notlob_graph`
tool takes `level` instead of `content`.

`NameGraph.to_dict(level="outline")` and `to_json(..., level=...)` write
the new document. The layer's old dict, which `tests/test_graph_layer.py`
compares with its snapshots, moves to a function of its own
(`legacy_dict(graph, include_content)`), used only there and by nothing
the user can call; the layer test calls it instead of `to_dict`.

## The schema

`notlob/schema/name_graph.json` describes the new document: `version`
(2), `level`, nodes with the fields above (which ones each level
carries), edges without `DEFINES`. One schema for the three levels; the
`level` says which optional fields to expect. The schema test validates
real output at each level for every example project.

## Docs

`LANGUAGE.md`'s `notlob graph` line and the paragraph on the graph's
schema say what is true now: the levels, `--level`, what each adds.
`DESIGN.md`'s command list line for `notlob graph` gains the levels
(they exist now). Keep both short; no history.

## Tests

1. **Each level**, on Roman and on a source with every kind of node:
   which nodes, which fields; `--level 2` the same as `--level index`;
   an unknown level is an error.
2. **Once:** at `full`, for every example project, each leaf's text
   occurs once in the document, and no symbol has `text`.
3. **Nesting:** `index` is `full` without `text`; `outline` is `index`
   with the anonymous leaves hidden and their edges lifted (implement
   the lifting in the test independently of the serialiser, from
   `index`, and compare).
4. **Lifting**, by hand: a symbol's and a reference's edges at
   `outline`; two references from two paragraphs of one section to one
   target merge, keeping the earlier line.
5. **Schema:** every level of every example validates.

## When to stop

Stop and report if a protected test fails, if the Turtle path cannot keep
working on the layer, if a field the table lists is not in the graph, or
if the slice grows past this brief.

## When you are done

Report, without committing: a short `outline` and `index` sample for
Roman's `##Decoding`; the lifting as built; the schema's shape; the CLI
and MCP changes; that the new tests failed first; the full suite result;
each rewritten test, old and new; a line-length check; anything you
stopped on.

## Amendments, 2026-10-26 (Adam)

Three protected tests compared the new graph document with outputs still
on the layer:

1. `tests/test_turtle.py::TestGraphFidelity::test_edges_are_exactly_the_graphs_edges`
   compares Turtle's edges with `legacy_dict(project_graph)["edges"]`
   while Turtle prints the layer.
2. `tests/test_cli_query_json.py::TestSchema::test_kind_enums_are_the_real_kinds`
   reads `name_graph.json`'s new node and edge definitions, with the
   edge enum equal to every `EdgeKind` but `DEFINES`.
3. `tests/test_cli_query_json.py::TestSchema::test_node_and_content_match_the_name_graph_schema`
   becomes `xfail(strict=True)`, its reason saying the queries' schema
   still describes their printed shape and the parity returns when the
   queries print the graph. Its assertions do not change.
