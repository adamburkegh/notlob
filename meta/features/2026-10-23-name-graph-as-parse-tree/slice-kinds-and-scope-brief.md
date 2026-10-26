# Slice brief: what a kind is, and the scope rule

**For:** an implementing session. **Written by:** the design session,
2026-10-26. **Design:** `design.md` in this directory, section 2
("Scope") and D2, D8, D10, D15; and findings 6 and 7 of
`../2026-10-26-missing-concepts/design.md`. Read them first. Comes
before slice 5d.

## Goal

Two ideas the design states have no home in the code, so each is written
out wherever it is needed:

* **What a kind is.** A node's kind is an adjective (D2): a claim, run by
  a binding, a section, and so on. The code asks with tuples of kinds
  repeated at each place, and with `kind == SYMBOL` special cases.
* **Scope and addresses.** A named node's address is its scope's address,
  `#`, and its name; an anonymous node's is its parent's address, its
  kind's segment and an ordinal. The code has seven address functions
  and as many f-strings, and `build` threads the module address beside
  the parent so it can address subheadings and symbols.

After this slice each has one home: a table of kinds, `scope_of`, and two
address functions. **No address and no output changes.** This is a
refactor; 5d then changes one rule with a small diff.

One behaviour fix rides along, kept apart from the refactor (section 4):
three checks leave the `#Appendix` out by accident, and asking the table
brings it in.

## Rules

* **May touch:** `notlob/graph.py`; `notlob/commands.py` and
  `notlob/check.py` only where they import or build what this slice
  replaces (`ANONYMOUS_LEAVES` at `commands.py:1431`, the f-string at
  `check.py:356`) and for section 4; the three `assemble.py` files only
  to call
  `named_address` in place of `subheading_address`; tests, only to call
  the new functions in place of removed ones, with what they assert
  unchanged. Report each test you change, old and new.
* **Must not touch:** `model.py`, `parser.py`, `grammar.lark`, the
  schemas, the docs, the bindings' runners and lint.
* **Must not change, and must pass:** the whole suite, unchanged in what
  it asserts. Every address and every output stays as it is, but for
  the findings section 4 adds.
* `module_address` stays, with its name: `ref-projects/notlob-vids`
  imports it.
* **Failing test first;** say that you did. Do not commit or stage.
  80-character lines. No phase or slice wording anywhere.

## Before you change anything

Write `notlob graph --level full` (JSON) for every project under
`examples/` into `var/scope-before/`, one file each. After the change,
write the same into `var/scope-after/` and diff. The diff must be empty.
`var/` is gitignored; leave the files there for review.

## 1. The table of kinds

One table in `graph.py`, beside `NodeKind`: a frozen dataclass of facts,
and a dict giving every kind its row. Each fact is one of the tuples or
special cases found in the code today:

| fact | meaning | kinds | replaces |
|---|---|---|---|
| `opens_scope` | a name written in it belongs to it | `MODULE`, `PROPERTY`, `TESTS`, `TEST_GROUP` | (new: section 2, D8) |
| `claim` | an `~example`, `~property` or `~run` | `EXAMPLE`, `PROPERTY`, `RUN` | `claims()` |
| `runnable` | a binding runs it | `EXAMPLE`, `PROPERTY`, `RUN`, `TEST` | `claims_to_run`, `_scanned_text`, `add_uses_edges` |
| `block` | a paragraph, code block or bullet list: what `outline` leaves out | `PROSE`, `CODE`, `BULLETS` | `ANONYMOUS_LEAVES` |
| `section` | a section of the document | `SUBHEADING`, `APPENDIX` | `sections()` |
| `region` | a region of the tree, no part of an address | `POST_TEXT` | `sections()`, the appendix address |
| `text_in_holder` | its text is lines of the node that holds it | `SYMBOL` | `text`, `_sizes`, `_node_entry`, `subtree` |
| `segment` | its address segment when anonymous | `PROSE` `prose`, `CODE` `code`, `BULLETS` `bullets`, `EXAMPLE` `example`, `RUN` `run`, `PROPERTY` `property`, `TEST` `test`, `APPENDIX` `appendix`, `POST_TEXT` `post-text` | the f-strings and `_claim_identity` |
| `numbered` | its anonymous address has an ordinal | all with a segment but `POST_TEXT` | `post_text_address` |

Write the segments out in the table; do not derive them from the enum
names. Call sites read the table (`KINDS[node.kind].claim`, or whatever
reads as plainly; one way, used everywhere). `ANONYMOUS_LEAVES` goes.

