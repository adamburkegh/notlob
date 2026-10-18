# Stored prose ran paragraphs together ("three.The patterns...")

**Component:** `notlob/graph.py` (`_prose_text`)
**Found by:** kamtrinia, in a `[quantifier]` advisory on `codabar.lob`.
notlob 0.5.4 (the check is unreleased; the join is older).
**Status:** fixed, 2026-10-18.

## Summary

`_prose_text` builds a node's stored `content["prose"]` from its prose
and bullet blocks. It joined them with an empty string, so the last
word of one paragraph touched the first word of the next:
`"...use three.The patterns below write..."`. Whitespace between blocks
was lost, and with it the sentence boundary.

The visible symptom was the `quantifier` advisory, which quotes a
sentence and so quoted one with the previous paragraph's tail glued on.
The same text appeared in `notlob query content`, the graph JSON
(`--include-content`) and the Turtle export, and the sentence splitter
could miss a boundary.

## Reproduction

```
#Main

A short introduction to the module.

Each token fires a randomly chosen transition.
```

`notlob check --only quantifier` quoted
`"A short introduction to the module.Each token fires a randomly chosen
transition."`.

## Resolution

Blocks are now separated by a blank line (`"\n\n"`), each stripped, and
empty blocks dropped. A single paragraph's own spans (text and inline
`#Ref`s) still join without separators.

Tests: `test_paragraphs_are_separated_not_run_together`,
`test_prose_and_bullets_are_separated` and
`test_single_paragraph_prose_is_unchanged` in `tests/test_graph_export.py`;
`test_message_does_not_run_paragraphs_together` in `tests/test_check.py`.

## Consequence

`content["prose"]` now contains blank lines between paragraphs, where it
had none. Consumers that substring-search it are unaffected; one that
expected a single unbroken line will see paragraph breaks. This is a
correction of stored content, not a schema change.
