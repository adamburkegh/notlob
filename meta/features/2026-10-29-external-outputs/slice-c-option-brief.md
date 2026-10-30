# Slice brief: `notlob -C <dir>`

**For:** an implementing session. **Written by:** the design session,
2026-10-30. **Decision:** Adam, 2026-10-30: "Let's use -C ... do this
first as it is slowing down our own work." Design note: `design.md` in
this directory, decision 11.

## Why

Every command that works on a project finds it from the current
directory. To ask anything of `examples/retail` from the repository
root, a person or an agent has to `cd` first; our own sessions do not
`cd`, so they cannot run notlob on the examples at all. `git -C <dir>`
is the familiar answer.

## The change

A global option, before the command:

```
notlob -C examples/retail query search discount
notlob -C examples/gutenberg test
notlob -C examples/roman mcp
```

It means what `git -C` means: run as if notlob had been started in
`<dir>`. Implement it once, in `cli.main()`, before the command is
dispatched (changing the working directory is the simplest faithful
form); no command gains its own option. A path argument given after it
(`notlob -C examples/retail test pricing/discounts.lob`) is then
relative to `<dir>`, as in git. A `<dir>` that does not exist or is not
a directory is an error, `ERROR  <cli>  ...` on stderr, exit 1, before
any command runs. One `-C`; repeating it is not supported (say so in the
help, or reject it; your choice, reported).

The MCP server started with `-C` serves that project, as every other
command does.

## Rules

* **May touch:** `notlob/cli.py`, the docs that list the global options
  (`LANGUAGE.md`, `USER-AGENTS.md`, if they do), the CHANGELOG
  (Unreleased, Added), tests.
* **Must not touch:** any command's own options or output, the graph,
  the bindings, the MCP tool definitions.
* No assertion changes. **Failing test first;** say that you did. Do not
  commit or stage. 80-character lines. Plain `pytest` and `ruff` calls.

## Tests

Run notlob as a subprocess from the repository root:

1. `notlob -C examples/retail query search discount` gives the same
   output and exit code as the same query run with `cwd` set to
   `examples/retail`.
2. `notlob -C examples/retail test pricing/discounts.lob` passes, the
   path read relative to `<dir>`.
3. A missing directory and a file given as `<dir>`: the error on
   stderr, nothing on stdout, exit 1.
4. Without `-C`, nothing changes (the existing suite).

## When you are done

Report: the change, the tests and how they failed first, the full
suite, a line-length check, anything you stopped on.
