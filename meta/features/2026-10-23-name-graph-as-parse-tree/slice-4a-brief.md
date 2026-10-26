# Slice 4a brief: notlob's own readers onto the graph

**For:** an implementing session. **Written by:** the design session,
2026-10-25. **Design:** `design.md` in this directory: D7, D17, D18, and
slice 4 in section 9. Read them first.

## Goal

The graph holds every element of a document, but several of notlob's own
readers still walk the model instead, each deciding where to look, and
each command builds graphs over and over. This slice moves the readers
that are notlob's own (not the bindings') onto the graph, and makes each
command build one graph.

1. **A `~run`'s mode is in the graph (D18).**
2. **`enrich` reads the graph's code** and so finds an `#Appendix`'s
   symbols too: the Appendix fix, for symbols.
3. **`validate_refs` reads the `PROSE` leaves.**
4. **`notlob build`'s entry points come from the graph's `RUN` nodes.**
5. **One graph per command (D7).**

Not here, because the bindings call them and the contract changes in 4b:
`collect_run_bodies`, the claim and test runners, a binding's `build()`
and `lint()`, and `notlob run`.

## Rules

* **May touch:** `notlob/graph.py`, `notlob/commands.py`,
  `notlob/project.py`, and tests (below).
* **Must not touch:** `model.py`, `check.py`, `notlob/bindings/`,
  `cli.py`, `mcp_server.py`, the schemas, the docs.
* **Must not change, and must pass:** the existing tests in
  `tests/test_check.py`, every `tests/test_cli_*.py`,
  `tests/test_address_collision.py`, `tests/test_graph_export.py`,
  `tests/test_turtle.py`, `tests/test_graph_layer.py`, and the accessor
  classes in `tests/test_graph.py`. New tests may be added to any file.
* **May be rewritten** where they assert the in-memory structure or the
  old call pattern: the rest of `tests/test_graph.py`,
  `tests/test_graph_forest.py`, `tests/test_graph_symbols.py`,
  `tests/test_graph_package.py`, `tests/test_project.py`. Report each,
  old and new.
* **Failing test first;** say that you did. Do not commit or stage.
  80-character lines. No phase or slice wording in code or docstrings.

## 1. The `~run` mode

