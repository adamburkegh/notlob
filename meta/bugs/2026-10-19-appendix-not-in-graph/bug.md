# `#Appendix` code is invisible to the name-graph, so `[imports]` flags real uses

**Component:** `notlob/graph.py` (`build`, `enrich`, `add_references_edges`)
**Found by:** kamtrinia, notlob 0.5.4, Python binding, 2026-10-19.
**Status:** open, not fixed. Cause confirmed by reading the code; the
extent beyond the symptom is partly unverified (see "Verify first").

## Summary

`notlob check` reported `unused import: Motif imports Typesetting but uses
none of its symbols`. The only use of Typesetting was `Face(...)` inside
`_text_width`, which lived in `#Appendix Width and test support`. Moving
the unchanged function into a body section (`##Text`) made the error
disappear. `LANGUAGE.md` says Appendix code "is assembled exactly like
main-body code", and at run time it is (claims calling it worked); only
the checker disagrees.

## Cause (confirmed)

The graph treats an `#Appendix` as second-class:

- `build` adds the Appendix's `##Subheading` nodes (graph.py ~line 651) but
  nothing from its direct code or claims.
- `enrich` walks `module.body` only. It never visits
  `module.post_text`'s `AppendixSection`, so symbols (and `~example`,
  `~run`, `~property` nodes) defined in an Appendix, including inside its
  subheadings, are not graph nodes and produce no `DEFINES` or `USES`
  edges.
- `add_references_edges` also walks only `module.body`, so a prose
  `#Label` reference in an Appendix yields no `REFERENCES` edge.
- By contrast `validate_refs` does walk the Appendix, and the three
  assemblers (`bindings/*/assemble.py`) include it, which is why it
  works at run time and in `notlob test`.

`check_imports` counts a dependency as used only if a `USES` or
`REFERENCES` edge runs from the module (or a node under it) to the
dependency. With no edges from Appendix code, an import used only there
looks unused.

## Wider effect

The same gap hides Appendix symbols from everything built on the graph:
`notlob query` (search, callers, callees, content), `notlob graph`, and
the `typos`, `conventions` and `titles` checks. The `[imports]` false
positive is only the one that turns into an error.

## Verify first

- Whether `~example` / `~property` claims written inside an `#Appendix`
  are collected and run. The runners' claim collectors
  (`_collect_example_assertions` and the property and test collectors)
  never mention `AppendixSection`, so they may be silently skipped, which
  would contradict `LANGUAGE.md` ("its body is a regular body (prose,
  code, subheadings, claims)"). Test it before assuming either way.
- Address numbering: an Appendix claim's `mod#example#N` must not collide
  with a body claim's, and must match between the graph and the runners.

## Plan (test first)

1. A failing test: a module whose only use of an import is in an
   `#Appendix` has no `[imports]` error; the Appendix function is a
   graph node with a `USES` edge to the dependency's symbol.
2. A failing test per claim kind: an `~example` in an Appendix runs and is
   reported with a distinct address.
3. Make `enrich` and `add_references_edges` walk the Appendix bodies the
   same way as `module.body`; fix claim collection if (2) shows it skips
   them.
4. Run the full suite; CHANGELOG under Fixed.
