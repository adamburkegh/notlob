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
