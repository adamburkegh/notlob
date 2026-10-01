# Python linter gives false findings when a module references other modules

**Component:** `notlob/bindings/python/lint.py`, notlob 0.5.4
**Found by:** notlob-vids (`C:\Users\adamb\bpm\notlob-vids`), reported via a
cross-session message from that project's Claude session, reviewed and
forwarded by Adam.

## Summary

To lint a module, notlob assembles its code, puts the assembled code of
every lob-ref dependency (`#References` → `#Module`) *above* it, and runs
ruff over the combined text (`_prepend_deps`). ruff then treats the whole
thing as a single Python file. That gives three kinds of false finding:

1. **Imports used only by claims are flagged unused (F401).** Claims
   (`~example`, `~property`, `#Tests`) aren't part of the linted source, so
   an import that only a claim uses looks unused. Independent of
   dependencies.
2. **A dependency's findings are reported against the module that
   references it.** The dependency's code is part of the text ruff checks,
   so its F401 findings appear again under every module that references
   it.
3. **An import shared by two modules is flagged as a redefinition
   (F811).** A dependency's own `#References` imports are prepended
   alongside its code; if the referencing module imports the same name
   again (correctly, per "each module lists exactly what it uses"), ruff
   sees two bindings of one name in one scope and flags the second as
   redefining an unused first.

## Reproduction

A three-file project (`binding.lob`, `alpha.lob` defining `load()` with
`Path` used only in a claim, `beta.lob` referencing `#Alpha` and
re-importing `json`) — see the forwarded report's full text for the exact
`.lob` contents; reproduced independently against a fresh copy in this
repo's own scratchpad before fixing anything.

```
$ notlob test alpha.lob
LINT   alpha  F401: `pathlib.Path` imported but unused (col 21)
...
$ notlob test beta.lob
LINT   beta  F401: `pathlib.Path` imported but unused (col 21)
LINT   beta  F811: Redefinition of unused `json` from line 1: `json` redefined here (col 8)
...
```

## Resolution

Adam asked for a split: fix 1 and 2 first, treat 3 as a separate
follow-up (it looked like it needed a heavier mechanism — see below).

**Fixed**, 2026-10-01, in two passes:

**Pass 1 — 1 and 2:**

- **F401-from-claims (1):** `_claim_text()` collects every claim's raw
  source (every `~example`/`#Tests`/`~property` body the runner actually
  executes) into a flat blob; an F401 finding is suppressed when the
  reported name appears in it. Textual, best-effort — consistent with how
  `extract_calls` is documented elsewhere in this codebase, not real
  static analysis. A name that only coincidentally appears in a claim
  (inside a string literal, say) would wrongly suppress a genuine finding;
  judged the safer failure mode than always flagging an import a claim
  genuinely uses.
- **Misattribution (2):** `_run_ruff` already computed an `adjusted` line
  number (ruff's reported row minus the dependency-text offset) to look up
  the section address, but when `adjusted` fell at or before 0 — meaning
  the finding was actually inside the prepended dependency text, not the
  module being linted — it silently fell back to the module's own
  address instead of being dropped. Now dropped unconditionally.

This pass still prepended each dependency's full assembled source
(imports included) ahead of the module being linted, for cross-module
name resolution — initial plan for 3 was to generate a lightweight
stub of a dependency's public names instead, to stop its imports from
being part of that prepended text at all.

**Pass 2 — simplified, and fixed 3 as a side effect:** on reflection,
prepending anything at all was unnecessary complexity for what the
mechanism was ever actually for — suppressing a false-positive `F821`
"undefined name" when a module calls something a lob-ref dependency
defines. `extract_symbols` already extracts a module's own top-level
`def`/`class`/assignment names (ignoring `import` lines entirely, since
those aren't AST nodes it handles) — reused here as `_dependency_names`
to collect what names a dependency defines, and an `F821` finding is now
dropped by name-match alone, with nothing ever prepended to what ruff
lints. Only the module's own source is ever sent to ruff. This:

- Makes 2 moot by construction (nothing to misattribute — there's no
  dependency text in the linted source at all).
- Fixes 3 as a side effect (the dependency's own `#References` imports
  are never part of the linted text either, so they can't collide with
  the referencing module's own).
- Is simpler than pass 1's own mechanism, not just a fix for 3 —
  deleted the whole `_prepend_deps`/offset/`adjusted <= 0` apparatus
  pass 1 added.

Real cross-module reference *correctness* (is this call actually valid,
not just "is this name spelled the same somewhere") is notlob's own
`NameGraph`-based `check` command's job, which has the real call graph —
ruff's F821 was only ever redundant noise for the cross-module case, not
a check anything relies on for real coverage.
