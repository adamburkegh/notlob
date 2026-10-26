# Python claims ran with the harness script's `__file__`, not the module's

**Component:** `notlob/bindings/python/runner.py` (`_module_source`),
`notlob/bindings/python/assemble.py` (`assemble_with_deps`).
**Found by:** running every example project end to end for the first time
(`tests/test_example_projects.py`), 2026-10-22. Not reported by a user.
**Status:** fixed, 2026-10-26, in `6e54c9d`, as resolved below; the
`1468f0f` tests are restored and pass, and every example project now runs
end to end in `tests/test_example_projects.py`.
Before that, reopened, 2026-10-23: the fix (`1468f0f`) was backed out in
`4230b04` with the name-graph refactor it was built on; see
`meta/retrospectives/2026-10-23-name-graph-redundancy/`. Was: fixed,
2026-10-22.

## Summary

`examples/gutenberg/gutenberg/hamlet.lob` finds its data with
`Path(__file__).parent.parent / "data"`. Under `notlob test` it failed:
`FileNotFoundError: ...\Temp\data\pg1524.txt`. The original in-process
loader (`ModuleCache`) executed each module with `__file__` set to its
`.lob` path. The subprocess harness that replaced it runs a temp script, so
`__file__` was the temp script's path. Any module that locates files
relative to itself broke under `notlob test`, and the one example that did
this was not covered by any test, so nothing noticed.

## Resolution

The claim runners now set `__file__` to the module's `.lob` path (resolved)
just before the module's own code (`assemble_with_deps` takes a
`module_prelude`; `_module_source` supplies it). A built artifact does not:
it is portable and must not carry the source tree's absolute path (a test
guards that).

**Limitation, not fixed:** one shared namespace. A dependency inlined
before the module sees the harness script's path when it loads, and the
module's path after. A dependency that reads `__file__` at load time would
still be wrong.

Tests: `tests/test_python_file_attribute.py` (examples, `#Tests` and
properties see the `.lob` file and can read data relative to it; the
artifact carries no source path). They failed before the fix.

## Found with it, in the same run

Two more defects in the Gutenberg example, both fixed in the example. Dated
afterwards by running `notlob test` over the project at past commits (git
worktrees; the example files last changed 2026-07-21, so every difference
below is notlob's behaviour, not the example's):

* **`__file__` (this bug): drift.** The project's claims passed (15) at
  `9fde779` (2026-08-11) and every commit tested back to `c082366`
  (2026-07-21); they failed at `cf9b0a1` (2026-08-12), the commit that moved
  claims into subprocess harnesses. Nothing covered the example, so nothing
  noticed.
* **Three f-strings with no placeholders in `hamlet.lob` (ruff `F541`):
  present since the example was written (`7161fb6`, 2026-05-21), hidden by
  a lint bug.** On Windows, `_run_ruff` fed ruff the source in the default
  codepage; ruff rejected it ("stream did not contain valid UTF-8", exit 2)
  and the empty output was read as "no findings". Lint therefore reported
  nothing for any source with non-ASCII text until `9fde779` (2026-08-11)
  added `encoding="utf-8"`, which is when the findings first appeared. The
  swallowing itself is still there: see
  `2026-10-22-lint-failure-reads-as-clean`.
* **`corpus.lob` mentioned `##Gutenberg Hamlet`, an unresolved reference:
  the language changed under the example.** This example is where the
  `##Name` prose reference was first used: the text was written on
  2026-05-22 as `##Litstats Hamlet` (`ea3cf48`; renamed by `9a11221`), when
  `##Name` was the one prose-reference sigil and the DESIGN said it referred
  to "a doc-node". On 2026-05-23 references became first-class and
  validation became a test failure (`7fe2d0f`, `edf3a89`, `c6833c3`), and
  `##Name` narrowed to a subheading of the current module, with `#Name`
  becoming the universal reference. Whole-project `notlob test` reports it
  as unresolved at every commit checked (2026-05-25 to 2026-08-11), and
  running `hamlet.lob` alone passes, which is probably why it looked
  healthy. Not tested: any commit before the 05-23 change, so whether it
  resolved at that moment is not established.

  **Open question, not settled by the edit made so far:** I changed the
  reference to plain prose ("the Gutenberg Hamlet module"). The current-syntax
  spelling, `#Gutenberg Hamlet`, resolves only for a module in `#References`,
  and `hamlet.lob` already imports `corpus.lob`, so importing it back would be
  a cycle. Whether a module may refer to a sibling that depends on it is a
  design question, and the example is the place it shows. The edit should be
  reverted if the example is meant to keep demonstrating the reference.

And one that is a fact about the environment: `examples/ts-media` declares
`fast-check` and `@types/node` but the local install lacks them, so its
property test errors (its other claims pass). The example-project test
skips it, with the reason, until `npm install` is run in that directory.
