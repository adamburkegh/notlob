# Slice 6a brief: loading follows need, read from the graph

**For:** an implementing session. **Written by:** the design session,
2026-10-26. **Design:** already settled with Adam, 2026-10-22, in
`meta/bugs/2026-10-22-mutual-references/bug.md` ("Resolution") and
`meta/bugs/2026-10-21-transitive-lob-refs/bug.md`. The rules, as written
then, are in `git show 1468f0f -- notlob/docs/DESIGN.md` ("Listing,
citing and loading", seven numbered rules) and the `LANGUAGE.md` part of
the same commit. Read those first; this brief does not restate them.

## Goal

`1468f0f` implemented those rules and was backed out with the
representation it was built on (`4230b04`). Its `project._plan` built a
graph per module and walked it with helpers of its own to find what a
module defines and uses. This slice redoes it on the package graph each
command already builds (D7), which holds both facts as edges:

* **lists:** an `IMPORTS` edge, module to module;
* **uses:** a `USES` edge from a node in the user's tree to a `SYMBOL`.

and notlob, not each binding, decides which modules a module's code is
loaded with, as it decides which claims are run (D17): structure is
notlob's, language is the binding's.

Out of this slice: Python's `__file__` in claims and running every
example project end to end (6b).

## Rules

* **May touch:** `notlob/project.py`, `notlob/commands.py`, the three
  bindings' runners, `__init__.py` and `assemble.py` (to take the
  dependencies they are handed in place of loading them),
  `notlob/bindings/__init__.py` (`BindingKit`), `notlob/docs/DESIGN.md`
  and `LANGUAGE.md` (the text named above), the Gutenberg example
  (`corpus.lob` cites and lists `#Gutenberg Hamlet`, as in `1468f0f`),
  tests.
* **Must not touch:** `graph.py` beyond a read-only helper if one is
  needed (say so), `model.py`, the grammar, the schemas, the lint
  modules' rule for what a module may *use* (still its direct listings).
* **The old tests come back first.** `git show 1468f0f:<path>` for
  `tests/test_mutual_refs.py`, `tests/test_reference_rules.py`,
  `tests/test_transitive_refs.py`, and `TestLoadDependencyModules` from
  `tests/test_project.py`. Restore them and run them: they are the
  behaviour this slice must give, and they fail now. Change only their
  calls to the new functions and anything that read the old graph
  (`content`, `body_holders`), never what they assert. Report each
  change, old and new. A test whose assertion cannot stand is a stop.
* The gutenberg strict `xfail` in `tests/test_graph_refs.py` must then
  pass: remove the marker.
* **Failing test first** (the restored tests are that); say so. Do not
  commit or stage. 80-character lines. No phase or slice wording. Plain
  `pytest` and `ruff` calls; scratch output in `var/`.

## 1. Need, from the graph

In `project.py`, one function, with a name of your choosing:

```python
def load_order(graph, address, kit) -> list[str]:
    """The modules the code of the module at *address* needs, and what
    they need, dependencies first, each once (rule 3). Raises
    LobRefCycleError naming a cycle of need (rule 5)."""
```

*A needs B* when there is an `IMPORTS` edge A to B and a `USES` edge from
a node in A's tree to a `SYMBOL` in B's tree that

* is written in a code block of B (its holder is a `CODE` node, so not a
  function a `~property` defines: Defined(B) is B's own code), and
* whose name A's own code does not define (a name A defines is A's own,
  even if B defines it too).

`USES` edges are made from a name index over the whole package, so an
edge to B's `helper` exists whenever A calls a `helper`; the `IMPORTS`
condition and the second bullet are what make it a need. Read
`graph.module_of`, `graph.parent_of`, `graph.edges`, `KINDS`; build no
graph, parse no file and extract nothing here.

**The fallback** (rule 6): when the kit's reference extraction is not
complete (`BindingKit.complete_references`, new, default `False`; `True`
for Python), or it has no `extract_calls`, A needs B when A lists B and B
is not a descendant of A in the address tree (`gutenberg/hamlet` is
below `gutenberg`).

`LobRefCycleError` keeps the old message (`circular code dependency: a
-> b -> a`, with its explanation). `transitive_lob_refs` goes; if
anything else still needs it, stop and report.

## 2. Handing the dependencies to the binding

A command that runs, tests or builds a module works out its load order
once, parses those modules once, and hands them to the kit callables as
a new keyword, `deps` (a sequence of `Module`, dependencies first). The
three bindings' `_load_dep_modules` and the TypeScript runner's loop over
`transitive_lob_refs` go; each inlines what it is handed, in that order.
`BindingKit`'s docstring says what `deps` is, beside `claims`.

Without a project root there is nothing to load: `deps` is empty.

Where the order raises `LobRefCycleError`, the module's result is
`ERROR  <imports>  circular code dependency: ...` and its claims do not
run, in `notlob test`, `run` and `build` alike. A listed module that
cannot be found is skipped, as now; its absence shows where it is used.

## 3. Docs and example

`DESIGN.md`: the "Listing, citing and loading" section and the changed
`#References` paragraph from `1468f0f`, with "it is the binding's own
call extraction, the one the `USES` edges come from" made exact: need
is read from the graph's `IMPORTS` and `USES` edges. `LANGUAGE.md`: the
`1468f0f` text. The Gutenberg example as in `1468f0f` (the reference and
the listing; its f-string lint fix too, if it is not in yet).

## Tests

1. The restored tests, passing.
2. Need from the graph: a case each for a use of B's code (needed), a
   citation only (not), a name both define (not), a function only a
   `~property` of B defines (not), a use from a claim or `#Tests` (needed),
   a listing nothing reads in a binding without complete extraction
   (needed unless a descendant).
3. Each binding is handed `deps` and loads nothing itself: no runner
   module imports `module_lob_refs` or `resolve_module_path` for loading
   (lint may, for what is visible).
4. The gutenberg `xfail` passes, marker removed.

## When to stop

Stop and report if a restored test's assertion cannot stand, if a lint
rule would have to change, if need cannot be read from the graph for
some case (say which), or if the slice grows past this brief.

## When you are done

Report, without committing: the load-order function; each binding's
change; each restored test and every call you changed in it; that the
tests failed first; the gutenberg result; the full suite; a line-length
check; anything you stopped on.
