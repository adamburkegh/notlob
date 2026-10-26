# Brief: delete `ModuleCache`

**For:** an implementing session. **Written by:** the design session,
2026-10-26. **Decision:** Adam, 2026-10-26: delete it, "a buried design
and sounds like a knockoff name-graph". After slice 6a, notlob works out
what a module's code is loaded with (`project.load_order`) and hands it
to the binding as `deps`; `ModuleCache` loads nothing anyone uses.

## What goes

* `notlob/bindings/python/loader.py` (`ModuleCache`,
  `CircularImportError`) and `tests/test_bindings_python_loader.py`.
* The `cache=` keyword: `commands.py` builds a `ModuleCache` and passes
  it to the three runners of every binding (and
  `bindings/typescript/__init__.py` passes one). Python and Haskell
  ignore it. TypeScript reads only its `.root`.
* In its place, a `root` keyword on the runners (as `lint` already has):
  the project root, or `None`. `commands.py` passes the root it has.
  TypeScript reads it where it read `cache.root`; Python and Haskell
  accept it. `BindingKit`'s docstring lists it with `claims` and `deps`.
* Docstrings, comments and test docstrings that describe `ModuleCache`
  as how anything works now (`python/runner.py`, `assemble.py`,
  `DESIGN.md` line 491, `tests/test_cli_cross_file.py`,
  `tests/test_cli_build.py`, `tests/test_bindings_python_runner_imports.py`,
  `tests/test_python_file_attribute.py`): say what is true now, or drop
  the sentence. A sentence that is history ("the original in-process
  loader set `__file__`...") may stay as history.

## Rules

* **May touch:** the files above, the three bindings' runners and
  `__init__.py`, `bindings/__init__.py`, `commands.py`, tests.
* **Must not touch:** `project.py`, `graph.py`, lint, the grammar.
* No test assertion changes, except tests that exist only to test
  `ModuleCache` (deleted with it) or that pass `cache=` (they pass
  `root=` instead, or nothing). Report each.
* A test first: no `notlob` module imports `loader` or mentions
  `ModuleCache` or `cache=`, and each runner takes keyword `root`. It
  fails now. Do not commit or stage; 80-character lines; plain `pytest`
  and `ruff` calls.

## When you are done

Report: what was deleted, with line counts; each test changed or
deleted; that the new test failed first; the full suite; a line-length
check; anything you stopped on.
