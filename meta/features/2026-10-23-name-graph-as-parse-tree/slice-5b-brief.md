# Slice 5b brief: `notlob query` reads the graph

**For:** an implementing session. **Written by:** the design session,
2026-10-26. **Design:** `design.md` in this directory: sections 5 and 6,
D5, and slice 5 in section 9. Read them first, and the 5a brief for the
document `notlob graph` now prints.

## Goal

Every `notlob query` still answers from the temporary layer
(`_require_query_graph` wraps the package graph in `legacy_graph`). From
this slice the queries answer from the graph itself, in the same node
shape as `notlob graph`, and `query content` returns the subtree at an
address. After it, only Turtle (5c) uses the layer.

Two follow-ups from the 5a review come with it: the printed `name`
becomes a `named` flag, and a long line in `LANGUAGE.md` is re-wrapped.

## Rules

* **May touch:** `notlob/commands.py` (the query commands and their
  helpers), `notlob/cli.py` (the `query` subcommands),
  `notlob/mcp_server.py` (the query tools), `notlob/graph.py` (the document
  serialiser, for `named` and for reuse by `query content`),
  `notlob/schema/query_result.json`, `notlob/schema/name_graph.json`
  (`named` only), `notlob/docs/LANGUAGE.md` (the query lines and
  paragraph, and the re-wrap), and tests.
* **Must not touch:** Turtle and `notlob.ttl`, `legacy_graph` (Turtle
  still uses it), the bindings, `check.py`, `model.py`.
* **May be rewritten:** `tests/test_cli_query_json.py` and any other
  test of a query's output, since what they pin is the output this
  slice replaces; the strict xfail on the schema parity test is
  replaced by the parity test below. Report each, old and new.
* **Must not change, and must pass:** `tests/test_turtle.py`,
  `tests/test_graph_layer.py`, `tests/test_check.py`, the test and
  build CLI tests, the collision and one-graph tests.
* **Failing test first;** say that you did. Do not commit or stage.
  80-character lines. No phase or slice wording in code, comments,
  docstrings or docs.

## 1. `named` instead of `name`

In the document `notlob graph` prints, a node with a document name gets
`"named": true` and no `name` (its `label` is the name already); an
anonymous node has neither. `Node.name` stays in the graph: it is the
fact the flag reports. `name_graph.json`'s `GraphNode` changes to match
(`named`, `const: true`).

## 2. The node every query prints

The queries print nodes in the shape of `name_graph.json`'s `GraphNode`
at `outline`: `address`, `label`, `kind`, `named`, `mode`, `file`,
`start_line`, `end_line` where they apply. `query_result.json` defines
its `Node` as exactly that, and the parity test (replacing the xfailed
one) checks the two definitions are equal. No query prints `content`.

## 3. The queries

All of them read the command's one package graph (`_require_graph`);
`_require_query_graph` goes.

| Query | Answers |
|---|---|
| `children <address> [--kind K]` | the targets of `K` edges from the address, `CONTAINS` by default; `K` is any edge kind the graph holds (`CONTAINS`, `IMPORTS`, `USES`, `REFERENCES`, `USES_EXTERNAL`); `DEFINES` is gone from the choices. `CONTAINS` children include anonymous leaves (a paragraph, a code block). |
| `resolve <label> [--context M]` | unchanged rule |
| `search <pattern> [--kind K]` | the nodes `outline` shows whose label matches (so not `prose#1` and the like); `--kind` takes any kind `outline` shows |
| `imports`, `imported-by` | unchanged |
| `callers`, `callees` | `USES` edges, as now (their ends are all shown at `outline`) |
| `references <address>` | the targets of `REFERENCES` edges from the address or from the paragraphs it holds directly, lifted as at `outline` (a section's references are its paragraphs') |
| `referenced-by <address>` | the sources of `REFERENCES` edges to it, each lifted to its nearest shown ancestor, once each |
| `content <address> [--depth N]` | the subtree (below) |

Reuse the lifting `notlob graph` already has (`_document_edges`) rather
than writing it again.

## 4. `query content`

```
notlob query content roman/numerals#Decoding            # the whole subtree
notlob query content roman/numerals#Decoding --depth 0  # the node alone
notlob query content roman/numerals#Decoding --depth 1  # and its children
```

It prints a document in `notlob graph`'s shape at `full`, restricted to
the subtree: `{"version": 2, "level": "full", "root": <address>,
"nodes": [...], "edges": [...]}`, the nodes in document order, the edges
those whose source is in the subtree (`CONTAINS` within it, and the
cross-references from it). `--depth` counts `CONTAINS` steps from the
root, as `find -maxdepth` does. An unknown address prints `null` and
exits 1, as now.

**A symbol's text.** Text is held once, on the leaf it is written in, and
a symbol's is read from its `CODE` leaf by its lines. In a `query
content` answer whose subtree does not include that leaf (asking for the
symbol itself, or `--depth` cutting the leaf off), the symbol node
carries its `text` (from `graph.text()`), so the answer still shows each
line of source once. Asking for `roman/numerals#to_roman` must show its
code.

`query_result.json` specifies this document (it may `$ref` the graph
schema's node and edge definitions, or copy them; the parity test then
covers them either way).

## 5. MCP and docs

The MCP query tools follow: `notlob_query_children`'s `kind` enum without
`DEFINES`; `notlob_query_search`'s `kind` enum the kinds `outline` shows;
`notlob_query_content` takes an optional `depth`. `LANGUAGE.md`: the
query lines in the command list (`content` with `--depth`), the paragraph
on what the queries print, and the Turtle sentence that runs past 80
characters re-wrapped.

## Tests

1. **Each query** on Roman: `children` of a section (paragraphs, code,
   claims, subheadings, in order) and with `--kind USES`; `search` not
   returning anonymous leaves; `references` and `referenced-by` lifted
   (a section's references, a module referenced from a paragraph shows
   the section).
2. **`query content`:** the whole subtree of `##Decoding` with each leaf's
   text once; `--depth 0` and `1`; a symbol alone shows its code; a
   `--depth` that cuts a code block off gives its symbols their text; an
   unknown address is `null` and exit 1.
3. **`named`:** printed on named nodes only, never `name`, at every
   level.
4. **Schemas:** every query's real output validates; the parity test.
5. **Nothing reads the layer** but Turtle: a test that the query
   commands never call `legacy_graph`.

## When to stop

Stop and report if a protected test fails, if Turtle stops working, if a
query needs a fact the graph does not hold, or if the slice grows past
this brief.

## When you are done

Report, without committing: a `query content` sample (`##Decoding` at
`--depth 1`, and a symbol alone); the query table as built; the schema
shape; CLI and MCP changes; that the new tests failed first; the full
suite result; each rewritten test, old and new; a line-length check;
anything you stopped on.
