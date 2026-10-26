# Review: concepts the code lacks, after the name-graph redesign

**Status:** review, for discussion before any slicing.
**Origin:** Adam, 2026-10-26, after slices 1 to 5c of
`2026-10-23-name-graph-as-parse-tree`: "Line cost is a symptom, not a
target. Let's treat the disease." The consolidation removed the bindings'
duplicated walks (about 300 lines of code) but `graph.py` absorbed it,
and code came out about flat. This note looks for why.
**Method:** read `notlob/graph.py` whole, and the parts of `commands.py`,
`project.py`, `model.py`, `parser.py` and the weaver that touch what it
holds. For each idea in the design, ask whether it has one home in the
code. Where it does not, the symptom is the same idea written in several
places, data threaded by hand through every caller, or a special case
standing in for a rule. Line numbers are as of the end of slice 5c.

## What now has one home

Worth saying first, since the redesign was about this:

* **The tree.** `build` is the one walk of the model that makes nodes;
  the checks, the queries, `enrich`, `validate_refs` and the reference
  edges read the graph.
* **Collecting claims.** `claims_to_run` is the only place; the three
  bindings' collectors are gone.
* **The printed graph.** One node writer (`_node_entry`) and one edge
  writer with the lifting (`_document_edges`) serve the JSON, Turtle and
  every query.
* **A symbol's text.** Held once, read by its lines (`NameGraph.text`).

## The findings

Ordered by harm: the first three have already produced a disagreement or
a bug.

### 1. Resolving a reference has two homes, and they disagree

`add_references_edges` resolves every reference with `graph.resolve`
(`graph.py:1202`), which ignores whether it was written `#` or `##`.
`validate_refs` resolves through `_resolves` (`graph.py:1603`), where `##`
must be a subheading:

```python
# add_references_edges
target = graph.resolve(ref.label, context=context)

# _resolves
if ref.sub:
    node = graph.node(f"{mod_addr}#{ref.label}")
    return node is not None and node.kind == NodeKind.SUBHEADING
```

So `##to_roman` in prose gets a `REFERENCES` edge to the function **and**
an "unresolved reference" error. (Found by reading; not yet shown by a
test.) The concept is "what a reference resolves to": one function,
from which both the edge and the error follow.

### 2. A module's document errors are not a concept

A module can be wrong in four ways the tooling reports: it does not
parse, its title does not match its path, its names collide, a reference
does not resolve. Each is found in a different place and reported by
hand:

* collisions are raised by `add_node` (two kinds) and `_add_child`
  (document names), collected through a mode flag on the graph
  (`NameGraph._collisions`, set and cleared by `build`), caught and
  rebuilt in `project._module_graph`, and passed as `(path, error)`
  lists through `_package_graph`, `_graph_of_module`, `_test_module`,
  `cmd_test`, `_build_one`, `cmd_build` and `_run_check_advisory`
  (the word appears 35 times in `commands.py`);
* `ERROR <names>` is printed in eight places, and `notlob check --json`
  builds a finding of its own for it (`_collision_finding`);
* address mismatches come from `_check_address`, called in two places;
  unresolved references from `validate_refs`, in one.

The concept is "the document errors of a module", held with the graph
(each module's tree carries its errors), and reported by one function per
kind of output. It is the 4a collision option C, set aside then as the
wider decision. With it, a module that collides is simply a module with an
error, and the collision lists go.

### 3. A claim's facts are read from its sigil string, in four places

The grammar already tells the sigils apart (`SIGIL` lists `~example`,
`~run`, `~run on-load`, `~run on-invocation`, `~property`, `~property
NAME`), but the model keeps the sigil as a string and each reader splits
it:

```
graph.py:800   _claim_identity   parts = claim.sigil.split(None, 1)
graph.py:820   _run_mode         parts = claim.sigil.split()
graph.py:983   document_name     len(item.sigil.split()) > 1
weave/markdown.py:128            if claim.sigil == "~run": return None
```

The last is a bug of the same family the graph had (fixed in 2c): the
weaver leaves out a bare `~run` but renders `~run on-load` and `~run
on-invocation` as documentary blocks, which `DESIGN.md` says it does not.
The concept is "a claim's kind, name and mode", parsed once, from the
grammar, into the model (`Claim.kind`, `Claim.name`, `Claim.mode`).
"Grammar over Python" applies.

### 4. An element's span is computed by hand, though the parser has it

`parser.py:47` builds the parser with `propagate_positions=True`, so every
tree node already carries `meta.line` and `meta.end_line`. Nothing reads
them: `model.py` works out each element's first and last line from its
tokens, element by element (`_line`, `_last_text_line`, `_furthest`; 51
position expressions in the file). The concept is "an element's span",
from the parser. One difference to settle: the grammar keeps trailing
blank lines inside a block, so `meta.end_line` would count them, where
the model's `end_line` is the last non-blank line. Either the grammar
stops putting trailing blanks in blocks, or one helper trims them.

### 5. Where an element's text starts is worked out four times

A claim's text starts the line after its sigil; a code block's on its
first line; a run of assertions on its own first line; and some readers
drop leading blank lines. Each reader works it out again:

```
graph.py:587    text()          holder.start_line + (0 if CODE else 1)
graph.py:1095   enrich          CODE: start_line; PROPERTY: start_line + 1
graph.py:1166   claims_to_run   start_line + 1, or a run's own start_line
graph.py:1247   _scanned_text   start_line + 1 + leading blanks, or a run's
```

The concept is a fact of the element (D18, "everything in the graph"): the
line its text starts on, set by `build`. Every reader then reads it.

### 6. Scope and the address rule have no home

`design.md` section 2 states one rule: a named node is addressed by its
scope and its name, the scope being the nearest enclosing node of a kind
that opens one; an anonymous node by its parent, its kind and an ordinal.
The code has no function for either. Instead:

* seven address functions (`module_address`, `subheading_address`,
  `symbol_address`, `property_address`, `appendix_address`,
  `post_text_address`, `claim_address`) and as many f-strings in `build`
  (`f"{parent}#prose#{n}"`, `f"{parent}#code#{n}"`, `f"{mod_addr}#Tests"`,
  `f"{parent}#{item.title}"`, `f"{holder.address}#{info.name}"`, ...);
* the scope passed by hand: `_add_items(graph, items, parent, mod_addr,
  file)` carries the module address beside the parent so subheadings and
  symbols can be addressed from it;
* resolution building addresses as strings (`f"{context}#{label}"` in
  `resolve`, again in `_resolves`).

Slice 5d's address change (D8: a named property in its module's scope)
touches every one of these. With `scope_of(node)` and two address
functions (named, anonymous), D8 is a small change. **This one comes
before 5d.**

