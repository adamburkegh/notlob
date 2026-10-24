# Design note: the name-graph as the parse tree with cross-references

**Status:** design agreed in discussion, 2026-10-23/24; for a final read
before slicing. Decisions and their reasons are in section 8.
**Origin:** the review of the backed-out 0.6.0 name-graph work
(`meta/retrospectives/2026-10-23-name-graph-redundancy/`), 2026-10-23.
**Supersedes:** the representation in `f4b9eb9` (backed out in `4230b04`).
**Decisions already taken (Adam):**

* The completeness contract stands: every element of the document is in
  the graph, with its kind, text, position and order.
* The name-graph is "literally just a parse tree with cross refs". It is
  the fundamental data structure; consumers read it.
* Not all of it need be exposed at once: a hierarchy of detail, enough for
  tools and agents to answer questions of the code.
* `query content` reads the name-graph, and may be reworked heavily.
* Export levels are one ladder, `outline` / `index` / `full`, also
  selectable as `--level 1|2|3`; `outline` is the default. No separate
  text or named-versus-all switch (section 5).
* The output format can change in this version (the schemas are new in
  it).
* The work is redone from `d7bbca9`, not repaired in place.

## 1. The model in one picture

`examples/roman/roman/numerals.lob`, lines 40 to 60:

```
40  ##Decoding
41
42  Decoding is the inverse of encoding. The subtractive pairs are handled
..
46      def from_roman(s: str) -> int:
..
56          return result
57
58  ~example
59      from_roman('IV')     == 4
60      from_roman('MMXXIV') == 2024
```

as a graph:

```
# the tree: position
roman/numerals#Decoding                SUBHEADING   40-60
 ├─CONTAINS→ roman/numerals#Decoding#prose#1    PROSE     42-44
 ├─CONTAINS→ roman/numerals#Decoding#code#1     CODE      46-56
 │            └─CONTAINS→ roman/numerals#from_roman  SYMBOL  46-56
 └─CONTAINS→ roman/numerals#Decoding#example#1  EXAMPLE   58-60

# the graph: meaning
roman/numerals#from_roman  ─USES→ roman/numerals#NUMERALS      (line 47)
roman/numerals#Decoding#example#1 ─USES→ roman/numerals#from_roman (59)
```

**Nodes and `CONTAINS` edges are a forest:** one tree per `.lob` file,
rooted at its `MODULE`. Every other node from a file has exactly one
`CONTAINS` parent, and there are no cycles. `CONTAINS` is position, for
every node, so a walk of the tree reaches everything.

**Every other edge is a directed graph across the forest:** `USES`,
`REFERENCES`, `IMPORTS`, `USES_EXTERNAL`. Each is the result of resolving
something (a call, a `#Label`, a `#References` line, a `~external`
declaration) to a node, and cycles are allowed (recursion, two sections
that reference each other, modules that cite each other).

What a node is (a claim, a paragraph, a symbol) is its kind: an
adjective, not an edge. Which scope a name belongs to is derived from the
tree and the kinds (section 2). Nothing else is stored: no list of a
section's items beside its `CONTAINS` edges, no copy of a symbol's text
beside its code block, no edge for a scope.

`EXTERNAL` nodes stand outside the trees: they are things outside the
`.lob` world, not elements of a `.lob` file. The `~external` (or
`~on-build`) declaration is a leaf of `binding.lob`'s tree (D6), and its
`USES_EXTERNAL` edge points out of the forest to the external node (D9):

```
binding.lob tree                          outside the forest
roman                       MODULE
 ├─ roman#external#1        (declaration leaf)
 │      ──USES_EXTERNAL──→  src/inject-bundle.ts   EXTERNAL
 └─ roman#on-build#1        (declaration leaf)
        ──USES_EXTERNAL──→  src/inject-bundle.ts   (the same node)
```

An `EXTERNAL` node's address is the declared string, verbatim, as today:
one node per distinct string, and a string declared twice is one node with
two incoming edges. That is why `USES_EXTERNAL` is in the graph layer, not
the tree: the tree is what is written, the graph is what it resolves to.
notlob does not normalise or resolve the string (`./src/x.ts` and
`src/x.ts` are two nodes), in keeping with `DESIGN.md`'s "not assembled,
tested, or owned by notlob".

