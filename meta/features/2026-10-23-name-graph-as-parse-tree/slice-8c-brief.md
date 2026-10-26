# Slice 8c brief: `query content` answers with the source

**For:** an implementing session. **Written by:** the design session,
2026-10-27. **Design:** this brief; the decision was taken with Adam on
2026-10-26/27 after measurements from notlob-vids and kamtrinia (below).
After 8b.

## Why

`notlob query content <address>` prints the subtree as a graph document
at `full`: every node with all its fields, every `CONTAINS` edge, and the
text. notlob-vids measured it on pn-chomper:

| | characters |
|---|---|
| `query content "petri/marking#Enabling and Firing"` now | 18,839 |
| the same query in 0.5.4 (prose and code only, no claims) | 2,597 |
| the section's own text | 3,763 |
| the whole file `petri/marking.lob` | 7,170 |

Asking for one section costs 2.6 times reading the module. kamtrinia's
agent never used `notlob query` at all: it read files and acted on the
`file:line` that `notlob test` and `check` print. Asked what it would
want, it said "the section as written in the .lob, with its file path
and starting line, because every change I make is an edit to that
text", and JSON "for a separate graph or edges command, where the
structure is the answer".

Adam: the problem is width, not compactness: "we may need a full graph
for our internal purposes but we shouldn't serialise all of it by
default for our external consumers"; and "text is better for humans,
JSON for machines, mostly". `notlob query` answers a question about one
thing; `notlob graph` is the export. `USER-AGENTS.md`, which notlob
ships to agents, already says `query content` will "show source at an
address".

## What it prints

```
notlob query content <address>                 # text (the default)
notlob query content <address> --format json   # [--depth N]
```

**Text:** a header line, the address and the span, then the node's own
lines from its file, as written, from `start_line` to `end_line`:

```
petri/marking#Enabling and Firing  petri/marking.lob:41-98
##Enabling and Firing

A transition is enabled when ...
```

The `.lob` syntax carries the kinds (a heading, an indented code block, a
sigil), so nothing else is added: no markers, no addresses of what is
inside (they are derivable from what is written). The lines are read from
the file at the node's `file` under the project root. A module prints
its whole file. A node with no file or lines (an `EXTERNAL`) and an
unknown address print `ERROR  <query>  ...` to stderr, nothing to
stdout, and exit 1. `--depth` is for JSON only; given with text it is an
error that says so.

**JSON:** the subtree, nested, narrow. Each node has `address`, `kind`,
`start_line`, `"named": true` when named, its facts when set (`mode`,
`declares`, `value`), `text` when it holds text, and `children` when it
has any. The root also has `file` and `end_line`. No edges (nesting is
the containment; the cross-references are the other queries'), no
`label` (the address carries it), no `size`, no `refs` (they are written
in the text), no `file` on every node. `--depth` limits the nesting as
now. An unknown address prints `null` and exits 1, as now.

## Rules

* **May touch:** `notlob/commands.py` (`cmd_query_content`), `cli.py`
  (its options), `graph.py` (`subtree` is replaced by what the two forms
  need; it has no other caller), `mcp_server.py`
  (`notlob_query_content`: a `format` argument, text by default, since
  its caller is an agent; `depth` with JSON), `query_result.json`
  (`SubtreeOrNull` becomes the nested content shape, recursive, or
  null), `LANGUAGE.md` (line 531), `USER-AGENTS.md` (if it needs a word),
  the CHANGELOG's Unreleased `query content` entries, tests.
* **Must not touch:** `notlob graph` and its document, the other
  queries, the model, the grammar, the bindings.
* **Assertions may change** only in the tests of `query content` and of
  `subtree` (`tests/test_cli_query_json.py`, `tests/test_cli_graph.py`,
  the `subtree` tests). Report each, old and new.
* **Failing test first;** say that you did. Do not commit or stage.
  80-character lines. No slice wording. Plain `pytest` and `ruff` calls.

## Tests

1. Text: for a section, a symbol, a claim and a module of the roman
   example, the output is the header and exactly the file's lines
   `start_line` to `end_line`.
2. **The claim the teaser makes, executable:** for every section of
   every example project, the text answer is no longer than the
   section's lines plus the header line, and shorter than its file.
3. JSON: validates against `query_result.json`; nested as the graph's
   `CONTAINS` says; no edges, labels, sizes or refs; each leaf's text
   once; `--depth` limits it.
4. The errors: unknown address, `EXTERNAL`, `--depth` with text.
5. The MCP tool: text by default, JSON on request.

## When to stop

Stop and report if a node's lines do not match its text in the graph
(that would be a span bug, not a formatting one), if another command
reads `subtree`, or if the slice grows past this brief.

## When you are done

Report, without committing: the text and JSON answers for
`roman/numerals#Decoding`, with their lengths and the file's; each
assertion changed, old and new; that the new tests failed first; the
full suite; a line-length check; anything you stopped on.
