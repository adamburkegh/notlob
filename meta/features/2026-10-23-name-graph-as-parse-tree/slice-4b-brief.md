# Slice 4b brief: the bindings run what notlob collects

**For:** an implementing session. **Written by:** the design session,
2026-10-25. **Design:** `design.md` in this directory: D14, D17, D18, and
slice 4 in section 9. Read them first.

## Goal

Every binding works out for itself which claims and tests a module has,
by walking the model (`_collect_example_assertions`,
`_collect_properties`, `_collect_test_assertions` and
`_collect_group_assertions` in Python, their equivalents in Haskell and
TypeScript, and `collect_run_bodies`, which their `build()` and the
Python `lint()` call). Those walks are why claims in an `#Appendix` are
never run, and why an assertion after commentary in `#Tests` is reported
at the wrong line (`meta/bugs/2026-10-25-tests-commentary-line-drift`).

From this slice, **notlob collects them from the graph and hands each
binding what to run** (D17). The binding keeps everything about its
language: assembling, splitting assertions (`_iter_assertions`),
running, reporting. This is a breaking change to `BindingKit`, which is
in the stable tier; the CHANGELOG entry is written in the release pass,
not here.

Also: **`notlob build` reports a name collision** instead of building
past it, and `build()` stops leaving its collision list on the graph.

## Rules

* **May touch:** `notlob/bindings/__init__.py`, the three bindings'
  `__init__.py`, `runner.py`, `harness.py` and `lint.py` (Python), the
  equivalent files of Haskell and TypeScript, `notlob/graph.py`,
  `notlob/commands.py`, the three `BINDING.md` files where they state
  the kit's signatures, and the tests below.
* **Must not touch:** `model.py`, `check.py`, `project.py`, the
  assemblers' walks of the model (`assemble`, `assemble_with_deps`;
  they stay on the model, `design.md` section 9), `cli.py`,
  `mcp_server.py`, the schemas, `DESIGN.md`, `LANGUAGE.md`, the
  CHANGELOG.
* **Must not change, and must pass:** `tests/test_check.py`, every
  `tests/test_cli_*.py`, `tests/test_address_collision.py`,
  `tests/test_cmd_test_one_graph.py`, `tests/test_graph_export.py`,
  `tests/test_turtle.py`, `tests/test_graph_layer.py`. The **results**
  notlob prints for every example project must not change except as
  listed under "What may change".
* **May be rewritten:** the call sites in the binding tests
  (`tests/test_bindings_*.py`, `tests/test_lint.py`, and any other test
  that calls a kit callable directly), to pass what notlob collects,
  through a small helper; their assertions stay. Report the helper and
  the files.
* **Failing test first;** say that you did. Do not commit or stage.
  80-character lines. No phase or slice wording in code or docstrings.

## 1. What notlob hands over

In `notlob/bindings/__init__.py`, next to `ClaimResult`:

```python
@dataclass(frozen=True)
class ClaimToRun:
    """A claim or test of a module, as notlob found it, for a binding
    to run."""
    address:    str              # the address results are reported at
    kind:       str              # "EXAMPLE", "PROPERTY", "RUN" or "TEST"
    lines:      list[str]        # its lines, one per file line
    first_line: int | None       # the file line of lines[0]
    sigil_line: int | None       # the line of its ~sigil (None for a run
                                 # of bare assertions)
    name:       str | None       # a named ~property's or ~test's name
    mode:       str | None       # a ~run's mode (D18)
```

(`kind` is the `NodeKind`'s name, a string, because `graph.py` imports
from `notlob.bindings` and the reverse would be circular.) And in
`notlob/graph.py`, one function, the only place claims are collected:

```python
def claims_to_run(graph, module_address) -> list[ClaimToRun]:
```

It returns every claim and test in the module's tree, in document order:
the body, subheadings, each `#Appendix` and its subheadings, and
`#Tests`. Each item comes from the graph's node (`graph.text()` split
into lines; the lines start the line after a sigil, or at a run's first
line).

**Result addresses do not move in this slice.** An example, a property,
a `~run` and a named test report at their own node's address, as today.
A run of bare assertions reports at the address of the group or `#Tests`
it is written in, as today (D14's "under the block's address" comes with
the output redesign, slice 5). So `address` for a run is its parent's.

