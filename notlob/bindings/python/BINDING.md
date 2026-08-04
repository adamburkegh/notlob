# Python Binding

Realizes notlob for Python. The default binding; claims execute
in-process.

## Toolchain

Nothing to install. `ruff`, `pytest`, and `hypothesis` are core
dependencies of notlob, so `pip install notlob` provides the whole
toolchain. This is the one binding whose tools ride along with notlob
itself — the others (TypeScript, Haskell) draw from their own
ecosystems.

## Linting

`ruff check` (run as `python -m ruff`) — style and correctness.
Diagnostics map back to `.lob` section addresses. Dependency modules
declared in `#References` are prepended before linting so cross-module
names resolve (suppressing false-positive undefined-name reports). If
`ruff` is somehow absent, `notlob test` fails rather than silently
skipping.

## Static call analysis

`extract_calls` performs an AST walk over each symbol's source text and
returns the names of all `Name` nodes with a `Load` context, minus
Python builtins.  These are used by `add_uses_edges` to add `USES` edges
between SYMBOL nodes in the name-graph.

Fidelity ceiling: parameters appear as `Name` loads and are included
(the graph resolves them away — parameters rarely match another
top-level symbol).  Dynamic dispatch (`getattr`, `eval`, string-based
calls) is invisible to static analysis and produces no USES edge.

## Property & unit testing

- `~property-testing hypothesis` — `~property` claims receive `@given`
  decoration automatically; authors do not import Hypothesis directly.
- `~unit-testing pytest` — injects `pytest`, `approx`, and `raises` into
  the `#Tests` assertion namespace.

## Claims

| Claim       | Support                                               |
|-------------|-------------------------------------------------------|
| `~example`  | yes — boolean expressions, `==` for equality          |
| `~property` | yes — Hypothesis (`~property-testing hypothesis`)     |
| `#Tests`    | yes — `~unit-testing pytest` enriches the namespace   |
| `~run`      | yes — included in `notlob build` output (entry point) |

Equality assertions use `==`; the runner reports concrete left/right
values on failure for `a == b`.

## Runner

Claims execute in-process: the module is assembled and `exec`'d into a
namespace, then each assertion is evaluated there. No subprocess.
