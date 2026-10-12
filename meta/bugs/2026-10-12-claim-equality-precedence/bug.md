# TypeScript claim lines mixing `===` with `&&` / `||` were split at the `===`

**Component:** `notlob/bindings/typescript/tokenizer.py` (`find_split`),
used by `_claim_call` in `notlob/bindings/typescript/runner.py`
**Found by:** pn-chomper (TypeScript target), while adding `~example`
claims. notlob 0.5.4.
**Status:** fixed, 2026-10-12.

## Summary

A claim line is compiled as an equality claim, with separate left and
right lambdas so a failure can report both values, when `find_split`
finds a top-level `===`. It took the *first* top-level `===` without
regard for operator precedence. `&&`, `||`, `??`, the ternary and the
bitwise operators all bind more loosely than `===`, so a line containing
one at the top level is not an equality, but it was split as though it
were:

- a true conjunction **failed**: `1 === 1 && 2 === 2` was read as
  `1 === (1 && 2 === 2)`, reported `left: 1, right: True`.
- a false conjunction **passed**: `0 === 0 && false` was read as
  `0 === (0 && false)`, i.e. `0 === 0`. The `&& false` was lost.

The false pass is the dangerous one: `x === y && z` stopped checking `z`
whenever `y && z` had the same value as `x`.

## Reproduction

The seven-line probe module from the report (`const a = 1; const b = 0;`
and an `~example` block with `1 === 1 && 2 === 2`,
`a === 1 && b === 0`, `a === 1 && true`, `(a === 1) && (b === 0)`,
`true && b === 0`, `0 === 0 && false`, `(0 === 0) && false`) gave
3 passed, 4 failed, with `0 === 0 && false` among the passes. Only the
last two should fail.

The one real instance in pn-chomper was in `io/pnml.lob`:
`_noDecl.defaults.dot === 1 && _noDecl.defaults.ghost === 0`. The
reporter grepped every indented line in every `.lob` file and found no
other claim line combining `===`, `!==`, `==` or `!=` with `&&`, `||`
or `?:`, so no other claim there should change result.

## Scope

- **TypeScript only.** The Python harness uses the AST and reports
  sides only for a single-operator `==` comparison, so `a == 1 and
  b == 0` is a `BoolOp` and was never split. The Haskell runner does not
  split claims at all.
- `||`, `??`, ternary and bitwise operators were affected for the same
  reason (the report had not run them). `!==` was not: it was already
  evaluated as a single boolean, but `a === b !== c` was still split at
  the first operator.

## Resolution

`find_split` now returns the *root* equality of the line:

1. If any operator looser than equality sits at the top level (`&&`,
   `||`, `??`, ternary `?`, `,`, `=>`, assignment, bitwise `& | ^`),
   that operator is the root and the line is not an equality: `None`,
   so it is evaluated as one boolean.
2. Otherwise equality is left-associative, so the *last* top-level
   equality operator is the root (`a === b === c` is
   `(a === b) === c`).
3. A root of `==` or `!=` is `None`, as before; only `===` is reported
   as left/right.

The scanner consumes multi-character operators whole, so the `=` of
`<=`, `>=`, `=>` is never read as an assignment, and `?.` is not read as
a ternary. An operator it cannot classify (a regex literal containing
`|`, say) errs towards "not an equality", which only loses the
left/right report, never a check.

Tests: `TestFindSplitPrecedence` and `TestRealClaimLines` in
`tests/test_bindings_typescript_tokenizer.py` (the latter holds real
lines supplied by pn-chomper), plus `test_conjunction_is_one_boolean_lambda`
and an end-to-end `test_equality_combined_with_and_is_one_boolean` in
`tests/test_bindings_typescript_runner.py`. The end-to-end test fails
with the fix disabled.

## Consequence for existing projects

A claim that was passing only because the `&&`/`||` operand was dropped
will now fail, and it should: those were claims asserting less than they
said. Run `notlob test` and read any new failure as a finding.
