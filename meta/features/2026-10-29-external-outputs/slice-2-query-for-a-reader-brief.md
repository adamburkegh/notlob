# Slice 2 brief: `query` answers a reader

**For:** an implementing session. **Written by:** the design session,
2026-10-30. **Design:** `design.md` in this directory, decisions 1, 2,
3 and 12; Adam, 2026-10-30. After slice 1.

## Why

Nine of the ten queries answer a reader in JSON, five lines and more a
node, and `callers` gives where a caller starts, not where it calls.
`query content` moved to text in 8c. This does the rest.

## The change

**Every query but `resolve` takes `--format text|json`, default
`text`.** The JSON is what it is today. `query content` already does
this and does not change.

**A text answer that lists nodes is one line a node, three columns,**
aligned within the answer:

```
~example   pricing/discounts#example#1                      pricing/discounts.lob:15
~example   pricing/discounts#Stacking Discounts#example#1   pricing/discounts.lob:27
~property  pricing/discounts#Stacking Discounts#property#1  pricing/discounts.lob:43
```

1. **The sigil,** blank for what has none. `~example`, `~property`,
   `~run`, and `~test` for a test named by one; a run of bare assertions
   has none in its file, so none here. Headings and symbols are blank.
   Give the sigil one home: a fact in `KINDS`, not a table in the
   printer.
2. **The address,** as the next query takes it.
3. **Where,** `file:line`, relative to the project root:
   * `callers`, `callees`, `cites`, `cited-by`, `imports`, `imported-by`
     follow an edge, so it is where the edge is written: the file of the
     edge's source and the edge's `start_line`. `callees
     gutenberg/hamlet#report` gives `gutenberg/hamlet.lob:47`, the use of
     `WORDS`, not where `WORDS` is defined. An edge with no line gives
     the source node's start.
   * `search` and `children`: where the node starts.
   * A node with no file (an `EXTERNAL`): the column is blank.

Blank columns stay aligned; trailing spaces are stripped.

An empty list prints nothing, exit 0, as `[]` does today. An unknown
address prints `ERROR  <query>  ...` to stderr, nothing to stdout, exit
1, as `query content` does; JSON stays `null`, exit 1.

**`query resolve` is deprecated** (Adam, 2026-10-30: "deprecate ... and
see how use evolves from here"). It is undocumented, unoffered over MCP,
and answers `null` for most names. It stays as it is: same options, same
JSON, no `--format`. It prints one line to stderr, `DEPRECATED  <query>
query resolve will be removed; use query search`, and a CHANGELOG entry
under Deprecated says so. Do not change `NameGraph.resolve`, which
builds `CITES`.

**The MCP query tools follow the commands:** they call with no format,
so they answer in text. (Slice 4 finishes the MCP server.)

## Rules

* **May touch:** `notlob/commands.py`, `notlob/cli.py`, `notlob/graph.py`
  (`KINDS`), `notlob/mcp_server.py` only as far as above,
  `schema/query_result.json` (a line saying this is the `--format json`
  form), `LANGUAGE.md`, `USER-AGENTS.md`, the
  CHANGELOG (Unreleased: breaking, say what to add for a program), tests.
* **Must not touch:** `notlob graph`, `NameGraph.resolve`, the bindings,
  the grammar, `query content`.
* **Assertions may change** in tests of query output and MCP query
  tools: most will gain `--format json`. Report the kinds of change, and
  each one that is more than that.
* **Failing tests first;** say that you did. Do not commit or stage.
  80-character lines. No slice wording. Plain `pytest` and `ruff` calls.

## Tests

Over the examples, with `-C`:

1. Each query's text answer on retail and gutenberg, exactly, as above,
   including `callees gutenberg/hamlet#report` at lines 47 and 55,
   `imports gutenberg/hamlet` at `gutenberg/hamlet.lob:87`, and `callers
   pricing/discounts#apply_discount` at 15, 27, 43, 51 and 62.
2. For every edge query over every example, each printed line of each
   file holds the name of the thing the edge reaches: the line is real,
   not just a number.
3. `--format json` gives what the query gave before this slice, and
   validates against `query_result.json`.
4. `resolve`: stdout and exit code as before; the deprecation line on
   stderr.
5. Every sigil printed is one the file has at that line, for a claim or
   a test.

## When to stop

Stop and report if an edge has no `start_line` where this brief expects
one, or if the slice grows past this brief.

## When you are done

Report: the answers for test 1, as printed; the kinds of assertion
changed, and any that is more than a flag; that the new tests failed
first; the full suite; a line-length check; anything you stopped on.