Ask each place what it means. Where a `kind == SYMBOL` test or a tuple is
really asking one of the facts above, it reads the table. Where it asks
about that one kind for its own reason (`resolve` accepting a `SYMBOL`
or `SUBHEADING`, `_scanned_text`'s symbol branch starting at the
symbol's line), it stays as it is. List every site in your report with
which it was. If one fits neither, stop and report it: do not invent a
fact.

`sections()` walks into regions and sections. Subheadings cannot nest
(`grammar.lark:54`), so walking into a subheading finds nothing new; if
that turns out not to be so, stop and report.

## 2. Scope

```python
def scope_of(self, address: str) -> str | None:
    """The address of the scope a name written in the node at *address*
    belongs to: the node itself if its kind opens a scope, or else the
    scope of the node that contains it."""
```

A `NameGraph` method, beside `module_of`. Nodes are added parents first,
so `build` and `enrich` can ask it of the node they are adding a child
to.

## 3. Two address functions

```python
def named_address(scope: str, name: str) -> str
def anonymous_address(parent: str, kind: NodeKind, n: int) -> str
```

`anonymous_address` writes the kind's segment, and the ordinal only if
the kind is `numbered`. The *parent* an anonymous address is written from
is the nearest container that is not a `region`: an appendix hangs from
the post-text and is addressed from the module, as now.

Every address in `build` and `enrich` is then one of:

| node | address |
|---|---|
| module | `module_address(title)` |
| named (subheading, symbol, `#Tests`, group, named test) | `named_address(graph.scope_of(parent), name)` |
| anonymous (block, unnamed claim, run of assertions, appendix, post-text) | `anonymous_address(base, kind, n)`, *base* the nearest container that is not a region |
| named `~property` | see below |

The ordinals stay as they are: per parent, per kind, a named property
still counting among its parent's properties. Key `_Ordinals` by kind
rather than by string.

**The one exception.** Today a named `~property` is addressed from the
section it is written in (`roman/numerals#Round-Trip#commutativity`),
where the scope rule gives its module (`roman/numerals#commutativity`).
That is D8, and 5d makes it. Until then the named property is the one
place that does not ask `scope_of`: it takes its parent's address as its
scope, in one line, with a comment that says why (the rule puts it in
its module's scope; its address has not moved yet). Nothing else may
need an exception; if something does, stop and report it.

Then: `subheading_address`, `symbol_address`, `property_address`,
`appendix_address`, `post_text_address` and `claim_address` go. `resolve`
and `_resolves` build their lookup with `named_address(context, label)`
(a module is a scope), and `check.py:356` with
`named_address(mod_node.address, sym)`. `_add_items` and `_add_tests`
lose their `mod_addr` parameter. `enrich`'s two branches become one
(`named_address(graph.scope_of(holder.address), info.name)`); the `_`
skip stays.

## 4. The checks see the Appendix

`check_titles`, `check_style` and the claims-missing check
(`check.py:252`, `368`, `481`) each skip every node not a `MODULE` or
`SUBHEADING`, so the subheadings in an `#Appendix` are checked but the
Appendix itself (its title, and what is written before its first
subheading) is not. That was not designed; it is how the code happened
to be written. Each asks the table instead:
a module or a `section`. The Appendix is then checked as any section
is: its title against the others, its bullet lists, its prose against
its claims.

Do this after sections 1 to 3, with the before-and-after diff already
empty, so the refactor and the fix are apart in your report. A failing
test first for each of the three checks: an Appendix that should get
the finding and does not today. If an existing test's assertion would
have to change (an example project's Appendix now drawing a finding,
say), stop and report it with the finding: that is for Adam to look at,
not to adjust.

## Tests

1. **Every kind has a row**, and the table states the design: the kinds
   that open a scope are exactly `MODULE`, `PROPERTY`, `TESTS` and
   `TEST_GROUP`; the claims, the runnable kinds, the blocks, the sections
   and the regions are exactly those in the table above.
2. **`scope_of`**, on Roman with a named property, a `#Tests` group and
   an Appendix added (build the module in the test, as other graph tests
   do): a code block in `##Decoding` and its symbol are in the module's
   scope; a symbol a `~property` defines is in the property's; a subheading
   in an Appendix is in the module's; a named test in a group is in the
   group's, the group in `#Tests`'s, `#Tests` in the module's.
3. **The addresses** of a node of every kind in that module, written out
   in full, as they are today. (The named property's included: 5d will
   change that one line.)
4. **The removed names are gone** from `notlob.graph`.

The whole suite is the guard that nothing moved, with the diff above.

## Not in this slice

* D8 itself and the rest of 5d.
* A module's file on every node (finding 10), reference resolution
  (finding 1), where a text starts (finding 5).

## When to stop

Stop and report if an address or an output changes, if a test's
assertion would have to change, if a site fits no fact, if anything but
the named property needs an exception, or if the slice grows past this
brief.

## When you are done

Report, without committing: the table as written; `scope_of` and the two
address functions; each site that read a tuple or a `kind ==` test, and
which way it went; each test changed, old and new; that the new tests
failed first; the empty diff of `var/scope-before/` and
`var/scope-after/`; what `notlob check` now says about each example
project's Appendices that it did not before; the full suite result; `graph.py`'s length before and
after; a line-length check; anything you stopped on.
