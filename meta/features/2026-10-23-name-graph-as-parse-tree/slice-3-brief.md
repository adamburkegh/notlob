# Slice 3 brief: symbols by their lines, and `USES` at the right line

**For:** an implementing session. **Written by:** the design session,
2026-10-25. **Design:** `design.md` in this directory: sections 3 and 4,
and slice 3 in section 9. Read them first.

## Goal

Two things the graph gets wrong today, both about lines:

```
roman/numerals#to_roman       start_line 12   (its def is at 19)
to_roman USES NUMERALS        start_line 14   (the use is at 21)
example#1 USES to_roman       start_line 27   (the call is at 28)
roman/numerals#Tests#encoding  no USES at all  (it calls to_roman at 78)
```

1. **A symbol holds its lines, not a copy of its text.** The binding says
   which lines of its code block a symbol occupies; the node takes its
   real `start_line` and `end_line` from them, and its text is read from
   the leaf it is written in. Today every symbol's source is stored twice:
   in its `CODE` leaf and on the symbol.
2. **Every `USES` edge carries the real line of the call,** from every
   kind of node that holds code: symbols, claims, named tests, and the
   anonymous tests in `#Tests` (each run scanned on its own, dedented, so
   a group's calls are found at all).

## Rules

* **May touch:** `notlob/bindings/__init__.py` (`SymbolInfo`), the three
  `symbols.py` files (`extract_symbols` only), `notlob/graph.py`, and the
  tests named below.
* **Must not touch:** `model.py`, `check.py`, `commands.py`, the runners,
  the assemblers, `cli.py`, `mcp_server.py`, the schemas, the docs.
* **Must not change, and must pass:** `tests/test_check.py`, every
  `tests/test_cli_*.py`, `tests/test_address_collision.py`,
  `tests/test_graph_export.py`, `tests/test_turtle.py`, the accessor
  classes in `tests/test_graph.py`.
* **`tests/test_graph_layer.py` changes in one stated way only** (see
  "The printed graph").
* **May be rewritten** where they assert the in-memory structure or the
  old lines: `tests/test_graph_forest.py`, `tests/test_graph_symbols.py`,
  `tests/test_graph_property.py`, the rest of `tests/test_graph.py`, the
  bindings' symbol tests. Report each, old and new.
* **Failing test first;** say that you did. Do not commit or stage.
  80-character lines. No phase or slice wording in code or docstrings.

## 1. Symbol lines

`SymbolInfo` gains:

```python
@dataclass
class SymbolInfo:
    name:       str
    source:     str | None = None
    first_line: int | None = None    # 1-based, within the lines given
    last_line:  int | None = None    # the last non-blank line of it
```

All three `extract_symbols` set them; each already knows them:

* **Python:** `node.lineno` and `node.end_lineno`.
* **TypeScript:** its line loop; `last_line` is the last non-blank line
  of the declaration's block (its `source` is `rstrip`ped today).
* **Haskell:** its line loop. Equations of one name are merged only while
  they are contiguous (a blank line ends a definition), so a name defined
  again after a blank line comes out as a second `SymbolInfo` of the same
  name, and the last one wins, as today. Keep that; do not merge across.

Keep `source` as it is: other callers read only `name`, and a binding that
does not set the lines still works (below).

**In the graph**, a symbol node gets:

* `start_line` and `end_line`: the real lines. For a symbol in a `CODE`
  leaf, `leaf.start_line + first_line - 1` (the leaf's text is its lines,
  dedented, one for one). For a function in a `~property`, whose lines
  start the line after the sigil, `claim.start_line + first_line`.
* **no `text`.** A new accessor gives it:

```python
graph.text("roman/numerals#to_roman")
# -> lines 8-14 of roman/numerals#code#1's text (file lines 19-25)
```

`text(address)` returns a leaf's own text, a symbol's lines of the leaf
that holds it, and `None` for anything else. Everything that read a
symbol's `text` reads `graph.text()` instead (the layer, `add_uses_edges`).

**Fallback:** a binding that leaves `first_line` unset keeps today's
behaviour for its symbols: `text = info.source`, `start_line` the block's.
A test checks that the three built-in bindings never take it.

## 2. `USES` lines

`add_uses_edges` scans, for each node that holds code, a text whose first
line is a known file line, and puts on each edge `that line + (line in the
text - 1)`:

| Node | Text scanned | Its first line |
|---|---|---|
| `SYMBOL` | `graph.text()` | the symbol's `start_line` |
| `EXAMPLE`, `RUN`, `PROPERTY` | the claim's dedented lines, leading blank lines dropped | the first non-blank line after the sigil |
| a named `TEST` | its lines | the first non-blank line after the `~test` line |
| an anonymous `TEST` (a run) | its lines, dedented | its `start_line` |

`TEST_GROUP` and `TESTS` are no longer scanned: their tests are. So
`_group_code` and `_tests_code` leave `add_uses_edges`; if the layer still
needs them for printing a group's `code`, they stay there only.

## 3. The printed graph

The layer prints today's shape. Two kinds of value change, both fixes:

* a `SYMBOL` node's `start_line` (now its own line, not its block's);
* `USES` edges: their `start_line`, and the edges a test group now has
  (the layer lifts a `USES` edge from an anonymous test to its group, or
  to the `#Tests` node for one written directly in `#Tests`, keeping one
  edge per source and target, at the earliest line, as for references).

