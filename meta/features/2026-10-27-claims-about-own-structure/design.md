# Bookmark: claims a project makes about its own structure

**Status:** bookmark (Adam, 2026-10-27). Not designed; not for 0.6.0.
**Origin:** the discussion of what `notlob query` and `notlob graph` are
for, after notlob-vids measured `query content`.

## The idea

A project may have good reason to state facts about its own structure
and have them checked: that each section has an example, that a code
sample in the prose is run, that the docs mention every command. Adam:
"When used correctly, it's not meta-wankery, it's theory consistency."

In most languages such a check has to parse the project's own source
crudely first. In a `.lob` project the parse already exists: the
name-graph is the parse tree with cross-references. A claim could read
it rather than re-derive it.

## Where it already happens

* **notlob's own tests.** `tests/test_language_md_currency.py` reads
  `grammar.lark` and `cli.py` and asserts that `LANGUAGE.md` mentions
  each sigil, declaration, command and check: a drift detector over
  notlob's own structure.
* **A Rust project** (Adam, 2026-10): a code sample in the docs was made
  a doc test, which needed a crude Markdown parse to find it. In a `.lob`
  file the sample is a claim or a code block already, and running it is
  what notlob does.
* **notlob-vids** writes claims over another project's graph: it reads
  `notlob graph` for pn-chomper, and its drift claim fails when the edge
  kinds change (as the `CITES` rename will make it do). It, or a later
  project, could make the same kind of claims about itself.

## How it is done today

A Python-bound `~property` (or `~example`) that runs `notlob graph` on
its own project and asserts over the JSON (Adam, 2026-10-27). A
quantified fact ("every section has an example") is naturally a
property. Since 0.6.0 a claim's `__file__` is its `.lob` path, so it can
find its project. A sketch, not run:

```
~property
    @given(st.sampled_from(sections()))
    def _(section):
        assert any(c["kind"] == "EXAMPLE"
                   for c in children(section))
```

with `sections()` and `children()` reading `notlob graph --level index`
(run with `subprocess` in the project root) in the module's code.

What it costs: `notlob` must be on the path of the interpreter the claims
run in; each claim (or module) runs the whole graph build again; it is
Python only; and the claim is written against the graph schema, so it
breaks on a schema change (which is the point of a drift claim, and the
cost of every other kind).

## What it would need

* **A way for a claim to read its own project's graph.** In-process
  (`import notlob`) only works where the claim runs in an interpreter
  that has notlob, which the Python binding's target interpreter need
  not, and never in Haskell or TypeScript. A language-neutral hand-off
  (the graph document at a path the claim is given) would serve every
  binding.
* **A stable surface to write such claims against.** That is the graph
  document and its schema, versioned (`version: 2`). Claims about
  structure make the schema a contract with the project itself, which
  raises the cost of every rename, as `CITES` shows for notlob-vids.
* **The claim's own address**, so a claim can say "my section" without
  writing its address out (`ClaimToRun` already carries it).

## Questions for when it is designed

* Is this plain `~example`/`~property` with an accessor, or something
  the language names?
* How does it sit beside `notlob check`? The checks are notlob's general
  structural claims; these would be a project's own, written in its own
  terms. Possibly the same mechanism, with notlob's checks as the
  built-in ones.
* Which width does a claim get by default: the narrow answer the queries
  give, or the full graph?
