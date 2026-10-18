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
| `notlob check --json` | `cmd_check` | **done**: `check_result.json` (2026-10-18) | `version: 1` added (additive); the finding definition is duplicated, not `$ref`d, in `test_result.json` and a test keeps them identical (a cross-file `$ref` needs a resolver in every consumer, and the written schemas must each stand alone); `tests/test_cli_check_json.py`. Address collision: `check --json` now prints a valid document with a `names` finding, as `test --json` does (fixed with it; with no project it still prints nothing, documented in the schema) |
| `notlob query children/imports/imported-by/callers/callees/references/referenced-by/search` | `cmd_query_*` | **done**: `query_result.json` (2026-10-19), `NodeList` | node summaries (`address`, `label`, `kind`, optional `start_line`); `Node`/`Content` are identical to `name_graph.json`'s, kept so by a test; bare values, not versioned (wrapping them would break every consumer for little gain) |
| `notlob query resolve` | `cmd_query_resolve` | **done**: `NodeOrNull` | a node, or `null` with exit 1 |
| `notlob query content` | `cmd_query_content` | **done**: `NodeOrNull` | a node plus `content`, or `null` with exit 1. Writing its test found `name_graph.json` rejecting real output (a bullet list adds `bullet_block_count` to content): schema fixed, CHANGELOG notes it |
| `~on-build` hook manifest | `_run_build_hook` | **done**: `build_manifest.json` (2026-10-18) | `version: 1` added (additive); `tests/test_build_manifest.py` runs a real hook that saves the manifest and validates it. `DESIGN.md`'s example, which had no `entry_points`, is corrected |
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

## Turtle: ontology and namespace (decided 2026-10-18)

In scope under the rule above. Decisions:

- **Namespace is a `urn:`.** `to_turtle` has been emitting
  `https://notlob.dev/ns#` and a default `@base https://notlob.dev/project/`,
  a domain that nobody here controls. A URL namespace is a public identity
  and a long-term commitment to keep it meaningful; with no current users
  and no RDF focus on the roadmap, a `urn:` avoids both. The ontology
  therefore ships as a file (it cannot be fetched from its own IRI).
  Form: `urn:notlob:ns:` (terms such as `urn:notlob:ns:Module`), decided
  2026-10-18. `notlob` is not a registered URN namespace identifier
  (RFC 8141 expects IANA registration); for a self-contained vocabulary
  that is acceptable, rdflib treats it as any IRI, and **the ontology file
  says in a comment that this is an informal namespace**. The considered
  alternative was a `tag:` URI (RFC 4151) such as
  `tag:adamburkegh.github.io,2026:notlob:ns:`: more correct, but longer
  and it puts a GitHub name in every export. Switching later is a
  one-line change plus a CHANGELOG callout. Changing from the current
  `https://notlob.dev/ns#` is a breaking change to the Turtle output, to
  be called out in the CHANGELOG.
- **No default `@base`.** Project data does not belong in notlob's
  namespace. Emit `@base` only when the caller supplies one, so addresses
  stay relative to wherever the file is loaded. (`to_turtle` already takes
  `base`; check whether the CLI exposes it.)
- **Ontology file** `notlob/schema/notlob.ttl`: classes (one per
  `NodeKind`), datatype properties (`address`, `startLine`, `prose`,
  `code`, plus `rdfs:label`) and edge predicates (one per `EdgeKind`),
  each with label, comment, domain and range. Shipped in package data and
  written to `notlob-docs/schema/` by `notlob docs`.
- **Drift test:** the ontology's classes and predicates equal the
  `NodeKind` and `EdgeKind` names `to_turtle` can emit.
- **Validation with `rdflib`**, added to the `[dev]` extra beside
  `jsonschema` (test-only; notlob itself stays dependency-free here): parse
  real `to_turtle` output, with and without content. This is expected to
  find emitter bugs (characters illegal in an IRI, prose ending in a
  quote); fix what it finds as part of the work.
- **No SHACL / `pyshacl`** (decided 2026-10-18). The vocabulary is small
  (8 classes, 5 datatype properties, 5 edge predicates) and notlob's own
  emitter is the only producer, so shapes would add a dependency, a file
  and a drift test for little. The constraints that matter (each typed
  node has exactly one address and label; every edge endpoint is a typed
  node; no term outside the ontology) are a few `rdflib` assertions in a
  test. Revisit if an external consumer wants to validate exports.

## The grammar

`grammar.lark` is the formal definition of `.lob` syntax, and an agent
without it has only prose to go on at the edges (the greedy claim body
is one example). It goes in the default `notlob docs` output, with a
header saying it is the syntax reference and that rule and terminal names
may change. `DESIGN.md`, `USER-AGENTS.md` stay `--full`. **Done.**
