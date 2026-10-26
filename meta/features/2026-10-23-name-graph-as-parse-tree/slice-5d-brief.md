# Slice 5d brief: addresses in results

**For:** an implementing session. **Written by:** the design session,
2026-10-26. **Design:** `design.md` in this directory: "Where it stands,
and the way home", section 2 ("Scope"), D8, D10, D14. The kinds and
scope slice (`slice-kinds-and-scope-brief.md`) is done: `scope_of`,
`named_address` and the table of kinds are in `graph.py`. Read them
first.

## Goal

Three deliberate output changes, made together so the format breaks
once:

1. **A named `~property` is addressed in its module's scope** (D8):
   `roman/numerals#commutativity`, not
   `roman/numerals#Round-Trip#commutativity`. Sections are not scopes.
2. **A run of bare assertions reports at its own address** (D14):
   `claims_to_run` hands a binding `roman/numerals#Tests#encoding#test#1`,
   not the group's `roman/numerals#Tests#encoding`. The graph already
   has the node at that address; only what is reported moves.
3. **`USES` edges come in document order.** `_SCAN_ORDER` in
   `add_uses_edges` exists only to keep the order the old per-kind loops
   made (`RUN`, `TEST`, `EXAMPLE`, `PROPERTY`). It goes, with its sort.

`DESIGN.md` already describes 1 (its `~property` naming paragraph). The
runners pass `ClaimToRun.address` through unchanged, so none of them
changes.

## Rules

* **May touch:** `notlob/graph.py`; `notlob/docs/LANGUAGE.md` (the
  `#Tests` addresses, lines 225 to 245) and `notlob/docs/DESIGN.md`
  (only if a line there contradicts the new addresses); tests;
  `tests/data/README.md` (one sentence, below).
* **Must not touch:** the bindings, `commands.py`, `check.py`,
  `model.py`, the grammar, the schemas, the recorded
  `tests/data/claims_*.json` (they are the record of what the runners
  collected, not expected values).
* **Assertions may change** only where they pin one of the three things
  above: a named property's address (or a symbol's under it), the
  address a run of bare assertions is reported at, or the order of
  `USES` edges. Report each, old and new. Any other assertion that would
  change is a stop.
* **Failing test first;** say that you did. Do not commit or stage.
  80-character lines. No phase or slice wording anywhere. Plain
  `pytest` and `ruff` calls; write scratch output to `var/`.

## 1. The named property

`_claim_identity` addresses a named property with
`named_address(graph.scope_of(parent), name)`, as every other named node
is; the comment that explains the exception goes. It needs the graph
(pass it, or move the naming to the caller: your choice, one way).
The label stays the name, and the property still counts among its
parent's properties for the ordinals of unnamed ones.

What follows from the rule, and needs a test each:

* the functions a named property defines are under it:
  `roman/numerals#commutativity#check_it`;
* two named properties of one name in one module, in different
  sections, now collide: a document name restated in its scope is an
  `AddressCollisionError` (D10), reported as other collisions are;
* a named property and a subheading or symbol of the same name in one
  module collide too, as a symbol and a subheading do today.

No example project and no `.lob` file under `ref-projects/` has such a
clash (searched 2026-10-26: four named properties in all).

## 2. The run of bare assertions

In `claims_to_run`, an anonymous test is reported at its own address.
It keeps `sigil_line=None` and `first_line` its own first line, as now.
Nothing else in `ClaimToRun` changes.

The oracle test (`tests/test_claims_to_run.py`,
`TestAgainstWhatTheRunnersCollected`) compares with the recorded data.
The data stays as recorded. The test gets one helper that says what
changed on purpose, the address the runners used to report a claim at,
read from the graph:

```python
def _as_recorded(graph, claim) -> str:
    """The address the runners reported *claim* at before notlob
    collected the claims: a run of bare assertions at the node it is
    written in, a named property in the scope of its section."""
```

and compares through it. Add one sentence to `tests/data/README.md`
saying so.

## 3. The `USES` order

Delete `_SCAN_ORDER` and the sort: the symbols first, then the runnable
nodes in the order they are in the graph (document order). The edge set
is unchanged; only its order in the JSON moves. Show it with a test
that the edge *set* of every example project is the same as before and
the order is document order, or say why you could not.

## 4. Docs

`LANGUAGE.md`, lines 225 to 245: a bare line is addressable through its
block (`roman/numerals#Tests#larger values#test#1`), not only through
its `##group`. Say what the address is and that the runner reports
each assertion under it with its line. Keep the paragraph's length.

`DESIGN.md`: check its `~property` and `~test` paragraphs (lines 135 to
176) against the new addresses. Change a line only if it is wrong.

## Tests

1. A named property in a section is at `module#name`; its function at
   `module#name#fn`; `scope_of` of the property is itself. Update
   `tests/test_graph_kinds.py` for the named property (its scope rows and
   the full address list), and add the named property to "a name
   belongs to the scope of what holds it".
2. The two collisions in section 1.
3. A run of bare assertions is reported at its own address; commentary
   still ends a run; the two runs either side of commentary have
   `#test#1` and `#test#2`.
4. The oracle test passes through `_as_recorded`, the data unchanged.
5. `USES` order as in section 3.
6. `notlob test` on the roman example, run from a test (not by hand):
   a result line for a bare assertion carries its block's address.

## When to stop

Stop and report if a runner needs changing, if an assertion outside the
three changes would move, if any example or `ref-projects/` file now
raises a collision, or if the slice grows past this brief.

## When you are done

Report, without committing: the addresses that moved, as before and
after, for the roman example (a named property you add in a test will
do if roman has none); each test changed, old and new; that the new
tests failed first; the full suite result; a line-length check;
anything you stopped on.
