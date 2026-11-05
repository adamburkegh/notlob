# Slice 11 brief: the code reads the whole parse tree

**For:** the implementing session. **Written by:** the design session,
2026-11-06. **Design:** "The parse tree is the whole source" in
`notlob/docs/DESIGN.md`; `notlob/grammar.lark` as Adam has written it.

## Why

Commit 790716c made the grammar's markers `_`-prefixed, so Lark dropped
them from the tree: `#`, `##`, `~test ` and the rest were in no token.
notlob-vids' highlighter, which tiles the source from the tree, caught
it; no notlob test did. Adam reverted the grammar (d009d48) and has
written a new one, now in the working tree, uncommitted. The code still
expects the 790716c grammar, so the suite is red. This slice makes the
code read the new grammar.

## Ruled (Adam, 2026-11-05 and 06)

* **The grammar is Adam's.** `notlob/grammar.lark` is not to be edited.
  If the code seems to need a grammar change, stop and send the design
  session the proposal, with why. Do not work around the grammar in
  Python to avoid that conversation.
* **The parse tree is the whole source**: every character of a `.lob`
  file is in exactly one token, in order. Nothing is filtered or folded:
  no name in the grammar begins with `_`.
* **Comments say only what the code cannot show** and no test holds, in
  a line or two. No explanatory essays (Adam, of the old grammar:
  "unreadable garbage").

## What the grammar now says

Each named line is a rule of its own, and each token is exactly one
thing:

```
module_head:   MOD_MARK SPACE? NAME EOL
sub_head:      SUB_MARK SPACE? NAME EOL       (subheading, test_group)
property_head: PROPERTY_MARK SPACE NAME EOL
test_head:     TEST_MARK SPACE NAME EOL
appendix_head: APPENDIX_MARK (SPACE NAME)? EOL

MOD_MARK "#"   SUB_MARK "##"   PROPERTY_MARK "~property"
TEST_MARK "~test"   APPENDIX_MARK "#Appendix"   SPACE /[ \t]+/
NAME (no `#`, no space at either end)   EOL (trailing spaces, newline)
```

`sub_item` and `body_line` are now nodes (they were `_sub_item` and
`_body_line`). `MOD_HEAD`, `SUBHEAD`, `TEST_SIGIL` and `APPENDIX_HEAD`
are gone; a bare `~property` is still `SIGIL`.

## The change

* `parser.py`, `model.py`: read the new tree. A name is the `NAME` token
  of the head node, by type, not by position. Nothing past `model.py`
  changes: the models of the examples are as they are today.
* `util/gen_grammar_latex.py` and `util/gen_listings_lang.py` run on the
  new grammar, and their tests pass.
* Anything else that reads tree rule or terminal names (weave, tests).
* CHANGELOG: rewrite in place the unreleased entry from 790716c ("a
  name is a terminal"): the tree is whole; the token types that went
  and what replaced them; `#AppendixFoo` is now an error.
* LANGUAGE.md, if it names terminals or rules.

## Tests, first

1. **The tree is whole.** For every `.lob` under `examples/`, and for a
   set of awkward sources (`# Title`, `#Appendix`, `#Appendix Notes`,
   `~test  two-spaces`, trailing spaces and tabs on a heading line, a
   bare `~property`), the tokens' `start_pos`/`end_pos`, in order,
   cover the source exactly: no gap, no overlap.
2. **No name in `grammar.lark` begins with `_`**, read from the file.
3. A bare `~property` line is `SIGIL`, and `~property name` is a
   `property_head`, pinned.
4. `#AppendixFoo` is a parse error.
5. What `test_names_no_hash.py` refuses is still refused.
6. The models and graph documents of the examples are unchanged (the
   existing goldens and tests, as they stand).

## Rules

May touch `notlob/` except `grammar.lark` and the bindings, the tests,
CHANGELOG and LANGUAGE.md. A test of the 790716c tree shape is
updated to the new shape only where the behaviour is the same; say
which. No commit, no staging. 80-character lines.

## Report

What changed, by file; test 1's sources and result, and how you
checked it fails on a tree with a gap (without editing `grammar.lark`:
a filtered marker in a copy under `var/`, say); tests changed, by file, and
why; anything that seemed to want a grammar change (stopped, with the
proposal).
