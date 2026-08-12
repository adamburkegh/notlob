# Notlob Language Reference

Notlob is a literate programming format. Source files (`.lob`) combine
prose, executable code, and verifiable claims in a single document.
A `.lob` file is read as structured text,
executed as a program, rendered as a document, and traversed as a
name-graph — all from the same source.

---

## File structure

A `.lob` file is UTF-8 text with this shape:

```
#Module Title

Body — prose and code, organised into subheadings.

---

Post-text — reserved sections (#Tests, #Binding, #References, #Appendix).
```

The title line is required. The `---` separator and post-text are
optional. Everything before `---` is the **body**; everything after
is the **post-text**.

---

## Module title

The first line must be a `#Title` heading. The title is the module's
human-facing name and determines its address in the project graph.

Address derivation:

- `#Roman Numerals`         → `roman/numerals`
- `#Pricing Discounts`      → `pricing/discounts`
- `#HTTP Client`            → `http/client`

Words are lowercased and separated by `/`. The tooling enforces
consistency: `notlob test` reports an address mismatch if the
title-derived address does not match the file path.

---

## Body

The body contains prose paragraphs and indented code blocks, optionally
organised into subheadings.

**Prose** — ordinary paragraphs at column 0.

**Code** — indented 4 spaces. Contiguous indented lines (blank lines
permitted within) form one code block.

**Claims** — `~sigil` lines at column 0, followed by indented content.
See the Claims section below.

**Subheadings** — `##Name` at column 0, introducing a named section.

**Bullet lists** — lines beginning with `* ` (or a bare `*`) at column 0.
Consecutive bullet lines form one list. Only `*` is a bullet; an
indented `*` line is code, not a bullet. Prefer prose for explanation:
`notlob check` flags more than one bullet list in a single section as a
style smell (see Linting and checks).

```
#Fibonacci

Computes Fibonacci numbers recursively.

    def fib(n: int) -> int:
        if n <= 1:
            return n
        return fib(n - 1) + fib(n - 2)

~example
    fib(10) == 55
    fib(0)  == 0

##Memoised variant

    from functools import lru_cache

    @lru_cache
    def fib_fast(n: int) -> int:
        if n <= 1:
            return n
        return fib_fast(n - 1) + fib_fast(n - 2)
```

---

## Claims

Claims are verifiable statements attached to the module. Each begins
with a `~sigil` line at column 0 and is followed by indented content.

