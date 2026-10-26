# Slice 8a brief: the `REFERENCES` edge becomes `CITES`

**For:** an implementing session. **Written by:** the design session,
2026-10-26. **Design:** `design.md` in this directory, D11 (decided
2026-10-26) and slice 8. After `6e54c9d`.

## Goal

The edge a prose `#Label` makes is called `REFERENCES`, which
contradicts the language's own `#References` heading: the lines under
that heading make `IMPORTS` edges, never `REFERENCES` ones. Adam: "it
*directly* contradicts the heading." The edge becomes `CITES`, as
`DESIGN.md` already says ("A *cites* B when A's prose mentions `#B`").
0.6.0 breaks the graph format already, so the rename goes in it.

A rename only. Nothing else about the edge changes: it still starts at
the paragraph that holds the reference, and still lifts to the section
at `outline`.

## What is renamed

* `EdgeKind.REFERENCES` to `EdgeKind.CITES`, and the `"REFERENCES"` it
  prints as, in every output.
* The Turtle property `notlob:references` to `notlob:cites`, in the
  emitter and `notlob.ttl`.
* The edge enums of `name_graph.json` and `query_result.json`, and any
  description there that names the edge.
* The queries: `notlob query references` to `cites`, `referenced-by` to
  `cited-by` (`cli.py`, `commands.py`), and `query children --kind`'s
  choices. The MCP server's tools, where they name the queries or the
  edge.
* The functions named after the edge: `add_references_edges`,
  `references_of`, `referenced_by` (to `add_cites_edges`, `cites_of`,
  `cited_by`, or names that read as plainly; one way).
* `LANGUAGE.md` and `DESIGN.md` where they name the edge or the two
  queries, and the CHANGELOG's Unreleased entries that do: the edge is
  `CITES` in the final difference from 0.5.4, not renamed in it.

## What is not renamed

* The `#References` heading, `REFERENCES_HEAD`, `ReferencesSection`, and
  everything else about the section: they are the section's names, and
  the next slice gives the section a node kind `REFERENCES`.
* The word "reference" for a prose `#Label` in the docs: it is the
  language's name for the syntax. Where the docs say what the syntax
  makes in the graph, they say a `CITES` edge.
* The `references` check (`check.py`, `check_result.json`) and the
  `<refs>` error tag. Their names are a separate question for Adam.

## Rules

* **May touch:** the files above and tests.
* **Must not touch:** the grammar, the parser, the model, the bindings,
  `check.py` beyond `EdgeKind.CITES`.
* **Assertions may change** only where they name the edge, the Turtle
  property or the two queries. Report each, old and new.
* **Failing test first:** that `EdgeKind` has `CITES` and no
  `REFERENCES`, that the ontology declares `notlob:cites`, and that
  `notlob query cites` and `cited-by` exist and `references` and
  `referenced-by` do not. Say that it failed.
* Do not commit or stage. 80-character lines. No slice wording. Plain
  `pytest` and `ruff` calls.

## When you are done

Report, without committing: every file changed; each assertion changed,
old and new; that the new test failed first; the full suite; a
line-length check; anything you stopped on.
