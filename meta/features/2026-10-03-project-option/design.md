# Design note: a `--project DIR` option

**Status:** proposal, queued (not started)
**Origin:** notlob-vids backport report (section 4) and follow-up
dialogue, 2026-10-03.
**Size:** small.

## Summary

`notlob graph`, `notlob query`, `notlob check` and whole-project
`notlob test` find the project from the current directory. To run them
against another project the caller has to change directory or spawn a
subprocess with a different `cwd`. notlob-vids does the latter for every
call into the reference projects it studies:

```python
subprocess.run(["notlob", "graph", "--format", "json"], cwd=project_dir, ...)
```

## Proposed interface

A global option naming the project root (the directory containing
`binding.lob`), like `git -C`:

```
notlob --project DIR graph --format json
notlob --project DIR query content "petri/marking#Enabling and Firing"
notlob --project DIR test
```

File arguments already locate their project by walking up from the file,
so this matters only for commands that take no file.

## Second use case: read-only reference projects

notlob-lab keeps git-ignored copies of other projects under
`ref-projects/` (the first is `ref-projects/notlob-vids`, whose project
root is its `src/`). They are read-only reference for a session that
works one-project-at-a-time. Today, running `graph`, `query` or `check`
against one means changing directory, which conflicts with working from
the project root with root-relative commands. With the option:

```
notlob --project ref-projects/notlob-vids/src graph --format json
```

`--project` doesn't change which commands are safe there: `graph`,
`query`, `check` and `weave` only read, while `test` and `build` write
artifacts (`dist/`, caches), so they stay off limits for a read-only copy.

## Notes

- Some of the plumbing exists: `_require_root(hint)` and
  `_require_graph(hint)` in `notlob/commands.py` already take a hint. The
  work is a global argparse option threaded through the file-less
  commands (`test`, `check`, `graph`, `query`, `weave`, `build`).
- It also solves the problem the shelved `~ignore` proposal addressed
  (reference projects living inside the host project) more simply: point
  at the other project instead of excluding it from this one.
- Node tooling resolves `tsx` relative to the project root
  (`node_bin`); with `--project` the root must be the one named, not the
  current directory.
