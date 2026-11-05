# Slice 11b brief: the tree is the text, the model is the meaning

**For:** the implementing session. **Written by:** the design session,
2026-11-06, after slice 11. **Design:** "The parse tree is the whole
source" in `notlob/docs/DESIGN.md`. Same rules as slice 11: the grammar
is Adam's and is not edited; stop and propose rather than work round it;
comments only for what the code cannot show.

## Why

Adam: "Sometimes we need the token text and sometimes we need
getName() == "Discount Rate" ... Seems like an underrealised model /
view design." Three things mix the two:

* `parser._normalize` rewrites token values in place ("to match
  pre-refactor shape"), so a line token's value is not its text.
* `Claim.sigil` packs kind, mode and name into one string (`"~run
  on-load"`, `"~property total"`) that `graph.py` splits again.
* `AppendixSection.title` is the source text (`"#Appendix Notes"`)
  beside `name`; nothing reads it.

`weave` drops a `~run` by `claim.sigil == "~run"`, so only a bare one:
a `~run on-load` is woven as `**Run on-load:**` and a bare one not at
all. Adam has ruled that a `~run` is documentation: every one is woven.

## The change

1. **The tree is the text.** `_normalize` and `_LINE_TOKEN_TYPES` go:
   `parse` returns the tree as Lark built it. `model.py` is the one place
   a token becomes a value, and takes the newline off a line where it
   reads one.
2. **A claim is its meaning.** `Claim.sigil` goes. A claim has `kind`,
   one of a closed set stated once in `model.py` (example, run,
   property); `mode`, a `~run`'s mode as written (`on-load`,
   `on-invocation`), `None` when bare; and `name`, a property's name or
   `None`. `graph.py` reads the fields (`_claim_identity`, `_run_mode`),
   and `weave` labels a claim from its kind and name. **`weave` writes
   every `~run`** (Adam, 2026-11-06: "Let's please include ~run in the
   documentation"), labelled as a claim is: `**Run:**`, `**Run
   on-load:**`, `**Run on-invocation:**`.
3. **`AppendixSection.title` goes.** `name` stays.
4. CHANGELOG, in the library callers' entry: `Claim.sigil` and
   `AppendixSection.title` are gone, and what replaces them; the parse
   tree's token values are now the source text. Under weave: every
   `~run` is now woven (a bare one was left out).

## Tests, first

1. The whole-tree test: a token's value is its text exactly,
   `str(tok) == source[tok.start_pos:tok.end_pos]` (was `startswith`).
2. A claim's `kind`, `mode` and `name` for each form: `~example`, bare
   `~run`, `~run on-load`, `~run on-invocation`, bare `~property`,
   `~property total`.
3. `weave` writes each form of `~run` (bare, `on-load`,
   `on-invocation`) with its label and its lines.
4. The models' and graph documents' digests and goldens are unchanged
   but where a test held `sigil` or `title` (say which).

## Report

What changed, by file; the tests changed and why; anything that wanted
a grammar change (stopped, with the proposal). No commit, no staging.
80-character lines.
