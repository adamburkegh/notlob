# Design note: the name-graph as the parse tree with cross-references

**Status:** design agreed in discussion, 2026-10-23/24; for a final read
before slicing. Decisions and their reasons are in section 8.

## Where it stands, and the way home (2026-10-26)

Done, reviewed, uncommitted: slices 1 to 5c, kinds and scope
(`slice-kinds-and-scope-brief.md`, the Appendix checks fix included),
5d (item 1 below), and slice 6 (6a, 6b), brought forward on Adam's
word; 2026-10-26, suite 2070 passed, 2 skipped (ts-media not
installed). See `review-questions.md` for what waits on him.
`ModuleCache` deleted (suite 2097 passed, 2 skipped) and the CHANGELOG
drafted against 0.5.4 (item 2), both for Adam to read. Next: the
release. The
graph is the parse tree; every output prints it; the legacy layer,
`DEFINES` and the bindings' own collection walks are gone.

**To release, and nothing else:**

1. **5d.** D8: delete the one commented line in `_claim_identity` that
   keeps a named property in its section's scope, so it is addressed in
   its module's. D14: a run of bare assertions reports at its own
   address, not its group's (`claims_to_run`). `notlob test` output and
   the tests that pin those addresses follow. Also `_SCAN_ORDER` in
   `add_uses_edges`: a tuple that only keeps `USES` edges in the order
   the old per-kind loops made them (`RUN`, `TEST`, `EXAMPLE`,
   `PROPERTY`), kept so the kinds refactor moved no output. Delete it and
   the sort, so the edges come in document order. Before the release
   because these change the output, and the format should break once.
2. **CHANGELOG and docs.** The graph document version 2 (levels, kinds,
   ordinal addresses, `--level`); the queries and `query content`;
   Turtle at three levels with UpperCamelCase classes; `BindingKit`
   (D17, breaking, stable tier); `subheading_address`, `symbol_address`,
   `property_address` and `claim_address` gone from `notlob.__all__`
   (`named_address` and `anonymous_address` in their place); Haskell
   property numbering; TypeScript's empty `#Tests`; the checks now
   reading an `#Appendix`. Mark resolved: the bug notes for the line
   drift, the Appendix not in the graph and the incomplete name-graph.
3. **Release**, then notlob-vids moves to the new format.

