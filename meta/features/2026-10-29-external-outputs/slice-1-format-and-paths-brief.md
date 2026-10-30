# Slice 1 brief: one `--format` flag, one path convention

**For:** an implementing session. **Written by:** the design session,
2026-10-30. **Design:** `design.md` in this directory, decisions 5
and 10; Adam, 2026-10-30.

## Why

Two flags do one job: `test` and `check` take `--json`; `graph` and
`query content` take `--format json`. And `file:line` means two things:
`notlob test` prints `discounts.lob:15`, which cannot be followed from
the project root; `query content` prints `pricing/discounts.lob:40-60`.
Run in `examples/retail` today:

```
PASS   discounts.lob:15  pricing/discounts#example#1  apply_discount(...)
PASS   discounts.lob:27  pricing/discounts#Stacking Discounts#example#1  (apply_discount(Decimal('0.8'),
apply_discount(Decimal('0.9'), Decimal('100')))
== Decimal('72'))
```

That second entry also shows a claim written over several lines breaking
the one-line format.

## The change

1. **`--format text|json` on `test` and `check`,** default `text`, as on
   `query content`. `--json` is removed, with no alias (Adam: "let's
   kill --json"). `notlob test --json` is then an argparse error. The
   command functions' `json_mode` parameter becomes whatever keeps them
   simple; the JSON itself does not change. `mcp_server.py` keeps
   asking for JSON for now, by the new spelling (slice 4 changes that).
2. **Every `file:line` notlob prints is relative to the project root,**
   with `/` separators: `pricing/discounts.lob:15`, in `test`, `check`,
   `lint` findings, and any other human-readable line with a file in
   it. Outside a project (a lone `.lob` file with no `binding.lob`), the
   path as given. The JSON outputs are in scope if they carry a bare
   file name: report each you change, old and new; they must validate
   against their schemas.
3. **A claim's line stays one line.** The text `test` prints for a claim
   written over several lines is joined with single spaces:

   ```
   PASS   pricing/discounts.lob:27  pricing/discounts#Stacking Discounts#example#1  (apply_discount(Decimal('0.8'), apply_discount(Decimal('0.9'), Decimal('100'))) == Decimal('72'))
   ```

   Only the printing changes; what runs and the JSON do not.

## Rules

* **May touch:** `notlob/cli.py`, `notlob/commands.py`, `notlob/mcp_server.py`
  (the call only), where the runners' results are formatted for
  printing, `LANGUAGE.md` and `USER-AGENTS.md` where they show the flag
  or the line, the CHANGELOG (Unreleased: the removal of `--json` is
  breaking; say what to write instead), tests.
* **Must not touch:** the graph, the query answers (slice 2), the
  grammar, what the bindings run.
* **Assertions may change** only where they pin `--json` or a bare file
  name or a multi-line claim's printing. Report each, old and new.
* **Failing tests first;** say that you did. Do not commit or stage.
  80-character lines. No slice wording. Plain `pytest` and `ruff` calls.
* 8f's work is uncommitted in the tree; leave it as it is.

## Tests

1. `test` and `check` with `--format json` give what `--json` gave;
   `--format text` and no flag give today's text but for rules 2 and 3;
   `--json` is rejected.
2. Over every example project, each file named in a `test` and a `check`
   line exists relative to the project root.
3. No line of `test`'s text output for an example project lacks its
   `PASS`/`FAIL` start: nothing runs on to a second line.
4. A lone `.lob` outside a project still prints.

## When to stop

Stop and report if a binding builds the printed line itself, so that rule
2 or 3 would mean changing all three bindings differently, or if the
slice grows past this brief.

## When you are done

Report: each output changed; each assertion changed, old and new; that
the new tests failed first; the full suite; a line-length check;
anything you stopped on.
