# Slice 9 brief: the swap

**For:** an implementing session. **Written by:** the design session,
2026-11-04. **Design:** the organising abstraction at the top of
`notlob/docs/DESIGN.md`; `design.md` in this directory, "What a level
is" and the rulings after "How it gets built"; the target,
`notlob/schema/name_graph_next.json` and `tests/test_graph_next.py`. The
fourth of the stages in `slice-6-the-model-brief.md`, after slice 8.

## Why

Slice 8 built the view and its writers beside the old path, and the
target tests pass against them. The swap makes them notlob's: `notlob
graph`, MCP and the queries write the view, and the old path goes. It
lands in 0.6.0 (Adam, 2026-11-03: "needed"), as one commit before
release. Most of it is deletion, and the target tests already say what
must hold when it is done.

## Ruled for this (Adam, 2026-11-04)

* **`query content` is the view from a start**, in 0.6.0. It was the
  last walk of its own, with a second document shape. A view started at
  a symbol showed nothing, since a symbol has no body; the rule that
  fixes it is now in `DESIGN.md`'s abstraction: "A line is in the body
  of the written node that holds it; where a view does not show that
  node, the line is in the body of the deepest node it shows that
  covers it." References move up to what a view shows, and lines to
  where it starts. See "A view from a start" below.
* **A one-file project** (`notlob graph some.lob`, with no `binding.lob`
  above it) has a file: the path passed. Building it without one, and
  without its source, was a confusion in the implementation. The module
  gets the path as given for its `file` and its source read as
  `parse_project` reads it, so every format and every level writes it.
* **`--level` as a number** is the rank, `1` to `4`: "four levels needs
  four numbers". `3` is `block`, `4` is `full`, in the CLI and MCP.
* **`query search --kind`** offers every kind: no list.

The target schema and `tests/test_graph_next.py` already say all of
this (the design session): `file` is on each root of a view, a module
or the node a view starts at; `body` carries the line rule; and
`TestContent` holds `query content`, marked to fail until it is done.

## The change

**The commands write the view.** `notlob graph` takes the view of a
preset and writes it with `write_json`, `write_turtle` or `write_text`,
for a project, including a one-file project; its errors stay as they
are.
`--level` takes the four names, or their ranks, `1` to `4`.
MCP's `notlob_graph` offers the same and says the same in its
description. `cli.py`'s `--level` help says what each level shows,
in a sentence each, from the target schema's `level` description.

**A view from a start.** The view gains the line rule: where it does
not show the written node that holds a line, the line is in the body of
the deepest node it shows that covers it (a node covers the lines from
its `start_line` to its `end_line`). From a whole project, nothing a
view shows changes. `query content ADDRESS` is the view started at
ADDRESS at `full`, its `--depth` the view's depth, in either format:

* **JSON** is the target document, `level` `full`, its root carrying
  `file`. `query_result.json`'s `Content` and `ContentOrNull` go, and
  with them `content_tree`, `text_in_holder` and `Node.text` if nothing
  else reads them (say what does). An address that is not a node is
  `null` and exit 1, as now.
* **Text** is the `full` text of the view: its root's file on a line,
  with the line the view starts at when that is not the first
  (`hello.lob:65`; the design session), then its lines from there. The
  text writer stops padding from line 1 (`_file_lines`): it writes from
  the first line it has. A node with no lines (an `EXTERNAL`) is an
  error, as now.

**The queries print the target's node.** A node a query prints is the
target's node at `outline`: `address`, `name` where it has one, `kind`,
`mode`, `declares`, `value`, `start_line`, with `file` on every node, not
a module only, because an answer stands on its own (the design session,
from today's `node_summary`). No `label` (Adam, 2026-11-03: "nothing
needs it"). `query_result.json`'s `Node` says so, and loses `size`,
`refs` and `text`, and the `GraphRef` and `Edge` definitions, which no
query prints. The test that holds `Node` to the graph's node holds it to
`name_graph_next.json`'s, `file` aside. The text answers are unchanged.

**The old path goes.** `outline.py`'s walk, the old document in
`graph.py` (`to_dict`, `to_json`, `to_turtle`, `parse_level`, `LEVELS`,
`_sizes`, `_node_entry`, `_document_*`, `_cross_references`,
`_lifted_citations`, `_turtle_node` and what only they use),
`hidden_at_outline`, the document's `size` and `refs`, and
`graph_next.py`. `name_graph.json` is deleted and `name_graph_next.json`
takes its name; `notlob docs` writes it as before. `Node.refs`, which
`check` reads for unresolved references, stays: it is the model's, not
the document's. `Edge.first_line` stays while the queries read it.

**What moves.** `_turtle_iri`, `_turtle_lit`, `_turtle_long_lit` and
`turtle_class_name` go to `writers.py`, the only writer of Turtle;
`_find_binding` and `_get_binding_kit` lose their underscore, or move,
as you see fit, so nothing imports a private name across modules.

**The model gains what slice 8 kept out.** `CONTAINS_INDIRECTLY` is an
`EdgeKind`; the view and `EDGE_RANKS` use the member, not its name, and
no graph holds one: only a view writes it. `query children --kind`
offers it only if it can return one; say which you chose.

**Ranges in text** (Adam, 2026-11-04). In the text writer, a run of two
or more consecutive lines is a range, `78-86`, and runs are joined with
`, ` (`28-30`, `59-60`, `12, 15-17`). JSON and Turtle keep every line.

**An appendix in text** (Adam, 2026-11-04). `KINDS` gains a `heading`
field, `"Appendix"` for `APPENDIX` and `None` for the rest. A node of a
kind with a heading says the heading then its name, and the heading once
where the name is the heading: `#Appendix Glossary` is `Appendix
Glossary`, a bare `#Appendix` is `Appendix`. "Wrinkly, and may not
endure, but the right trade for now."

