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

## Static call analysis

`extract_calls` scans each symbol's source text with a regex for
lowercase identifiers, then subtracts the names defined in the same
block and a fixed set of Haskell keywords.  The survivors are treated as
references to other top-level symbols and used by `add_uses_edges` to
add `USES` edges in the name-graph.

Fidelity ceiling: operator sections, point-free compositions, and
qualified names contribute only their leaf (e.g. `Data.List.sort` →
`sort`).  Locally-bound names introduced by `let`/`where` may appear
as false positives if they happen to match another top-level symbol —
graph resolution drops them when no matching address exists.

## Property & unit testing

- `~property` claims run in their own `runghc` subprocess with
  `Test.QuickCheck` loaded; the first top-level function in the block
  is the property.
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
