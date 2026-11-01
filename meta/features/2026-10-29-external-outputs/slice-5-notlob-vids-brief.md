# Slice 5 brief: notlob-vids moves to the new outputs

**For:** the notlob-vids session. **Written by:** the design session,
2026-11-01. **Design:** `design.md` in this directory, "Slices", item 5.
After slice 4, at notlob 0f5b49b. notlob-vids is the first outside user:
Adam intends it to be a 0.6.0 user, compatible on release.

## Why

The code of notlob-vids is a program, so it reads JSON against a schema;
its agent is a reader, and can read the text. Every command now prints
text by default, so a call that parses stdout must ask for JSON.

## What changed in notlob

* **`--format` is the one flag:** `text|json`, plus `turtle` for `graph`.
  `--json` is gone with no alias: `notlob test --json` is an argument
  error.
* **`graph`, `query` and `test` print text by default.** `query resolve`
  is deprecated and unchanged.
* **The graph document** is `{version: 2, level, nodes, edges}`. `label`
  and `file` are on a `MODULE` only. There is no `end_line` and no
  `parent`. Nodes come in writing order; `CONTAINS` edges come first,
  then the cross-references.
* **`--level`:** at `outline`, the default, `edges` holds `CONTAINS`
  only. `USES`, `CITES`, `IMPORTS` and `USES_EXTERNAL` arrive at
  `--level index`.
* **`query` answers** keep `label` and `file` on every node; they stand
  alone.
* **`notlob -C <dir>`**, as `git -C`, sets the directory once.
* **Output is UTF-8,** with `ensure_ascii=False` in JSON.
* **The MCP tools** answer in text unless `format` says otherwise, and a
  tool's stderr comes back as a second text block.

## The change

1. **`teaser.lob`, `graph_beat`, lines 593 and 602,** read
   `nodes[a]["label"]`, a `KeyError` on render that claims do not catch.
   Take the name from the address: what follows the last `#` for a named
   node or a symbol, `label` for a module.
2. **Add a claim:** every lifted name is found in its own listing line.
3. **`encoding="utf-8"` on all four subprocess reads,** which decode as
   cp1252: `claim_results` and the query and search measures in
   `src/evidence.lob`, `load_graph` in `src/graph.lob`, and `split_states`'
   `notlob build`.
4. **`--format json`** on every `test`, `check`, `query` and `graph` call
   that parses stdout, and `--level index` where cross-reference edges
   are read.
5. **Read `start_line`.** Nothing reads `end_line` or `parent`.
6. **Palette:** update it only if the above needs it.

## Rules

* Change notlob-vids only. notlob is an input: do not patch your copy.
* A failure of notlob's goes in the report, not worked around.
* Failing claims first where a claim can see the fault. Adam handles
  source control: do not commit or stage.

## When you are done

Report: the claims and a real render; each read of notlob's output you
moved; what you could not move. The scope of 0.6.0 is frozen, so a new
finding goes on the list for after it unless it would break a schema
after release: say which of those each finding is.

As the alpha user, say also what the text forms were like for an agent:
`notlob graph`, `notlob graph --level index`, and the query lines.
