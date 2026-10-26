# An assertion after commentary in #Tests is reported at the wrong line

**Component:** the `#Tests` collectors in all three bindings' runners
(`_collect_group_assertions` and the section-level loop in
`notlob/bindings/{python,haskell,typescript}/runner.py`).
**Found by:** reading the Python runner while designing the
`assertion_block` rule (`meta/features/2026-10-23-name-graph-as-parse-tree`,
D14), 2026-10-25. Not reported by a user.
**Status:** open. Shown for Python by an expected-failure test,
`tests/test_bindings_python_runner.py::TestTestsLinesAfterCommentary`
(`xfail(strict=True)`: remove the marker when it is fixed). Haskell and
TypeScript have the same code shape and are not yet shown by a test.

## Summary

```
#Tests

##g
    f() == 1        line 11   reported 11
                    line 12
Commentary.         line 13
                    line 14
    f() == 1        line 15   reported 14
```

The test fails with `assert [11, 14] == [11, 15]`.

## Cause

The runner gathers a group's bare assertion lines into one list and ends
the list only at a `~test` (or, at the section level, at a group).
Commentary is skipped without ending it:

```python
for idx, item in enumerate(group.items):
    if isinstance(item, str):
        bare.append(item)              # bare lines and blank lines
    elif isinstance(item, NamedTest):
        _flush_bare()
    # ProseBlock: commentary, not evaluated.
```

The lines on either side of the commentary are then handed to
`_iter_assertions` as one block, and each assertion's line is computed as
the first line of the list plus its position in it. The commentary's
lines are not in the list, so every assertion after it is reported that
many lines early. An assertion that is incomplete at the commentary (an
open bracket) would also be joined across it.

## Why it was not seen

The example projects put commentary just before a `~test`, where the
list ends anyway (e.g. Roman's `encoding` group).

## Fix

By design rather than in the runners: commentary ends an anonymous test,
and an `assertion_block` grammar rule defines where each begins and ends
(D14, slice 2e). The runners then read the blocks instead of regrouping
lines, which slice 4 does. Today the same grouping is done three ways
(`build`, the forest oracle test, and each runner), and the runners' way
is the one that differs.
