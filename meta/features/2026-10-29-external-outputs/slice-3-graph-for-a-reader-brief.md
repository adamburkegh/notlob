# Slice 3 brief: `graph` answers a reader, and a level is one content

**For:** an implementing session. **Written by:** the design session,
2026-10-30. **Design:** `design.md` in this directory: "The reader form
of the graph", "A level is the same content in either form", decisions
2, 4, 6, 8 and 9; Adam, 2026-10-30. After slice 2.

## Why

`notlob graph` at `outline` is not an outline: retail's is 5,283 bytes
for a 2,363-byte file. A reader, a person or an LLM, wants the shape of
the project in the file's own words; a program wants the document. And
a level should mean the same content in either form.

## The change

**`notlob graph [--level L] [--format text|json|turtle]`, default
`text`.** `graph` is the whole project, as now. The file argument and
`-m` stay as they are.

### Text

For each module, in the graph's order, with a blank line between: its
file on a line alone, relative to the project root, then its lines.

```
pricing/discounts.lob
Pricing Discounts                        1
  cites Stacking Discounts               9
  apply_discount                        11
  ~example                              14
    uses apply_discount                 15
  Stacking Discounts                    17
    ~example                            26
      uses apply_discount               27
    ~property                           31
      uses apply_discount               43
  Tests                                 48
    boundary conditions                 50
      uses apply_discount               51
    composition                         55
      cites Stacking Discounts          58
      ~test composition_is_commutative  61
        uses apply_discount             62
  References                            69

binding.lob
Pricing                1
  Binding              8
    ~language python   9
```

* **The name first, the line number in a column on the right,** right
  aligned, two spaces past the file's longest entry; the column is set
  per file.
* **Indented by what is written in what**, two spaces a step, in line
  order. A node `outline` leaves out is not a line: what it holds
  belongs to the node above it, as at `outline` in the document.
* **What a line says.** A heading, group or module: its name, no hashes.
  A symbol: its name. A claim or named test: its sigil, then the name
  if it has one (`sigil_of`). A run of bare assertions has no line of
  its own; its references belong to its group. `POST_TEXT` has no line.
* **`outline`:** those lines. **`index`:** and, indented under the node
  that holds them, in line order, one line for each cross-reference
  written there: `uses <name>`, `cites <name>`, `imports <name>`
  (under `References`), at the line it is written on. `<name>` is what
  follows the last `#` of the target's address, or a module's title.
  At `index` the `#Binding` declarations are lines too: `~language
  python`, `~external index.html`. A reference repeated in one node is
  one line, the first.
* **`full`:** each module as `query content` prints it, in turn, by the
  same code.

Put the line layout in one place; slice 2's `_columns` is a different
layout, so do not bend either to fit. A later `query outline` would
print with this code, so keep it working on a node, not only a project.

### JSON and Turtle

A level is the same content in either form:

* **`outline`: the cross-references leave.** `edges` holds `CONTAINS`
  only. `USES`, `CITES`, `IMPORTS` and `USES_EXTERNAL` arrive at `index`.
* **`end_line` leaves** the graph document, `node_summary`, and
  `content_tree`'s root, at every level, and `notlob:endLine` leaves the
  ontology and the Turtle. The model keeps it. `query content`'s text
  header keeps `file:40-60`: it says what it printed.

Careful: `cites_of`, `cited_by` and their edges in `graph.py` read
`_document_edges(graph, "outline")` for the lifted edges. They must
answer as now. Keep the lifting; it stops being what the document
writes at `outline`, so give it a name of its own.

`version` stays `2`: unreleased.

The MCP `notlob_graph` tool takes no format, so it answers in text, as
slice 2's did. The schema of `level` in its definition is unchanged.

## Rules

* **May touch:** `notlob/graph.py`, `notlob/commands.py`, `notlob/cli.py`
  (the options and the help, which must say that `uses` and `cites` are
  at `--level index`), `schema/name_graph.json`,
  `schema/query_result.json`, `schema/notlob.ttl`, `LANGUAGE.md`,
  `USER-AGENTS.md` (say `outline` is the default and `--level index`
  adds the references: the risk in decision 4), the CHANGELOG (Unreleased:
  breaking; a program adds `--format json`, and `--level index` for
  cross-references), tests.
* **Must not touch:** the model's `end_line`, the bindings, the grammar,
  `query`'s text.
* **Assertions may change** in the tests of the graph document, Turtle,
  and query JSON, for the moves above, and most graph calls gain
  `--format json`. Report the kinds of change, and each one that is more
  than that.
* **Failing tests first;** say that you did. Do not commit or stage.
  80-character lines. No slice wording. One shell command per call;
  use `-C`, not `cd`. Plain `pytest` and `ruff` calls.

## Tests

1. Retail at `outline` and `index`, exactly, as text.
2. Gutenberg at `index`: `imports Gutenberg Corpus` under `References`
   at 87, and the cross-module `uses load_play` at 9.
3. Over every example at `outline` and `index`: every line number is
   real: the file's line at that number holds the name printed.
4. Each line of `index` not in `outline` is a `uses`, `cites`, `imports`
   or a declaration; `outline`'s lines are all in `index`, in order.
5. `full` is `query content` of each module.
6. JSON `outline` holds only `CONTAINS`; no document or query answer
   has `end_line`, at any level; all validate against their schemas;
   `tests/test_field_or_edge.py` still holds.
7. `query cites` and `cited-by` answer as before.
8. Text is smaller than the file it outlines, for every module of every
   example, at `outline`.

## When to stop

Stop and report if a reference's holder has no line under these rules,
if anything else reads the outline-level edges from the document, or if
the slice grows past this brief.

## When you are done

Report: retail and gutenberg at `index`, as printed; the kinds of
assertion changed, and any that is more than a flag; that the new tests
failed first; the full suite; a line-length check; anything you stopped
on.
