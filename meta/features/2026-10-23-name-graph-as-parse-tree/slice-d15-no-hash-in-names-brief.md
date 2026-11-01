# Brief: a name is a terminal, and may not hold `#`

**For:** an implementing session. **Written by:** the design session,
2026-11-01. **Design:** D15 in `design.md`, option 1, by the grammar.
Adam, 2026-11-01: "0.6 is turning into an important milestone release
and I want # gone". Taken out of slice 2e for this; the
`assertion_block` stays in 2e, after the release. Replaces the first
version of this brief, which put the rule in the parser. Adam rejected
that: the grammar must say what a name is.

## Why

`#` is notlob's address separator and its reference sigil. A name that
holds one breaks the schema's rule for a label ("what follows the last
`#`"): `##Calling C# from Python` is `sharp#Calling C# from Python`, and
the rule says ` from Python`. It can take an ordinal's form: `~test
test#1` lands on the first anonymous test's address, and the last one
wins. And it can never be cited: `REF` allows no `#` in a label.

Underneath, a name does not exist in the grammar. It is what is left of
a line when `_STRIP_PREFIX` has trimmed it, or what `split` finds in
`~test <name>`. This change gives it one definition.

## The change

### The grammar

```
module:           _MOD_MARK NAME _EOL body post_text?
subheading:       _SUB_MARK NAME _EOL _sub_item*
claim:            SIGIL _body_line+
                | _PROPERTY_MARK NAME _EOL _body_line+
test_group:       _SUB_MARK NAME _EOL (INDENTED_LINE | ...)*
named_test:       _TEST_MARK NAME _EOL _body_line+
appendix_section: _APPENDIX_MARK NAME? _EOL body_item*

NAME: /[^#\s](?:[^#\n]*[^#\s])?/
_EOL: /[ \t]*\n/
_MOD_MARK.10: /#[ \t]*/
_SUB_MARK.10: /##[ \t]*/
_PROPERTY_MARK.10: /~property +/
_TEST_MARK.10: /~test +/
_APPENDIX_MARK.20: /#Appendix[ \t]*/
```

`SIGIL` keeps `~example`, the `~run` forms and bare `~property`.
`MOD_HEAD`, `SUBHEAD`, `TEST_SIGIL` and `APPENDIX_HEAD` go. This form was
run on real Lark over all 28 `.lob` files reachable from the repository
(`var/grammar_probe.py`, option `B2`): it refused every bad line below,
and every name came out as it does today. The model and the tests have
not been run on it.

The marker is a terminal and so outranks `REF` and the prose terminals
at column zero. Nothing changes in `REF`, `LINE_START_TEXT` or
`PROSE_TEXT`, and no `##` line can fall through to prose. Update the
comments in the file, including its header and the priorities note.

**A name has at least one character that is not a space.** Adam ruled on
this: a bare `##`, or `##` and spaces, is now an error, for a heading and
a test group. `#Appendix` alone stays legal: its name is optional.

### The parsing layer

Nothing past `model.py` changes: `Claim.sigil`, `AppendixSection.title`
and the rest keep their values.

* `parser.py`: `_STRIP_PREFIX` goes, and so does the marker stripping
  and its comments. The markers and `_EOL` start with `_`, so Lark keeps
  them out of the tree, and `NAME` is exact.
* `model.py`: `_module`, `_subheading` and `_test_group` go on reading
  `children[0]`, now the `NAME`. `_named_test` loses its `split`.
  `_claim` tells the two forms apart and gives `~property <name>` as
  `sigil`. `_appendix_section` gives the title as today: see
  `weave/markdown.py:234`, and report any case that differs
  (`#AppendixFoo`, say).

### The error

The grammar refuses. Lark's own words are poor, though:

```
Unexpected token Token('_MOD_MARK', '#') at line 5, column 12.
Expected one of: _EOL
```

So `parse` words it, and holds no rule: where Lark refuses a `#` after a
`NAME`, it raises what reads

```
sharp.lob:5: a name may not hold '#': 'Calling C# from Python'
```