## 2. Nodes

Every node has `address`, `label`, `kind`, `file` (relative to the project
root), `start_line` and `end_line`. Leaves also have their `text`.

| Kind | Is | Text held | Children (`CONTAINS`) |
|---|---|---|---|
| `MODULE` | a `.lob` file | none | its sections, items and claims |
| `SUBHEADING` | `##Heading` | none | its items and claims |
| `APPENDIX` | `#Appendix` | none | its items, claims and subheadings |
| `PROSE` | a paragraph | the paragraph, `#Label` sigils as written | none |
| `CODE` | an indented code block | the dedented block | the symbols written in it |
| `BULLETS` | a bullet list | the items | none |
| `EXAMPLE`, `PROPERTY`, `RUN` | a claim | its lines | (a `PROPERTY`) the functions written in it |
| `TESTS` | the `#Tests` section | none | groups, assertion blocks, named tests, prose |
| `TEST` | a group, an assertion block or a `~test` | an assertion block's or `~test`'s lines | (a group) its items |
| `SYMBOL` | a name defined in code | **none**: its lines lie inside its parent | none |
| `EXTERNAL` | a `~external` file | none | none (outside the trees) |

New: `PROSE`, `CODE`, `BULLETS`, `TESTS`, and `APPENDIX` again (it was in
the backed-out work). `end_line` and `file` are new on every node. Binding
declarations (`~language`, `~on-build`, ...) are leaves of `binding.lob`'s
tree (D6).

Leaf addresses are ordinal, as claim addresses already are:
`holder#prose#1`, `holder#code#2`, `holder#bullets#1` (D1). A named thing
keeps its name-based address.

### Scope

A name belongs to the nearest enclosing node, along `CONTAINS`, whose kind
opens a scope. The kinds that open one are `MODULE`, `PROPERTY`, `TESTS`
and a `#Tests` group (D8). Sections do not. The Roman example, with a
named property and an Appendix added for illustration:

```
roman/numerals                        MODULE      scope
 ├─ #Decoding                         SUBHEADING
 │   └─ #Decoding#code#1              CODE
 │       └─ #from_roman               SYMBOL      → roman/numerals
 ├─ #Round-Trip                       SUBHEADING
 │   └─ #commutativity                PROPERTY    → roman/numerals
 │       └─ #commutativity#gen        SYMBOL      → ...#commutativity
 └─ #appendix#1                       APPENDIX
     └─ #Notes                        SUBHEADING  → roman/numerals
```

A named node's address is its scope's address, `#`, and its name:
`roman/numerals#from_roman`, `roman/numerals#commutativity`. A named
property's address changes from today's
`roman/numerals#Round-Trip#commutativity`. An anonymous node (a leaf, an
unnamed claim, an Appendix) is addressed by position instead: its
parent's address, its kind and its ordinal, as today:
`roman/numerals#Decoding#example#1`, `roman/numerals#appendix#1`.

What a scope defines is a derived query (`graph.names(scope)`), and name
resolution reads an index built from the tree: nothing reads a scope out
of an address string.

### References in prose

A `PROSE` leaf also holds the references written in it, as parsed:

```json
{"address": "pricing/discounts#Stacking#prose#2", "kind": "PROSE",
 "start_line": 31, "end_line": 33,
 "text": "Stacking follows #apply_discount, then ##Rounding.",
 "refs": [{"label": "apply_discount", "sub": false, "line": 31},
          {"label": "Rounding", "sub": true, "line": 31}]}
```

The `refs` are the parse tree (what was written); a `REFERENCES` edge is
the cross-reference (what it resolved to). An unresolved reference has a
`refs` entry and no edge, which is what `validate_refs` reports. These are
two different facts, not one fact twice.

## 3. Text is held once

A symbol's text is read from the leaf it lies in, by its lines:

```python
graph.text("roman/numerals#from_roman")
# -> the lines 46-56 of roman/numerals#Decoding#code#1
```

So the binding's `SymbolInfo` gains the symbol's lines within its block:

```python
@dataclass
class SymbolInfo:
    name:       str
    source:     str | None = None
    first_line: int | None = None    # 1-based, within the block
    last_line:  int | None = None
```

