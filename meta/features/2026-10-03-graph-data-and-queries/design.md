# Design note: richer graph data, agent queries and a binding API

**Status:** proposal, queued (not started)
**Origin:** the notlob-vids dialogue, 2026-10-03: what its visualisation
needed from `notlob graph --format json`, and what an agent working in a
project needs to ask of the graph.
**Decisions already taken (Adam):** agent-facing queries belong in core;
visualisation does not (see `2026-10-03-graph-visualisation`).

## Part A: data the graph export should carry

Wished for by a consumer that draws the graph and shows source excerpts:

- `end_line` as well as `start_line`, so a node has an extent. Today
  consumers hand-pick line ranges.
- A project-relative file for each node (derivable from the address for
  modules, but worth having directly).
- The column where a name starts, so a label can be located exactly.
- A position on REFERENCES edges. Reported as missing from the export;
  the builder (`add_references_edges`) says it sets `start_line` from
  `Ref.start_line`, so first check whether it is lost at export or just
  null.
- A size per node (characters of prose and code under it), so an agent
  can budget before reading.
- A marker for which MODULE node(s) are binding modules.
- A schema version, and `schema/name_graph.json` shipped in the wheel.
  It sits outside the `notlob` package and is not in `package-data`
  (only `grammar.lark` and the docs are), so a consumer outside a repo
  checkout cannot find it.

## Part B: queries in core

An agent wants answers, not a picture. Candidates, each a thin consumer
of data the graph already holds:

- `notlob query dependents <address>`: transitive dependents of a symbol
  or module, a blast radius before a change.
- `notlob query uncovered`: symbols that no EXAMPLE, PROPERTY or TEST
  node uses.
- `notlob query cost <address>`: size of a node, module or neighbourhood,
  for context budgeting.

What exists: USES edges are computed from SYMBOL, RUN, TEST, EXAMPLE and
PROPERTY nodes (`notlob/graph.py`), name-based and statically visible.
Measured on pn-chomper's graph: SYMBOL to SYMBOL 109, TEST to SYMBOL 47,
EXAMPLE to SYMBOL 30, PROPERTY to SYMBOL 20, RUN to SYMBOL 9, and 38 of
its 86 symbols are the target of a claim's USES edge. So "what is thinly
checked" is answerable today. Caveat to document: "used by a claim" is
name-based and direct, so a symbol exercised only through another
function counts as untouched.

The existing `quantifier` check already answers a related question
("behavioural prose with no claim beside it").

## Part C: a public `binding_of(path)`

"What language is this project?" is in `binding.lob`, and
`BindingSection.language` is structured data, reachable today through
public names (`parse_file`, `from_tree`, `BindingSection`). What is
missing is a named one-call function; the CLI's own helper
(`_find_binding` in `commands.py`) is private, so a consumer fell back to
reading the raw `LANGUAGE_DECL` token, which couples it to unstable
grammar internals.

Shape it for the roadmap: **multi-binding projects are planned**, so the
function takes a file path and returns the nearest governing binding, as
`_find_binding` already does, not a project-wide "the language". Note
that graph building is single-language today (`build_package` takes one
extractor and one root binding picks it); multi-binding would need that
to become per-module.
