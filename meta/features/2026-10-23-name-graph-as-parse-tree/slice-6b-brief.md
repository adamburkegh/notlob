# Slice 6b brief: Python claims see their own file; every example runs

**For:** an implementing session. **Written by:** the design session,
2026-10-26. **Design:** `meta/bugs/2026-10-22-python-claims-file-attribute/
bug.md` ("Resolution" and its limitation), settled 2026-10-22. After 6a.

## Goal

Two things `1468f0f` did that were backed out with it, neither touching
the graph:

1. **`__file__` in Python claims** is the module's `.lob` path, as under
   the original in-process loader, so a module that finds data relative
   to itself (`examples/gutenberg/gutenberg/hamlet.lob`) works under
   `notlob test`. A built artifact does not carry it: it is portable.
2. **Every example project is run end to end** by a test, so an example
   that breaks is noticed. Nothing did, which is how the Gutenberg
   example stayed broken for months.

## Rules

* **May touch:** `notlob/bindings/python/runner.py` and `assemble.py`;
  tests; the Gutenberg example only if a run shows it needs it (report
  why).
* **Must not touch:** the graph, `project.py`'s load order, the other
  bindings.
* **The old tests come back first:** `git show
  1468f0f:tests/test_python_file_attribute.py` and
  `1468f0f:tests/test_example_projects.py`. Restore, run (they fail now),
  and change only their calls, never what they assert. Report each
  change.
* An example whose toolchain is missing is skipped with the reason, as
  the old test did (`ts-media` needs `npm install`; Haskell needs GHC).
  Skips are reported, never silent passes.
* Failing test first; no commit or stage; 80-character lines; no slice
  wording; plain `pytest` and `ruff` calls.

## The change

As in `1468f0f`: `assemble_with_deps` takes a prelude for the module's
own code, and the claim runners set `__file__` to the module's resolved
`.lob` path just before it. `build` does not. The limitation stays and is
documented where the prelude is: dependencies inlined before the module
see the harness's path at load time.

## When you are done

Report, without committing: the change; each restored test and its
changed calls; that they failed first; which examples ran and which were
skipped and why; the full suite; a line-length check; anything you
stopped on.
