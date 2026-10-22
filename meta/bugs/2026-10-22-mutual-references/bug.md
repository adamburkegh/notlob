# Modules could not list each other: a listing meant "load this first"

**Component:** `notlob/project.py` (`_dependency_order` and what became
`_plan`), every binding's runner and builder, `notlob/commands.py`
(`_test_module`).
**Found by:** Adam, 2026-10-22, pressing on why the Gutenberg example's
`##Gutenberg Hamlet` reference had "never resolved". Not reported by a user.
**Status:** reopened, 2026-10-23: the fix (`1468f0f`) was backed out in
`4230b04` with the name-graph refactor it was built on; see
`meta/retrospectives/2026-10-23-name-graph-redundancy/`. Was: fixed in
Python, 2026-10-22, with TypeScript and Haskell falling back to the old
loading (below).

## Summary

`#References` was read three ways at once: a bibliography (this module is in
conversation with that one), a scope declaration (a prose `#Name` resolves
only if listed), and a load instruction (inline that module's code first).
The third made a mutual listing unrunnable. `corpus` cites `hamlet` in prose
("a second text would be a module of the same shape as ...") and so should
list it, but `hamlet`'s code needs `corpus`'s. With both listed, running
`hamlet` loaded `corpus`, then `hamlet` (as `corpus`'s dependency), then
`hamlet` itself: `hamlet`'s code ran before `corpus`'s defined `load_play`.
`NameError: name 'double' is not defined` in the reproduction
(`tests/test_mutual_refs.py`). A real cycle of use gave the same error and
nothing named the cycle.

Agent sessions worked round it for months instead of treating it as a bug.
The Gutenberg example is where `##Name` was first used for a module (written
`##Litstats Hamlet` on 2026-05-22, when any module resolved); it was
tightened to "listed modules only" the next day (`c013a43`) and the example
was never updated; and in the end this session's first fix was to turn the
reference into plain prose. The example was the only place that showed the
shape, and nothing ran the whole project.

It was not Java-style package scope that had been lost: `DESIGN.md` has said
"there is no implicit package import" since 2026-05-22 (`9fc4ff8`).

## Resolution

Rules in `DESIGN.md` ("Listing, citing and loading") and `LANGUAGE.md`;
properties in `tests/test_reference_rules.py` (generated projects) and
`tests/test_mutual_refs.py` (the shapes).

* Listing is free, including circular. Citing still needs listing (the scope
  of a citation is authored, never ambient: not the package, not the
  project; traceability like a bibliography).
* Loading follows *need*: A needs B when A lists B and A's code (body and
  claims, from the graph) refers to a name B's own code defines, less names
  A defines itself, outside strings and comments (the binding's call
  extraction). A listing nothing uses is a citation and loads nothing.
* A cycle of need is an error naming the cycle.
* Fallback (D): when use cannot be told, the address tree decides: a listing
  of a descendant is a citation, any other is loaded.

Considered and rejected: loading by use only inside a cycle ("a hacky
workaround, made more hacky by its conservatism"); a project-wide citation
namespace ("one citation namespace would get polluted quickly"); Java-style
sibling scope (siblings list each other to cite, as to use); explicit
citation-only syntax (discourages citation).

**Limitation, deliberate:** `BindingKit.complete_references` is false for
TypeScript (its `extract_calls` sees `name(...)` only) and Haskell (lowercase
identifiers only, and it reads strings). Their kits therefore take the
fallback: every listing but a descendant's is loaded, as before, and two
siblings that list each other are a cycle there. Widening those extractors
changes their `USES` edges and ~20 tests; a separate piece of work.

## Found with it

* **`#Tests` code was unparseable for `USES`.** A `#Tests` group's node code
  was `"\n".join(lines).strip()`: first line unindented, the rest indented.
  `extract_calls` returns nothing on a syntax error, so every multi-line
  `#Tests` group (and `~test` block) contributed no `USES` edges. Found
  because the first version of the need check missed `#Tests` uses. Fixed
  in `graph._assertion_source`.
* The Gutenberg example now cites `#Gutenberg Hamlet` and lists it, which
  `tests/test_example_projects.py` runs.
