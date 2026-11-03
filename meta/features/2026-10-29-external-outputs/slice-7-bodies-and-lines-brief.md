# Slice 7 brief: bodies and lines

**For:** an implementing session. **Written by:** the design session,
2026-11-03. **Design:** `design.md` in this directory, "What a level
is"; the organising abstraction at the top of `notlob/docs/DESIGN.md`;
the target, `notlob/schema/name_graph_next.json`. The second of the
stages in `slice-6-the-model-brief.md`, after slice 6.

## Why

The target writes two things the model does not hold. A written node's
`body` is its own lines, verbatim: "Full means full" (Adam,
2026-11-02), so the bodies of a file, each at its `start_line`, are the
file. And a reference is one edge for each source, target and kind,
with every line it is written on (Adam, 2026-11-02: "per target is what
looks right"). Today an edge keeps one line, and every binding's
`extract_calls` keeps only the first line a name is used on.

## The change

**A node's body** (Adam, 2026-11-02). Every node written in a file gets
`body`: the lines of its span that no node under it holds, as they are
in the file, indent and all, less blank lines at either end. Blank lines
inside a body stay in it. A heading's body is its line (`##Decoding`), a
module's its title line, `POST_TEXT`'s is `---`, a claim's is its sigil
line and the lines under it, a test group's is its `##` line. A `SYMBOL`
and an `EXTERNAL` are derived and have none, and a symbol's lines do not
count as held by it: they are its code block's. A blank line between two
nodes is in no body. `var/target_doc.py`'s `bodies` does this from the
file and held over every example; read it, do not import it.

The body is the file's own lines, not rebuilt from the model's pieces.
The model does not keep them today; where they come from (the parse, or
the file read beside it) is yours, and say which. A module built with
no file has no bodies. `text` stays as it is, for the old documents.

**A reference's lines** (Adam, 2026-11-02). `Edge.start_line` becomes
`lines`, a tuple of the lines it is written on, in order, each once;
empty where none is known. There is one edge for each source, target and
kind. Each binding's `extract_calls` gives every line a name is used on,
not the first: Python, Haskell and TypeScript. `add_uses_edges` and
`add_cites_edges` keep all of them; a `#References` listing and a
`#Binding` declaration have one line each.

**The source stays where it is written** (the design session): a
paragraph for a citation, a symbol or claim for a call. Moving a
reference to the nearest node an outline shows is the view's, in stage
3, defined by rank.

**Two fixes from slice 6** (Adam agreed both, 2026-11-03).
* An appendix's name comes from the grammar. `NAME` is already a
  terminal of `appendix_section`; `AppendixSection` carries it as
  `name`, `None` when bare, and `graph.py` stops cutting it out of
  `title` (Adam's rule: grammar over Python).
* A test result is reported with the kind of the test it ran. One whose
  address matches no test collected is a fault: raise, do not call it
  `TEST` (`commands.py`, `test_kind.get(r.address, "TEST")`).

**The old documents do not change.** Every edge the old writers, the
outline, `query` and `content_tree` read takes its first line where it
took `start_line`, so they print what they print now.

## Rules

* **May touch:** `notlob/graph.py`, `notlob/model.py` and the parse
  (where the body's lines come from, and `AppendixSection.name`),
  `notlob/project.py`, `notlob/outline.py`, `notlob/commands.py`, the
  three bindings' `extract_calls` and their docstrings, the stale
  docstrings in `notlob/bindings/__init__.py` (`:17`, `:47`, `:234`),
  tests.
* **Must not touch:** the grammar, any schema or the ontology,
  `name_graph_next.json`, `test_graph_next.py`, `DESIGN.md`, what any
  command prints.
* **Assertions may change** where a test reads `Edge.start_line`, or
  holds `extract_calls` to one line a name. Report the kinds of change,
  and each that is more than that.
* **Failing tests first;** say that you did. Do not commit or stage.
  80-character lines. No slice wording. One shell command per call; use
  `-C`, not `cd`. Plain `pytest` and `ruff` calls.

## Tests

1. Over every example: the bodies of each file, each placed at its
   node's `start_line`, give every line of the file that is not blank,
   each from one body; a line in no body is blank.
2. Over every example: a `SYMBOL` or `EXTERNAL` has no body, and every
   other node built from a file has one. Roman: `##Decoding`'s is
   `##Decoding`, the post-text's `---`, the first `~example`'s begins
   `~example` with the next line indented as written.
3. A code block with a blank line inside keeps it in its body.
4. In each language, a function that uses a symbol on two lines gives
   one `USES` edge with both lines; a name used twice on one line, one
   line.
5. A paragraph citing `#X` on two lines gives one `CITES` edge with
   both.
6. `#Appendix Glossary` parses to `name` `Glossary`, bare `#Appendix`
   to `None`; the graph's names are as in slice 6.
7. A test result with no collected test raises.
8. Every old document of every example is as it was: graph JSON at each
   level, Turtle, the text outline, node summaries and content trees
   (`var/test_baseline_s6.py` captured them).
9. `test_graph_next.py`: its 18 pass and the rest stay xfail, none
   passing.

## When to stop

Stop and report if a node's own lines are not one run (a gap a child
does not explain), if any value of an old document changes, if a
binding cannot give every line without changing what it finds, or if
this grows past the brief.

## When you are done

Report: roman's `Decoding` section's nodes with their bodies; one
`USES` edge with several lines, from each language; where the lines of
a body come from; the assertions changed; that the new tests failed
first; the full suite; a line-length check; anything you stopped on.
