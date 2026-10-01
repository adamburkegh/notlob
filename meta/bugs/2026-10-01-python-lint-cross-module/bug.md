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

Adam asked for a split: fix 1 and 2 now, treat 3 as a separate follow-up
(it needs a different, heavier mechanism — see below).

**Fixed**, 2026-10-01:

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

**Deferred** — F811 (3): the dependency's own `#References` imports
shouldn't be part of the prepended context at all; only its top-level
*names* are needed for cross-module name resolution (suppressing
false-positive F821). Fixing this properly means generating a lightweight
stub of a dependency's public names instead of prepending its full
assembled source (imports included) — a heavier change than 1/2, and one
that touches the same "don't let a quick fix regress the thing it meant
to fix" territory as the PEP8 blank-line bug earlier this project
(see `2026-08-12-py-lint-space`). Not started.
