# A failing `~property` loses its real exception behind Hypothesis's own output

**Component:** Python property-claim harness (`notlob/bindings/python/harness.py`
`_PROPERTY_HELPER`, parsed by `notlob/bindings/python/runner.py`
`_parse_property_protocol`).
**Found by:** notlob-vids (`src/highlight.lob`, property
`spans-tile-source`), reported via Adam.
**Status:** open, not fixed. Root cause confirmed by reading the code;
no fix implemented yet.

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
verbose reporting. Not yet reproduced from a from-scratch minimal
example in notlob-lab itself — confirmed only by reading the harness/
parser code end to end, matching the reported symptom exactly.

## Possible direction (not implemented)

Suppress Hypothesis's own stdout reporting entirely within the harness,
so only the harness's own `print()` calls ever reach the parser.
`hypothesis.reporting.with_reporter(new_reporter)` (confirmed present in
hypothesis 6.152.9, the version this repo depends on) is a context
manager built for exactly this — wrapping the call to `_notlob_callable()`
in `with _notlob_hyp.reporting.with_reporter(lambda msg: None):` would
swallow Hypothesis's own chatter regardless of which specific setting
(verbosity, `print_blob`, ...) would otherwise control any one message,
rather than chasing each diagnostic line Hypothesis might print by name.
Not implemented or tested yet — picking the right reporter behavior
(swallow everything vs. capture-and-attach to the FAIL line as extra
detail, which the original report suggested would help) needs a decision
before writing the fix.
