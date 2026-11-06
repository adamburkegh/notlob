# notlob-vids tries out 0.6.0 before release

**For:** the notlob-vids session. **Written by:** the notlob design
session, 2026-11-05, at Adam's request: "Let's get notlob-vids to try it
out before releasing." Stage 5 of the external-outputs work, as a trial:
notlob is not released until this comes back.

## What to do

1. Pick up notlob-lab at Adam's latest commit. How notlob-vids gets it
   (its install, its `ref-projects/` copy) is your project's business:
   ask Adam if it is not obvious.
2. Move notlob-vids onto it: its renders, its tests (`notlob test`), and
   its `style.lob` check of kinds against `schema/name_graph.json`.
3. Report back to the design session (below). Do not patch notlob; a
   problem in notlob is the finding.

## What changed in notlob, for a consumer

**`notlob graph --format json`** is one view at a level:

* Levels are `outline` (the default, `1`), `index` (`2`), `block` (`3`,
  new) and `full` (`4`), each holding the one before.
* **At the default `outline` there are no reference edges.** `IMPORTS`,
  `USES`, `CITES` and `USES_EXTERNAL` arrive at `--level index`. A
  consumer that reads `IMPORTS` from the default document gets none.
* The tree's edges are `CONTAINS` and, new, `CONTAINS_INDIRECTLY`, which
  runs from a node to what is written in it through nodes the level hides
  (a section to the symbols of its code blocks, at `outline`). A walk of
  the tree takes both.
* A reference starts at the nearest node an `outline` shows, at every
  level, and is one edge for each source, target and kind, with `lines`
  (every line it is on) in place of `start_line`.
* A node has `address`, `kind`, `name` where it has one, `start_line`,
  and `file` on the root of each tree (a module) only. **There is no
  `label`**: use `name`. A paragraph, code block, unnamed claim or keyword
  section (`#Tests`, `#References`, `#Binding`) has no name. There is no
  `size`, `refs` or `text`; at `full` a node has `body`, its own lines as
  written.
* The schema is `schema/name_graph.json`, rewritten; `APPENDIX`,
  `TEST_LINES` and the rest of the kinds are in its enum.

**`notlob graph`** as text is an outline: each file's path, then a line
for each node with its line number, runs of lines as ranges (`78-86`).

**`notlob query content ADDR`** prints the view started at the address,
at `full`: as text, the file (with `:LINE` when the view does not start
at line 1, `hello.lob:65`) and then its lines, with no other header; as
JSON, a graph document. `--depth` works in both.

**`notlob query`** answers print `name`, not `label`, and `file` on
every node. `search` matches names only: a node with no name is never
found by a pattern.

**Library callers** (`notlob.graph`): `Node.label` and `Node.body` are
gone (`bodies(graph, shown)` gives a view's bodies); `to_dict`,
`to_json`, `to_turtle`, `hidden_at_outline`, `node_summary` and
`content_tree` are gone; a view is `notlob.view.level_view` and its
writers are in `notlob.writers`. `KINDS` has a `rank` for every kind.

The whole list is under `[Unreleased]` in notlob-lab's `CHANGELOG.md`.

**Added 2026-11-06, after your `~test` finding (commit 590ef65).** The
parse tree is the whole source again, and more strictly than before:

* Every character of a `.lob` file is in exactly one token, and a
  token's value is its text, newline and all (`parse` no longer strips
  it).
* A named line is a rule of its own, three or four tokens: the marker,
  a `SPACE` where one is written, the `NAME`, and `EOL` (trailing spaces
  and the newline).

  ```
  module_head:   MOD_MARK SPACE? NAME EOL          # "#"
  sub_head:      SUB_MARK SPACE? NAME EOL          # "##" (sections, groups)
  property_head: PROPERTY_MARK SPACE NAME EOL      # "~property"
  test_head:     TEST_MARK SPACE NAME EOL          # "~test"
  appendix_head: APPENDIX_MARK (SPACE NAME)? EOL   # "#Appendix"
  ```

  `MOD_HEAD`, `SUBHEAD`, `TEST_SIGIL` and `APPENDIX_HEAD` are gone. A
  bare `~property` and the other claims are still one `SIGIL` token.
* `sub_item` and `body_line` are nodes now: an indented line in a code
  block or claim is a `body_line` holding an `INDENTED_LINE`.
* Model: `Claim.sigil` is `kind` (`example`, `run`, `property`), `mode`
  and `name`; `AppendixSection.title` is gone (`name` stays).
* `weave` writes every `~run`, a property's name as written, and a bare
  `#Appendix` as `## Appendix`.

Your highlighter's tiling check should now pass over the tree; tell us
if it does not. Its token table needs the new names.

## Report

* What broke, where, and what you changed to fix it on your side.
* What was friction: a change that was right but cost more than it
  should, or that the CHANGELOG or schema did not tell you.
* Anything that looks wrong in notlob, with the command and its output.
* Whether the renders look as they did, where they should.
