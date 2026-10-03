# `~on-build` hooks run on single-file builds and warn

**Component:** `notlob/commands.py` (`cmd_build`, `_run_build_hook`)
**Found by:** notlob-vids, listed under "Smaller observations" in its
backport report (copied to `meta/features/2026-10-03-notlob-vids-backport/`);
the reporter hits it on every render.
**Status:** open, not fixed. Behaviour confirmed by reading the code, not
yet reproduced here.

## Summary

`notlob build --output DIR <file>` builds one module, but a declared
`~on-build` hook still runs. The hook receives a manifest holding just
that one artifact, so a hook written for the whole build (pn-chomper's
`inject-bundle.ts`, which bundles the whole game) exits 1. notlob then
prints `WARN   <build>  ~on-build exited 1`, although the module built
and notlob exits 0. Noise, not a failure.

## What the code does

- `cmd_build` with a path (single file) calls
  `_run_build_hook(binding, root, [out_path], output_dir,
  entry_points=...)` once, after `_build_one` (around line 1018).
- The whole-project path calls it with all artifacts (around line 1074).
- `_run_build_hook` documents that a non-zero hook exit "prints a warning
  but does not fail the build", so the exit code stays 0 either way.

## Options

1. **Skip the hook for single-file builds** and say so ("~on-build
   skipped: single-file build"). The hook's contract is "after the
   build assembles artifacts", which a single-module build doesn't
   satisfy for a hook that expects the whole set.
2. **A `--no-on-build` flag**, for callers that want control either way.
3. Both. Option 1 changes behaviour for anyone who relies on the hook
   running after a single-file build, so call it out in the CHANGELOG if
   chosen.

Decision needed from Adam before any change.
