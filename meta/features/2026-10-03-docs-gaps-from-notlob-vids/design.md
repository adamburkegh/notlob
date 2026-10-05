# Design note: documentation gaps found by notlob-vids

**Status:** documentation pass done 2026-10-05. Language-level items are
in `LANGUAGE.md`; Python-specific ones in `notlob/bindings/python/BINDING.md`
(`LANGUAGE.md` points readers there). Open: items 1, 11 (code part), 12.
**Origin:** the notlob-vids dialogue, 2026-10-03. The reporter worked from
`LANGUAGE.md` (via `notlob docs`), then `--help` for the commands it was
stuck on, then the source, then trial and error. These are the places the
docs failed it. Most are documentation only; a few need a small change
noted against them. "Verify first" means a claim taken from the reporter
that has not been checked against the code.

## Items

1. **`--json` for `test` and `check`** is not in `LANGUAGE.md` (only
   `graph --format` is). Covered with the shape fix in
   `2026-10-03-test-json-shape`, which also proposes extending
   `tests/test_language_md_currency.py` to cover CLI flags.
2. **Whole-project commands discover every `**/*.lob` under the root**,
   including nested projects' modules. This is what swept in reference
   projects and started the shelved `~ignore` discussion. *Done:* stated
   under Project structure.
3. **A claim absorbs the code that follows it.** *Done:* stated in the
   Claims section of `LANGUAGE.md`, and the Python runner now explains
   the resulting error (`2026-10-03-claim-body-style-check`).
4. **One namespace per module** (a subheading and a symbol can't share a
   name). Learned from the crash, now reported as an error
   (`2026-10-02-address-collision-crash`). *Done:* now in `LANGUAGE.md`
   under Project structure.
5. **What a lob-ref brings into scope.** The dependency's own top-level
   names, including its `#Appendix`, but not its imports. Verify first:
   at claim run time the dependency's whole assembled source (imports
   included) is inlined, while lint only recognises the dependency's own
   top-level names, so code that leans on a dependency's imports runs but
   fails lint with F821. *Done:* verified in the runner and lint code;
   in `BINDING.md`.
6. **What lint sees.** Only the module's own assembled body code; claims
   are excluded (an unused-import finding is suppressed by name when a
   claim or `~run` body uses it; the `~run` case was fixed in
   `bugs/2026-10-03-run-body-imports-flagged-unused`). *Done:* in
   `BINDING.md`.
7. **`#References` and ruff's import sorting:** a blank line between
   stdlib and third-party groups; a long import may be parenthesised and
   span lines. Both work. *Done:* verified by `TestReferencesImportShapes`
   (`tests/test_lint.py`); in `BINDING.md`.
8. **`notlob build` writes `dist/` relative to the current directory**,
   not the project root. Verified in `cmd_build`. *Done:* documented under
   Commands (`notlob docs` behaves the same). Whether to change the
   default is open.
9. **The namespace injected into `~property` blocks:** `given`,
   `settings`, `assume`, `note`, `target`, `HealthCheck`, `Phase`,
   `Verbosity`, `st`, `strategies` (checked in `harness.py`). `LANGUAGE.md`
   lists only `given` and `st`, so the reporter added a redundant
   `from hypothesis import ...`. Module-level code runs before the
   injection and doesn't see these names. *Done:* in `BINDING.md`, not
   the language reference (it is binding-specific).
10. **Each claim batch re-imports the module.** `~example`, `#Tests` and
    `~property` run in separate subprocesses, so module-level work (for
    example loading a real project's graph in an `#Appendix`) runs once
    per batch. Worth a sentence. *Done:* verified in the runner;
    in `BINDING.md`.
11. **Which interpreter claims ran under.** Running `notlob test` without
    the project's Python on `PATH` fails inside the harness with
    `ModuleNotFoundError`; the message could name the interpreter. Small
    code change plus a doc line. *Doc line done* (`BINDING.md`); the
    code change is not.
12. **A project-wide way to set Hypothesis settings.** A harness with
    heavy imports (manim) can trip the `too_slow` health check on the
    first draw. Currently each property sets it itself. A documented
    project-level setting would be a (small) feature, not just docs.
13. **Depending on notlob as a library** puts a `notlob` executable in the
    consumer's venv ahead of the real one on `PATH`. Deprioritised
    (see the roadmap note); at minimum, document it. *Done:* a note in
    `BINDING.md`. Not reproduced; it states the standard consequence of a
    console-script entry point.
