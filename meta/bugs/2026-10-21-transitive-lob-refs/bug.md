# Python and Haskell loaded only a module's direct lob-refs

**Component:** the `_load_dep_modules` loaders in
`notlob/bindings/python/runner.py` and `notlob/bindings/haskell/runner.py`
(used by claims, and by `notlob build` for both).
**Found by:** kamtrinia, notlob 0.5.4, Python binding, 2026-10-19.
**Status:** fixed, 2026-10-21.

## Summary

`Top` lists only `Middle`. `Middle` lists `Base` and uses it at module
level (`MIDDLE_VALUE = base_value() + 1`). `notlob test middle.lob`
passed, but `notlob test top.lob` failed with
`NameError: name 'base_value' is not defined` from *Middle's* code: the
runners inlined only the module's direct references, so Base was never
loaded for Top. Listing Base in Top (in the right order) made it run, but
then `[imports]` reported the import unused: no way to satisfy both. A
kamtrinia project hit it with four transitive modules.

## Cause

Loading was direct-only in Python and Haskell: each had its own
`_load_dep_modules` that walked `module_lob_refs(module)` one level, in
the order listed. TypeScript already called `project.transitive_lob_refs`
(dependencies first, de-duplicated, cycle-safe). The original in-process
loader, `ModuleCache`, was also transitive; the subprocess runners that
replaced it dropped that. So the three bindings disagreed.

## Why it is a bug

Loading and visibility are different questions. Middle's own code needs
Base to run, and Middle lists Base, which is what it should do. A module
that works on its own must work when something else uses it. Loading
must therefore be transitive. What Top may *use* is a separate matter: it
should use only what it lists. That is enforced by lint (the Python linter
reports a name from an unlisted module as `F821`), and this change leaves
it alone: lint's name filter still knows only direct dependencies, so
loading everything does not widen what a module may use.

## Resolution

One shared function, `project.load_dependency_modules(module, root)`: the
module's lob-refs, theirs, and so on, parsed, dependencies first, each
once, tolerant of cycles and of missing modules (skipped; the absence
surfaces where it is used). `transitive_lob_refs` and it share one
traversal, so each dependency is parsed once. Python's loader, Haskell's
loader and TypeScript's source builder all call it; TypeScript's
behaviour is unchanged and its private loop is gone. `notlob build` for
Python and Haskell is fixed by the same change.

`LANGUAGE.md` now says, once and for every binding, what a reference
means: a module runs with everything it depends on, transitively, and
should use only what it lists. The Python `BINDING.md` states the
narrower thing lint treats as in scope.

Tests: `tests/test_transitive_refs.py` (kamtrinia's chain, Python claims,
`#Tests`, properties, listing order, the whole `notlob test` command,
`notlob build` order and run, lint and `[imports]`, a Haskell chain, and a
TypeScript regression), and `TestLoadDependencyModules` in
`tests/test_project.py`. They failed before the change with the same
NameError the reporter saw.

## Not done

* An unlisted module's name is flagged by Python lint but not, as far as
  I checked, by the TypeScript or Haskell linters; the rule "use only
  what you list" is enforced unevenly across bindings. Not investigated
  further.
* The `ModuleCache` (`bindings/python/loader.py`) is vestigial for claims
  (the runners ignore it) and still loads recursively.
