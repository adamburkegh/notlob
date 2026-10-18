# Design note: review the test suite as a suite

**Status:** bookmarked 2026-10-18, not started.
**Origin:** Adam, at ~1350 tests: a broad automated suite is wanted, but
this is a good moment to check how the tests fit together, and to look at
the long-running and redundant ones.

## Goal

Not to cut coverage. To understand the suite as a whole: where the time
goes, where the same behaviour is pinned several times over, and whether
the layout still tells a reader what is tested where.

## What is known (from this session, not yet measured properly)

- The full run has grown from ~100 s (1239 tests) to ~160 s (1351 tests).
- Project-mode CLI tests are the expensive kind: each spawns real
  subprocesses (the claim runners run under a `PATH` python, `tsx` for
  TypeScript, `ruff` for lint). For example `tests/test_cli_test_json.py`
  with `tests/test_address_collision.py` took ~38 s for ~27 tests.
- `tests/test_bindings_python_target_interpreter.py` builds a real venv
  (module-scoped, so once per run).
- `pyproject.toml` runs `--doctest-modules` over `tests` and `notlob`, so
  doctests are part of the count.

## First measurement (`pytest --durations=25`, 2026-10-18)

1355 tests, 161.78 s, so about 0.12 s per test on average. The slowest 25
are all between 1.5 s and 2.6 s: the time is a broad spread of
subprocess-backed tests, not a few outliers.

- **`tests/test_cli_test_json.py` is 20 of the 25.** It re-runs the same
  project once per assertion (a single-file run is ~1.7-1.9 s each, a
  project run ~2.5 s each), roughly 30 s for what is two or three real
  runs. Written this session; the clearest case for a module-scoped
  fixture (one run, many assertions on its output).
- **`tests/test_bindings_haskell_runner.py` integration tests** are
  1.6-2.4 s each (real `runghc`), and `tests/test_cli_run_haskell.py` has
  one in the list. These need the real toolchain; the question is how many
  need a separate run.
- `tests/test_cli_check_json.py` and `tests/test_address_collision.py`
  did not make the top 25, but follow the same pattern.

Only the top 25 were listed; per-file totals and the long tail of the
remaining ~1300 tests still need measuring.

## Method

1. `pytest --durations=50` (and per-file totals) for a real picture
   before touching anything. The list above is a guess until then.
2. For each slow test, ask whether it needs a subprocess or a real
   project on disk, or whether the same assertion can be made at the
   unit level, or from a shared module-scoped fixture (one project, many
   assertions on its output). The `test --json` and `check --json` tests
   re-run the same project for each assertion; one run per fixture would
   cut that.
3. For redundancy: the same behaviour pinned at several levels (parser,
   graph, runner, CLI) is sometimes right (each level can break
   separately) and sometimes copy-paste. List candidates per area, don't
   delete on a hunch.
4. Layout: do file names say what they cover (`test_bindings_<lang>_<part>`,
   `test_cli_<command>`)? Are there two files for one subject?
5. Markers: a `slow`/`integration` split so the fast loop (unit tests,
   seconds) is separate from the full run, if the data says it pays.
   Parallelism (`pytest-xdist`) is an option, not a goal: it is a
   dependency and the subprocess tests may contend.

## Output

A short report here: per-area counts and time, a list of slow tests with
a proposed treatment each, a list of suspected redundant groups, and
proposed layout or marker changes. Decisions are Adam's; nothing is
deleted or restructured without review. The coverage claims in
`CHANGELOG.md` and the bug records (each fix names the test that guards
it) must keep pointing at tests that still exist.
