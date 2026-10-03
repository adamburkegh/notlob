# Python lint flags an import used only by a `~run` body

**Component:** `notlob/bindings/python/lint.py` (`_claim_text`)
**Found by:** notlob-vids, reproduced by observation on 2026-10-03, after
the cross-module lint fix (`2026-10-01-python-lint-cross-module`).
**Status:** open, not fixed. No regression test yet.

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

## Likely fix

Add the `~run` bodies to the text `_claim_text` collects. A helper
already exists: `collect_run_bodies(module)` in
`notlob/bindings/__init__.py` returns `(on_load, on_invocation)` bodies,
dedented. Add a case to `tests/test_lint.py::TestClaimOnlyImportNotFlagged`
using the module above.

## Related, not part of this bug

`~run` code is never linted at all, so an undefined name inside a `~run`
body is not caught by ruff either. Whether it should be is a separate
question (the claim runners would surface it at run time).
