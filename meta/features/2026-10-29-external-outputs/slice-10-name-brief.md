# Slice 10 brief: a node has a name, not a label

**For:** an implementing session. **Written by:** the design session,
2026-11-05. **Design:** "Node addresses and names are distinct" in
`notlob/docs/DESIGN.md` (rewritten 2026-11-05); the `name` field of
`Node` in `notlob/graph.py`. After slice 9, the swap, in 0.6.0.

## Why

A `Node` holds both a `label` and a `name`. For a named node they are
the same string. For a node with no name (a paragraph, a code block, an
unnamed claim, a keyword section) `label` is a made-up identity
(`prose#1`, `Tests`) that is also in its address, and `name` is `None`.
So "the name of a node" has two homes, and the outputs, the schemas and
`DESIGN.md` already know only one, `name`. `label` is read in three
places: `NameGraph.resolve` (two comparisons), `NameGraph.search`, and
lint and project code that reads the label of a symbol, module or
section, all of which have a name. This slice takes `label` out of
`Node`.

## Ruled for this (Adam, 2026-11-05)

* **Fold `Node.label` into `Node.name`.** `label` goes from `Node`;
  nothing reads it any more.
* **`search` matches names only.** A node with no name is never found
  by a pattern, whatever `--kind` is given. Matching `prose#1` against
  `prose*` told a reader nothing; a node of a kind is listed by
  `query children --kind` or a view.
* **A default `query search` still finds EXTERNAL nodes** (Adam, later
  the same day: "keep them"). Slice 9 had the default show only what an
  `outline` shows, which dropped them. With names only, no filter is
  needed: every named kind is at or below `index`, and every nameless
  one is never matched. So `cmd_query_search` drops its rank filter
  entirely, and `--kind` only narrows. (The design session's reading of
  the ruling; it adds no list.)
* **The titles lint compares names** (Adam, 2026-11-05, on the design
  session's recommendation). An appendix's label was the heading as a
  reader sees it (`Appendix Notes`), and `check_titles` leant on that.
  A "title as a reader sees it" for the lint would be a second string on
  a node, which is `label` back under another name. So the keyword is
  not part of an appendix's title: `test_check_appendix.py`'s titles test
  is rewritten to titles that still collide on their names, and
  `test_lint_findings.py` keeps the appendix title it was changed to.

## The design session's calls (overrule if you disagree, Adam)

* **A node's identity is its address and its kind.** `Node` compares
  and hashes on `(address, label, kind)` today; the label added nothing,
  as the address holds it.
* **`Ref.label` stays.** It is a different thing: the text of a
  `#Label` written in prose, as parsed (`notlob/model.py`). It is not a
  node's.
* **`NameGraph.resolve(label, ...)` becomes `resolve(name, ...)`**: a
  reference names a node. The CLI's `query resolve` (deprecated) keeps
  its argument as it is.

## The change

* `Node` loses `label`, its docstring line, and its place in equality
  and hash. Every `Node(...)` in `notlob/` loses `label=`; a node that
  has a name is given it as `name=` where it is not already.
* `_positional_identity` returns the address alone, and
  `_claim_identity` drops its label: what they returned as a label was
  the end of the address.
* `resolve` compares `name` where it compared `label`, and `search`
  matches `name`, skipping a node whose `name` is `None`.
* `check.py` and `project.py` read `name` where they read `label`
  (symbols, modules and sections: each has one).
* The module docstring of `notlob/graph.py` (the address table, and
  "labels are the human-readable names") says names.
* `cli.py` (`search` help: "by label pattern") and `mcp_server.py` (the
  search tool's description, if it says label) say name.
* CHANGELOG, under the library callers' entry for 0.6.0: `Node.label` is
  gone; `Node.name` is the name as written, `None` for a node addressed
  by position or a keyword section; `search` matches names only. Rewrite
  in place, as in slice 9; no new entry on top.

## Rules

* May touch `notlob/` except the grammar and bindings, tests, and
  CHANGELOG. Must not touch: `DESIGN.md`, the schemas, `grammar.lark`,
  the bindings.
* A test that reads `Node.label` reads `Node.name` if the node has one.
  A test that holds a nameless node's label (`prose#1`) is of the old
  model: delete it, and say which. Stop if one wants rewriting to a
  behaviour this brief does not name.
* If any reader of `label` turns out to need a nameless node's label,
  stop and say where: that is a design question, not a workaround.
* Failing tests first. No commit, no staging. 80-character lines.

## Tests

1. `Node` has no `label` field, and two nodes with one address and kind
   are equal.
2. `search("prose*")` over roman finds nothing; `search("*Roman*")`
   finds the module; a nameless node is found by no pattern, with or
   without a kind (`search("*", NodeKind.PROSE)` is empty). `query
   search` with no `--kind` finds an EXTERNAL by its name (ts-media
   declares one), and finds every named node that the default found
   before.
3. `resolve` answers every reference in the five examples and the small
   project as it does today (the existing reference tests, unchanged,
   are the check).
4. The lint findings over the five examples are what they are today.
   If no test pins them, add one before the change (a pytest test, not
   runs of the CLI by hand), and let it pass on both sides.
5. Nothing in `notlob/` reads `.label` on a `Node` (a `Ref.label` is
   fine): say how you checked.
6. The full suite, ruff, and line lengths.

## Report

What changed, by file; the tests deleted, by file, and why; the check
for test 4 and its result; how you checked test 5; anything stopped on.
