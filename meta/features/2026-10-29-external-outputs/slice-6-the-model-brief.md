# Slice 6 brief: the model says what the target needs

**For:** an implementing session. **Written by:** the design session,
2026-11-03. **Design:** `design.md` in this directory, "What a level
is", and the organising abstraction at the top of `notlob/docs/DESIGN.md`.
The first of the stages below. The decisions marked *ruled* were the
design session's proposals; Adam ruled on them, 2026-11-03.

## The stages

The target is two files on disk: `notlob/schema/name_graph_next.json`
and `tests/test_graph_next.py`. The old path, `name_graph.json` and what
writes it, runs until the swap, so notlob-vids keeps working. Each stage
leaves the suite green and gets its own brief, written when the one
before it is done.

1. **The model** (this brief): `TEST_LINES`, appendices named by their
   titles, `name` on every named node, "positional".
2. **Bodies and lines:** each written node's own lines, verbatim; a
   reference is one edge per source, target and kind, with every line
   it is written on, which needs all three bindings' `extract_calls`.
3. **The view:** `rank` in `KINDS`, the named levels as presets, one
   selection, and the JSON and Turtle writers of the target.
   `test_graph_next.py`'s `_output` points at them and its marks come
   off. Open, Adam's: how Turtle writes an edge's `lines`, and what the
   text form shows at `block`.
4. **The swap,** one commit before release: the commands, MCP and
   `query` move to the view; the old walks, `hidden_at_outline`,
   `size`, `refs` and `name_graph.json` go. Open, Adam's: whether
   `query`'s JSON loses `label` too.
5. **notlob-vids moves.**

## Why

Rank must be a fact of a kind, and two things shared `TEST`: a run of
test lines, rank 3, and `~test <name>`, rank 1 (Adam, 2026-11-03). An
appendix's address is positional, though its author names it. And
`name` is set on headings, groups and named claims, but not on modules,
symbols or appendices, whose names the target writes.

## The change

**`TEST_LINES`.** A new `NodeKind` for a run of bare assertions in a
test group; `TEST` is `~test <name>` alone (Adam, 2026-11-03). `TEST`
always has a name, so its row in `KINDS` loses `segment`, `numbered` and
`sigil_needs_name`; if nothing else reads `sigil_needs_name`, it goes,
and `_is_anonymous_test` with it. *Ruled:* `TEST_LINES` keeps the
segment `test`, so no address changes
(`roman/numerals#Tests#encoding#test#1` stays).

**An appendix is named by its title** (Adam, 2026-11-02).
`#Appendix Glossary` is `mod#Glossary`, with name `Glossary`; a bare
`#Appendix` is `mod#Appendix`. Their contents' addresses follow. A
title written twice in a file, or two bare appendices, is an address
collision, as two `##Glossary` headings are, and so is `#Appendix
Glossary` beside `##Glossary`. *Ruled:* a bare appendix's name is
`Appendix`, the word its author wrote, since its address is built from
it. The `title` the model gives (`#Appendix Glossary`) does not change;
the name is what follows the word.

**`name` on every named node** (Adam, 2026-11-02): a module's title, a
symbol, an `EXTERNAL`'s file, an appendix's name, beside the heading,
group, named claim and test that have it now. A positional node has
none. `label` stays as it is: the old document writes it.

**"Positional"** (Adam, 2026-11-02). `anonymous_address` becomes
`positional_address` and is in `__all__`; `_anonymous_identity` and the
rest follow. "Anonymous" stays only for a claim or test that could have
a name and has none, as an unnamed `~property`.

**The old path carries the model.** *Ruled:* `name_graph.json` and
`query_result.json` gain `TEST_LINES` in their kind lists, and
`notlob.ttl` the class `TestLines`, so the old documents stay valid.

**`named` goes now** (Adam ruled it goes; 2026-11-03: now, not at the
swap). With `name` on every named node, `named` would turn true on
every module and symbol. It leaves `_what_it_is`, `content_tree`,
`_turtle_node`, both old schemas and `notlob.ttl`. No other field of an
old document changes.

**`notlob test --json` says which.** *Ruled:* `test_result.json`'s
kind list (`EXAMPLE`, `PROPERTY`, `TEST`) gains `TEST_LINES`, and a run
of test lines reports it, as a result names the kind of what ran.

## Rules

* **May touch:** `notlob/graph.py`, `notlob/__init__.py`,
  `notlob/project.py` (an `EXTERNAL`'s name), `notlob/outline.py` (so
  the old outline prints no line for `TEST_LINES`, as it prints none
  for a run of lines today), what reports a test result's kind, the
  kind lists and `named` in `schema/name_graph.json`,
  `schema/query_result.json` and `schema/test_result.json`,
  `schema/notlob.ttl` (the one class, and `named`), `weave/markdown.py`
  (if it reads the kind), `LANGUAGE.md` (the appendix rule, and
  "positional"), the CHANGELOG (Unreleased: breaking, the kind, the
  appendix addresses and `named`), tests.
* **Must not touch:** `name_graph_next.json`, `test_graph_next.py`,
  `DESIGN.md`, the grammar, the bindings, any other field of any
  document, what any command prints but the moves above.
* **Every reader of `Node.name`** (in `graph.py` and `outline.py` at
  least): some read "no name" as "anonymous". Report each and what
  it does now that modules and symbols have one.
* **Assertions may change** where a test names `TEST` for a run of
  lines, an appendix's address, `named`, or `anonymous_address`.
  Report the kinds of change, and each that is more than that.
* **Failing tests first;** say that you did. Do not commit or stage.
  80-character lines. No slice wording. One shell command per call; use
  `-C`, not `cd`. Plain `pytest` and `ruff` calls.

## Tests

1. Over every example: no `TEST` without a name, and no `TEST_LINES`
   with one; roman's `##encoding` lines are `TEST_LINES` at the address
   they had, and `~test mcmxciv` is `TEST` with name `mcmxciv`. `notlob
   test --json` on roman reports both kinds.
2. `#Appendix Glossary` is `mod#Glossary`, name `Glossary`, and a
   paragraph in it is under that address; bare `#Appendix` is
   `mod#Appendix`; each holds no `#` past the module's.
3. Each is a collision: two `#Appendix Glossary`, two bare `#Appendix`,
   `#Appendix Glossary` and `##Glossary`. `#Appendix Glossary` and a
   bare `#Appendix` together are not.
4. Over every example: every node whose address is built from a name
   has `name`, and it is what follows the last `#` of the address, or a
   module's title; no positional node has one.
5. `positional_address` is public and `anonymous_address` is gone.
6. Every old document validates against its schema, and the old
   Turtle against the ontology's guard; none has `named`.
7. `test_graph_next.py`: its 18 pass and the rest stay xfail, none
   passing.

## When to stop

Stop and report if any value of an old document changes but a kind, an
appendix's address and `named`, if a reader of `Node.name` cannot keep its
meaning without a rule of its own, if a `.lob` file in the repository
now collides, or if this grows past the brief.

## When you are done

Report: an appendix and a run of test lines as the old document writes
them; the readers of `Node.name` and what each does; the assertions
changed; that the new tests failed first; the full suite; a line-length
check; anything you stopped on.