with a file where there is one. If this takes more than a few lines, or
needs anything but Lark's error to go on, stop and say so. Other parse
errors stay as they are.

### A file that does not parse is an error

Adam ruled on this too. `build_package` skips a file that fails to parse
(`except Exception: continue`, `project.py:320`; also `pass` at `216`).
With the ban, that would turn a working file into a missing one and
leave `notlob test` green. In a project, a `.lob` file that fails to
parse now stops the command as an address collision does: nothing on
stdout, each failure on stderr as `ERROR  <parse>  <file>:<line>: ...`
where the line is known, and exit 1. Find how collisions reach each
command and use the same way. This covers `test`, `check`, `graph`,
`query`, `build` and `weave` over a project. Say if any command needs
something else, and if a schema's description of failure needs a word.

## Not names

`~external` values (D9, verbatim: a URL can have a fragment), a listing
in `#References`, prose, code, assertions, and the `#` in an anonymous
node's address. `_turtle_iri` still encodes later `#`s for those; only
its docstring stops saying a title can hold one.

## Rules

* **May touch:** `grammar.lark`, `parser.py`, `model.py`, `project.py`,
  `commands.py` (to report a file that does not parse), `graph.py` (that
  docstring), `util/gen_grammar_latex.py` and `util/gen_listings_lang.py`
  (their terminal lists), `LANGUAGE.md`, the CHANGELOG (Unreleased:
  breaking, both the ban and the error), the description of failure in a
  schema, tests.
* **Must not touch:** the shape of any schema, `Claim`, `AppendixSection`
  or any other model type, the graph, the bindings, `weave`, what any
  command prints but these errors.
* **Assertions may change** where a test names a terminal this removes,
  and where a test builds a name with a `#`
  (`tests/test_graph_forest.py:500-513`, `tests/test_turtle.py:249`).
  Report each, and what it held. A collision with no `#` in a name must
  still be tested. A test that relied on a bad file being skipped is
  more than that: report it.
* `tests/test_names_no_hash.py` is yours from the first brief: rework it.
* **Failing tests first;** say that you did. Do not commit or stage.
  80-character lines. No slice wording. One shell command per call; use
  `-C`, not `cd`. Plain `pytest` and `ruff` calls.

## Tests

1. Each of these is refused, the grammar alone doing it, and the error
   gives the line and the name: `##Calling C# from Python`, `###Notes`,
   `##g#2`, `##Trailing#`, `#Module#1`, `~property a#b`, `~test test#1`,
   a test group `##h#1`, `#Appendix C#` as a first and as a later
   appendix.
2. Bare `##` and `##` with spaces are refused, as heading and as group.
3. These are accepted, with these names: `##Notes`, `## Spaced`,
   `##Trailing  `, `##Two words  here` (the inner spaces kept), `~test
   total` with two spaces after `~test`, `~property total`, bare
   `~property`, `#Appendix`, `#Appendix A`.
4. Prose is as it was: `See ##Notes and #Other.`, `#Other` at column
   zero, `#5 and #lower`. `~external index.html#top`, a `#` in code and
   in an assertion are accepted.
5. Over every example, the parse gives the model it gave before: compare
   `from_tree` output against what is committed, and every graph
   document at `full`, unchanged.
6. Over every example, every named node's label holds no `#`, and the
   schema's rule gives it from the address.
7. In a project with one bad file: `test`, `check`, `graph`, `query`,
   `build` and `weave` exit 1, name the file and line, and print nothing
   to stdout. With no bad file they answer as before.
8. `gen_grammar_latex` and `gen_listings_lang` still run, and the
   grammar printed for the paper shows `NAME`.

## When to stop

Stop and report if any `.lob` file in the repository is refused, if any
downstream value changes, if a tool for the paper cannot show the new
form, or if this grows past the brief.

## When you are done

Report: the error as printed, in one file and in a project; the
assertions changed; that the new tests failed first; the full suite; a
line-length check; anything you stopped on.
