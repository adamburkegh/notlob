# A failing `~property` loses its real exception behind Hypothesis's own output

**Component:** Python property-claim harness (`notlob/bindings/python/harness.py`
`_PROPERTY_HELPER`, parsed by `notlob/bindings/python/runner.py`
`_parse_property_protocol`).
**Found by:** notlob-vids (`src/highlight.lob`, property
`spans-tile-source`), reported via Adam.
**Status:** fixed, 2026-10-03.

## Summary

When a Python `~property` fails for a Hypothesis reason other than a
plain assertion (here a `FailedHealthCheck`), `notlob test` reports only:

```
ERROR  highlight.lob:197  highlight#Syntax#spans-tile-source  ~property spans-tile-source
         error: unexpected runner output: 'You can reproduce this failure by adding @seed(66785644850119754922777760180824991438) to this test.'
```

The actual cause never appears. Replaying the seed by hand showed it was:

```
FailedHealthCheck: Input generation is slow: Hypothesis only generated 1 valid inputs after 1.59 seconds ...
```

(Probably caused by the laptop sleeping mid-run; the property passes on
retry.)

## Root cause

The harness block for one property (`harness.py`, `build_properties_harness`)
is:

```python
print("CLAIM\t" + addr + "\t" + sl + "\t" + sigil)
_notlob_claim_ns = dict(globals())
try:
    exec(prop_source, _notlob_claim_ns)
except Exception as _notlob_exc:
    print("ERROR\t" + type(_notlob_exc).__name__ + "\t" + repr(str(_notlob_exc)))
else:
    _notlob_run_property(sigil, _notlob_claim_ns, _notlob_baseline)
```

and `_notlob_run_property` (also in `harness.py`) does:

```python
try:
    _notlob_callable()
    print("PASS")
except Exception as _notlob_exc:
    print("FAIL\t" + type(_notlob_exc).__name__ + "\t" + repr(str(_notlob_exc)))
```

That `except Exception` *does* catch `FailedHealthCheck` and *does* print
a structured `FAIL\t...` line — the harness side looks correct in
isolation. The actual problem is upstream of it: calling
`_notlob_callable()` runs the `@given(...)`-decorated property, and
Hypothesis's own internal reporting (`hypothesis.reporting.report`, which
by default just calls `print`) writes its own diagnostic lines — the
"Falsifying example"/"@seed(...) to reproduce" hint among them — directly
to stdout *during* that call, before the exception ever reaches our
`except Exception` handler.

So the real stdout sequence on a health-check failure is:

1. `CLAIM\t<addr>\t<line>\t<sigil>` (ours)
2. one or more lines of Hypothesis's own verbose reporting (not ours —
   interleaved in, not suppressed)
3. `FAIL\t<type>\t<message>` (ours, printed only after step 2's exception
   propagates out)

`_parse_property_protocol` (`runner.py:299-`) assumes the line
*immediately following* `CLAIM` is always the one result line:

```python
i += 1
if i < len(lines):
    result_line = lines[i]
    if result_line == "PASS": ...
    elif result_line.startswith("FAIL\t"): ...
    elif result_line.startswith("ERROR\t"): ...
    else:
        # "unexpected runner output" -- this branch
```

It has no tolerance for Hypothesis's own lines landing in between, so it
grabs the first intervening line (the `@seed(...)` hint) as "the result,"
reports it as `unexpected runner output`, and never looks at the real
`FAIL` line that would have followed it.

## Reproduction

Any `~property` whose strategy is slow on its first draw (e.g. a large
`st.from_regex(...)` on a cold start) or the machine sleeping mid-run,
either of which can trigger Hypothesis's `FailedHealthCheck` and its
verbose reporting. Reproduced deterministically and quickly, without
relying on real timing, via `st.integers().filter(lambda x: False)` —
a filter that drops every input reliably triggers the same
`FailedHealthCheck` and the same `@seed(...)` stdout interleaving as
the slow/sleeping-machine case in the original report; confirmed by a
first-principles check that an *ordinary* `AssertionError`-based
property failure (a real falsifying example, no health check involved)
was never affected by this bug in the first place — Hypothesis doesn't
interleave the same verbose reporting ahead of a plain assertion
failure, only ahead of exceptions like `FailedHealthCheck` that it
handles through a different internal path.

## Resolution

`_notlob_run_property` (`harness.py`) now wraps the call to the
property callable in
`with _notlob_hyp.reporting.with_reporter(lambda _msg: None):`,
swallowing Hypothesis's own stdout reporting entirely for the duration
of that one call — regardless of which specific setting (verbosity,
`print_blob`, ...) would otherwise control any one message, rather
than chasing each diagnostic line Hypothesis might print by name. Only
the harness's own `print()` calls (never touched by `with_reporter`,
which is specific to Hypothesis's internal reporting channel) reach
the parser now.

Separately, acting on the original report's own suggestion ("It would
help if the runner reported the exception type and message"):
`_parse_property_protocol` (`runner.py`) already received the
exception's type name over the wire (`FAIL\t<type>\t<message>`) but
discarded it, keeping only the message. Both the `FAIL` and `ERROR`
branches now prefix the reported message with the type name (e.g.
`FailedHealthCheck: It looks like this test is filtering out a lot of
inputs...`), for every property failure, not just this bug's specific
trigger.

Not done: capturing Hypothesis's suppressed reporter output and
reattaching it to the FAIL message as extra detail (the report's "kept
the seed line as extra detail" suggestion). Swallowing it entirely
already fixes the actual complaint — the real exception no longer
disappears — and keeping the message's provenance as a deliberately
separate, smaller nice-to-have avoids adding complexity (buffering,
formatting a multi-line extra-detail block) for something that isn't
needed to close the bug.

Tests in `tests/test_bindings_python_property_runner.py`
(`test_failed_health_check_reported_not_swallowed`): reproduces the
exact bug with the deterministic `filter` trick above, asserts the
result is a normal `FAIL` carrying the real `FailedHealthCheck`
message (type-prefixed) rather than an `ERROR` quoting the `@seed(...)`
hint, and asserts the hint itself no longer appears anywhere in the
reported error. Confirmed failing before the fix (reproduces the
original bug exactly), passing after. Full suite green.
