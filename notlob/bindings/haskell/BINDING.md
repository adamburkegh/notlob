# Haskell Binding

Realizes notlob for Haskell. Claims run through `runghc`; linting runs
through `hlint`.

## Toolchain

`runghc` (runs claims) and `hlint` (lints) must be available on `PATH` —
typically via [Stack](https://docs.haskellstack.org). The linter also
falls back to `stack exec -- hlint` when Stack is present. There is no
notlob-generated manifest: Haskell tooling is installed system-wide
(`stack install hlint`) rather than per-project.

If `hlint` is not found, `notlob test` fails — a missing checker is
never reported as a pass.

## Linting

`hlint --json` — idiomatic-style hints (redundant brackets, suggested
combinators, etc.). Diagnostics map back to `.lob` section addresses.
Unlike the Python linter, hlint is style-only and needs no cross-module
name resolution.

## Property & unit testing

- `~property-testing quickcheck` — `~property` claims run in their own
  `runghc` subprocess with `Test.QuickCheck` loaded; the first top-level
  function in the block is the property. Without this declaration,
  `~property` claims report `SKIP`.
- `#Tests` assertions are Boolean Haskell expressions.

## Claims

| Claim       | Support                                                  |
|-------------|----------------------------------------------------------|
| `~example`  | yes — Boolean expressions, `==` for equality             |
| `~property` | yes — QuickCheck (`~property-testing quickcheck`)        |
| `#Tests`    | yes                                                      |
| `~run`      | yes — assembled source must define `main :: IO ()`       |

## Runner

Each claim batch is assembled into a standalone Haskell harness (module
header + inlined dependency modules + the assertions) and executed as a
`runghc` subprocess; results are parsed back from a line protocol.