The sigil vocabulary is closed: `~example`, `~run`, and `~property` are
the only recognised claim sigils. An unrecognised `~word` is a parse
error, not a silent no-op. (`~test` is a related but separate sigil,
legal only inside a `#Tests` `##group` — see [#Tests](#tests) below.)

### ~example

One or more boolean expressions, each expected to be true.

```
~example
    fib(10) == 55
    fib(1)  == 1
```

Run during `notlob test`. Not included in `notlob build` output.

### ~property

A property-based test using whichever property-testing library the
binding provides — Hypothesis for Python, QuickCheck for Haskell,
fast-check for TypeScript. No declaration needed beyond `~language`;
this example is the Python binding's Hypothesis syntax. Receives
`@given` decoration automatically; authors do not import the library
directly.

```
~property
    @given(n=st.integers(min_value=0, max_value=50))
    def _(n):
        assert fib(n) >= 0
```

Named properties (`~property commutativity`) create a navigable node
in the name-graph.

### ~run

Code that executes during `notlob run` (and in `notlob build` output)
only — never during `notlob test`. Side-effecting code (printing, I/O)
belongs here or in a function called from here.

```
~run
    print(fib(10))
```

`~run` takes an optional mode — a closed pair, not free text:

- `~run on-invocation` (the default for bare `~run`) fires only when
  the built artifact is the thing actually being executed, not when
  something else merely imports it. The notlob equivalent of
  `if __name__ == "__main__":`.
- `~run on-load` fires unconditionally, the moment the artifact is
  loaded at all — the natural fit for browser-target code (DOM wiring,
  event listeners), where being loaded by the page *is* the deliberate
  execution moment.

Both can appear in the same module — code that should always wire up
on load, plus a heavier entry point that only fires when directly
invoked, are not mutually exclusive.

```
~run on-load
    document.getElementById('run').addEventListener('click', runAll);

~run on-invocation
    console.log('running standalone');
```

Support is binding-dependent:

- **Python** — `on-invocation` is the normal case; `on-load` is legal
  but unusual.
- **TypeScript** — both are meaningful: `on-invocation` for
  Node-targeted code, `on-load` for browser-targeted code.
- **Haskell** — `on-load` is a build-time error (Haskell's `import`
  never runs `IO` actions merely by loading a module, so it has no
  meaningful translation there). Bare `~run` and `~run on-invocation`
  are equivalent.

---

## Post-text sections

After the `---` separator, the post-text contains named sections
(`#SectionName`). Four have reserved meaning:

### #Tests

Assertion blocks — epistemically humble, exhaustive, grouped by `##`
subheadings. Bare assertions have the same syntax as `~example` but
belong to the appendix rather than the argument. Prose commentary may
be freely interleaved with assertions, both directly under `#Tests`
and within a `##group` — the same literate-programming style as the
rest of the document.

```
#Tests

Basic identities, checked directly against the closed-form values.

##base cases
    fib(0) == 0
    fib(1) == 1

##larger values
    fib(10) == 55
    fib(20) == 6765
```

An individual assertion can be named with `~test <name>`, so it is
addressable the way `def test_specific_thing():` names a pytest
test — unlike a bare line, which is only addressable via its `##group`
heading. `~test` has no bare (nameless) form; naming is the point of
using it over a plain assertion line.

```
##larger values
    fib(10) == 55

~test known_large_value
    fib(50) == 12586269025
```

Bare assertions, `~test <name>` blocks, and prose commentary can repeat
and interleave in any order within one group. All assertion lines
sharing one `##group` or one `~test` block share a single address —
e.g. `roman/numerals#Tests#larger values` for the bare block above, or
`roman/numerals#Tests#larger values#known_large_value` for the named
one — distinguished within the runner by source line, not a separate
address per line.

### #Binding

Project-level configuration. Appears in `binding.lob` only.

```
#Binding
    ~language python
```

Available declarations:

| Sigil                  | Values                                                    |
|------------------------|------------------------------------------------------------|
| `~language`            | `python`, `haskell`, `typescript`                          |
| `~external`            | a filename, relative to the project root, that `notlob build` should be aware of but not assemble |
| `~on-build`            | a script path, in the project's own language, run after `notlob build` assembles artifacts |
| `~keep-generated-src`  | a directory path for writing generated source alongside the normal build output, for debugging |

Property-testing (Hypothesis, QuickCheck, fast-check) and unit-testing
(pytest) tools are provided by the binding itself, not declared here —
see [Toolchains](#toolchains).

### #References

Declares this module's dependencies.

```
#References
    #Fibonacci          ← lob module reference (resolved by title)
    from decimal import Decimal   ← language import (passed through)
```

Two kinds of entry:
- **Lob-ref** — a line beginning with `#`. Resolved to a module in the
  same project by title; that module's names are available in this
  module's namespace.
- **Language import** — any other non-blank line. Passed through
  verbatim to the language runtime.

Lob module imports must be declared explicitly. There is no implicit
package import; each module lists exactly what it uses.

### #Appendix

An open extension point for domain-specific appendices — a glossary,
references, supplementary notes — that don't fit the claim-driven
`#Tests` shape. `#Appendix` optionally carries a title (`#Appendix
Glossary`); its body is a regular body (prose, code, subheadings,
claims), so `##Subheading` inside it works exactly like a body
subheading, including being cross-referenceable by `##Name` from the
main module body.

```
---

#Appendix Glossary

##Discount Strategy

A multiplier in [0,1] representing the fraction of the price to retain.
```

```
See ##Discount Strategy for the definition.
```

---

## Project structure

A notlob project is a directory tree rooted at `binding.lob`.

```
my-project/
  AGENTS.md              agent orientation (checked in)
  binding.lob            project manifest
  hello.lob              a module  (address: hello)
  pricing/
    discounts.lob        address: pricing/discounts
  notlob-docs/           generated reference docs (not checked in)
    LANGUAGE.md
```

`binding.lob` is the project root marker. It is not a regular module —
it carries only the `#Binding` post-text section.

**Module address** — the file path relative to the project root,
without the `.lob` extension. Forward slashes on all platforms.

---

## Cross-references in prose

`#Name` and `##Name` in prose are live cross-references validated
against the name-graph.

- `##Name` — refers to a subheading in the current module.
- `#Name` — resolves in order: symbol in current module, subheading in
  current module, module declared in `#References`.

A reference's first letter must be uppercase (or, for scripts with no
case distinction at all — CJK, Arabic, Hebrew, Thai, Devanagari, etc.
— any letter). This is what tells `#pricing` (lowercase, stays
ordinary prose — a casual mention, not a link) apart from `#Pricing`
(a real cross-reference); `#日本語` needs no capitalisation to count,
since Japanese has no case to require. Every word in a multi-word
reference (`#Pricing Discounts`) is checked the same way.

An unresolved reference is a build error. References are
machine-validated; rendered output cannot contain dead links.

---

## Worked example

```
#Pricing Discounts

A discount strategy is a multiplier in [0,1] representing the fraction
of the price to retain. See ##Stacking Discounts.

    def apply_discount(strategy: Decimal, price: Decimal) -> Decimal:
        return price * strategy

~example
    apply_discount(Decimal('0.8'), Decimal('100')) == Decimal('80')

##Stacking Discounts

Strategies compose multiplicatively. Two successive discounts of 20%
and 10% yield 72% of the original — not 70%.

~example
    (apply_discount(Decimal('0.8'),
                    apply_discount(Decimal('0.9'), Decimal('100')))
     == Decimal('72'))

~property
    @given(
        s1=st.decimals(min_value=0, max_value=1, allow_nan=False),
        s2=st.decimals(min_value=0, max_value=1, allow_nan=False),
        price=st.decimals(min_value=Decimal('0'), allow_nan=False),
    )
    def _(s1, s2, price):
        assert (apply_discount(s1, apply_discount(s2, price))
                == apply_discount(s1 * s2, price))

---

#Tests

##boundary conditions
    apply_discount(Decimal('1'), Decimal('100')) == Decimal('100')
    apply_discount(Decimal('0'), Decimal('100')) == Decimal('0')

#Binding
    ~language python

#References
    #Pricing Base
    from decimal import Decimal
```

---

## Linting and checks

Notlob enforces quality at two levels, both run automatically during
`notlob test` (and `notlob build`).

**Linting** — each language binding may define a linter. When it does,
that linter is part of the test contract. 
If a binding declares a linter but its tool is not
installed, `notlob test` fails with an error rather than silently
skipping the check — a missing checker is never reported as a pass. A
binding may also declare no linter at all, which is fine.

**Semantic checks** (`notlob check`) — analyse the name-graph for
consistency. One is an error; the rest are advisory nudges:

| Check         | Severity  | Flags                                            |
|---------------|-----------|--------------------------------------------------|
| `imports`     | error     | a module imports another but uses none of its symbols |
| `typos`       | advisory  | near-duplicate symbol names (likely misspellings) |
| `conventions` | advisory  | inconsistent verb prefixes for one concept (`get_` vs `fetch_`) |
| `titles`      | advisory  | near-duplicate module / subheading titles         |
| `references`  | advisory  | a symbol named in prose without a `#` cross-reference |
| `style`       | advisory  | more than one bullet list in a section            |

`notlob check -v` adds a coverage summary; `--only <names>` runs a
subset. Advisory findings never fail the build; only error-severity
findings (and a missing linter) do.

---

## Toolchains

Each language binding needs its tools available; how they are provided
differs by ecosystem.

- **Python** — `ruff`, `pytest`, and `hypothesis` ship with notlob and
  are always available, regardless of your project's own environment.
  Everything else — the module's own code, and any third-party
  libraries it imports — runs under whatever `python` your shell's
  `PATH` resolves (an activated venv, an asdf/mise shim, ...), the same
  way `ghc`/`tsc`/other external toolchains work: install your own
  dependencies the normal way (venv, `requirements.txt`,
  `pyproject.toml`) and notlob picks them up from there.
- **TypeScript** — `tsx` (runs claims) and `typescript`/`tsc`
  (type-checks) come from npm. `notlob init --language typescript`
  scaffolds `package.json` and `tsconfig.json`; run `npm install` to
  fetch them (the npm analog of `pip install`).
- **Haskell** — `runghc` and `hlint` must be on `PATH` (e.g. via Stack).

---

## Commands

```
notlob init [--language LANG]    scaffold a new project in the current dir
notlob test [file]              run all claims (project or one file)
notlob check [--only ...] [-v]  run semantic checks on the name-graph
notlob build [file]             assemble to source artifacts in dist/
notlob run <file>               execute a module
notlob weave [file]             render as Markdown
notlob new <name>               create a new module
notlob docs [--output DIR]      write this reference to notlob-docs/
notlob query search <pattern>   find nodes by label (bare word = substring)
notlob query content <address>  show prose and code at an address
notlob query children <address> list child nodes
notlob query imports <address>  modules imported by an address
notlob query imported-by <addr> modules that import an address
notlob graph [--format json|turtle]  export the package name-graph
notlob mcp                      start the MCP tool server (stdin/stdout)
```

File arguments accept either a filesystem path or a module address via
`-m` (e.g. `notlob test -m pricing/discounts`).
