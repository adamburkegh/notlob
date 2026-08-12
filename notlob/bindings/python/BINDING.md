# Python Binding

Realizes notlob for Python. The default binding.

## Toolchain

`ruff`, `pytest`, and `hypothesis` are core dependencies of notlob, so
`pip install notlob` provides them all — but *where* each one actually
runs differs, and it's worth being precise about it:

- `ruff` runs under notlob's own interpreter (`sys.executable`) — it's
  static analysis, not execution, so it doesn't need the target
  project's environment.
- The module's own code — including whatever third-party libraries it
  imports (`pandas`, etc.) — runs under an interpreter resolved from
  `PATH` (an activated venv, an asdf/mise shim, ...), *not* notlob's
  own. Notlob is meant to be used as an external tool (pipx, uvx),
  the same way you'd use `ghc`/`javac`/`tsc` against a project without
  installing them into it, so the project's own dependencies need to
  come from the project's own environment — that's what makes plain
  `import pandas` in a `.lob` module work at all.
- `pytest`/`hypothesis` specifically are notlob's own tooling, not the
  target project's concern, so they're guaranteed available regardless
  of what's on `PATH` — see "Property & unit testing" below for how.

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

Since claims execute under the *target* interpreter (see Toolchain),
"always available" needs its own mechanism: the `#Tests`/`~property`
harness scripts append notlob's own site-packages directory to
`sys.path` as a fallback — Python searches the target interpreter's
own locations first, so a project with its own pinned `pytest`/
`hypothesis` keeps using it unchanged, and notlob's bundled copies
only fill the gap when the target has neither at all. Verified against
a target venv with neither installed: both `@given` and `approx`
resolved correctly, while a target-only third-party import in the same
module also resolved correctly.

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

Each claim batch is assembled into a self-contained harness script
(with lob-ref dependencies inlined, matching `notlob build`) and run
as a subprocess under a `PATH`-resolved interpreter; results are
parsed back from a `CLAIM`/`PASS`/`FAIL`/`ERROR` line protocol — the
same shape as the Haskell and TypeScript runners, for the same reason
(claims need to run under the target project's own toolchain, not
notlob's). See `notlob.bindings.python.runner`'s module docstring and
`notlob.bindings.python.harness` for the exact mechanism and protocol.
