# The name-graph is not the graph of names, prose, concepts and code the design describes

**Component:** `notlob/graph.py` and `notlob/model.py`; everything that
walks a module instead of reading the graph.
**Found by:** Adam, 2026-10-20, while reviewing the Appendix blind spot
(`2026-10-19-appendix-not-in-graph`), which is one instance of this.
**Status:** reopened, 2026-10-23. The fix below (`f4b9eb9`) was backed
out in `4230b04`: the completeness contract stands, but the representation
it used stored each section's text, claims and references several times
and exported that through the graph schemas. See
`meta/retrospectives/2026-10-23-name-graph-redundancy/`. "Progress" below
describes the backed-out work, kept for the record. Was: fixed for module,
subheading and appendix bodies, 2026-10-21.

## The design

The paper:

> it is straightforward to use the parse tree to build a graph of names,
> prose, concepts and code that can be accessed by tooling. There are then
> two types of adjacency available cheaply to human and machine agents:
> file-adjacency, where elements are close together in the same chunk of
> serial text on the filesystem, and concept-adjacency, where related
> elements are connected on a path with a small number of edges. [...] It
> can also be used for consistency checks across the codebase, which
> includes the prose.

Two more statements from the paper bear on this: nodes "reference their
location in source files to allow precise navigation among related
elements of code", and a node's address is generated "from its location on
the file system and within source files". And, on concepts: heading
references make "conceptual dependencies ... visible in the name-graph
structure itself", so concepts are headings, linked by `REFERENCES` edges.

`LANGUAGE.md` says the same in one line: a `.lob` file is "read as
structured text, executed as a program, rendered as a document, and
traversed as a name-graph — all from the same source."

So the graph is meant to be a complete index of the document: names,
prose, concepts and code, with both kinds of adjacency, the substrate
tooling and consistency checks read. `DESIGN.md` had described it as
"every named thing in a `.lob` file or package is a node", the weaker
framing, and now states the completeness contract.

## What was missing (verified in the code, 2026-10-20)

1. **Order and structure inside a body.** Prose and code were two separate
   concatenations; how they interleave was lost, and file-adjacency could
   not be answered below the level of a node.
2. **Prose had no position, even in the model.** `ProseBlock` had no
   `start_line`.
3. **The `~run` mode.** A `RUN` node did not record `on-load` or
   `on-invocation`. (Worse: a `~run on-load` was made a `PROPERTY` node
   named "on-load", because the graph compared the sigil to `~run`
   exactly.)
4. **Language imports.** `graph.py` never read the `#References` section;
   only lob-refs became `IMPORTS` edges.
5. **A `~run` body was counted twice:** appended to the region's code text
   and again as its own `RUN` node.
6. **Fidelity of claim source:** `.strip()` removed leading blank lines,
   which would shift reported line numbers.
7. **Concepts:** nothing missing (see above).
8. **Completeness was nowhere checked.** A completeness test existed since
   June (`tests/test_graph_completeness.py`) but its fixture had no
   Appendix and it found claims with the same hand-written walk, so it
   shared the blind spot.

Consequence: the consumers that needed the document's contents did not use
the graph; each walked the parse tree itself, roughly ten walks, each
deciding where to look. The Appendix bug was one miss; the checks that do
read the graph (`[imports]`, `typos`, `conventions`, `quantifier`) were
blind in the same places.

Adam's assessment (2026-10-20), recorded as his: this is "a bug right at
the core of the implementation, caused by a succession of agents hacking
around one of the core ideas in the design." Each August fix (`20b9390`,
`2b2dd3e`) made one consumer see the Appendix rather than making the graph
complete and having consumers rely on it.

## Progress

Done, 2026-10-21 (in the commit that fixes the Appendix bug):

* **A body is held on its node.** A module, a subheading and an
  `#Appendix` each have a body (the grammar's term) and each is a node.
  The node's `content.body` lists its body items in order: prose (with its
  text, its cross-references as data, and its line), code (dedented, with
  its line), bullets, and claims (by the address of the claim's own node,
  with the claim's line). `graph.body(address)` reads it.
* **Claim nodes are made by `build`,** not `enrich` (claims are structure,
  not symbols), and keep their `sigil` (so the `~run` mode) and their
  lines with leading blank lines intact. A `~run on-load` is a `RUN`.
* **The module node carries its imports** (`content.imports`: each
  `#References` line, whether it is a lob-ref, and its line).
* **Prose has a position** in the model (`ProseBlock.start_line`).
* **The Appendix is a node** (`APPENDIX`), with its body and its
  subheadings.
* **The graph is the only reader of bodies.** `build` is the one place the
  parse tree is walked to find them. Symbol extraction (`enrich`), the
  reference edges, reference validation, the claim collectors in all three
  bindings, `collect_run_bodies` and `notlob run`'s entry-point test read
  the graph. Claim addresses and numbering have one owner. (This also fixed
  a divergence: Haskell numbered unnamed properties with one counter for
  the whole module, the graph per body.)
* **The contract is tested,** `tests/test_graph_body.py`: an oracle walks
  the parse tree independently and, for every combination of places code
  can be written, what the graph holds for each node's body equals what
  the tree says, in order, with positions; plus the claims' sigils and
  lines, refs as data, imports, and JSON-schema conformance.
  `tests/test_appendix_graph.py` checks the assembler, graph and collectors
  agree, and derives the set of body-holding model fields from the grammar.

## Still open

* **`#Tests`:** group and named-test nodes carry joined bare lines; the
  per-assertion lines and the order of assertions, prose and named tests
  are not in the graph, so the `#Tests` collectors still read the tree.
* **Binding declarations** (`~language`, `~on-build`, `~keep-generated-src`
  in `binding.lob`) are not in the graph; `~external` files are.
* **Turtle** does not export the body items, imports or claim sigils (the
  JSON export and `query content` do). Whether it should is undecided.
* **The assemblers and the weaver** read the parse tree. They are correct
  today; the consistency tests tie their output to the graph. Moving them
  onto the graph would make the contract structural rather than tested.
* **Queries and checks** still use the concatenated `prose` and `code`;
  none use `body` yet.

## Related

* `meta/bugs/2026-10-19-appendix-not-in-graph/bug.md` (fixed): one
  instance.
* `meta/retrospectives/2026-10-19-appendix-blind-spot/retrospective.md`
  (second layer is Adam's).