## 2. The new contract

| Field | Was | Now |
|---|---|---|
| `run_examples` | `(module, *, file_path=None, ...)` | `(module, claims, *, file_path=None, ...)` |
| `run_properties` | `(module, *, ...)` | `(module, claims, *, ...)` |
| `run_tests` | `(module, *, ...)` | `(module, claims, *, ...)` |
| `lint` | `(module, *, root=None)` | `(module, claims, *, root=None)` |
| `build` | `(module, file_path=None)` | `(module, claims, file_path=None)` |

`claims` is a list of `ClaimToRun`. notlob passes each callable only the
kinds it runs: examples to `run_examples`, properties to
`run_properties`, tests to `run_tests`, `~run`s to `build`, all of them
to `lint`. `module` stays, for assembly. Update `BindingKit`'s
docstring, which is the contract's statement.

`collect_run_bodies(module)` becomes `run_bodies(claims)`: the same
`(on_load, on_invocation)` pair, from the `RUN` items' `mode` and lines.
The three `build()` functions and Python's `lint()` call it.

In each binding, delete the `_collect_*` walks; the runners and harness
builders read the `ClaimToRun` items instead. Keep each language's own
work where it is (`_iter_assertions`, `_is_complete`, the harnesses).

## 3. notlob's side

In `commands.py`, wherever a kit callable is called:
`_test_module` (lint and the three runners), `cmd_run` and its Haskell
and TypeScript paths (`build_haskell`, `build_typescript`), and
`_build_one`. Each reads `claims_to_run` from the command's one graph
(4a): the package graph in a project; `build(module)` (no binding is
needed for claims) for a file on its own.

**`notlob build` and a name collision.** A module whose names collide
is not built: `ERROR <names>`, counted as a failure, no artifact, as
`notlob test` reports it. Today a single file with no project swallows
it (the entry-point check's `except Exception`); in a project the
collision list from `build_package` says which modules. Test both.

**`build()`'s collision list.** `build(module, file, collisions)` leaves
the list on the graph (`graph._collisions`) after it returns. Pass it to
the functions that need it, or clear it before `build` returns, so no
graph keeps a reference to it.

## What may change

* **Claims in an `#Appendix` now run** (the rest of the Appendix fix,
  `meta/bugs/2026-10-19-appendix-not-in-graph`). If an example project
  has a claim in an Appendix that now fails, stop and report it.
* **An assertion after commentary in `#Tests` reports its real line.**
  The strict xfail in `tests/test_bindings_python_runner.py` then
  passes; remove its marker and say so. Add the same test for Haskell
  and TypeScript. Do not edit the bug note; the design session marks it
  resolved after Adam commits.
* **A run of bare assertions is split at commentary.** Assertions on
  either side of a paragraph were one list before; now they are two
  runs. Results are per assertion, so this should change only lines.

Anything else that changes in the printed results is a stop.

## Tests

1. `claims_to_run` on sources with a claim in every place one can be
   written (body, subheading, Appendix, Appendix subheading, `#Tests`,
   a group), with addresses, kinds, names, modes and lines; and on every
   example project, compared with what the runners collected before this
   slice (capture that from the current code into the test as data first,
   then expect the same plus the Appendix claims, if any).
2. The runners on handed-over claims: an Appendix example runs and
   reports at its address; a `~run on-load` and a bare `~run` reach
   `build()` in the right group.
3. The line-drift tests, for all three bindings.
4. `notlob build` and a collision, alone and in a project.
5. No graph holds a collision list after `build` returns.

## When to stop

Stop and report if a protected test fails, if a printed result changes
in a way not listed above, if an example's Appendix claim fails, if a
binding needs something `ClaimToRun` does not carry, or if the slice
grows past this brief.

## When you are done

Report, without committing: `ClaimToRun` and `claims_to_run` as built;
the new kit signatures; for each binding, what was deleted and what
reads the claims now; the commands changes; that the new tests failed
first; the full suite result; the rewritten call sites and their helper;
whether any example has Appendix claims; a line-length check; anything
you stopped on.