`Node` gains `mode: str | None = None` (compare and hash off, like the
other fields). `build` sets it on every `RUN` node: `"on-load"` for
`~run on-load`, `"on-invocation"` for `~run on-invocation` and for a bare
`~run` (the grammar's meaning). `None` on every other node. The printed
graph does not show it.

## 2. `enrich` reads the graph

`enrich(graph, module, extractor)` keeps its signature, so its callers do
not change, but uses `module` only for its address. It finds the code to
extract from in the graph: every `CODE` leaf and every `PROPERTY` node in
the module's tree, at any depth, in document order. It hands the
extractor the leaf's text as lines (dedented already; the three
extractors dedent what they are given, so the result is the same, and
`first_line` still counts the leaf's lines one for one). Its docstring
says what it reads and that `module` is used for its address.

So symbols written in an `#Appendix`, or in one of its subheadings, are
now in the graph, contained by their `CODE` leaf. The printed graph does
not show them (it leaves out what is written in an Appendix, as since
2c), so the snapshots do not move. But the checks read the graph, and
this is the bug kamtrinia reported
(`meta/bugs/2026-10-19-appendix-not-in-graph`): an import used only by
code in an Appendix was called unused. Add a test in `tests/test_check.py`
that shows it fixed: a module that imports another, uses it only from a
function in its `#Appendix`, and gets no `[imports]` finding. It must
fail before the change.

## 3. `validate_refs` reads the `PROSE` leaves

`validate_refs(graph, module)` keeps its signature and checks the `refs`
of every `PROSE` leaf in the module's tree: the body, subheadings, each
`#Appendix` and its subheadings, and the commentary in `#Tests` and its
groups. Resolution (`_resolves`) is unchanged. A `RefError`'s `location`
stays what it is today for the places it covered: the module or
subheading the paragraph is written in, and the module for a paragraph
written directly in an `#Appendix`. A paragraph in an Appendix's
subheading is located at that subheading; one in `#Tests` or a group at
the module.

Commentary in `#Tests` was never checked before. If an example project
now fails on an unresolved reference in its tests commentary, stop and
report it rather than changing the example.

## 4. `notlob build`'s entry points

`_collect_run_claims(module)` goes. A module is an entry point when its
tree holds a `RUN` node (`graph.nodes(NodeKind.RUN)` with `module_of`),
read from the command's one graph. A `~run` in an `#Appendix` now makes
an entry point, which it did not before; add a test.

## 5. One graph per command

Today `notlob test` builds, for every module, a graph of its own for
`validate_refs` (`_build_ref_graph`: `build`, `enrich`, then each direct
import's `build`), and in project mode builds the package graph again for
the closing checks. `notlob build` parses each module a second time for
its entry points.

* **`notlob test`, in a project** (one file or all): `build_package`
  once, before the modules are tested; each module's `validate_refs`
  reads it; the closing checks read it. `_build_ref_graph` goes.
* **`notlob test` on a file with no project:** `build` and `enrich` once.
* **`notlob build`:** one graph, read for every module's entry point.

`tests/test_address_collision.py` pins how a name collision is reported
by `notlob test` (today, as a document error of the module it is in,
with the other modules still tested). Keep exactly that. If one package
graph cannot keep it (the collision stops `build_package` for every
module), stop and report the options instead of choosing one.

Add a test that `notlob test` in project mode calls `build_package` once
and `build` only through it (count the calls with a monkeypatch).

## When to stop

Stop and report if a protected test fails, if an example newly fails
`validate_refs`, if the collision behaviour cannot be kept, if anything
needs a change in `notlob/bindings/` or `check.py`, or if the slice grows
past this brief.

## When you are done

Report, without committing: each part with a short snippet (the `mode`
assignment, `enrich`'s new walk, `validate_refs`'s loop, the one graph in
`cmd_test`); that the new tests failed first; the full suite result; each
rewritten test, old and new; a line-length check; anything you stopped on.

## Amendments, 2026-10-25 (Adam)

After the implementing session stopped on name collisions in `notlob
test`:

1. **Option A.** `build_package` takes an optional list to collect
   collisions into. Given one, a module whose names collide keeps its
   structural graph (`build`, without `enrich`), the collision is
   appended with the module's path, and the build carries on; without
   one, it raises as now, so other callers do not change. `notlob test`
   builds the package once with the list, reports each module's
   collision as that module's `<names>` error, and tests the rest on the
   shared graph; `_build_ref_graph` goes. **If any module collided, the
   closing checks report the collision as they do today** (`ERROR
   <names>`, an error) rather than running on a graph that lacks that
   module's symbols, where another module could get a false
   `[imports]` finding. `tests/test_address_collision.py` must pass
   unchanged. Then add the call-count test.
2. **A document name restated in its scope is an error** (`design.md`
   D10, as split): a second heading, `~property` name or `~test` name
   with the same name in the same scope raises `AddressCollisionError`,
   as a name shared by two kinds already does, instead of replacing the
   first. Code names (symbols) keep "the last definition wins" until D10
   is decided for them. Under option A it is one more collision.
   Today's replacement leaves one node with the second heading's lines
   and both headings' children; test that it is an error instead,
   including a body `##Notes` and an Appendix `##Notes`.
3. **Gutenberg's unresolved reference is a strict expected failure.**
   Replace `_KNOWN_UNRESOLVED` in `tests/test_graph_refs.py` with
   `pytest.mark.xfail(strict=True)` on the gutenberg case only, its
   reason pointing at `meta/bugs/2026-10-22-mutual-references` (the
   cause: `corpus.lob` cites `hamlet`, which uses `corpus`; module
   listing, slice 6, lets it list and cite `#Gutenberg Hamlet`). The
   other four projects must still have no unresolved reference.