All three built-in extractors already know these (Python:
`node.lineno`/`node.end_lineno`; TypeScript and Haskell: their line
loops). A binding that does not supply them keeps `source` on the node, as
now; a test checks that the built-in bindings never fall back.

Derived, not stored: a section's prose or code as one string
(`graph.prose(addr)`, `graph.code(addr)`), a node's size, its order among
its siblings (`start_line`), its scope.

### `USES`

The algorithm does not change: it has never read `DEFINES`. Today
(`add_uses_edges`, `graph.py`) it indexes every `SYMBOL` by label, runs
the binding's call extractor over the code of each symbol, claim and test
node, and adds an edge for each name found in the index:

```python
name_index: dict[str, list[str]] = {}
for node in graph.nodes(kind=NodeKind.SYMBOL):
    name_index.setdefault(node.label, []).append(node.address)
...
for ref_name, src_line in call_extractor(source):
    for target_addr in name_index.get(ref_name, []):
        ...  # USES edge
```

In the new graph the code is read from the leaves (a symbol's text by its
lines; claims and tests by their own text). Optionally `CODE` leaves too,
for top-level statements outside any symbol (a module-level call), which
today produce no `USES` edge at all.

**Later, not in this redesign:** the label index is global, so if two
modules define `helper`, every call to `helper` gets an edge to both.
With scope derivable, lookup could follow the language: the caller's own
scope, then modules reached by `IMPORTS`. Bindings differ here
(`DESIGN.md`: Python names travel transitively across lob imports), so it
is an improvement of its own.

## 4. Positions

Every node's `start_line` and `end_line` are its own. Two defects in the
current code go with this (both predate the backed-out work):

```
roman/numerals#to_roman     start_line 12   (def is at 19)
example#1 USES to_roman     start_line 27   (line is 28)
```

A symbol takes its block's first line, and a `USES` edge from a claim or
test node is one line short (the claim's text starts on the line after its
sigil).

## 5. Levels of detail

One axis, three points on it, each named for the question it answers.
Each level contains the one before.

| Level | Answers | Adds | Today |
|---|---|---|---|
| 1 `outline` | what is here, and how is it connected? | modules, sections, claims, tests, symbols; positions; edges | lean `notlob graph`, plus `file` and `end_line` |
| 2 `index` | where is everything, and how big? | the anonymous leaves (`PROSE`, `CODE`, `BULLETS`), `refs`, a `size` per node | new |
| 3 `full` | what does it say? | `text` on leaves, each once | `--content` |

```
notlob graph                       # outline
notlob graph --level index         # or --level 2
notlob graph --level full          # or --level 3
notlob query content <address>     # the subtree at <address>, full
```

The names are canonical (in the output and the docs); the numbers are a
shorthand, ordered by how much is shown. There is no separate switch for
text or for named-versus-all nodes: each would only pick a point the
ladder already names.

**Hiding a leaf lifts its edges.** At `outline` the anonymous leaves are
not shown, so an edge to or from one is attached to its nearest shown
ancestor along `CONTAINS`, and duplicates that result are merged (keeping
the earliest `start_line`). `CONTAINS` edges to hidden leaves are dropped.
At `index`, from roman/numerals:

```json
{"source": "roman/numerals#Decoding#code#1",
 "target": "roman/numerals#from_roman", "kind": "CONTAINS"}
```

and at `outline` the same edge, lifted:

```json
{"version": 2, "level": "outline",
 "nodes": [{"address": "roman/numerals#from_roman", "label": "from_roman",
            "kind": "SYMBOL", "file": "roman/numerals.lob",
            "start_line": 46, "end_line": 56}, ...],
 "edges": [{"source": "roman/numerals#Decoding",
            "target": "roman/numerals#from_roman", "kind": "CONTAINS"},
           ...]}
```

The `outline` tree is still a forest: lifting a `CONTAINS` edge only
skips a hidden node.

The document carries a `version` (the schema rule in `DESIGN.md`) and its
`level`. Each level is written by its own serialiser from the nodes'
fields: the in-memory layout is not dumped. One schema
(`schema/name_graph.json`) covers all three, with `level` saying which
fields are present.

## 6. `query content`

A walk of the tree, meant to replace `find` and `grep` over the files for
an agent reading a project. By default it returns the whole subtree at the
address, at `full` level, in document order; `--depth N` limits it, with
`find -maxdepth` meaning:

