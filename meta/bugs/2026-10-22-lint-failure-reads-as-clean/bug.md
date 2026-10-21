# A linter that fails to run is reported as a clean lint

**Component:** `notlob/bindings/python/lint.py` (`_run_ruff`),
`notlob/bindings/haskell/lint.py` (the hlint JSON read).
**Found by:** dating the Gutenberg example's `F541` findings, 2026-10-22.
**Status:** open, not fixed.

## Summary

`_run_ruff` runs ruff, then does `json.loads(proc.stdout)` and on
`JSONDecodeError` or `ValueError` returns `[]`: no findings. When ruff itself
fails (non-zero exit with nothing on stdout, as it did when handed source it
could not decode), that is indistinguishable from a clean module. The
Haskell binding has the same shape (`haskell/lint.py`, around line 126).

It hid real findings for months: on Windows, source with non-ASCII text was
passed to ruff in the default codepage, ruff exited 2 with "stream did not
contain valid UTF-8", and `notlob test` reported no lint at all for such a
module from the lint module's arrival (`bbc9c8c`, 2026-05-28) until the
encoding was set explicitly (`9fde779`, 2026-08-11). The Gutenberg example's
three `F541` findings surfaced only then, and were still unnoticed because
no test ran the example.

This is the same family as the Appendix being dropped from the name-graph: a
failure path that degrades to an empty, plausible result.

## Expected

Output ruff (or hlint) could not produce is an error on the module, with the
tool's stderr and exit code, not an empty list. A genuinely clean run exits
0 (or 1 with findings) and prints a JSON list.

## Not yet checked

* The TypeScript lint (`typescript/lint.py`) has `return []` paths; whether
  any are the same swallowing was not looked at.
* A test that makes the tool fail (a fake interpreter, or source ruff
  rejects) and expects an error rather than a pass.
