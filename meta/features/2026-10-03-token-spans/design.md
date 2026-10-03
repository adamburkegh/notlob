# Design note: token spans for `.lob` source

**Status:** proposal, queued (not started)
**Origin:** notlob-vids backport report (section 2) and follow-up
dialogue, 2026-10-03.
**Tier:** a narrow stable wrapper over unstable internals, the pattern
`DESIGN.md` ("What tools can build on") describes.

## Summary

Editors, an HTML `weave`, documentation sites and visualisers all need to
know what each span of a `.lob` file *is* (title, prose, ref, code,
claim, ...). notlob-vids did this by reading positions off notlob's own
parse tree, so what it colours as a claim is exactly what notlob runs as
a claim. That works, but it ties the consumer to Lark rule and terminal
names, which are in the unstable tier. This proposes promoting a small,
specified function so that coupling lives inside notlob.

## Why consumers need help today

1. The parser normalises token *values* (strips `#`, `##`, trailing
   newlines), so values cannot give positions. Positions must come from
   `start_pos` / `end_pos` / `line`, which survive normalisation.
2. One terminal means different things in different places.
   `INDENTED_LINE` is code in a `code_block`, a claim body in `claim`,
   `named_test`, `test_group` or `test_item`, and a declaration in
   `references_section`. The kind has to come from the enclosing rule.

## Proposed interface

```python
from notlob.tokens import spans
spans(source: str) -> list[Span]      # Span(line, start, end, kind)
```

and optionally `notlob tokens <file> [--format json]`.

- `line` is 0-based; `start`/`end` are columns, end exclusive.
- Spans never cross a line and never include the newline.
- **Tiling guarantee:** on every line the spans are in order, do not
  overlap, leave no gap and end where the line ends, so every character
  is in exactly one span.

Kinds (names are a suggestion): `title` (`MOD_HEAD`), `subheading`
(`SUBHEAD`), `prose` (`LINE_START_TEXT`, `PROSE_TEXT`), `ref` (`REF`),
`bullet` (`BULLET`), `sigil` (`SIGIL`, `TEST_SIGIL`), `code`
(`INDENTED_LINE` in `code_block`), `claim` (`INDENTED_LINE` in `claim`,
`named_test`, `test_group`, `test_item`), `structure` (everything else:
separator, post-text heads, binding declarations, references lines).

## Conditions agreed in review

- **A currency test** asserting every terminal in `grammar.lark` has a
  kind, built like `tests/test_language_md_currency.py`. The consumer's
  own `TOKEN_KINDS` silently falls back to `structure` for any terminal
  it did not list; that is the "declarative artifact that rots" failure
  mode the quantifier-check design warns about.
- **The tiling property as a test**, both as a generated property and as
  a test over every `.lob` in notlob's own `examples/`.

## Not proposed for core

Colouring the *inside* of code blocks (notlob-vids uses Pygments, picking
a lexer from the binding's `~language`). That is rendering, adds a
dependency, and stays outside.

## Reference code

notlob-vids `src/highlight.lob`: `Span`, `TOKEN_KINDS`, `INDENTED_KINDS`,
`classify(rule, token_type)`, `_tokens(tree)`, `spans(source)`,
`tiles(source, spans)`, `~property spans-tile-source` and the `#Tests`
group `real sources tile`. The Pygments layer (`syntax_spans`,
`highlight`) is for reference only.
