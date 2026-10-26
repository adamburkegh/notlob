# Slice 8d brief: notlob writes UTF-8, and JSON stops escaping

**For:** an implementing session. **Written by:** the design session,
2026-10-27. **Decision:** Adam, 2026-10-27: escaping non-ASCII exists
only for "bad windows default codepages". After 8c.

## Why

Every JSON output escapes non-ASCII (`—` for an em dash): longer,
harder to read, and only there because a console might not take UTF-8.
And notlob never sets its own output encoding (it sets
`PYTHONIOENCODING` only for the child interpreters it runs), so on
Windows, piped or redirected output is written in the system codepage
(cp1252). The text answer of `query content` prints an em dash only
because cp1252 has one: prose in CJK, Greek or Arabic, which the
reference syntax supports, would raise `UnicodeEncodeError` when piped.

## The change

1. **notlob's output is UTF-8.** Reconfigure `sys.stdout` and
   `sys.stderr` to UTF-8 once, where the CLI starts (`cli.py`'s main)
   and where the MCP server starts (it talks JSON-RPC over stdio). Not
   per command.
2. **JSON is written as UTF-8 text:** `ensure_ascii=False` in every
   JSON output notlob prints or writes: `notlob graph`, every `query`,
   `check --json`, `test --json`, the build manifest, `parser.py`'s
   tree dump, and the MCP server's responses. Not the TypeScript
   runner's `json.dumps` calls, which build TypeScript string literals
   inside generated code, not output.

No flag to escape non-ASCII. If a real consumer needs escaped output, a
non-default flag can be added then (Adam, 2026-10-27); not
pre-emptively.

## Rules

* **May touch:** `cli.py`, `mcp_server.py`, `commands.py`, `graph.py`,
  `parser.py` (their `json.dumps` calls), the CHANGELOG (one entry under
  Changed: output is UTF-8 on every platform, JSON no longer escapes
  non-ASCII; a consumer that decoded piped output in a legacy codepage
  must read UTF-8), tests.
* **Must not touch:** the bindings' generated code.
* No assertion changes, except one that pinned an escape sequence.
  Report each.
* **Failing test first:** a module whose prose holds CJK and an em dash;
  `notlob query content` (text) and `notlob graph --format json`, run
  as a subprocess with `PYTHONIOENCODING` unset and output captured as
  bytes, give valid UTF-8 containing the characters themselves, not
  escapes, and exit 0. Say that it failed (on this machine the text
  case should raise today when piped).
* Do not commit or stage. 80-character lines. Plain `pytest` and `ruff`.

## When you are done

Report: each output changed; the test, and how it failed first; the full
suite; anything you stopped on.
