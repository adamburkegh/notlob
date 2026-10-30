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
#Pricing Discounts                          1
  cites ##Stacking Discounts                9
  apply_discount                           11
  ~example                                 14
    uses apply_discount                    15
  ##Stacking Discounts                     17
    ~example                               26
      uses apply_discount                  27
    ~property                              31
      uses apply_discount                  43
  #Tests                                   48
    ##boundary conditions                  50
      uses apply_discount                  51
    ##composition                          55
      cites ##Stacking Discounts           58
      ~test composition_is_commutative     61
        uses apply_discount                62
  #References                              69

binding.lob
#Pricing                                    1
  #Binding                                  8
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
  sigil, a name, or `uses`/`cites` and the name as written.
* References point outward, from where they are written. Who points at
  a thing is a question: `query callers`, `query cited-by`.
* Names as the source writes them, not addresses: an address is a
  program's handle.
* A module's `#References` lists what it imports
  (`70    #pricing`); retail lists none.

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
#Pricing Discounts                          1
  apply_discount                           11
  ~example                                 14
  ##Stacking Discounts                     17
    ~example                               26
    ~property                              31
  #Tests                                   48
    ##boundary conditions                  50
    ##composition                          55
      ~test composition_is_commutative     61
  #References                              69
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

## To decide

Adam's rulings, 2026-10-30, are marked **Decided**.

1. **Decided:** the rule, for 0.6.0. "It may not be a final form but I
   think I need to drive it around a bit, maybe across versions, to
   rebuild my intuition."
2. **Decided:** reader lines keep the sigils (`~example`) and drop the
   hashes on headings (`Stacking Discounts`, not `##Stacking
   Discounts`). The skeleton and outline above still show hashes; they
   lose them.
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
8. **Open, with a direction:** Adam is sceptical of `end_line`: either
   a range as a book gives one (`11-32`), or no end line and readers
   take local context from the file.
9. **Decided:** text is `graph`'s default, as everywhere. Open: whether
   the reader form for one node is `graph` at a level or
   `query outline <address>`.
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

**Decided (Adam, 2026-10-30):** one query, the flag picks the question:
"those look a lot like two different flags to pass". `query resolve X`
lists every node named X; `query resolve X --context <module>` applies
the language's rule in that module.