**The ontology.** `notlob.ttl` declares what the writer writes and
nothing else: it gains `notlob:name`, `notlob:body`, `notlob:lines`,
`notlob:containsIndirectly` and `notlob:usesExternal` (for
`uses_external`), and loses `notlob:size`, `notlob:text`, `notlob:ref`,
`notlob:sub` and `uses_external`. The guard that holds it to the writer
(`tests/test_turtle.py`) holds every predicate and class the writer
writes, at every level of every example, to a declaration, and every
declaration to something written.

**The docs.** `LANGUAGE.md`'s `notlob graph` and `notlob query`
sections say what they print now. `CHANGELOG.md`: this is all
unreleased, so rewrite the `[Unreleased]` entries that describe the old
document (three levels, `size`, `refs`, `label`, `text`) to describe what
0.6.0 prints, rather than adding a breaking entry on top of them. In
`DESIGN.md`, the "Label" passage and "anonymous" (lines 336 to 351) are
out of date: list what you find there, and do not edit it (Adam's).

## Rules

* **May touch:** `notlob/` except the grammar and the bindings; tests;
  `notlob.ttl`; `LANGUAGE.md`; `CHANGELOG.md`.
* **Must not touch:** `name_graph_next.json`'s content (it is renamed,
  not edited); `tests/test_graph_next.py` except `_output`, the
  `not_yet` mark and the docstring; `DESIGN.md`; the grammar; the
  bindings.
* **A test of the old path is deleted, not rewritten**, where what it
  holds is gone. If one seems to want rewriting to new behaviour that
  this brief does not name, stop: that is an unruled behaviour.
* **No rank, level name or kind list outside the rank column and the
  presets**, as in slice 8.
* **Failing tests first;** say that you did. Do not commit or stage.
  80-character lines. No slice wording. One shell command per call; use
  `-C`, not `cd`. Plain `pytest` and `ruff` calls.

## Tests

1. `test_graph_next.py`'s `_output` runs `notlob graph` again, in a
   fresh process, the `not_yet` mark is gone, and every test passes,
   `TestContent` included.
2. Slice 8's three breaks, and an indirect edge written as `CONTAINS`
   against `test_an_outline_has_indirect_edges`, each caught through
   `notlob graph`.
3. The text goldens with ranges; the diff of each is ranges alone.
4. A small project with `#Appendix Glossary` and a bare `#Appendix`, as
   text at `outline`, exactly.
5. `notlob graph --level block`, and `--level 3` and `4`; a one-file
   project, as text at `outline` and at `full`.
6. MCP's `notlob_graph` at `block`, as the CLI prints it.
7. A query's JSON validates against `query_result.json`, with `name` and
   no `label`.
8. The ontology guard, both ways.
9. Nothing in `notlob/` names `hidden_at_outline`, `name_graph_next`,
   `graph_next`, `to_dict`, `parse_level`, `_sizes` or `content_tree`.
10. A fifth break: the line rule left out (a started view gives no body
    to a node whose holder it hides), caught by `TestContent`.

## When to stop

Stop and report if a target test or the target schema seems wrong, if a
test of the old path wants rewriting rather than deleting, if a writer
needs a rank or a level's name, if the view needs a kind list, or if this
grows past the brief.

## When you are done

Report: roman at `index` as text, with its ranges; the appendix golden;
`notlob graph --level 3` on roman, its first ten lines; `query content
roman/numerals#to_roman` as text and as JSON; the five breaks
and what caught each; the old tests deleted, by file, and any rewritten
and why; what you chose for `query children --kind`; what you found in
`DESIGN.md`; the full suite; a line-length check; anything you stopped
on.
