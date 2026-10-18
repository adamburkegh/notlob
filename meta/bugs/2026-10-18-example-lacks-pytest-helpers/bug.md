# `approx` / `raises` were in scope for `#Tests` but not for `~example`

**Component:** `notlob/bindings/python/harness.py`
(`build_examples_harness`, `build_tests_harness`)
**Found by:** kamtrinia. notlob 0.5.4.
**Status:** fixed, 2026-10-18.

## Summary

`total == approx(0.3)` passed as a `#Tests` line (bare or `~test`) and
raised `NameError: name 'approx' is not defined` as an `~example`. The
verdict differed because of the environment, not the assertion
evaluation. `build_tests_harness` bound `pytest`, `approx` and `raises`
after the module code; `build_examples_harness` bound nothing. No one had
decided on the asymmetry, and `LANGUAGE.md` says `#Tests` assertions have
"the same syntax" as `~example`, so a reader reasonably expects the same
environment. Python `BINDING.md` documented only the `#Tests` side.

## Reproduction

```
#Scope

    total = 0.1 + 0.2

~example
    total == approx(0.3)

---

#Tests
    total == approx(0.3)
```

`ERROR scope#example#1 ... name 'approx' is not defined`, while the
`#Tests` line passed.

## Resolution

Decided with Adam (2026-10-18): same names in `~example`.
`build_examples_harness` now binds `pytest`, `approx` and `raises` after
the module code, with the notlob site-packages fallback on the path first
(`run_examples` passes it), so it also works when the target interpreter
has no pytest of its own.

One deliberate difference remains. In `#Tests` the injected pytest helper
replaces a module's own `approx`/`raises` (kept from the in-process
runner). In `~example` the module's own name is kept, since `~example`
never had these names and no existing module can depend on them
overriding its own. Aligning `#Tests` to the same rule would be a
behaviour change for modules that define those names; not done here.

Tests: `TestPytestHelpersInScope` and two harness unit tests in
`tests/test_bindings_python_runner.py`; an isolated-venv test (no pytest
in the target) in `tests/test_bindings_python_target_interpreter.py`,
which fails with the site-packages fallback removed.
