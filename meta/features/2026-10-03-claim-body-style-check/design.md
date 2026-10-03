# Design note: flag code placed directly after a claim

**Status:** partly done; the advisory check is queued (not started)
**Origin:** the notlob-vids dialogue, 2026-10-03. The reporter hit this
three times and called it the biggest time sink of the project.

## Problem

A claim's body ends only at the first line that is neither indented nor
blank (`claim: SIGIL _body_line+` in `grammar.lark`). An indented code
block placed directly after an `~example`, even across blank lines, is
therefore absorbed into the claim. The absorbed `def` or `class` then
fails as an assertion with a bare "invalid syntax", and the names it
would have defined show up as undefined elsewhere (F821). It is also
poor literate style: prose should introduce code.

There is no declarative grammar fix without changing the language (a
terminator, or different indentation), which is not proposed.

## Done

- The Python runner now says what happened when an `~example` or
  `#Tests` line fails to parse because it is a statement (a `def`,
  `class`, `import`, decorator, or an assignment): the error names the
  cause and the fix (a line of prose between the claim and the code).
  See `CHANGELOG.md`.
- `LANGUAGE.md` states the convention.

## Remaining

1. **An advisory `style` check** that flags the same thing without
   running anything. It cannot be purely structural, because the parse
   tree has no "code after a claim", only a claim with odd contents; it
   is content-based. It would apply to `~example` and `#Tests` bodies,
   never `~property` or `~run`, where code is legitimate.
2. **Per-binding keyword lists.** The definition keywords differ by
   language (`def`/`class`; `function`/`const`; a Haskell signature), so
   this needs a small hook on `BindingKit` or a Python-only first
   version.
3. **The same clearer message in the TypeScript and Haskell runners**,
   which are unchanged.

Main tradeoff: the check mostly duplicates what the runner already
catches at test time, just earlier and with a clearer message. Worth
doing if people still hit it after the runner message and the doc line.
