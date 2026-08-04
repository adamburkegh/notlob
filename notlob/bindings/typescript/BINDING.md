# TypeScript Binding

Realizes notlob for TypeScript. Claims run through `tsx`; type-checking
runs through `tsc`.

## Toolchain

`tsx` (runs claims), `typescript`/`tsc` (type-checks), and `fast-check`
(property testing) come from npm. notlob is distributed via pip and
cannot ship npm packages, so a TypeScript project provides its own
toolchain:

- `notlob init --language typescript` scaffolds `package.json` (tsx +
  typescript + fast-check) and `tsconfig.json`.
- Run `npm install` to fetch them — the npm analog of `pip install`.

The runner discovers `tsx` (then `ts-node`) from the project's
`node_modules/.bin` first, then `PATH`; the linter discovers `tsc` the
same way. `fast-check` is located as a package directory rather than a
binary. On Windows the `.cmd` shim is preferred for executables (the
extensionless shim is not directly executable).

## Static call analysis

`extract_calls` scans each symbol's source text for bare function calls
— identifiers immediately followed by `(` that are not preceded by `.`
(which would indicate a method call).  The matched names minus the
symbol's own defined names and a set of TypeScript built-ins are used by
`add_uses_edges` to add `USES` edges in the name-graph.

Fidelity ceiling: method calls (`.foo()`) require type information that
is unavailable without running `tsc`, so they are excluded by design.
Higher-order calls through variables and dynamic dispatch are also
invisible.  The ceiling is real but bounded: bare function calls —
the dominant call form in functional-style TypeScript — are reliably
captured.

## Linting

`tsc --noEmit` — type-checking. Because `tsx` strips types and runs
without checking them, `tsc` is the only stage that catches type errors,
which makes it the binding's linter (correctness, not style).
Diagnostics map back to `.lob` section addresses. If `tsc` is not
installed, `notlob test` fails — a missing checker is never reported as a
pass.

The scaffolded `tsconfig.json` mirrors the linter's flags (target
`ES2020`, `DOM` lib, non-strict) so an editor and `notlob test` agree.

## Claims

| Claim       | Support                                                  |
|-------------|----------------------------------------------------------|
| `~example`  | yes — boolean expressions, `===` for equality            |
| `#Tests`    | yes                                                      |
| `~run`      | yes — included in `notlob build` output (entry point)    |
| `~property` | yes — fast-check; `fc` is injected into the claim scope automatically |

Equality assertions use `===`; the runner reports concrete left/right
values on failure for `a === b`. Other expressions are evaluated as
booleans.

## Runner

Each claim batch is assembled into a single `.ts` harness and executed
as a `tsx` subprocess; results are parsed back from a line protocol.
