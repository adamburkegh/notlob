# `notlob run` crashes for TypeScript-bound projects

**Component:** `notlob/commands.py` `cmd_run`, notlob-lab at the time of report
(post-0.5.4, pre-0.5.5-cut)
**Found by:** pn-chomper (a TypeScript-bound project), reported via Adam from
that session. Independently cross-checked by notlob-vids against the same
`main` after the fix landed.

## Summary

`cmd_run` only special-cases `language == "haskell"` before falling through
into Python-specific build/execution logic. There was no equivalent branch
for `language == "typescript"`, so a TS-bound module's correctly-assembled
TypeScript source (produced by the real `BindingKit.build`, i.e.
`build_typescript`) got written to a file literally named `<stem>.py` and
handed to a Python interpreter — which fails on the first TS-specific
syntax it hits.

`notlob test`/`notlob build` were unaffected: both already dispatch
per-language through the `BindingKit` abstraction (`run_examples`/
`run_tests`/`run_properties`/`build`), so only `notlob run`'s own
hand-rolled Haskell-or-Python branch was missing the TypeScript case.

## Reproduction

```
$ notlob run petri/marking.lob
  File "...\marking.py", line 128
    `Cannot remove ${count} tokens from '${placeId}' — only ${current} present`
SyntaxError: invalid character '—' (U+2014)
```

A TypeScript template literal (with an em-dash inside it, which is what
made the symptom look like an encoding bug at first) being fed to Python's
tokenizer. Confirmed pre-existing and unrelated to any same-day lint/check
work by running against an untouched module.

## Resolution

**Fixed:** 2026-10-02, commit `edf1c52`.

Added `_cmd_run_typescript`, mirroring the existing `_cmd_run_haskell`'s
shape exactly: calls `build_typescript` (which already correctly handles
`~run`'s on-load/on-invocation split for `notlob build`) and executes the
result with `tsx`/`ts-node` instead of a Python interpreter. Wired into
`cmd_run` as a second `if language == "typescript":` branch alongside the
existing Haskell one.

Also extended TypeScript's `_run_harness` (in
`notlob/bindings/typescript/runner.py`) with a `program_args` parameter,
matching the Haskell runner's existing one — needed so `notlob run
<module> -- arg1 arg2` can pass arguments through for TypeScript the same
way it already does for Python and Haskell.

Covered by a new `tests/test_cli_run_typescript.py`, mirroring
`test_cli_run_haskell.py`'s structure (bare `~run`, `~run on-invocation`,
`~run on-load` — which Haskell doesn't support but TypeScript does, a
plain module with no `~run` claim at all, and a dedicated regression test
reproducing the exact template-literal-with-em-dash shape from the
report). Sabotage-verified: removing the new dispatch branch reproduces
the original failure signature exactly (TS source written to and
SyntaxError'd as `.py`) across all five new tests.

Cross-checked independently by notlob-vids running their own Python-bound
test suite plus pn-chomper's `test`/`build`/`graph`/`query` commands
against the fixed `main` — no regressions, though that check didn't
exercise `notlob run` on a TS-bound module directly (notlob-vids doesn't
call it that way); direct confirmation from pn-chomper against
`petri/marking.lob` itself is still pending at time of writing.
