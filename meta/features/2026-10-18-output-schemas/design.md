# Design note: a schema for every structured output

**Status:** policy adopted 2026-10-18 (in `DESIGN.md`, "What tools can
build on"); schema work below not started except where marked done.
**Origin:** Adam, while the `notlob test --json` shape was being fixed:
structured output should always have a schema, and notlob has several
outputs that grew organically without one.

## The rule

Every structured output meant for a program to read has a JSON Schema
under `notlob/schema/`. The schema is in the package data, is written out
by `notlob docs` (so an agent in another project can read it), and is
checked by a test that validates real output against it. Anything that may
change carries a `version` field.

## Inventory

| Output | Where | Schema | Notes |
|---|---|---|---|
| `notlob graph --format json` | `graph.py` `to_json` | **done**: `name_graph.json` | validated in `tests/test_graph_export.py` |
| `notlob test --json` | `cmd_test` | **done**: `test_result.json` | `version: 1`; `tests/test_cli_test_json.py` |
| `notlob check --json` | `cmd_check` | none | `{findings, counts}`; the finding shape is the one `test --json` `checks` uses, so share a definition |
| `notlob query children/imports/imported-by/callers/callees/references/referenced-by/search` | `cmd_query_*` | none | a JSON array of node summaries (`_node_dict`: `address`, `label`, `kind`, optional `start_line`) |
| `notlob query resolve` | `cmd_query_resolve` | none | one node summary, or `null` (exit 1) |
| `notlob query content` | `cmd_query_content` | none | a node summary plus `content` (`prose`, `code`, bullet count), or `null` (exit 1) |
| `~on-build` hook manifest | `_run_build_hook` | none | `artifacts`, `entry_points`, `externals`, `language`, `project_root`, `output_dir`; a contract hook scripts code against (pn-chomper's `inject-bundle.ts`), documented only in a docstring and `DESIGN.md` |
| `notlob graph --format turtle` | `graph.py` `to_turtle` | none | RDF; the vocabulary (`notlob:` classes and predicates) is built inline. A schema here means a vocabulary file, not JSON Schema |
| MCP tool results | `mcp_server.py` | n/a | they are the CLI JSON above, so they inherit the schemas; the tool `inputSchema`s are already JSON Schema, inline |

Outside the rule, deliberately:

- The Lark parse tree JSON (`parser.to_json`): the unstable tier.
- The runners' CLAIM/PASS/FAIL wire protocols: the unstable tier.
- Human-readable text output: for people; use the JSON.
- `package.json` / `tsconfig.json` written by `notlob init`: other
  tools' formats.

## Work

1. Schemas for the unspecified JSON outputs, each with a test that
   validates real output, in this order of use to a consumer: the hook
   manifest, `check --json` (shared finding definition with
   `test_result.json`), the `query` node summary and `query content`.
2. Decide whether the existing `check --json` and `query` shapes need
   changes or a `version` field now that they are specified (the
   `test --json` shape needed a breaking change; these may not).
3. **Done, 2026-10-18** (released together with the `test --json`
   change, Adam's call): `notlob docs` writes `schema/*.json` and
   `grammar.lark` to `notlob-docs/`, and `LANGUAGE.md` points at the
   written paths. A test fails if `LANGUAGE.md` names a schema file the
   dump does not write, or the source-tree path `notlob/schema/`.
4. A test that fails when a file is added to `notlob/schema/` but not to
   package-data (exists for `BINDING.md` and, in
   `tests/test_cli_test_json.py`, for schemas).
5. Optional: a vocabulary file for the Turtle export.

## The grammar

`grammar.lark` is the formal definition of `.lob` syntax, and an agent
without it has only prose to go on at the edges (the greedy claim body
is one example). It goes in the default `notlob docs` output, with a
header saying it is the syntax reference and that rule and terminal names
may change. `DESIGN.md`, `USER-AGENTS.md` stay `--full`. **Done.**
