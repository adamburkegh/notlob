# External outputs: one rule for what notlob prints

**Status:** design, for 0.6.0 (Adam, 2026-10-29: "I don't know that we
have really resolved the problem with 0.6 until we have resolved
this"). **Origin:** after 8e, looking at real output.

## The problem

Adam: "We have done good work to consolidate and reengineer internally,
but the externals have become a mess." The internals now have one home
per concept (the name-graph, the kinds table, loading by need). The
outputs grew a slice at a time and were never looked at together.

The case that started it, `examples/retail`, unedited:

| | bytes |
|---|---|
| `pricing/discounts.lob`, the file | 2,363 |
| `notlob graph`, level `outline` | 5,283 |

Adam on the `outline`: "This is not in any sense an outline." It is the
graph minus its paragraphs: every node with its lines, every `CONTAINS`
edge (in retail all twelve restate the target's address), the `USES`
and `CITES` edges, in JSON.

## The rule

**Text for readers; JSON for programs.** A reader is a person or an
LLM: it reads text and acts on `file:line` (kamtrinia never used
`notlob query`; it followed the `file:line` that `test` and `check`
print). A program needs a defined interface: a schema, a version,
stable names (notlob-vids is an LLM project, but its code parses the
graph). Adam: JSON is "for parsers that need a highly defined
interface, basically. An LLM is not really that."

The rule is about the reader, not the command. Adam: "An LLM reader
might want to read notlob graph. As with notlob-vids *agent*. But when
plugging it into a program, as in the notlob-vids *code*, JSON is more
useful." So every output has both forms, `graph` included: text for a
reader, and JSON (or Turtle) against a schema for a program, on
`--format json`. The MCP tools are called by an agent, so they are
readers: text by default.

Replaces "text for humans, JSON for machines" (slice 8c brief).

## What there is today

From `cli.py` and `mcp_server.py`, 2026-10-29:

| Output | Who reads it | Default | Other forms, and the flag |
|---|---|---|---|
| `test` | reader | text, `file:line` | JSON, `--json` |
| `check` | reader | text, `file:line` | JSON, `--json` |
| `query content` | reader | text, the source | JSON, `--format json` |
| `query children`, `resolve`, `search`, `imports`, `imported-by`, `callers`, `callees`, `cites`, `cited-by` | reader | **JSON** | none |
| `graph` | program | JSON, level `outline` | Turtle, `--format turtle` |
| `weave` | reader | Markdown | |
| `build` manifest | program (the hook) | JSON | |
| MCP `notlob_test`, `notlob_check` | reader | **JSON** (forced) | none |
| MCP `notlob_query_search`, `_children`, `_imports`, `_imported_by` | reader | **JSON** | none |
| MCP `notlob_query_content` | reader | text | JSON, `format` |
| MCP `notlob_graph` | reader (an agent) | **the graph JSON** | |
| MCP callers, callees, cites, cited-by, resolve | | **not offered** | |

What is wrong with it, read off the table:

1. Nine of the ten queries answer a reader in JSON.
2. Two flags for one thing: `--json` (`test`, `check`) and
   `--format json` (`graph`, `query content`).
3. The MCP tools force JSON on `test` and `check`, whose text is the
   form readers already act on, and offer half the queries.
4. The MCP server reports version `"0.3"` (`_SERVER_INFO`).
5. There is no outline anywhere, and the graph's first level is called
   one.

## Examples, `examples/retail`

Today's output is captured from runs in `examples/retail` at ff6dc6a
(2026-10-29). The text forms are proposals, written by hand from the
same graph.

### What the runs showed

```
$ notlob test
PASS   discounts.lob:15  pricing/discounts#example#1  apply_discount(Decimal('0.8'), Decimal('100')) == Decimal('80')
PASS   discounts.lob:27  pricing/discounts#Stacking Discounts#example#1  (apply_discount(Decimal('0.8'),
apply_discount(Decimal('0.9'), Decimal('100')))
== Decimal('72'))
...
8 passed

$ notlob query resolve "Stacking Discounts"
null

$ notlob query children pricing/discounts
[ prose#1, prose#2, code#1, example#1, Stacking Discounts, post-text ]
  (each a full node summary; abridged here)
```

1. `test` prints `discounts.lob:15`, without its directory, so the
   reference cannot be followed from the project root; `query content`
   prints `pricing/discounts.lob:40-60`. Two path conventions.
2. A claim written over several lines breaks `test`'s one-line format:
   its continuation lines start at column 0.
3. `resolve "Stacking Discounts"` answers `null` for a section that
   exists; without a context only a module's title resolves.
4. `children` shows the parse tree as it is (paragraphs, code blocks,
   `post-text`), where `graph`'s first level hides them: two views of
   containment, neither named.
5. The queries take their project from the current directory, with no
   way to point them at one (`git -C <dir>` is the usual form).

### `notlob query callers pricing/discounts#apply_discount`

Today, five entries like these:

```json
[
  {
    "address": "pricing/discounts#example#1",
    "label": "example#1",
    "kind": "EXAMPLE",
    "file": "pricing/discounts.lob",
    "start_line": 14,
    "end_line": 15
  },
  {
    "address": "pricing/discounts#Stacking Discounts#example#1",
    "label": "example#1",
    "kind": "EXAMPLE",
    "file": "pricing/discounts.lob",
    "start_line": 26,
    "end_line": 29
  },
  ... three more: property#1 at 31-44, test#1 at 51-53,
      composition_is_commutative at 61-67
]
```

Proposed text, one line a caller, at the line of the call (today's
answer gives where the caller starts, not where it calls; the edge's
line is dropped):

```
pricing/discounts.lob:15  pricing/discounts#example#1
pricing/discounts.lob:27  pricing/discounts#Stacking Discounts#example#1
pricing/discounts.lob:43  pricing/discounts#Stacking Discounts#property#1
pricing/discounts.lob:51  pricing/discounts#Tests#boundary conditions#test#1
pricing/discounts.lob:62  pricing/discounts#Tests#composition#composition_is_commutative
```

`file:line` first, as `grep` and compilers print it, so a terminal or
editor can follow it.

### The reader form of the graph: a skeleton of each file

Adam, 2026-10-30: "That looks way more useful to me." Retail, written by
hand from the real graph and file:

```
pricing/discounts.lob
Pricing Discounts                           1
  cites Stacking Discounts                  9
  apply_discount                           11
  ~example                                 14
    uses apply_discount                    15
  Stacking Discounts                       17
    ~example                               26
      uses apply_discount                  27
    ~property                              31
      uses apply_discount                  43
  Tests                                    48
    boundary conditions                    50
      uses apply_discount                  51
    composition                            55
      cites Stacking Discounts             58
      ~test composition_is_commutative     61
        uses apply_discount                62
  References                               69

binding.lob
Pricing                                     1
  Binding                                   8
    ~language python                        9
```

The file stands alone on its first line; every line under it is a line
of the file, the name first and its line number in a column on the
right, as a table of contents gives the page (Adam, 2026-10-30: the
module heading had no number at first; then "the name should be
primary", not the line number). The column is set per file, past its
longest entry.

About 600 bytes, against 2,363 for the file and 5,283 for today's JSON.

* Every structural line and every reference, in file order, each with
  its own line number and the file's own words after it: a heading, a
  sigil, a name, or `uses`/`cites` and the name. Headings lose their
  hashes (decision 2); sigils stay.
* References point outward, from where they are written. Who points at
  a thing is a question: `query callers`, `query cited-by`.
* Names, not addresses: an address is a handle for the next query.
* `References` lists what a module imports, as `imports Gutenberg
  Corpus` under it; retail lists none.

The levels then mean the same for a reader as for a program:

| Level | Reader (text) | Program (JSON, Turtle) |
|---|---|---|
| first | the structural lines: an outline | nodes but the leaves, and their edges |
| `index` | and the references: the skeleton above | every node, sizes, refs |
| `full` | the source: each module as `query content` prints it | and the text |

At `full` the reader form is no new output: it is `query content` on
each module in turn. Adam, 2026-10-30: "basically a graph formatted
full source listing"; kept for completeness, so every level has both
forms and no pair needs an error.

The outline is the skeleton without its `uses` and `cites` lines:

```
pricing/discounts.lob
Pricing Discounts                           1
  apply_discount                           11
  ~example                                 14
  Stacking Discounts                       17
    ~example                               26
    ~property                              31
  Tests                                    48
    boundary conditions                    50
    composition                            55
      ~test composition_is_commutative     61
  References                               69
```

### `query`, for a reader

Run in `examples/gutenberg` (2026-10-30), where `hamlet` lists and
calls `corpus`. Every answer today is a JSON list of node summaries, each
like this:

```
$ notlob query callers gutenberg/corpus#load_play
[
  {
    "address": "gutenberg/hamlet#HAMLET",
    "label": "HAMLET",
    "kind": "SYMBOL",
    "file": "gutenberg/hamlet.lob",
    "start_line": 9,
    "end_line": 9
  }
]
```

Proposed: one line a node, its address first (the name a reader passes
to the next query), then where it is, in a column on the right. For a
query that follows an edge, "where" is the line the edge is written on
(the call, the citation, the listing), which the graph holds and today's
answer drops; for the others, the line the node starts on.

```
$ notlob query imports gutenberg/hamlet
gutenberg/corpus                    gutenberg/hamlet.lob:87

$ notlob query imported-by gutenberg/corpus
gutenberg/hamlet                    gutenberg/hamlet.lob:87

$ notlob query callers gutenberg/corpus#load_play
gutenberg/hamlet#HAMLET             gutenberg/hamlet.lob:9

$ notlob query callees gutenberg/hamlet#report
gutenberg/hamlet#WORDS              gutenberg/hamlet.lob:47
gutenberg/hamlet#_TOP               gutenberg/hamlet.lob:55

$ notlob query cites gutenberg/hamlet
gutenberg/corpus                    gutenberg/hamlet.lob:5

$ notlob query cited-by gutenberg/corpus#Word Frequencies
                                    (nothing; exit 0, as today's [])

$ notlob query search discount          (in examples/retail)
pricing/discounts                       pricing/discounts.lob:1
pricing/discounts#Stacking Discounts    pricing/discounts.lob:17
pricing/discounts#apply_discount        pricing/discounts.lob:11
```

The lines are the edges' own (`graph --level index`): the listing on
87, the call on 9, the uses in `report` on 47 and 55, the citation in
the first paragraph on 5. `imports` and `imported-by` give the same line
because it is the one listing, read from either end.

Found by the runs:

* `resolve "Word Frequencies"` gives `null`, exit 1. Both modules have
  a `##Word Frequencies`; the answer is not "no such thing" but "two".
  A reader's answer would list both.
* `children gutenberg/hamlet#Speaking Parts` lists `prose#1`, `code#1`,
  `example#1`, `prose#2`, `code#2`, `run#1`: the parse tree. A reader
  wants what the outline shows under that heading (`SPEAKERS`, `_TOP`,
  `~example`, `report`, `~run`), which is `outline` on that address.
  So `children` is a program's question, and a reader's is
  `query outline <address>`, the outline or skeleton of any node.
* A named symbol and a named section look alike in an address
  (`#apply_discount`, `#Stacking Discounts`); `search` mixes them.

### `notlob graph`, for a program

Unchanged in shape (nodes and edges, D19). Its first level is not an
outline in JSON; whether the levels keep one set of names for both
forms is decision 6.

## Slices

Adam, 2026-10-30: go ahead. Each stands alone and is green at its end.

1. **`--format` and paths** (decisions 5, 10): one flag, `--json` gone;
   every `file:line` relative to the project root; a claim's line stays
   one line. Brief: `slice-1-format-and-paths-brief.md`.
2. **`query` for a reader** (decisions 2, 3, 12): text by default,
   `--format json` on every query, the edge's line, `resolve`
   deprecated.
3. **`graph` for a reader** (decisions 4, 9): text by default; outline,
   skeleton, source, for the whole project.
4. **MCP** (decision 7): a thin layer: every command, the command's
   defaults, the server's real version.
5. **notlob-vids** moves to all of it, as the first outside user.

Slice 3 also carries the cross-references' move to `index` and
`end_line` leaving the JSON (decision 8).

**Scope frozen for 0.6.0 (Adam, 2026-10-30).** These five slices, then
Adam drives it, then the release. A new finding goes on the list below
unless it would break a schema after the release.

**One addition (Adam, 2026-11-01):** no `#` in a name, D15, for 0.6.0,
by the grammar. notlob-vids found that the address rule in
`schema/name_graph.json`, and `_name` in `outline.py`, are wrong for
`##Calling C# from Python`. With it, a `.lob` file that does not parse
stops a project command, where it was skipped in silence.

After 0.6.0:

* A parse error other than `#` in a name prints the first line of Lark's
  message: `Unexpected token Token('BLANK', '\n') at line 3, column 3.`
  for a bare `##`. It says where but not what is wrong, and names a
  terminal.
* `check --format json` and `test --format json` print nothing to stdout
  when a file does not parse, while an address collision gives a
  document with a `names` finding. Kept for 0.6.0 (the graph could not be
  built, as with no project; a `parse` finding would be a new value for a
  check that never ran). Adding a document later breaks no reader.
* Part of a project, by `graph <address>` or `query outline <address>`
  (decision 9): only if driving it shows the need. Both give the same
  text but not the same JSON. notlob-vids, as an agent (2026-11-01),
  named this first: it grepped 60 lines from 916 of `--level index`.
* `notlob graph <file>` in a project, which only finds the project.
* The reader form of `graph` gives no addresses, and an agent cannot
  always derive one, so it cannot go from a line to a `query`. A `uses`
  gives a bare name, with no module.
* In that form a one-word heading and a one-word symbol look alike at
  the same indent (`References`, `Phase`).
* Names with their cross-references are no longer a level: `index`
  brings the anonymous nodes with the edges. On pn-chomper, 672 nodes
  and 1,206 edges, where the old `outline` had 408 and 941.
* A node's parent changes with the level: a symbol is under its section
  at `outline` and under its code block at `index`. Documented, but it
  failed silently in notlob-vids.
* The quantifier check reads a plural noun as a verb: "code blocks"
  beside "each" or "only" is flagged.
* `notlob_version` on every document: the version of notlob that made
  it, for people tracing a bug, beside `version`, the document's format,
  for programs (Adam, 2026-11-02: "a good idea, it will just be an extra
  field later, not particularly breaking").
* `project_version`: a program written in notlob stamps its own version
  on what notlob makes for it, from a new `~version` in `#Binding` (a
  grammar change). Multi-binding is what makes it compelling. Tying it
  to `pyproject.toml` and the like can wait: `~external` can simulate it.
* `~example <name>` (Adam, 2026-11-02: good to add, safely after
  0.6.0; it only adds). Today only `~property` and `~test` take a name.
  `~run` not considered.
* `named` on symbols.
* LF line endings on every platform.
* The size bound on `query content --format json`.
* Whether `query resolve` goes, or becomes what use shows it should be.
* `NameGraph.search` uses `fnmatch.fnmatch`, which folds case on
  Windows, where its docstring says case-sensitive: `search discount`
  differs between platforms.
* `query cites` on a section answers for its paragraphs; `query callees`
  on a section answers nothing, as it has no `USES` edges of its own.

## A level is the same content in either form

Adam, 2026-10-30: "same content, different format ... better to have
same content". **Decided:** the cross-references (`USES`, `CITES`,
`IMPORTS`, `USES_EXTERNAL`) leave the JSON `outline` and arrive at
`index`, as they do in the reader form. The JSON `outline` is nodes and
`CONTAINS` edges: 547 of pn-chomper's 941 edges go. Cost: the lifted,
section-level view of the edges is no longer in the document; a program
that wants it walks `CONTAINS` itself, and anything reading edges at the
default level asks for `--level index`.

## What a level is (Adam, 2026-11-01, in progress)

A rethink, not yet a plan. The levels' content had two homes:
`outline.py:42` leaves `hidden_at_outline` kinds out at every level,
and `graph.py:1680` at `outline` only, so text and JSON disagree at
`index`. The flag stood in for a question nobody had answered.

**Ruled:**

* A level is content and a format is how it is written: they are
  independent. A level has one definition, which the formats write out.
* Rank is an explicit element, and it replaces `hidden_at_outline`.
  Hiding low ranks at `outline` and `index` is fine once it is explicit:
  "It was without those explicit elements that it became confusing".
* Claims are structure, whatever their address: `~example` and
  `~property` behave like numbered theorems and examples in a paper,
  and `Decoding#example#1` is "Example 2.1".
* A paragraph may have an address, and is not "anonymous": it is under a
  name. It does not appear at `index`: "No book index or contents page
  does that."
* An address is named or positional. "Positional" is the word for what
  can never have a name, as a paragraph. "Anonymous" is kept for a claim
  or test that could have a name and has none, as in "anonymous lemma"
  in `DESIGN.md`; its address is positional too.
* Every named node carries `name`, as the author wrote it, in place of
  `label` and `named` (Adam, 2026-11-02: "It is hard to rectify names
  when they can't be found"). A name is what the author writes to name
  something; an address is built from names, never the reverse. 8e took
  `label` off all but modules under the pressure of size, when JSON was
  also the reader's form; that part is reversed, and the rest of 8e
  stands. `#Binding`, `#Tests` and `#References` are keywords, not
  names, and have none.
* The reader's `full` is the document, once, in order. A reference is
  there as written: `to_roman(1)` is the use.
* An element's parent is its nearest visible holder. A symbol is
  structure inside a block, which is a lower rank, so the parent shown
  depends on the level. The address does not. References move to the
  holder by the same rule.
* Direct and indirect containment are two edge kinds (Adam,
  2026-11-03: "direct contains should be distinguished from indirect
  contains"). A `CONTAINS` edge is always the tree's. Where a view hides
  what holds a node, it writes `CONTAINS_INDIRECTLY` from the nearest
  node above that it shows ("a feature that it explains itself"). So a
  level holds the `CONTAINS` edges of the one before, literally. Rank
  does not follow the tree: blocks are low because they are boring, and
  may hold a symbol of high rank (Adam: a rule that a node's rank is
  never below its container's is "the wrong rule"). Only `CODE` over
  `SYMBOL` and `POST_TEXT` over its sections do this in the examples
  (`var/monotone_probe.py`).

**Leaning, not ruled:**

* Depth counts the steps a view shows, so `query content --depth`, which
  shows everything, is the same rule.
* An unnamed test is the body of its group; a `~test` is an element.
  So they are two kinds (Adam, 2026-11-02: "now we have a clearer
  reason to"): one `TEST` held both, at rank 3 without a name and 1
  with one, and a rank that turns on a flag is a missing kind. `~test`
  must have a name and a run of test lines can never have one, so
  nothing is both. `TEST` stays for `~test <name>`, and a run of test
  lines is `TEST_LINES` (Adam, 2026-11-03).
* The target stays `version` 2: that version is not yet released
  (Adam, 2026-11-02).

**A fourth level, `block`** (Adam: "fairly convinced" the distinction is
useful, though how often it is called is unknown), between `index` and
`full`: the low-rank nodes with their address, and no words. `size` is
not there: it is a measure of the document, not a fact of it, so it
probably has no place on the name graph (Adam, 2026-11-02), and anyone
can sum it from `text` at `full`. Nothing in notlob reads it, and
notlob-vids does not either: its token-cost visual measures the length
of each command's actual output, which is what an agent reads.
The jump from `index` to `full` is too big, and we drew this level by
accident while confusing the two. It shows the nodes as they are: a code
block is listed, `code#1` holding `from_roman`, and does not dissolve
into what it defines. You call it because you want to see the blocks.

JSON at `full` stays as it is: `block` plus the words, with `text` on
each block, once. No rule collapses a block with one symbol into its
parent. Adam: "the special case isn't worth it. If you want to see
#.....#para3 then you will be fine with a usually hidden code parent to
a code function". What was dumb was paragraphs at a level named `index`.

**How it gets built (Adam, 2026-11-02):** the schema first, then the
repair, with two literal files on disk for the duration:
`name_graph.json` (what is true now) and `name_graph_next.json` (the
target). The old path runs until the swap. In order: rule on the shape;
write the target, with `roman` validated against it; a short file of
property tests for the five lines; stages towards the target, each
leaving everything working; the swap, one commit before release that
deletes the old walks, `hidden_at_outline` and the old file; then
notlob-vids moves.

**Rulings for the swap (Adam, 2026-11-03):** it lands in 0.6.0
("needed"). `query`'s JSON loses `label` too: nothing needs it. A named
level shows the whole tree by default, for now ("I'm not sure if that
will be the final form"). The text form at `full` is probably the
bodies in order; how it frames several files is open.

**More for the swap (Adam, 2026-11-04).** `query content` is the view
from a start, in 0.6.0, not a walk of its own: "looks like excuses".
A started view needed one rule, now in `DESIGN.md`: where a view does
not show the written node that holds a line, the line is in the body of
the deepest node it shows that covers it. A one-file project has a
file, the path passed; building it without one was a confusion in the
implementation. `--level` takes `1` to `4`, the ranks: "four levels
needs four numbers". `query search --kind` offers every kind. The brief
is `slice-9-the-swap-brief.md`.

**The text form at `block` (Adam, 2026-11-03: "the output looks
ok").** As `index`, with a line for each positional node saying the end
of its address (`prose#1`, `code#1`, `test#1`), and `post-text` a line
as its rank gives it. A reference stays with its source, the nearest
node an outline shows, so it sits beside the blocks, not under them.
The line numbers are right aligned, as at every level.
`var/block_text_sketch.py` drew it from the scratch target.

**Ranges in text (Adam, 2026-11-04).** A reference on every line of a
run printed each, and one widened the number column of its whole file
(roman's `uses to_roman` at 78 to 86). In text, a run of two or more
consecutive lines is a range, `78-86`, and runs are joined with `, `
(`28-30`, `59-60`, `12, 15-17`). JSON and Turtle keep every line: a
range is the reader's, not the document's.

**The text form at `full` (Adam, 2026-11-03: "yes, just that").** Each
file's path on a line of its own, then its bodies in order, a blank line
between files: the project's files, each under its path. A symbol or a
reference has no line of its own: it is inferred from a body, and is
written there.

**Turtle and an edge's `lines` (Adam, 2026-11-03: reification).** A
triple has no place for them,
and dropping them is the formatter deciding. Adam would take RDF 1.2's
annotation (`s notlob:uses t {| notlob:line 28, 29 |}`) if our tool
reads it: "the ontology stuff is a statement of intent". rdflib 7.6 does
not (`var/rdf_star_probe.py`: refused as `turtle`, and no star parser is
registered). So every edge is a triple, its kind the predicate in
camelCase, and an edge with lines also has an `rdf:Statement` about that
triple carrying them as `notlob:lines`, one value a line. Each relation
stays a property the ontology can describe. Should rdflib come to read
the annotation, moving to it is a change of spelling.

**Names (Adam, 2026-11-02):** a field is named once, in snake_case, in
the view; a formatter whose format has its own convention converts the
name mechanically, as Turtle's camelCase. No table of names per field:
the one at `graph.py:419` goes. A value is notlob's own word, spelled as
the language spells it (`on-load`, `post-text`).

**A named level is a preset (Adam, 2026-11-02):** a tuple of depth and
rank. The selection takes those, and a start, and never sees a level's
name. `--level` looks the tuple up and `--depth` replaces its depth.
There is no `--rank` yet, but there is room for one: it would replace the
rank, and the selection would not change.

**Rank is one scale of natural numbers** (Adam, 2026-11-02), with enum
labels for the common ranks. A node has a name and may have a body: its
own written lines, not what is under it, and an attribute, not a child
(Adam, 2026-11-02). Bodies are the last step of the same scale, so there
is no dimension for them: a view shows every node at or below its rank,
and from `BODY` on their bodies too. Scale, values open: `STRUCTURE` 1,
`REFERENCES` 2 (with declarations), `BLOCK` 3, `BODY` 4. A named level
is exactly a depth and a rank. `block` is the full node structure and
`full` is that with its bodies. Symbols and references have no body:
they are derived, inferred from a body, by the grammar for a citation
and by a binding for a symbol or a `uses`. Origin is not rank:
`from_roman` is derived and rank 1. References are edges, not nodes:
"edges are mostly verbs" (Adam, 2026-11-02), and `rank` takes `Node ∪
Edge ∪ Body`. The edge kinds stay. An edge needs both its ends in the
view. A reference is one edge per holder and target,
with its lines as a list, as a book index has one entry and its pages
(Adam, 2026-11-02): it is a fact about what holds it, and what is written
is the call, in the words. An edge's source is the nearest structural
node (Adam, 2026-11-02): `index` then reads its edges, with no search and
no merge, and a reference's source is the same at every level. It is
"the nearest node an `outline` shows", so it holds for `IMPORTS` and
`USES_EXTERNAL` too: their sources are `mod#References` and
`mod#Binding`, not the module (Adam, 2026-11-02). `refs`
goes, and an edge's `start_line` becomes `lines`. It is not sized.

**A formatter only writes (Adam, 2026-11-02):** the test is what adding
XML and YAML would take. One selection gives nodes and edges; no
formatter knows what a level is. `var/view_sketch.py` ran this on `roman`'s `Decoding`: text, JSON,
YAML and XML from one selection, and `full` written back identical to the
file for that section. A sketch, over one Python section. Today
`outline.py` and `graph.py` each have the walk, the move to the holder
and the merge of references; only `_turtle_node` is a formatter already.

**Every node carries its own written lines at `full`** (Adam, 2026-11-02),
so no formatter needs notlob's syntax and `full` is each node's lines in
order: `#Tests`, `---`, a heading and a sigil line included, each once.
Adam: "Full means full". So `text` is verbatim, indent included: today a
test's keeps its indent and a code block's or claim's is dedented. Blank
lines are in no node, and `start_line` places each node, so a writer can
restore them.

**Open:**

* An Appendix's address. A file may have several appendices, but a
  second bare `#Appendix` breaks naming uniqueness (Adam, 2026-11-02),
  so an appendix is named, not numbered, and a repeat is a collision.
  That also ends `appendix#1`, which loses the title below `full`
  against `name_graph.json:89`. The name is the title:
  `#Appendix Glossary` is `mod#Glossary`, of kind `APPENDIX`, and a bare
  `#Appendix` is `mod#Appendix`. It collides with a `##Glossary` in the
  body, rightly. Text says `Appendix Glossary`, from the kind (Adam,
  2026-11-04), and a bare one `Appendix`: a word for `APPENDIX` in
  `KINDS` is the accepted cost, and a kind showing that was hidden is
  the name graph doing its job. One appendix a module was weighed
  against agents' habit of pushing work there, and not taken: no rule
  in the grammar or `check` (Adam, 2026-11-04). The word is a field of
  its own in `KINDS` (`heading="Appendix"`), not the sigil, so no `#`
  shows; the writer puts it before the name, and once where the name
  is the word (a bare `#Appendix`). Wrinkly, and may not endure, but
  the right trade for now (Adam, 2026-11-04). No example
  has an appendix, so this needs tests of its own.
* `outline`'s default depth, and whether rank has a flag of its own (the
  ladder said no switch for named versus all).
* Whether this is 0.6.0 or the first work after it. Several items in
  "After 0.6.0" above belong here, and went on that list when they
  should have stopped the work.

## To decide

Adam's rulings, 2026-10-30, are marked **Decided**.

1. **Decided:** the rule, for 0.6.0. "It may not be a final form but I
   think I need to drive it around a bit, maybe across versions, to
   rebuild my intuition."
2. **Decided:** reader lines keep the sigils (`~example`) and drop the
   hashes on headings (`Stacking Discounts`, not `##Stacking
   Discounts`). The skeleton and outline above still show hashes; they
   lose them. A query line is three columns (Adam, 2026-10-30): the
   sigil, blank for what has none; the address; `file:line`.
3. **Decided:** a query that follows an edge (`callers`, `callees`,
   `cites`, `cited-by`, `imports`, `imported-by`) gives the line the
   edge is written on: the call, not the start of its caller. Adam:
   "surely the actual line of code is right"; the start of the block
   was a limit of earlier implementations, before the graph held the
   whole parse tree. Other queries give the line a node starts on.
4. **Decided:** a reader's default level is the outline. Risk, noted:
   readers may not find that `uses` and `cites` are at `index`; the
   outline's help and `USER-AGENTS.md` should say so.
5. **Decided (Adam, 2026-10-30):** one flag, `--format`, everywhere
   (`text|json`, and `turtle` for `graph`). `--json` is removed from
   `test` and `check` in 0.6.0, with no alias: "I don't like the
   inconsistency".
6. **Decided:** the levels stay `outline`, `index`, `full`. "outline is
   good. index is ok but I can't think of better."
7. **Decided:** the MCP server is a thin layer over the command line:
   every command and query is offered, `notlob_graph` included, with the
   command's defaults (so text). "It would seem strange not to offer
   notlob graph through MCP."
8. **Decided (Adam, 2026-10-30):** no end line in what notlob prints:
   readers take local context from the file. Reader forms carry one
   line. `end_line` leaves the graph document and the query JSON too,
   on the principle that a level is the same content in either format
   (Adam: "same content, different format ... better to have same
   content"). The model keeps it:
   `query content` needs the span, and its header's `file:40-60` says
   what it printed.
9. **Decided in part:** text is `graph`'s default, as everywhere, and
   `graph` with no argument is the whole project, wherever it is run
   from. Open: the reader form for part of a project, by `graph
   <address>` or `query outline <address>`; a file argument to `graph`
   inside a project is ignored today.
10. One path convention, relative to the project root, for every
    `file:line` notlob prints. Taken as agreed with 11; not ruled
    separately.
11. **Decided:** `notlob -C <dir>`, done first, "as it is slowing down
    our own work". Brief: `slice-c-option-brief.md`.
12. `resolve` on a name with no context. Example asked for; see below.

### `resolve`, run in `examples/retail`, 2026-10-30

```
$ notlob query resolve "Stacking Discounts"
null                                                    [exit 1]
$ notlob query resolve "Stacking Discounts" --context pricing/discounts
{ "address": "pricing/discounts#Stacking Discounts", ... }   [exit 0]
$ notlob query resolve "Pricing Discounts"
{ "address": "pricing/discounts", ... }                 [exit 0]
$ notlob query resolve apply_discount
null                                                    [exit 1]
```

There is one `Stacking Discounts` in the project and one
`apply_discount`; neither resolves without `--context`. Only a module's
title does. `resolve` answers "what would `#Label` mean if written in
this module", the language's reference rule, so without a module it
can only find modules. A reader asking "where is `Stacking Discounts`"
gets `null`, exit 1, which reads as "no such thing". In gutenberg,
`##Word Frequencies` is in two modules, and gets the same `null`.

Adam: "That query resolve behaviour seems nuts to me, I certainly don't
remember designing it like that." Its origin: `NameGraph.resolve`, in
f04b40c (2026-05-20), "Implements the three-step resolution order from
DESIGN.md ... Without context only step 3 is attempted": the language's
rule for what `#Label` means written in a module, which builds `CITES`.
`query resolve` exposes that rule as it is. Proposed: two questions,
apart. A reader's "where is X": every node of that exact name, one line
each, nothing if none. A program's "what would `#X` mean here": the
rule, with the module required.

Adam first said the two questions "look a lot like two different flags
to pass". **Decided, in the end (Adam, 2026-10-30):** deprecate `query
resolve` "and see how use evolves from here". It is undocumented and
unoffered over MCP; it stays as it is, with a line on stderr, and
`query search` is the answer for now.