**After the release, not before:** slice 6 (module listing; the
gutenberg strict xfail marks it), 2e, 7, D11, D16, and findings 1 to 5
and 10 of `../2026-10-26-missing-concepts/design.md` (finding 3's weaver
`~run` bug and finding 1's `##` disagreement are known defects; the
weaver was not touched by this work, and finding 1 is not yet shown by
a test). None of these is needed to bring this change home.
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
| D10 | Label uniqueness, and an anonymous node's label | A named node's label is unique within its scope: a second is an error (the address would name two nodes). Correction, 2026-10-24: "as now" was wrong. `add_node` raises `AddressCollisionError` only for two nodes of different kinds; two of the same kind (two `def f` in a module) silently keep the last. Choice: ban redefinition, or follow the binding's language; leaning to banning it, since notlob is name-oriented (Adam). Slice 2c keeps today's behaviour. Split (Adam, 2026-10-25), as D15 was: a **document name** restated in its scope (two headings, `~property` or `~test` names) is an error, `AddressCollisionError`, from slice 4a, since headings have no bound language to follow and replacement left one node with one heading's lines and both headings' children. For **code names** the choice stays open; the last definition wins meanwhile. The same name in different scopes (a property's `helper` shadowing the module's, or two modules' `helper`) is legal, and `notlob check` warns. An anonymous node's label is its kind and ordinal (`prose#1`), as claims' are. The compiler enforces uniqueness in a scope; the linter nudges across scopes |
| D11 | Node kinds for the `#Binding` section and its declarations, and for the `#References` section and its lines (section 2's table has none, though D6 and the completeness contract need them); with it, `USES_EXTERNAL` from the declaration leaf (D9) | Decided (Adam, 2026-10-26), for 0.6.0, since it changes the schemas the release breaks anyway. **Sections:** `REFERENCES` at `mod#References` and `BINDING` at `mod#Binding`, named like `mod#Tests`. **Their lines**, one node each, told apart by who owns the syntax: `LISTING`, a `#Module` line (notlob's; its `IMPORTS` edge to the module starts at it) and `IMPORT`, a line of the bound language (the binding's; notlob holds its text verbatim, as code). In `#Binding`, `DECLARATION`, with its facts as fields (D18): `declares` (`language`, `external`, `on-build`, `keep-generated-src`) and `value`; `USES_EXTERNAL` starts at the declaration that names the file. All three are anonymous and numbered, and left out of `outline` like paragraphs, so their edges lift to the section there. **The `REFERENCES` edge is renamed `CITES`:** its name contradicted the `#References` heading, whose lines make `IMPORTS` edges, not `REFERENCES` ones (Adam: "it *directly* contradicts the heading"). `IMPORTS` keeps its name (five months old; loose since loading follows need, but not contradictory). Open: whether a host-language import that spans lines (`import {\n a\n} from 'x'`) is one node per line or one per run of lines |
| D12 | Where the post-text sections hang | From a `POST_TEXT` node, starting at the `---` line, at `mod#post-text`: the grammar's `post_text`, which the language has always called the appendix (`LANGUAGE.md`: bare assertions "belong to the appendix rather than the argument"). `#Tests`, each `#Appendix` and `#References` are its children. `APPENDIX` stays the kind of one `#Appendix` section. Needs a position on the model's `PostText`. Its children keep their addresses (`mod#Tests`, `mod#appendix#1`): the post-text is a region of the tree, not part of an address, as a section is not a scope. (Proposed by the design session drafting 2d and agreed by Adam, 2026-10-25: test results already carry `mod#Tests#group` addresses, and `mod#post-text#Tests` would change them for no gain.) |
| D13 | The kinds in `#Tests` | `TESTS` (the section), `TEST_GROUP` (a `##group`, which holds things) and `TEST` (a test, named by `~test` or anonymous), as `PROPERTY` covers named and unnamed properties: being named is in the label and the address rule, not the kind. Replaces 2c's single `TEST` for three things, which made the code tell them apart by address pattern |
| D14 | Where an anonymous test begins and ends | An `assertion_block` grammar rule, built like `code_block`. The block is layout and is notlob's (indentation, blank lines, commentary); the assertions in it are the binding's, which splits them by its own language (`_iter_assertions`) and runs and reports them one by one, under the block's address and their line, as for `~example` and `~test`. Commentary ends a block. Today `build`, the oracle test and each runner each work the runs out, and disagree (`meta/bugs/2026-10-25-tests-commentary-line-drift`) |
| D15 | Names and ordinals share one address space (below) | Decided (Adam, 2026-10-25): **no `#` in a document name** (option 1). No `.lob` file under `examples/` or `ref-projects/` has one, so nothing needs renaming. To be enforced by the grammar's name terminals (`MOD_HEAD`, `SUBHEAD`, the `~property` and `~test` names, `APPENDIX_HEAD`), with a parse error that says which name and why; it goes with the grammar work of 2e. **Dashes: disliked, not banned.** They clash with references (`##Round-Trip` cites `Round`), but a module title is its path (`#Media-Attributes Analysis` is `media-attributes/analysis.lob`), and notlob-vids writes its named properties in kebab case (`layouts-are-well-formed`), so a ban needs its own decision. Narrowed (Adam, 2026-10-25): it is about **document names** only (headings, `~property` and `~test` names, Appendix titles), which are notlob's syntax. **Code names** follow the binding's identifier rules and notlob does not restrict them ("or we will fight the bound executable layer"); if a binding ever allows `#` in an identifier, the address encodes it rather than banning it. None of the three does today |
| D17 | Who collects the claims and tests a binding runs | notlob, from the graph (Adam, 2026-10-25). Each runner is handed what to run (address, kind, mode, lines, first line) and keeps execution: assembling, splitting assertions by its language, running, reporting. The same division as D14: notlob owns structure, the binding owns its language. A breaking change to `BindingKit` (stable tier), to be called out in the CHANGELOG; the users are the three built-in bindings and a partial Rust binding that predates `BindingKit` |
| D18 | Facts of an element the graph does not hold (first: a `~run`'s mode) | Everything should be in the graph (Adam, 2026-10-25): the completeness contract covers an element's facts, not only its text and position. A `RUN` node records its mode, a bare `~run` as `on-invocation` (the grammar's meaning). The same rule is behind D11. Second case, slice 4b: `Node.name`, the document name of a heading, `##group`, named `~property` or `~test` (`None` for an anonymous node), so a named test is told from a run of bare assertions by a fact, not by its lines |
| D16 | Referring to code names from prose | Open, and a defect: a function cannot be referenced from prose (`meta/bugs/2026-10-25-code-names-not-referenceable`). The reference terminal's Title Case rule was made for headings and leaked onto code names. Needs a reference form that follows the binding's identifiers; its own design discussion, not part of 2e. Widened (2026-10-25): the same form should reach document names the Title Case rule cannot (``##`Round-Trip` ``, ``#`mix-never-clips` ``), so names stay free apart from `#` and lint waits for real cases. Also (2026-10-25): citing a symbol of another, listed module (`#load_play` in `corpus` for `hamlet`'s function) does not resolve today, since step 3 resolves a module's name only. Citation may be circular (listing is free; only a cycle of need is an error, `meta/bugs/2026-10-22-mutual-references`) |

**D15.** Named nodes are addressed by name (D10) and anonymous ones by
kind and ordinal (D1), under the same parent, so a name can take the
form of an ordinal and the two land on one address. Found in 2d: `~test
test#1` after a run of bare assertions puts both at `g#test#1`, and the
last wins. Not only tests:

```
##prose#1                 -> mod#prose#1      (the module's first paragraph)
~property property#1      -> mod#property#1   (its first unnamed property)
```

No `.lob` file under `examples/` has a name with a `#` in it (searched
2026-10-25). The options:

1. **Names may not contain `#`.** `#` is notlob's address separator and
   its reference sigil, so a name holding one is already ambiguous to
   read (`#Notes#2` in prose). It removes the clash entirely, since every
   anonymous segment has a `#` and no name could. An error from the
   parser or `notlob check`. The Turtle helper's comment that a title can
   hold `#` would then be about addresses made by older files only.
2. **Names may not take an ordinal's form** (`prose#1`, `test#3`, any
   anonymous kind followed by `#` and a number). Narrower; names with
   other `#`s stay legal, and so does the reading ambiguity.
3. **Leave it to the collision error.** With redefinition banned (D10,
   leaning), the clash becomes an `AddressCollisionError`. Least work,
   but the error would name an address the author never wrote.
4. **Mark anonymous segments differently** (`mod#~prose1`, say). Clean
   in principle, but it changes every anonymous address, claims'
   included, which test results and tools already carry.

Leaning to 1, for document names. It costs authors nothing: the
reference terminal (`REF` in `grammar.lark`) already allows only
letters, digits, `_` and single spaces in a label, so a heading or
property with `#` in its name can never be cited.

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

**Where the code stands.** `DESIGN.md` describes this design as the
theory, with no implementation status (it is kept tight; phase and slice
information lives here). Until the slices land, the code builds the
earlier graph: named nodes, claims and tests only, a section's prose and
code as concatenated strings on its node, `DEFINES` edges from a section
to its symbols, claims and tests, and no node for an `#Appendix`. The
`--level` option of `notlob graph`, the `--depth` option of `notlob query
content` and the duplicate-name warning do not exist yet.

Each slice is a brief for one implementing session, with its failing test
first, a list of files it may touch, and a stop point. Order:

1. **`DESIGN.md`:** the contract and this model (section 10). Docs only.
2. **Nodes and tree**, in three parts, each leaving the suite green.
   Found when drafting the brief (2026-10-24): the model records no
   `end_line` and no position for prose or an Appendix, and `check.py`
   reads the graph's raw content and `DEFINES` edges, so the
   representation cannot change without its readers changing too.
   * **2a, model positions:** `start_line` and `end_line` on every
     element of the model, prose and Appendix included. `model.py` and
     its tests only.
   * **2b, accessors first:** `check.py` reads through `NameGraph`
     methods (a section's prose; its claims, by kind) instead of raw
     content and `DEFINES`, implemented over today's representation. No
     change to any output.
   * **2c, the forest behind today's outputs:** the leaf kinds,
     `APPENDIX`, `TESTS`, `file`, `end_line`, `CONTAINS` as the only tree
     edge, claims made by `build`, `REFERENCES` from the `PROSE` leaf
     (D3); the six accessors over the forest; the oracle and forest
     tests. Every output (`notlob graph` JSON and Turtle, every `notlob
     query`, the MCP tools) keeps today's shape, produced from the forest
     by a temporary layer that slice 5 deletes. Decided with Adam,
     2026-10-24, after finding that every output prints the
     representation: the CLI-level tests and the check tests stay
     unchanged as a guard; the tests of the in-memory structure are
     rewritten, since that is what changes. Also: today only an exact
     `~run` becomes a `RUN` node; `~run on-load` and `~run
     on-invocation` fall into the property branch of `enrich` and become
     `PROPERTY` nodes named after the mode (found in 2b; the backed-out
     work had fixed it). A claim's kind must follow its sigil.
   * **2d, follow-up to 2c:** the `POST_TEXT` node (D12, with a position
     on the model's `PostText`); `TEST_GROUP` and `TEST` (D13), so
     nothing tells tests apart by address outside the temporary layer;
     the stale docstrings in `graph.py` and the ontology comments.
   * **2e, the assertion block:** an `assertion_block` grammar rule
     (D14), through the parser and the model to `build`, and the oracle
     test reading the model's blocks instead of regrouping lines. With
     it, the other grammar change: no `#` in a document name (D15).
     **Moved after the release** (Adam, 2026-10-25): `build` already
     groups runs correctly (commentary ends one), so when slice 4 moves
     the runners onto the graph they read its runs and the line-drift
     bug goes with it; 2e then moves the grouping from Python into the
     grammar, a quality change not needed for a fixed graph.
3. **Symbol lines:** `SymbolInfo` lines in all three bindings, symbols
   without text, `graph.text()`, the `USES` line fixes. With them the
   `#Tests` `USES` fix (each anonymous test scanned on its own,
   dedented), since it is the same pass.
4. **Consumers onto the graph**, in two parts (Adam, 2026-10-25):
   * **4a, without the binding contract:** `enrich` reads the graph's
     code leaves (an `#Appendix` included, which brings back the
     Appendix symbols); `validate_refs` reads the `PROSE` leaves; the
     `RUN` nodes carry their mode (D18) and `notlob build` finds its
     entry points from them; one graph per command (D7). (The
     reference edges and the checks are already on the graph.)
     `collect_run_bodies` is called by the bindings, so it moves in 4b.
   * **4b, the binding contract (D17):** the runners of all three
     bindings run what notlob collects from the graph, and their
     `build()` and `lint()` take their `~run` bodies from it
     (`collect_run_bodies`, and so `notlob run`); their own collection
     walks go, and with them the `#Tests` line drift
     (`meta/bugs/2026-10-25-tests-commentary-line-drift`, whose
     strict xfail then passes) and the rest of the Appendix fix.
5. **Export:** replace the temporary output layer of 2c, in four parts,
   each moving some outputs off the layer (2026-10-25):
   * **5a, `notlob graph` as JSON:** the three levels with lifting,
     `--level`, `version` and `level` in the document, `name_graph.json`
     rewritten, the MCP graph tool, `LANGUAGE.md`'s graph section and
     `DESIGN.md`'s command line; the "once" and "nesting" tests.
   * **5b, `notlob query`:** every query on the graph itself, `query
     content` as the subtree with `--depth`, `query_result.json`, the
     MCP query tools, the `--edge` choices without `DEFINES`.
   * **5c, Turtle, and the layer deleted:** Turtle at the three levels
     and the ontology to match; then `legacy_graph` and its helpers,
     the `DEFINES` edge kind, `Node.content`, the snapshot tests.
   * **Kinds and scope, before 5d** (Adam, 2026-10-26, from findings 6
     and 7 of `../2026-10-26-missing-concepts/design.md`): a table of
     what each kind is, `scope_of`, and two address functions, named
     and anonymous, in place of seven; no address or output changes.
     Brief: `slice-kinds-and-scope-brief.md`.
   * **5d, addresses in results:** a named property addressed in its
     module's scope (D8), a run of bare assertions reporting at its
     own address (D14), the scope test; `notlob test` output follows.
6. **Module listing** (`1468f0f`), redone on the new graph, with the old
   commit as reference. (Its `#Tests` `USES` fix moved to slice 3.)
   Split (2026-10-26), with Adam's go-ahead to carry on through slice 6:
   * **6a, loading follows need, from the graph:** need is an `IMPORTS`
     edge and a `USES` edge into the listed module's own code; notlob
     works out the load order and hands the modules to the binding
     (`deps`), as it hands the claims (D17). Brief:
     `slice-6a-brief.md`.
   * **6b, `__file__` and the examples:** Python claims see their
     `.lob` path; every example project runs end to end in a test.
     Brief: `slice-6b-brief.md`.
   Committed as `6e54c9d`, with everything before it.
8. **D11, before the 0.6.0 release** (Adam, 2026-10-26), in two parts:
   * **8a, `REFERENCES` becomes `CITES`:** the edge kind, the Turtle
     property, the queries `references` and `referenced-by` (now `cites`
     and `cited-by`) and the MCP tools. Mechanical; no other change.
     Brief: `slice-8a-brief.md`.
   * **8b, the `#References` and `#Binding` nodes:** the kinds of D11,
     the model keeping each declaration with its line, listings told
     from imports by the grammar, `IMPORTS` and `USES_EXTERNAL` starting
     at their lines. Brief: `slice-8b-brief.md`.
7. **Duplicate-name warning** (D10): a `notlob check` advisory for the
   same name in different scopes, beside the `typos` check. It also makes
   the doubtful `USES` edges of the global label index visible until
   scoped lookup (section 3) arrives. Not needed for the release.

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
> is written. `USES`, `REFERENCES`, `IMPORTS` and `USES_EXTERNAL` are a
> directed graph over the forest: what each call, reference, listing and
> external declaration resolves to. What a node is (a claim, a paragraph,
> a symbol) is its kind; which scope a name belongs to is derived from the
> tree. Each node has its file and its first and last line. Text is held
> once, on the leaf it was written in; a symbol's text is the lines of its
> code block. What a consumer wants as one string is derived. An element of
> the document that is missing from the graph is a bug.
>
> The graph is exported at three levels of detail (`outline`, `index`,
> `full`), each a view of the same structure written by its own
> serialiser; the in-memory layout is not the wire format.

and the layers that follow it (Structure, Symbols, Cross-references, ...)
updated to match.
