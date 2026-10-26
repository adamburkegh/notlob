# Slice 2d brief: the post-text node, the test kinds, and the docs

**For:** an implementing session. **Written by:** the design session,
2026-10-25. **Design:** `design.md` in this directory: decisions D12 and
D13, and slice 2d in section 9. Read them first.

## Goal

A follow-up to 2c, in three parts:

1. **The post-text node (D12).** The sections after `---` hang from a
   `POST_TEXT` node, not from the module.
2. **The test kinds (D13).** 2c's single `TEST` covers three things, and
   the code tells them apart by the shape of an address (`_is_run`).
   Groups become `TEST_GROUP`; `TEST` means a test, named by `~test` or
   anonymous (a run of bare assertions), as `PROPERTY` covers named and
   unnamed properties.
3. **Docs that describe the old graph:** the `graph.py` docstrings and
   comments, and the new ontology comments.

Every output keeps today's shape, through the temporary layer, as in 2c.

## Rules

* **May touch:** `notlob/model.py` (the `PostText` position only),
  `notlob/graph.py`, `notlob/schema/name_graph.json`,
  `notlob/schema/query_result.json` (the `kind` enums only),
  `notlob/schema/notlob.ttl`, and the tests named below.
* **Must not touch:** `check.py`, `commands.py`, the bindings, the
  runners, `cli.py`, `mcp_server.py`, `DESIGN.md`.
* **Must not change, and must pass:** `tests/test_check.py`, every
  `tests/test_cli_*.py`, `tests/test_address_collision.py`,
  `tests/test_graph_export.py`, `tests/test_turtle.py`,
  `tests/test_graph_layer.py` (its five snapshots are the proof the
  printed shape did not move), and the accessor classes in
  `tests/test_graph.py`.
* **May be rewritten** where they assert the in-memory structure:
  `tests/test_graph_forest.py`, the rest of `tests/test_graph.py`,
  `tests/test_graph_completeness.py`, `tests/test_graph_package.py`,
  `tests/test_graph_symbols.py`, `tests/test_graph_property.py`, and
  `tests/test_model.py` (additions). Report each change, old and new.
* **Failing test first** for the new structure; say that you did.
* Do not commit or stage. 80-character lines. No phase or slice wording
  in code, comments or docstrings.

## 1. The post-text node

**Model.** `PostText` gains `start_line` (the `---` line) and `end_line`
(the last non-blank line of the post-text, which is the module's last
line). Additive, defaults `None`. Extend `tests/test_model.py`: the
per-class tests, the Roman row (`---` is line 73; the post-text runs
73-105), and the every-example invariant (the post-text lies inside the
module and its sections inside it).

**Graph.** One `POST_TEXT` node per module that has a `---`:

| Field | Value |
|---|---|
| address | `mod#post-text` |
| label | `post-text` |
| lines | the model's `PostText` lines |
| parent | the module |
| children | the `TESTS` node and each `APPENDIX`, in document order |

Its children **keep their addresses** (`mod#Tests`, `mod#appendix#1`,
and so everything below them): the post-text is a region of the tree,
not part of an address (D12). `#References` and `#Binding` are still not
nodes (D11).

**Accessors.** `sections(module)` must still return the subheadings, the
`#Appendix` sections and their subheadings, in document order: walk into
`POST_TEXT`. `module_of` needs nothing (it follows parents). Their tests
do not change.

## 2. The test kinds

| Element | Kind | Address and label |
|---|---|---|
| `#Tests` | `TESTS` | unchanged |
| a `##group` | `TEST_GROUP` (new) | unchanged (`mod#Tests#encoding`) |
| a `~test name` | `TEST` | unchanged (`group#name`) |
| a run of bare assertions | `TEST` | unchanged (`parent#test#n`, `test#n`) |

`TEST` keeps meaning "a test", named or anonymous. Telling the two apart
is needed in exactly two places, both of which exist only to reproduce
today's output and today's `USES` lines: the temporary layer (an
anonymous test's lines are folded into its group's `code`) and the text
`add_uses_edges` scans for a group (`_group_code`, `_scanned_text`).
Replace `_is_run` with one helper, `_is_anonymous_test(node)`, used only
there, with a docstring saying what it tells apart and how. Nothing else
in `graph.py` may read an address or a label to learn what a node is:
a `TEST_GROUP` is found by its kind.

The layer prints `TEST_GROUP` nodes as `TEST`, as today.

## 3. The docs

* **`graph.py` module docstring.** It still describes the old graph
  ("module and subheading nodes", `REFERENCES` "not yet implemented", an
  edge vocabulary with `DEFINES`, and an example walking `DEFINES`).
  Rewrite it to describe the graph as it is: one tree per file joined by
  `CONTAINS`, with text on the leaves; the cross-reference edges; the
  address rules (named nodes by name, anonymous ones by position); and
  an example that walks `CONTAINS`. Mention that `legacy_graph` is what
  the outputs print, in one sentence, without saying when it goes.
* **`EdgeKind` and `NodeKind` comments.** Make each say what the kind
  is now (for example `CONTAINS`: "parent to child: where a node is
  written"; `DEFINES`: "only in the printed graph").
* **`enrich`'s docstring** says what it walks; keep it true (it still
  does not walk an `#Appendix`: say so plainly, as a fact).
* **`notlob.ttl` comments.** `Prose`, `Code` and `Bullets` are written
  in a module, a subheading, an `#Appendix`, `#Tests` or a group, not
  only "a module or subheading". `Appendix`: "An `#Appendix` section:
  one of the sections after the `---` separator, with an optional title
  and a body of its own." Add classes for `POST_TEXT` and `TEST_GROUP`
  with the names the existing guard expects (`kind.name.capitalize()`:
  `Post_text`, `Test_group`); whether the classes should be
  `PostText`/`TestGroup` is a question for later, not this slice.

Add `POST_TEXT` and `TEST_GROUP` to the two schema enums.

## Tests

New, or extended:

1. **Oracle** (`test_graph_forest.py`): the independent walk of the
   model puts the post-text level in (`POST_TEXT` with `TESTS` and the
   Appendices under it) and `TEST_GROUP` for groups; every source and
   every example still matches.
2. **Kinds:** a group is `TEST_GROUP`; a named test and an anonymous
   one are both `TEST`; a named test whose name looks like an ordinal
   (`~test test#1`, if the grammar accepts that name; say if it does
   not) is still told apart correctly by the layer, which 2c's
   `_is_run` got wrong.
3. **Post-text:** addresses of `#Tests`, its groups and tests, and of an
   Appendix and what it holds are unchanged; a module with no `---` has
   no `POST_TEXT`; a bare `---` with nothing after it is a `POST_TEXT`
   with no children.
4. **A guard,** like 2b's for `check.py`: the source of `graph.py`
   outside `legacy_graph`, its helpers and `_is_anonymous_test` does not
   match an address or label pattern to decide a kind (for example, no
   `re.fullmatch` on a label). Name it for what it protects.

## When to stop

Stop and report if a protected test fails, if a snapshot in
`test_graph_layer.py` would have to change, if `check.py` or a binding
would have to change, or if the slice grows past this brief.

## When you are done

Report, without committing: what changed in each part, with a short
snippet of the new `POST_TEXT` node and of `_is_anonymous_test`; that the
new tests failed first; the full suite result; each rewritten test, old
and new; a line-length check; and anything you stopped on.