```
notlob query content roman/numerals               # the whole module
notlob query content roman/numerals --depth 0     # the module node only
notlob query content roman/numerals --depth 1     # and its direct children
```

For `roman/numerals#Decoding` the subtree is the subheading, its prose,
its code, its claim with the claim's lines (not just its address), and the
symbol `from_roman` with its lines but no text of its own: each line of
source appears once in the answer.

The content search proposal (`2026-10-21-content-search`) is the matching
half: find a pattern, then return the leaves around it. It was written
against the backed-out `body` lists; with leaves as nodes, its "body
items" are a section's leaf children, and its context is their siblings.
It needs revising to say so, and the two commands should share their walk
options (`--depth`, and any kind filter).

## 7. Tests that hold it

1. **Oracle.** An independent walk of the parse tree finds the same
   elements as the graph's nodes, with the same kinds, positions and
   order, for every place an element can be written (body, subheading,
   Appendix, Appendix subheading, `#Tests`). The grammar decides which
   rules hold a body, as in the backed-out guard test.
2. **Forest.** Each node from a `.lob` file other than its `MODULE` has
   exactly one `CONTAINS` parent; following `CONTAINS` from any node
   reaches its `MODULE` with no cycle; `EXTERNAL` nodes have no `CONTAINS`
   edge.
3. **Scope.** Each named node's address is its scope's address, `#`, and
   its name, with the scope found by the rule in section 2.
4. **Once.** In the whole graph (built and enriched, all passes) at
   `full`, and in `query content`, each leaf's text occurs once.
5. **Nesting.** `index` is `full` without `text`, node for node and edge
   for edge. `outline` is `index` with the anonymous leaves hidden and
   their edges lifted by the rule above.
6. **Schemas.** Each level validates against `name_graph.json`; Turtle at
   each level parses and matches `notlob.ttl`.
7. **Positions.** For each symbol and claim in the example projects,
   `start_line` is the line its definition or first claim line is on.

## 8. Decisions

| # | Question | Decision |
|---|---|---|
| D1 | Leaf addresses: ordinal (`#prose#2`), line-based or content hash | Ordinal. They shift when a sibling of the same kind is added above, as claim addresses already do; line-based ones shift on any edit above, and hashes are unreadable. Line numbers are always the real ones |
| D2 | The tree and naming edges (below) | `CONTAINS` is the only tree edge, claims included; `DEFINES` is removed |
| D3 | Source of a `REFERENCES` edge: the `PROSE` leaf, or its section | The `PROSE` leaf |
| D4 | `#Tests` always a `TESTS` node, its commentary prose as `PROSE` leaves | Yes |
| D5 | `query content` on a module: its own items, or its whole subtree | The whole subtree, with `--depth` (section 6) |
| D6 | Binding declarations (`~language`, `~on-build`, `~keep-generated-src`) as nodes | Yes, as leaves of the binding module |
| D7 | Build the graph once per command and pass it on, rather than each consumer calling `build(module)` | Yes |
| D8 | Which kinds open a scope | `MODULE`, `PROPERTY`, `TESTS` and `#Tests` groups. Sections do not, so a named property's address becomes `module#name` (section 2) |
| D9 | `EXTERNAL` identity, and how much of external resolution notlob owns | The declared string, verbatim; no normalisation, no ban on URLs. The build manifest keeps joining the string to the project root, as now; a non-file declaration is the hook script's to handle (section 1) |

**D2, and how it was reached** (2026-10-23/24; the reasons matter more
than the outcome).

A claim belongs to its section as a theorem belongs to a chapter. The
options for the edge that says so were `CONTAINS`, as for every other
child; `DEFINES`, as today; or a new verb such as `ASSERTS`.

* `ASSERTS` was chosen first: claims are growing in importance, and a
  claim reached through a generic edge plus a kind filter looked like a
  claim downgraded.
* Worked examples (walking a section, finding its claims, a named
  property, the `outline` view) moved Adam back to `CONTAINS`. The
  distinction is verb against adjective: a node's kind is an adjective,
  and finding a section's claims is a simple kind test. Asserting is not
  different enough from containing to need its own verb. A claim keeps
  its importance through its kind and its `USES` edges.
