# Python lint flags an import used only by a `~run` body

**Component:** `notlob/bindings/python/lint.py` (`_claim_text`)
**Found by:** notlob-vids, reproduced by observation on 2026-10-03, after
the cross-module lint fix (`2026-10-01-python-lint-cross-module`).
**Status:** fixed, 2026-10-03.

## Summary

That earlier fix stops an F401 for an import used only inside a claim by
checking the unused name against the raw text of every claim
(`_claim_text`). It covers `~example`, `#Tests` and `~property`, but not
`~run`. `assemble()` leaves `~run` bodies out of the linted source (only
`build_python` appends them), so an import used only by a `~run` body
still looks unused to ruff.

## Reproduction

Minimal module, supplied by the notlob-vids session:

```
#Gamma

Doubles a number. Path is imported only for use in the run block.

    def double(n):
        return n * 2

~example
    double(2) == 4

~run
    print(Path("x").name, double(2))

---

#References
    from pathlib import Path
```

```
$ notlob test gamma.lob
LINT   gamma  F401: `pathlib.Path` imported but unused (col 21)
PASS   gamma.lob:9  gamma#example#1  double(2) == 4

1 passed, 1 lint
```

Expected: no lint finding, since `Path` is used by the `~run` body. It
bit notlob-vids before (manim's `config`, used only in a `~run`); they
worked around it by moving the code into a body function.

## Resolution

`_claim_text` now also collects the `~run` bodies, using the existing
`collect_run_bodies(module)` helper in `notlob/bindings/__init__.py`
(both `on-load` and bare/`on-invocation` bodies, module body and
subheadings). A name used only by a `~run` body is no longer reported as
an unused import.

Tests: a new `TestRunBodyImportNotFlagged` class in `tests/test_lint.py`
covers a bare `~run`, `~run on-load`, a `~run` inside a subheading, and a
guard that an import no `~run` uses is still flagged. The three positive
cases failed before the change (reproducing the report exactly) and pass
after.

Confirmed by notlob-vids on 2026-10-05: the minimal repro above now
passes with no LINT line, and their whole project is at 114 claims
passing with no lint findings. They had no `~run` instance left to retest
(the manim `config` use now lives in a body function, which they prefer).

## Related, not part of this bug

`~run` code is never linted at all, so an undefined name inside a `~run`
body is not caught by ruff either. Whether it should be is a separate
question (the claim runners would surface it at run time). notlob-vids
(2026-10-05) doesn't think it needs its own bug, since a `~run` runs on
first use anyway; linting it would be a nice consistency ("everything
indented is linted") but lower priority than the documentation gaps.
