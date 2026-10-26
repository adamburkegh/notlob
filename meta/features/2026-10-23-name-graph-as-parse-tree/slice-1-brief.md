# Slice 1 brief: bring `DESIGN.md` into line with the name-graph design

**For:** an implementing session. **Written by:** the design session,
2026-10-24. **Design:** `design.md` in this directory (read it first,
sections 1, 2, 3, 5, 8 and 10).

## Goal

`notlob/docs/DESIGN.md` describes the name-graph as "every named thing
... is a node". Make it describe the agreed design instead: the parse
tree with cross-references, as set out in `design.md`. Docs only. The code
does not change in this slice, so `DESIGN.md` must also say, plainly, that
the code has not caught up yet.

## Rules

* **Touch only `notlob/docs/DESIGN.md`.** Not `LANGUAGE.md`, not
  `CHANGELOG.md`, not code, docstrings, schemas or tests. If another file
  needs a change to stay true, list it in your report; do not make it.
* **Say only what `design.md` says.** Do not add design. If a passage of
  `DESIGN.md` raises a question `design.md` does not answer, stop editing
  that passage, leave it as it is, and put the question in your report.
* **Do not commit or stage.** Adam handles source control.
* 80-character lines. Australian/British spelling, matching the file.
  Match the file's existing tone and density; do not add headings it
  does not have.

## The passages to change

Line numbers are as of `4230b04`. Each item: where, what it says now, what
it should say.

**1. `~property` naming (lines 135-159).** Now:

```
(`~property commutativity`), which creates a named node in the name-graph
at the level of its containing doc-node. ...
roman/numerals#Round-Trip#commutativity        ← property node
roman/numerals#Round-Trip#commutativity#prop   ← named function within
...
Unnamed `~property` claims have no property node in the name-graph; the
runner addresses them by ordinal within their containing doc-node.
```

Should say: a named property's name is in its **module's** namespace
(sections are not scopes, `design.md` D8), so its address is
`roman/numerals#commutativity`, and a function inside it is
`roman/numerals#commutativity#prop` (a property opens a scope). An
unnamed property **is** a node, addressed by ordinal within its section
(`roman/numerals#Round-Trip#property#1`). Keep the theorem/lemma framing
and the `_` paragraph as they are.

**2. Node addresses and labels (lines 225-241).** Now:

```
The two are mechanically related: `address = parent_address + "#" +
label`. This mirrors the URI fragment convention and is isomorphic to
an RDF URI, enabling a mechanical export to RDF/Turtle as a build
artifact (planned, not yet implemented).
```

Should say: a named node's address is its **scope's** address, `#`, and
its name, where the scope is the nearest enclosing node whose kind opens
one (`MODULE`, `PROPERTY`, `TESTS`, a `#Tests` group); an anonymous node
(a prose paragraph, a code block, an unnamed claim, an Appendix) is
addressed by position: its parent's address, its kind and its ordinal
(`design.md` section 2, "Scope", and D1). The RDF/Turtle export exists
(`notlob graph --format turtle`): drop "planned, not yet implemented".

**3. The "Name-graph" paragraph and its layers (lines 332-379).** Replace
the opening paragraph (lines 332-335, "The central data structure ...
each adding richer information:") with the text in `design.md` section
10, verbatim apart from line wrapping. Then update the five layers that
follow so they agree with it:

* *Structure:* every element of a file is a node, in one tree per file
  (`CONTAINS`); still binding-agnostic.
* *Symbols:* a `SYMBOL` is contained by the `CODE` leaf (or `PROPERTY`) it
  is written in, and holds its lines, not a copy of its text
  (`design.md` section 3).
* *Cross-references:* a `REFERENCES` edge comes from the `PROSE` leaf that
  holds the reference (D3); the three-step resolution order is unchanged.
* *Package graph:* unchanged.
* *Call graph:* `USES` edges come from the code of symbols, claims and
  tests (`design.md` section 3, "`USES`"). Keep the fidelity caveat. The
  `USES_EXTERNAL` sentence: the edge comes from the `~external`
  declaration's leaf (item 5).

Then add, after the layers, the status note in item 6.

**4. Commands (lines 488-491).** `notlob graph` exports JSON or Turtle at
three levels (`outline`, `index`, `full`; `--level`); `notlob query
content` returns the subtree at an address, with `--depth` (`design.md`
sections 5 and 6). One line each; the detail belongs in `LANGUAGE.md`,
later.

**5. `~external` (lines 619-623).** Now: "connected to the binding module
via a `USES_EXTERNAL` edge". Should say: connected from its declaration
(a leaf of `binding.lob`'s tree) by a `USES_EXTERNAL` edge; the node's
identity is the declared string, verbatim, which notlob does not
normalise or resolve (D9).

**6. A status note,** after the layers in item 3, in the style of the
file's other status notes:

> *Status, 2026-10-24:* this is the target design
> (`meta/features/2026-10-23-name-graph-as-parse-tree/design.md`), being
> implemented in slices. Until they land, the code builds the earlier
> graph: named nodes, claims and tests only, a section's prose and code
> as concatenated strings on its node, `DEFINES` edges from a section to
> its symbols, claims and tests, and no node for an `#Appendix`.

## Not in this slice

`LANGUAGE.md` (its graph and query sections change with the export, in
slice 5; its calling `~run` a claim is a separate fix). The `graph.py`
docstrings. The CHANGELOG. The "doc-node graph" wording at lines 302-305
and 692.

## When you are done

Stop and report, without committing:

1. Each passage changed: its line range, and the new text or a short
   before/after snippet.
2. The output of a line-length check on the file, e.g. any line over 80
   characters.
3. Any question you stopped on, and any other file you think needs a
   change, with the passage that made you think so.

The design session reviews the diff against this brief and `design.md`
before it goes to Adam.
