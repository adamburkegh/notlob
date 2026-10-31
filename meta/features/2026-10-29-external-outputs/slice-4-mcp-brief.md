# Slice 4 brief: the MCP server is a thin layer

**For:** an implementing session. **Written by:** the design session,
2026-10-31. **Design:** `design.md` in this directory, decision 7; Adam,
2026-10-30: "The MCP should just be a thin layer over the cmd line
tools." After slice 3.

## Why

The MCP tools have drifted from the commands. `notlob_test` and
`notlob_check` force JSON on an agent, which is a reader. Half the
queries are not offered. Descriptions still say "Export ... as JSON"
and "Returns structured results". The server reports version `"0.3"`.

## The change

1. **Every query is a tool:** add `notlob_query_callers`, `_callees`,
   `_cites`, `_cited_by`. `query resolve` is deprecated and stays
   unoffered.
2. **A tool has its command's defaults:** `test`, `check` and `graph`
   answer in text unless asked. Every tool takes `format`, the choices
   its command has (`text`, `json`; `turtle` for `notlob_graph`), and
   passes it on. `notlob_graph` keeps `level`.
3. **One home for the mapping.** Today `_dispatch` is an if-chain beside
   the `TOOLS` table. Keep what is simplest, but a tool must not be able
   to list an argument its command does not take; a test holds each
   tool to its command's options in `cli.py`.
4. **Descriptions say what comes back:** text, one line a node, and
   `format` for JSON. `notlob_graph` says `outline` is the default and
   `level` `index` adds `uses`, `cites` and `imports`.
5. **The server's version is notlob's,** `__version__`, not `"0.3"`.
6. **A tool loses nothing its command says.** Added in review, on Adam's
   ruling, 2026-10-31: most failures say why on stderr, and the server
   took only stdout, so a client got `""` and `isError: true`. A result
   is stdout, then stderr as a second text block when there is any, so
   `format: json` still answers `null`, parseable, in the first block.
   With nothing on stdout, stderr is the only block.

## Rules

* **May touch:** `notlob/mcp_server.py`, `USER-AGENTS.md` and
  `LANGUAGE.md` where they describe the tools, the CHANGELOG (Unreleased:
  breaking, the tools answer in text; ask for `format: json`), tests.
* **Must not touch:** what the commands print, the graph, the bindings.
* **Assertions may change** in MCP tests, for text and for `format`.
  Report the kinds of change, and each that is more than that.
* **Failing tests first;** say that you did. Do not commit or stage.
  80-character lines. No slice wording. One shell command per call; use
  `-C`, not `cd`. Plain `pytest` and `ruff` calls.

## Tests

1. Each tool's default answer equals its command's stdout, over an
   example, through the server.
2. `format: json` equals the command's `--format json`.
3. Every query but `resolve` has a tool, and every tool's arguments are
   options its command takes.
4. `serverInfo.version` is `notlob.__version__`.

## When to stop

Stop and report if a tool needs something its command cannot do, or if
the slice grows past this brief.

## When you are done

Report: the tool list; the kinds of assertion changed; that the new
tests failed first; the full suite; a line-length check; anything you
stopped on.
