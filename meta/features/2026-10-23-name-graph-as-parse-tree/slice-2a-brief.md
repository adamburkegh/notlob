# Slice 2a brief: positions on every element of the model

**For:** an implementing session. **Written by:** the design session,
2026-10-24. **Design:** `design.md` in this directory, sections 2 and 4,
and slice 2a in section 9.

## Goal

The name-graph design gives every node its first and last line. The
model it will be built from (`notlob/model.py`) records a `start_line` on
most elements and an `end_line` on none, and records no position at all
for a prose paragraph, the `#Tests` section, the `#References` section,
the `#Binding` section or an `#Appendix`. Make every element of the model
carry both. Nothing reads the new fields yet; that comes in later slices.

## Rules

* **Touch only `notlob/model.py` and `tests/test_model.py`.** Not
  `graph.py`, not any consumer, not `grammar.lark` or `parser.py`. If a
  position cannot be had without a change outside these two files, stop
  and report: do not work around the grammar in Python.
* **Additive only.** New fields have defaults (`None`), existing fields
  and their values do not change, and no existing test changes. The full
  suite must pass afterwards.
* **Failing test first.** Write the tests below, run them, and confirm
  they fail for the right reason (missing attribute or wrong value)
  before changing `model.py`. Say in your report that you did.
* **Do not commit or stage.** Adam handles source control.
* 80-character lines; match the file's style (dataclass field
  alignment, docstring density).
* Do not put phase or slice wording in code comments or docstrings: the
  fields describe the model, not the plan.

## What a position means

* `start_line` and `end_line` are 1-based lines of the `.lob` file, both
  inclusive.
* `end_line` is the **last non-blank line** of the element. Trailing
  blank lines inside a block (the grammar keeps them as `BLANK` children)
  do not count.
* Take lines from the `line` of the first and last non-blank token. Every
  line-level token is a single line, so this avoids depending on Lark's
  `end_line`, whose value depends on whether the token's newline was
  stripped.
* A section (module, subheading, `#Tests`, test group, `#Appendix`,
  `#References`, `#Binding`) starts at its heading line and ends at the
  last non-blank line of its last item, or at its heading line if it has
  none.
* A module ends at the last non-blank line of the file (post-text
  included: the `#Tests`, `#Appendix` and other sections are the
  module's).

## The fields

| Class | Has now | Add |
|---|---|---|
| `ProseBlock` | nothing | `start_line`, `end_line` |
| `CodeBlock`, `Claim`, `BulletBlock`, `NamedTest` | `start_line` | `end_line` |
| `Subheading`, `TestGroup`, `Module` | `start_line` | `end_line` |
| `TestsSection`, `ReferencesSection`, `BindingSection`, `AppendixSection` | nothing | `start_line`, `end_line` |

`Ref` stays as it is (a reference is on one line). The per-line positions
that exist (`TestsSection.line_offsets`, `TestGroup.line_offsets`,
`ReferencesSection.line_numbers`, `BindingSection.external_lines`,
`on_build_line`) stay as they are.

## The tests

In `tests/test_model.py`, in its style (source strings parsed in the
test, no fixture files):

1. **Per class:** for each class in the table, a small source and the
   expected `start_line` and `end_line`, including a block with trailing
   blank lines and a section with no items.
2. **The Roman example, end to end.** `examples/roman/roman/numerals.lob`
   is real and stable; read it in the test and assert these, which the
   design session checked against the file:

   | Element | Lines |
   |---|---|
   | the module | 1-105 |
   | prose paragraphs in the body | 3-6, 8-10, 32-35 |
   | the first code block | 12-25 |
   | `~example` claims in the body | 27-30, 37-38 |
   | `##Decoding` | 40-60 (prose 42-44, code 46-56, claim 58-60) |
   | `##Round-Trip` | 62-71 (prose 64-66, claim 68-71) |
   | `#Tests` | 75-103 |
   | group `encoding` | 77-93 (its prose 88-90, `~test mcmxciv` 92-93) |
   | groups `decoding`, `round-trip` | 95-98, 100-103 |
   | `#References` | 105-105 |

3. **An invariant over every example project.** For every `.lob` file
   under `examples/`, every element has `start_line <= end_line`; the
   items of a body (and of a test group) are in order and do not
   overlap; and each item lies within its section. This is the test that
   catches an element someone forgets.

## When you are done

Stop and report, without committing:

1. The fields added, with a two-line snippet of one class as changed.
2. That the new tests failed first, and why; then the full suite result
   (`notlobenv/Scripts/pytest`, run through Bash).
3. A line-length check on both files.
4. Anything you stopped on, and anything outside the two files you think
   needs changing, with the passage that made you think so.

The design session reviews the diff against this brief before it goes to
Adam.
