# Slice 8b brief: `#References` and `#Binding` in the graph

**For:** an implementing session. **Written by:** the design session,
2026-10-26. **Design:** `design.md` in this directory, D11 (decided
2026-10-26), D9, D18, and slice 8. After 8a (the `CITES` rename).

## Goal

The last two post-text sections are the only parts of a `.lob` file the
graph does not hold. After this slice they are nodes like the rest, and
the edges they make start at the line that makes them:

```
mod#post-text                        POST_TEXT
 ├─ mod#Tests                        TESTS
 ├─ mod#References                   REFERENCES     (named, like #Tests)
 │   ├─ mod#References#listing#1     LISTING        #Roman Numerals
 │   │       └─IMPORTS→ roman/numerals
 │   └─ mod#References#import#1      IMPORT         from decimal import (
 │                                                      Decimal, ROUND_UP)
 └─ binding#Binding                  BINDING        (binding.lob only)
     ├─ binding#Binding#declaration#1  DECLARATION  declares=language
     │                                              value=python
     └─ binding#Binding#declaration#2  DECLARATION  declares=external
             └─USES_EXTERNAL→ data/pg1524.txt          value=data/pg1524.txt
```

Who owns the syntax decides who makes the node (as D14 and D17):

* `#Name` lines are notlob's: `LISTING`, made by `build`.
* The other lines are the bound language's import statements: `IMPORT`,
  **one node per statement**, a statement that spans lines (`from x
  import (a,\n b)`, a trailing `\`, `import {\n a\n} from 'x'`) being
  one node (Adam, 2026-10-26). Where a statement ends is the language's
  rule, so these are made in the binding's pass, `enrich`, as symbols
  are.
* `#Binding` declarations are notlob's: `DECLARATION`, made by `build`,
  with their facts as fields (D18).

## Rules

* **May touch:** `grammar.lark`, `parser.py` (terminal list),
  `model.py` (the two section classes), `graph.py`, `project.py`
  (`build_package`'s `IMPORTS` and external passes, `load_order`),
  `commands.py` and `check.py` (only to read listings through the new
  helper), `bindings/__init__.py` and each binding's `__init__.py` (the
  statement splitter), the two JSON schemas and `notlob.ttl`,
  `LANGUAGE.md` and `DESIGN.md` (the graph's kinds), the CHANGELOG's
  Unreleased graph entry, tests.
* **The three assemblers** may change only to read the model's import
  lines (section 1) in place of their own `startswith("#")` filters.
* **Must not touch:** the lints (they keep reading the model; moving
  readers onto the graph is later work), the weaver. The model's
  existing fields stay for them.
* **Assertions may change** only where they pin the graph's kinds, the
  source of an `IMPORTS` or `USES_EXTERNAL` edge, or outline lifting of
  those edges. Report each, old and new.
* **Failing test first;** say that you did. Do not commit or stage.
  80-character lines. No slice wording. Plain `pytest` and `ruff` calls.

## 1. Listings told apart by the grammar

Today a `#References` line is an `INDENTED_LINE`, and "is this line a
listing?" is answered by `startswith("#")` on the stripped line in five
places: `project.parse_lob_refs`, `project._module_lob_refs_with_lines`,
`project.parse_python_imports`, `typescript/assemble._ts_imports` and
`haskell/assemble._haskell_imports`. Grammar over Python, and one home
for the concept (Adam agreed the change, 2026-10-26):

```lark
references_section: REFERENCES_HEAD (LISTING_LINE | INDENTED_LINE | BLANK)*

// A listing: an indented `#` and a module title, as MOD_HEAD writes
// one at column zero. Outranks INDENTED_LINE, which matches the same
// text; reachable only in references_section, so a `#` comment in a
// code block is untouched.
LISTING_LINE.9: INDENT "#" /[^#\s]/ REST_OF_LINE
```

Add `LISTING_LINE` wherever `parser.py` lists the terminals. The model's
`ReferencesSection` gains `listings` (title and line, from
`LISTING_LINE`) and `imports` (text and line, from `INDENTED_LINE`), as
the parser classified them; `lines` stays. The five readers above read
`listings` or `imports` instead of filtering, and the `startswith` checks
go. Two behaviour changes follow, both fixes, each pinned by a test:

```
    #Roman Numerals        a listing       (as today)
    # used for parsing     an import line  (was a listing of a module
                                            called "used for parsing")
    ##Notes                an import line  (was a listing of "#notes")
```

If the terminal cannot be made to work with the contextual lexer without
a Python check, stop and report what you tried.

## 2. Declarations kept in order

`BindingSection` keeps typed fields but no line or order for `~language`
and `~keep-generated-src`. Add the declarations in document order, each
with its keyword (from the token type the grammar already gives:
`LANGUAGE_DECL` is `language`, and so on), value and line. The typed
fields stay.

## 3. The nodes

Rows in the kinds table: `REFERENCES` and `BINDING` (named sections like
`TESTS`: no segment, no scope, not a `section`, which the checks read);
`LISTING`, `IMPORT` and `DECLARATION` (anonymous, numbered, segments
`listing`, `import`, `declaration`, and left out of `outline`). The
`block` fact now covers more than paragraphs, code blocks and bullet
lists: rename it for what it means, left out of `outline`, and keep its
one meaning everywhere it is read.

* `LISTING`: text is the line as written (`#Roman Numerals`).
* `IMPORT`: text is the statement, dedented, as written.
* `DECLARATION`: two new node fields, `declares` and `value`, printed
  like `mode` (from `outline`, when set); text is the line as written.

The statement splitter: a new `BindingKit` field (a name of your
choosing, documented with the others), taking the section's `imports`
(the same lines the assemblers read) and
giving each statement's text and first line. The default is one
statement per non-blank line, so a third-party binding keeps working.
Python, TypeScript and Haskell each supply theirs, by their own rules
(Python can use the compiler; the TypeScript tokenizer knows brackets).
`enrich` takes it and adds the `IMPORT` nodes under `mod#References`; a
graph built without a binding has the section and its listings and no
imports, as it has no symbols. Test each binding with a one-line import,
a parenthesised or braced one over several lines, and (Python) a `\`
continuation.

## 4. Edges from their lines

* `IMPORTS` starts at the `LISTING` that makes it (still to the listed
  module, still only when that module is in the graph).
* `USES_EXTERNAL` starts at the `~external` or `~on-build`
  `DECLARATION` that names the file. `_add_external_nodes` reads the
  graph's declarations instead of parsing `binding.lob` again.
* At `outline` both lift to their section (`mod#References`,
  `binding#Binding`), by the existing lifting.

Six readers take an `IMPORTS` edge's source to be the module:
`load_order`, the `[imports]` check, `NameGraph.resolve`'s third step,
`_resolves`, and `query imports` and `imported-by`. Give them one
helper, what a module lists (the targets of the `IMPORTS` edges from the
listings in its tree, in document order), and the modules that list a
module. Their answers stay at module level: `query imports roman` still
prints modules.

## 5. Schemas, ontology, docs

The kinds enum and the `declares` and `value` properties in
`name_graph.json` and `query_result.json` (kept identical, as the test
already requires); classes and the two properties in `notlob.ttl`;
`LANGUAGE.md`'s and `DESIGN.md`'s lists of kinds and what each edge
starts at; the CHANGELOG's graph entry (its list of kinds, and that
`IMPORTS` and `USES_EXTERNAL` start at their lines).

## Tests

1. The completeness oracle covers the two sections: every listing,
   import statement and declaration of every example project is a node,
   at its line, in document order.
2. Each kind's address, label and fields on a small module and a
   `binding.lob`.
3. The splitter, per binding, as in section 3.
4. The edges start at their lines; at `outline` they lift to the
   section; the six readers answer as before (their tests unchanged).
5. Schemas validate at every level; the ontology guards pass.

## When to stop

Stop and report if the listing terminal needs a Python check, if a
binding's statements cannot be told apart by its own rules without a
new dependency, if a test outside those named would change, or if the
slice grows past this brief.

## When you are done

Report, without committing: the grammar change and the five readers it
replaced; the model change; the
kinds and fields; each binding's splitter with its cases; the helper and
the six readers; a `notlob graph --level index` sample of a module's
`#References` and of `binding.lob`; each assertion changed, old and new;
that the new tests failed first; the full suite; a line-length check;
anything you stopped on.
