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

Hypothesis and pytest are always available — no `binding.lob`
declaration beyond `~language python` is needed (an earlier
`~property-testing hypothesis` / `~unit-testing pytest` declaration
syntax existed briefly but was never actually part of the grammar and
was removed in 0.5.2). Wanting a different property-testing or
unit-testing library means writing an alternative Python-targeting
binding, not declaring one in `binding.lob`.

- `~property` claims receive `@given` decoration automatically; authors
  do not import Hypothesis directly.
- `#Tests` assertions get `pytest`, `approx`, and `raises` injected into
  the assertion namespace.

## Claims

| Claim       | Support                                               |
|-------------|-------------------------------------------------------|
| `~example`  | yes — boolean expressions, `==` for equality          |
| `~property` | yes — Hypothesis, always available                    |
| `#Tests`    | yes — pytest helpers always enrich the namespace      |
| `~run`      | yes — bare/`on-invocation` wrapped in `if __name__ == "__main__":`; `on-load` unconditional (legal, unusual) |

Equality assertions use `==`; the runner reports concrete left/right
values on failure for `a == b`.

## Runner

Claims execute in-process: the module is assembled and `exec`'d into a
namespace, then each assertion is evaluated there. No subprocess.
