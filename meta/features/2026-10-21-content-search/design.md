# Design note: search the content of the name-graph, with local context

**Status:** proposal, queued (not started)
**Origin:** Adam, 2026-10-21, seeing a graph-reading example in `DESIGN.md`:
a search with local context, "a bit like certain diff options that give
you the unchanged lines before and after" (grep's `-A`/`-B`/`-C`).
**Tier:** a new machine-readable output, so stable tier: it needs a
schema and a `version` (`DESIGN.md`, "Structured output has a schema").

## Summary

Today `notlob query search <pattern>` matches node **labels** only
(`NameGraph.search`: fnmatch on `node.label`). It cannot find a word in
prose or in code, and it returns node summaries, so there is nothing to
put context around. Add a content search that matches the text of body
items, and an option to return each match with the items around it.

## Why now

The name-graph holds each body as an ordered list of items (prose, code,
bullets, claims) with source positions (`NameGraph.body`, added with the
completeness fix, `2026-10-20-name-graph-incomplete`). Before that a node
had only two separate concatenations of its prose and code, with the order
lost, so "the item before this one" had no answer. Now it is a list slice.
That also serves the paper's context-window argument: an agent that finds
a match wants the surrounding paragraph and the function it explains, not
the whole file.

## What it would do

* **Content search:** match a pattern against the text of body items
  (prose text, code text, bullet items, claim source) across the project,
  and report, for each match, the node that holds it (`address`), the
  item's index in that body, its kind and its source line.
* **With local context** (`--context N`, or `-C N` by analogy with grep):
  also return the N body items before and after the match, in the same
  body, in document order. Context never crosses into another node's body,
  as grep's does not cross files.
* **With graph neighbours** (optional, e.g. `--neighbours`): the two
  adjacencies in one result. File-adjacency is the context above;
  concept-adjacency is the match's edges: the symbol it defines, what uses
  or references it, what it references. A prose match shows the nodes it
  cross-references; a code match shows the symbol and its callers.
* The same query through the MCP server, since agents are the main reader.

## Decisions needed (Adam)

1. **The unit of context:** body items (a paragraph, a code block, a
   claim) or source lines. Items are what the graph holds and are the
   natural boundary; lines would need the text split back out. Leaning to
   items, with `start_line` on each so a caller can ask for lines.
2. **What counts as a match, and how it is shown:** substring by default
   with a regex option? Case sensitivity (label search is case-sensitive;
   prose search probably should not be)? Matching inside a claim or a
   symbol: report the claim's or symbol's node, with the matching lines.
3. **Whether neighbours are on by default.** They cost size and the
   caller often does not want them.
4. **Output shape and where it lives.** A new JSON Schema
   (`notlob/schema/content_search.json`) with a `version`, separate from
   `query_result.json` (whose outputs are bare node arrays). A match is
   roughly `{address, kind, index, start_line, item, before: [...],
   after: [...], neighbours?: {...}}`.
5. **Filters:** by item kind (`prose`, `code`, `claim`), by node kind, by
   module. Reuse the existing `--kind` idea for nodes.

## Dependencies and limits

* Needs the bodies in the graph. Done for modules, subheadings and
  appendices. **`#Tests` content is not in the graph's bodies yet** (the
  open part of the completeness bug), so it would not be searchable until
  that is done.
* Tied to the graph, not the files, so it sees the same things the checks
  do, the Appendix included.
* Not a replacement for a text-search tool over the repository. The point
  is search that returns structure: the node, its place, its neighbours.

## Tests (when built)

An oracle in the style of `tests/test_graph_body.py`: for a small project
with known prose, code and claims, every match and its before/after items
equal what a plain walk of the parse tree says; context stops at the edge
of a body; the output validates against its schema.
