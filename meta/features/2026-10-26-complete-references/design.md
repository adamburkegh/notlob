# Bookmark: complete reference extraction for TypeScript and Haskell

**Status:** scheduled for design and discussion (Adam, 2026-10-26). Not
started. Not needed for the release.
**Origin:** slice 6a of `2026-10-23-name-graph-as-parse-tree`, and the
limitation recorded in `meta/bugs/2026-10-22-mutual-references/bug.md`.

## The problem in one example

Loading follows need: module A's code is loaded with module B's only
when A lists B **and A's code uses a name B's code defines**. "Uses" is
read from the graph's `USES` edges, which come from each binding's
`extract_calls`. So the rule is only as good as that function.

```
#Core                               #Demo
    def double(n): ...                  VALUE = double(21)
Prose cites #Demo.                  #References
#References                             #Core
    #Demo
```

Both list each other. Only Demo's code uses Core's. With Python, notlob
sees that: Demo needs Core, Core merely cites Demo, and both run. The
same two modules in TypeScript or Haskell are reported as
`circular code dependency: core -> demo -> core`, because notlob cannot
trust what those bindings' extractors say, and falls back to treating
every listing as a need (except a listing of a module below you in the
address tree).

## Why it cannot trust them

What each `extract_calls` sees today:

| binding | sees | misses | sees wrongly |
|---|---|---|---|
| Python | every name read (`ast.Name` loads), less builtins | dynamic access only (`getattr`, `eval`) | nothing |
| TypeScript | `name(` not after a `.` | constants (`MAX`), classes (`new Shape`), types, a function passed as a value (`xs.map(double)`) | nothing much |
| Haskell | every lowercase identifier, by regex over the raw text | constructors and types (`Circle 1.0`, `Shape`) | names inside strings and comments |

A miss is the dangerous one: notlob would call a real use a citation,
not load B, and the claim fails with a name error that points nowhere
useful. A false sighting is milder: an unneeded load, or a false cycle.
`BindingKit.complete_references` is how a binding says "my extraction
sees every use, outside strings and comments"; only Python says so.

The same gaps show in the graph itself for those bindings: missing
`USES` edges in `notlob graph`, `query callers` and `callees`, and the
`[imports]` check (an import used only through a constant can be
reported unused).

## Options, for the discussion

1. **Widen the existing extractors.** TypeScript already has a tokenizer
   (`bindings/typescript/tokenizer.py`) that knows strings and comments:
   every identifier not after a `.`, less the module's own locals and
   builtins. Haskell: tokenise past strings and comments, and include
   uppercase names (constructors, types). Standard library only. Changes
   their `USES` edges and about 20 tests (estimate from 2026-10-22).
2. **Ask the real compilers** (the TypeScript compiler API, GHC's
   `-ddump-` output or the GHC API). Exact, but a new dependency and a
   new technology per binding: a design conversation in its own right.
3. **Leave it** as a documented limitation: in those bindings, modules
   that cite each other must not both list each other.

Questions for the discussion: is option 1 enough to set
`complete_references` for each, and how would we know (a test corpus of
uses each must find)? Should "complete" be per binding, or per kind of
name?