`tests/test_graph_layer.py` keeps comparing against the five snapshots,
**except** that it leaves out exactly those two things (symbol
`start_line` and the `USES` edges), and a new test checks them instead on
Roman against the lines in the file:

```
roman/numerals#NUMERALS   12-17      roman/numerals#to_roman   19-25
roman/numerals#from_roman 46-56
to_roman             USES NUMERALS      21
from_roman           USES NUMERALS      47
example#1            USES to_roman      28
example#2            USES to_roman      38
Decoding#example#1   USES from_roman    59
Round-Trip#property#1 USES from_roman, to_roman   71
Tests#encoding       USES to_roman      78
Tests#encoding#mcmxciv USES to_roman    93
Tests#decoding       USES from_roman    96
Tests#round-trip     USES from_roman, to_roman    101
```

(The design session read these from the file; check each, and say if one
is wrong.) Do not re-capture the snapshots: they are the record of the old
output.

The symbol's `content.code` in the printed graph must not change: the
text read by its lines must equal today's `source`, for every symbol in
every example project. Test that directly.

## Tests

1. **Each binding:** `first_line` and `last_line` on a block with several
   definitions, a multi-line one, a trailing blank line, and (Haskell) a
   signature with its equations and a name defined twice.
2. **Positions:** every symbol in every example has `start_line <=
   end_line`, both inside its `CODE` leaf (or `PROPERTY`), and its text
   by lines equals the binding's `source`.
3. **No stored copy:** in the graph after `enrich`, no `SYMBOL` node has
   `text` (with the built-in bindings).
4. **The fallback:** a fake extractor without lines gives today's node.
5. **`USES` lines:** the Roman table above; plus a claim with blank lines
   before its first assertion, a named test, a run after commentary (line
   right, as the runner bug in `meta/bugs/2026-10-25-tests-commentary-line-drift`
   is not), and a call on the second line of a symbol.

## When to stop

Stop and report if a protected test fails, if a symbol's text by its lines
cannot be made equal to today's `source` for an example, if a binding's
lines are not contiguous for one name in a way not described here, or if
the slice grows past this brief.

## When you are done

Report, without committing: the `SymbolInfo` change and a snippet of one
extractor; `graph.text`; the new `add_uses_edges` table as built; that
the new tests failed first; the full suite result; each rewritten test,
old and new; any Roman line above that was wrong; a line-length check;
anything you stopped on.