* That raised what `DEFINES` is for. "Only for names found inside code"
  was rejected: a subheading defines a symbol too (`##Decoding` puts
  `Decoding` into the module's namespace exactly as `def from_roman`
  does). "`CONTAINS` for position and `DEFINES` for namespace, on every
  named node" was tried next, and rejected as redundant: for a top-level
  subheading or a symbol in the module body it is two edges between the
  same pair of nodes.
* The namespace is derived instead, from the tree and the kinds that
  open a scope (section 2), so it needs no edge. With code blocks in the
  graph as nodes, "this code introduces this name" is `code CONTAINS
  symbol` plus the symbol's kind. `DEFINES` was a bridge from when the
  graph held no code: the only way to say where a symbol came from.

What reads `DEFINES` today, to move in slices 4 and 5:

```
notlob/check.py:493     the quantifier check: "does this section have a
                        claim?" -- a kind filter over CONTAINS children
notlob/cli.py:249       query children --edge choices
notlob/mcp_server.py:150  the MCP edge-kind list
notlob/schema/name_graph.json, notlob/schema/notlob.ttl
```

notlob-vids draws `DEFINES` edges today, from a section to its claims and
symbols, and will draw `CONTAINS` instead.

**Also noted.** `LANGUAGE.md` lists `~run` among the claims ("verifiable
statements"), but a `~run` is an entry point and is never verified. Worth
fixing in the language reference.

## 9. Slices

Each slice is a brief for one implementing session, with its failing test
first, a list of files it may touch, and a stop point. Order:

1. **`DESIGN.md`:** the contract and this model (section 10). Docs only.
2. **Nodes and tree:** the leaf kinds, `APPENDIX`, `TESTS`, binding
   declarations, `file`, `end_line`, `CONTAINS` as the only tree edge,
   scopes and the named-property address (D8); the oracle, forest and
   scope tests. No consumer changes beyond what `build` itself needs.
3. **Symbol lines:** `SymbolInfo` lines in all three bindings, symbols
   without text, `graph.text()`, the `USES` line fixes.
4. **Consumers onto the graph:** `enrich`, the reference edges,
   `validate_refs`, the claim collectors, `collect_run_bodies`, `notlob
   run`, the checks (the quantifier check off `DEFINES`); one graph per
   command (D7). This brings back the Appendix fix.
5. **Export:** the three levels, `query content`, schemas, Turtle, the
   CLI and MCP edge filters without `DEFINES`; the "once" and "nesting"
   tests.
6. **Module listing** (`1468f0f`) and the `#Tests` `USES` fix, redone on
   the new graph, with the old commit as reference.

Then a CHANGELOG pass and the release. notlob-vids is updated after the
format settles, at slice 5.

Not in this note: moving the assemblers and the weaver onto the graph
(they read the parse tree correctly today; the oracle and consistency tests
tie them to it), scoped `USES` lookup (section 3), content search
(`2026-10-21-content-search`), and the queries of
`2026-10-03-graph-data-and-queries` Part B.

## 10. Proposed `DESIGN.md` text

To replace the opening of "**Name-graph:**" (it now says "Every named
thing in a `.lob` file or package is a node"):

> **Name-graph:** The central data structure of the tooling layer: the
> parse tree, with cross-references. Every element of a `.lob` file is a
> node: modules, sections, prose paragraphs, code blocks, bullet lists,
> claims, tests and the names code defines. Nodes and `CONTAINS` edges
> are a forest, one tree per file: `CONTAINS` is position, where each node
> is written. `USES`, `REFERENCES` and `IMPORTS` are a directed graph over
> the forest: what each call, reference and listing resolves to. What a
> node is (a claim, a paragraph, a symbol) is its kind; which scope a name
> belongs to is derived from the tree. Each node has its file and its
> first and last line. Text is held once, on the leaf it was written in; a
> symbol's text is the lines of its code block. What a consumer wants as
> one string is derived. An element of the document that is missing from
> the graph is a bug.
>
> The graph is exported at three levels of detail (`outline`, `index`,
> `full`), each a view of the same structure written by its own
> serialiser; the in-memory layout is not the wire format.

and the layers that follow it (Structure, Symbols, Cross-references, ...)
updated to match.
