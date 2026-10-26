# Questions for Adam, from 5d to the end of slice 6

**Answered (Adam, 2026-10-26):**

1. `deps` on `BindingKit`: yes, "probably constructive and better to
   take the hit now".
2. Delete `ModuleCache` ("a buried design and sounds like a knockoff
   name-graph"): briefed, `slice-modulecache-brief.md`.
3. Widening TypeScript and Haskell reference extraction: scheduled for
   design and discussion, `../2026-10-26-complete-references/design.md`.
4. fast-check (ts-media's property-testing library, as Hypothesis is
   Python's): asked whether to install it.
5. CHANGELOG: draft it with the change, recording the final difference
   from 0.5.4, not the journey; no phase or slice wording.

**Written by:** the design session, 2026-10-26, while Adam was at work
("push ahead to the end of slice 6 ... accumulate all questions for my
review there"). Each says what was done meanwhile, so nothing waits on
it. Newest last.

## 1. Slice 6 hands the bindings their dependencies (`deps`)

Slice 6 was one line in the plan; `1468f0f` was 1800 lines across four
concerns, so it is now 6a (loading follows need, from the graph) and 6b
(Python `__file__`, every example run end to end).

The design of 6a is yours from 2026-10-22 (the mutual-references bug
note). One decision is new to the redo: notlob works out which modules a
module's code needs, from the package graph's `IMPORTS` and `USES`
edges, and hands them to the binding as `deps`, as it hands `claims`
(D17). Today each binding loads its own, and two of three do it wrongly
(direct listings only). It is a second change to `BindingKit` in this
release, on the same principle as D17.

**Done meanwhile:** briefed that way (`slice-6a-brief.md`).
**Question:** agree, or keep loading inside the bindings and have them
call one shared function (the `1468f0f` shape)?

## 2. 5d done: what moved, for the CHANGELOG and notlob-vids

No question; a record. Suite after 5d: 1987 passed, 1 xfailed (my run).

* A run of bare assertions is reported at its own address:
  `roman/numerals#Tests#encoding` became
  `roman/numerals#Tests#encoding#test#1` in `notlob test` output, each
  assertion still at its own line.
* A named property is in its module's scope:
  `media-attributes/analysis#Distance#symmetry` became
  `media-attributes/analysis#symmetry`. Two named properties of one name
  in one module now collide, as does one named like a subheading or
  symbol. notlob-vids' three named properties are all under sections,
  so they move too; nothing in notlob-vids names those addresses.
* `USES` edges come in document order (the same set).
* Known and left for 2e: a bare run followed by `~test test#1` in one
  group collides (both `g#test#1`), with an error naming an address the
  author did not write. D15's grammar rule (no `#` in a document name)
  removes it.

## 3. 6a done; two questions from it

Suite after 6a: 2054 passed, no xfail (the gutenberg one passes). The
1468f0f tests came back with only their calls changed (listed in the
implementer's report; e.g. `load_dependency_modules(m, root, kit)`
became a test helper over the package graph). `load_order` in
`project.py` reads only `IMPORTS` and `USES` edges; the three bindings'
loaders are gone and each is handed `deps`. Gutenberg's `corpus` cites
and lists `#Gutenberg Hamlet`, and a cycle of need is `ERROR <imports>
circular code dependency: ...` in `test`, `run` and `build`.

One process lapse, owned by the implementer: the restored tests were
not run before the code was written, so there is no failing run to
show. They could not have passed (each calls something that did not
exist), so I accepted it.

**Question 3a:** `bindings/python/loader.py` (`ModuleCache`) now loads
nothing anyone uses; commands still build one and pass it as `cache=`,
which only TypeScript reads, for its project root. Delete it and the
plumbing (pass `root` where TypeScript needs it)? Left alone meanwhile.

**Question 3b:** as settled on 2026-10-22, TypeScript and Haskell cannot
tell use from citation (their call extraction is partial), so two
sibling modules there that list each other are a cycle. Documented in
`DESIGN.md`; no example has the shape. Widening their extraction is the
fix and is its own piece of work: schedule it, or leave it as a known
limitation for this release?

## 4. 6b done; the end of slice 6

Suite after 6b (my run): 2070 passed, 2 skipped, no xfail. Python claims
see their module's `.lob` path as `__file__` (a built artifact does
not); every example project now runs end to end in
`tests/test_example_projects.py`: roman, retail, gutenberg and
haskell-roman pass. The restored tests failed first, on behaviour as
well as call shape (Gutenberg's data file not found).

**Question 4a:** the two skips are ts-media, whose `fast-check` is not
installed (`npm install` in `examples/ts-media`). Installing is yours to
decide; until then that example is not run end to end here.

**Question 4b:** next is the CHANGELOG and docs pass, then the release
(the way home, item 2). The implementer offered to draft the CHANGELOG
entries for you to read. Go ahead with that, or do you want to commit
first?

## After you commit

Mark resolved, with the commit: the bug notes
`2026-10-20-name-graph-incomplete`, `2026-10-21-transitive-lob-refs`,
`2026-10-22-mutual-references`,
`2026-10-22-python-claims-file-attribute`,
`2026-10-25-tests-commentary-line-drift`. Still open:
`2026-10-22-lint-failure-reads-as-clean`,
`2026-10-25-code-names-not-referenceable` (D16).
