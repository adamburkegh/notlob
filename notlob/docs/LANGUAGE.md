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

Post-text — reserved sections (#Tests, #Binding, #References).
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

### ~example

One or more boolean expressions, each expected to be true.

```
~example
    fib(10) == 55
    fib(1)  == 1
```

Run during `notlob test`. Not included in `notlob build` output.

### ~property

A property-based test using the declared `~property-testing` library
(default: Hypothesis). Receives `@given` decoration automatically;
authors do not import Hypothesis directly.

```
~property
    @given(n=st.integers(min_value=0, max_value=50))
    def _(n):
        assert fib(n) >= 0
```

Named properties (`~property commutativity`) create a navigable node
in the name-graph.

### ~test

A pytest test function. Must be a `def test_*` function.

```
~test
    def test_base_cases():
        assert fib(0) == 0
        assert fib(1) == 1
```

### ~run

Code that executes during `notlob run` only — not during `notlob test`.
The notlob equivalent of `if __name__ == "__main__"`. Side-effecting
code (printing, I/O) belongs here or in a function called from here.

```
~run
    print(fib(10))
```

---

## Post-text sections

After the `---` separator, the post-text contains named sections
(`#SectionName`). Three have reserved meaning:

### #Tests

Assertion blocks — epistemically humble, exhaustive, grouped by `##`
subheadings. Assertions have the same syntax as `~example` but belong
to the appendix rather than the argument.

```
#Tests

##base cases
    fib(0) == 0
    fib(1) == 1

##larger values
    fib(10) == 55
    fib(20) == 6765
```

### #Binding

Project-level configuration. Appears in `binding.lob` only.

```
#Binding
    ~language python
    ~property-testing hypothesis
    ~unit-testing pytest
```

Available declarations:

| Sigil                | Values                    |
|----------------------|---------------------------|
| `~language`          | `python`, `haskell`       |
| `~property-testing`  | `hypothesis`              |
| `~unit-testing`      | `pytest`                  |

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
    ~property-testing hypothesis
    ~unit-testing pytest

#References
    #Pricing Base
    from decimal import Decimal
```

---

## Commands

```
notlob test [file]              run all claims (project or one file)
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
notlob graph                    export the package name-graph as JSON
```

File arguments accept either a filesystem path or a module address via
`-m` (e.g. `notlob test -m pricing/discounts`).
