# Design note: fix the shape of `notlob test --json`

**Status:** proposal, queued (not started)
**Origin:** notlob-vids backport report (`notlob-vids/docs/notlob-backport.md`,
section 1) and the follow-up dialogue, 2026-10-03.
**Tier:** machine-readable output, i.e. the stable tier in `DESIGN.md`
("What tools can build on").

## Summary

The report asked for `notlob test --format json`. That output already
exists as `notlob test --json` (`cmd_test`, `_result_dict` in
`notlob/commands.py`), but it is not mentioned in `LANGUAGE.md`, so the
consumer never found it and parsed the human-readable text with a regex.
So this is a proposal to fix the shape of what exists, plus documenting
it, not to add a flag.

## Current shape

```
{"passed": N, "failed": N, "lint": N,
 "results": [ ...claim dicts and lint dicts, mixed... ],
 "check_findings": [...]}      # project mode only, and only if non-empty
```

A claim dict is `{address, line, status, file, source_line, ...}` with
`left`/`right` on FAIL and `error` when present. A lint dict is
`{address, code, message, col}`.

## Gaps found

- `file` is `Path(...).name`, a bare file name. Two modules with the same
  file name in different directories are indistinguishable. The text
  output has the same problem (`marking.lob:136`).
- Claim results and lint findings share one `results` list, told apart
  only by which keys they carry.
- `line` is the assertion's source text and `source_line` is the number.
  Consumers expect the opposite naming.
- No `kind` (EXAMPLE, PROPERTY, TEST, ...).
- Check findings appear only in project mode and only when non-empty.
- No schema and no version field.

## Proposed

Keep it additive where it can be:

- A project-relative path field (the existing `file` could be corrected
  to this; it is a fix, not a feature).
- Separate `claims`, `lint` and `checks` arrays; `checks` always present
  in project mode (possibly empty).
- `kind` on each claim; `source` for the assertion text.
- A `version` field, and a schema file beside `schema/name_graph.json`.
- Exit codes unchanged.
- Document `--json` for `test` and `check` in `LANGUAGE.md`, and extend
  `tests/test_language_md_currency.py` to cover CLI flags (it currently
  checks subcommand and check names only, which is why this gap was not
  caught).

Open decision: whether the renamed `line`/`source` fields are introduced
alongside the old ones for a deprecation period, or as a version bump.
Per `DESIGN.md`, a breaking change here must be called out in the
CHANGELOG either way.

## Consumer requirements (notlob-vids, 2026-10-05)

From the notlob-vids session, written against its real use. `src/evidence.lob`
runs `notlob test petri/marking.lob` in pn-chomper and builds
`{source line: status}` for that module, to draw a tick beside each source
line of a listing. It runs with `check=False` and reads the document
whether or not a claim failed (a failing claim is a result to show, not an
error).

Needed, in order of importance:

1. `line` as an integer, 1-based: the assertion's own line for `~example`
   and `#Tests`; the sigil line for a `~property` (as the text output gives
   today).
2. `status`: PASS / FAIL / ERROR / SKIP.
3. `file` relative to the project root (`petri/marking.lob`), so two
   modules with the same file name can be told apart.
4. Claims in their own list, separate from lint and check findings.
5. Stdout is only the JSON document: any Hypothesis output goes to
   stderr, so `json.loads(stdout)` always works. *Verify first* that this
   holds today. (The `~on-build` warning the reporter mentioned is not a
   concern: only `notlob build` runs the hook, and its warning goes to
   stderr.)
6. Exit codes unchanged.

Useful, not needed: `address` (joining to graph nodes is more robust than
joining on line numbers, which shift on edit); `kind`
(EXAMPLE/PROPERTY/TEST); `end_line` for multi-line assertions; a duration
per claim; a `version` field. Not needed: the assertion's source text, or
per-run totals.

Behaviour to pin down: when a single file is tested, the document contains
only that module's claims, though its dependencies are assembled alongside
(this matches the text output today).

Note that item 1 conflicts with the current names: today `line` is the
assertion text and `source_line` the number (see "Gaps found"), so meeting
the consumer's `line` is the breaking rename the open decision above is
about. Item 3 keeps the name `file` but changes its value (bare name to
project-relative path).

## Reference code

notlob-vids `src/evidence.lob`, section `##Claim Results`: `RESULT_LINE`,
`parse_results(output)` (the regex this makes unnecessary) and
`claim_results(project, module)` (which would become a `json.loads`).