Correction, on writing the brief: today's addresses already follow the
design's rule for every named kind but one. A named `~property` takes
the section it is written in as its scope, where the rule gives its
module; a section does not scope a subheading or a symbol. So the
refactor keeps that one exception, in one line, and 5d deletes it,
rather than 5d changing a row of the table.

### 7. What a kind *is* has no home

D2 settled that a node's kind is an adjective. The adjectives are
scattered as tuples and special cases:

```
(EXAMPLE, PROPERTY, RUN)        claims()                   a claim
(EXAMPLE, PROPERTY, RUN, TEST)  claims_to_run, add_uses    runnable
ANONYMOUS_LEAVES                outline, references_of     hidden at outline
(SUBHEADING, APPENDIX)          sections()                 a section
(APPENDIX, POST_TEXT)           sections()                 walked into
kind == SYMBOL                  text, _sizes, _node_entry,
                                subtree, _scanned_text     holds no text
```

and the one the design names but the code never states: the kinds that
open a scope (finding 6). The concept is a table, one row per kind, of
what it is. Each tuple becomes a question asked of the table.

### 8. An anonymous test has no grammar rule

Known: D14 and slice 2e. A run of bare assertions is grouped in Python
(`_add_assertions`, and again in the oracle test). Listed here for
completeness; it is the same disease.

### 9. Readers still on the model

Known and deliberately out of scope: the three assemblers and the weaver
walk the model (31 type checks between them, against 69 at `d7bbca9`
across eleven files). Finding 3's weaver bug is the cost of it.

### 10. Smaller: a module's file on every node

Every node stores `file`, which is its module's. It is printed per node,
which is useful, but it is a fact of the module stored on each of its
nodes, and every `build` helper threads it through. It could be read
from the node's module (`module_of`) when printed.

## Suggested order

No line targets: each step removes a concept's duplicates and is judged
by whether the concept now has one home, with the tests unchanged in
what they assert.

1. **Findings 6 and 7, before 5d:** the kind table, `scope_of`, and the
   two address functions. 5d then changes a row of the table.
2. **Findings 1 and 2:** one resolution, and document errors held with
   the graph. Collision lists, `_collisions` and the eight `ERROR
   <names>` sites go. (Finding 1's disagreement gets a failing test
   first.)
3. **Findings 3, 4 and 5:** the model takes its facts from the grammar
   and the parser: a claim's kind, name and mode; spans from `meta`; the
   line a text starts on. The weaver bug gets a failing test first.
4. **Finding 8** is 2e, after the release, as planned. **9** stays out of
   scope. **10** whenever `build` is next touched.

## Decisions (Adam, 2026-10-26)

* **Order:** findings 6 and 7 before 5d, cost accepted.
* **Finding 2:** what is missing is an error *concept*, and so a type: a
  module's document errors, held with the graph. Not uniform wording:
  compiler errors are notorious because each needs its own message to
  help the developer, so each kind of error keeps a message written for
  it.
* **Finding 4:** the lines come from the parser, which has them. No
  recalculating by hand. Adam: perhaps the classic case of agents having
  to be pushed to use declarative artifacts, though they help. If the
  grammar puts trailing blank lines inside a block, so that the parser's
  span is not the element's, that is fixed in the grammar, not trimmed
  in Python.
* **The checks and the Appendix** (found writing the finding 6 and 7
  brief): `check.py` asks `kind in (MODULE, SUBHEADING)` in three checks
  (titles, style, claims-missing), so an `#Appendix` is never checked.
  Not deliberate: an artifact of how the code was written. The checks
  ask the table of kinds (a module or a section), and the Appendix is
  checked like any section.
