# Slice 8e brief: the graph document says each thing once

**For:** an implementing session. **Written by:** the design session,
2026-10-27. **Decision:** Adam, 2026-10-27, after an alpha read by
notlob-vids. After 8d.

## Why

`roman/numerals.lob` is 3,022 bytes; its outline (`notlob graph`) is
9,467. The set of nodes is right. The bulk is repetition: every node
carries a `label` that its address already says, and the `file` its
module already has. `graph` is the export, so it keeps the standard
shape of nodes and an edge list, with `CONTAINS` an edge like the
others, as Turtle writes it.

**Amended, 2026-10-27:** this brief first also moved the tree into a
`parent` field on each node, out of `edges`. Adam rejected it: it
changes the export's shape for one edge kind, it is not repetition
(a symbol's address does not say the section it is written in), the
parent it gave varied with the level, and Turtle had to turn it back
into `contains` triples. Item 4 below is now the reverse: `CONTAINS`
stays in `edges`.

## The change

At every level unless stated:

1. **`label` on `MODULE` nodes only.** A module's label is its title
   ("Roman Numerals"), which its address does not keep. Any other node's
   label follows from its address: a named node's is what follows the
   last `#`; an anonymous node's is its kind's segment and ordinal
   (`example#1`), or the segment alone for a kind that is not numbered
   (`post-text`). An `EXTERNAL` has no label; its address is its name.
   (A `#` in a name is a known bug, fixed separately; do not work
   around it.)
2. **`file` on `MODULE` nodes only.** A node's module is the part of
   its address before the first `#`, for every kind but `MODULE` (its
   own) and `EXTERNAL` (none). Externals already carry no `file`.
3. **`POST_TEXT` is hidden at `outline`**: `hidden_at_outline=True` in
   `KINDS`, so its children (`#Tests`, `#References`, `#Binding`) have
   the module as parent there, and its edges move up as any hidden
   node's do (the `CONTAINS` edges into them come from the module at
   `outline`). It stays at `index` and `full`.
4. **No `parent` field; `CONTAINS` stays in `edges`**, lifted as before,
   one edge into every node but a module and an `EXTERNAL`.
5. **`nodes` is in writing order**: each module, then what is written
   in it depth first, siblings by `start_line`; `EXTERNAL` nodes last,
   in the order they were added. Today symbols come after everything
   else in their module. The `CONTAINS` edges are written in the same
   order, so a node's children come in the order they are written, and
   before the cross-references, which follow in the order added (Adam,
   2026-10-27).

Turtle writes what the JSON does at the same level: `rdfs:label` and
`notlob:file` on modules only, and the tree as `notlob:contains`
triples from the `CONTAINS` edges, so `schema/notlob.ttl` does not
change.

`version` stays `2`: version 2 has not been released.

**Not changed:** `query`'s answers. `node_summary` keeps its shape
(`label` and `file` on every node it prints): a query answer stands on
its own, with no module node beside it to look `file` up in. Separate
it from the document's node entry rather than pass flags through one.
The edge queries (`cites`, `cited-by`, which read `_document_edges`)
must answer as now.

## Rules

* **May touch:** `graph.py` (the document and Turtle writers, `KINDS`
  for `POST_TEXT`), `schema/name_graph.json` (`label` and `file`
  described as above, `nodes`' order, `POST_TEXT` at `outline`),
  `LANGUAGE.md` and `USER-AGENTS.md` where they describe the document,
  the CHANGELOG's Unreleased name-graph entry (fold this in; do not add
  a second entry), tests.
* **Must not touch:** the model, the grammar, the bindings, `query`'s
  answers, `schema/query_result.json`, `schema/notlob.ttl`.
* **Assertions may change** only in the tests of the graph document and
  of Turtle. Report each, old and new.
* **Failing tests first;** say that you did. Do not commit or stage.
  80-character lines. No slice wording. Plain `pytest` and `ruff` calls.

## Tests

1. **Nothing said twice**, over every example project at every level:
   no node but a module has `label` or `file`; for every other node but
   an `EXTERNAL`, the label the graph holds equals the one derived from
   its address by rule 1 (so the rule is checked against the builder,
   not restated).
2. **The tree:** every node but a module and an `EXTERNAL` has exactly
   one `CONTAINS` edge into it, at every level.
3. **Order:** `nodes` is in writing order as rule 5 says, and so are
   each node's outgoing `CONTAINS` edges; in roman, `from_roman` comes
   after `#Decoding` and before `#Decoding#example#1`.
4. `POST_TEXT` appears at `index` and `full`, not at `outline`, where
   its children's `CONTAINS` edge comes from the module.
5. Turtle at each level: the same nodes, with `contains` triples equal
   to the `CONTAINS` edges; it still parses as the existing Turtle
   tests parse it.
6. `query` answers are unchanged: a `node_summary` still has `label`
   and `file`; `cites` and `cited-by` give what they gave.
7. The document validates against `name_graph.json` at every level.

## When to stop

Stop and report if a node's label is not what rule 1 derives (that is a
naming bug to fix in the builder, not a case for the schema), if
anything but the document, Turtle and the edge queries reads
`_document_nodes` or `_document_edges`, or if the slice grows past this
brief.

## When you are done

Report, without committing: roman's outline before and after (bytes,
nodes, edges); each assertion changed, old and new; that the new tests
failed first; the full suite; a line-length check; anything you stopped
on.
