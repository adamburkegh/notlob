# Notlob Language Design

## Philosophy

The intellectual lineage is Knuth's literate programming, Naur's
theory-building view of programming, and Dominic Fox's observation that
LLMs are good at following theory-traces in a codebase but lack the
overarching theory that would let them extend it non-aberrantly. The
Confucian rectification of names (正名) is also in the background: names
should fit the shape of things, be community-owned, and be continuously
rectified.

The key moves away from Knuth:

- The document structure is the primary innovation, not the
  tangling/weaving mechanism
- Claims (examples, properties, proofs) are a distinct syntactic layer
  between prose and code
- Tests live in a post-text appendix, as a different genre — assertional
  rather than discursive — bound into the same volume
- References (imports) live at the end as a bibliography, not at the top
  as preamble
- The module name is the document title, and translates deterministically
  to a filesystem path

The LLM collaboration story: a `.lob` file is self-contained context.
Prose establishes the concept. Claims make it checkable. Examples make it
palpable. Tests nail it to the executable surface. An LLM reading a
well-structured `.lob` file has the theory, not just the code.

**Aesthetic goal.** A `.lob` file should feel like a well-written
technical book chapter — the kind where an argument is made in prose,
illuminated by examples, and nailed to executable ground. This aesthetic
is not decorative; it is the hypothesis. If the format does not feel like
that, the format is wrong. The binding layer is responsible for honouring
this aesthetic in its own idiom: a good binding chooses test and property
tools whose syntax reads as claims, not as boilerplate.

---

## File Structure

A `.lob` file has two sections divided by `---`: the essay body and the
post-text.

```
#Module Name        ← document title and module address

Prose establishing the concept...

    code block      ← indented; execution substrate (Python or Haskell)

~example            ← concrete executable claim
    expression == value

~property           ← abstract claim, verified by property testing
    @given(...)
    def _(x):
        assert condition

##Subsection        ← heading hierarchy creates doc-node graph

Further prose...

---                 ← semantic boundary: post-text begins here

#Tests              ← reserved heading, compiler runs these

    expression == value
    expression == value

##boundary conditions   ← grouping headings within tests

    expression == value

#Binding            ← reserved heading, declares execution substrate
    ~language python
    ~property-testing hypothesis

#References         ← reserved heading, compiler resolves these
    from library import Thing
```

---

## Syntax Decisions

**Headings as module addresses.** `#Pricing Discount Strategies` is both
the document title and the module address. It translates deterministically
to `pricing/discount/strategies/` — lowercase, spaces to slashes. The
author maintains the title; the tooling derives the path. The `.`
namespace separator is a machine convention that should not leak into the
human-facing layer.

**`---` as post-text boundary.** Everything after `---` is post-text. The
compiler treats `#Tests`, `#Binding`, and `#References` as reserved
headings with special behaviour. `#Appendix:` is available as an open
extension point for domain-specific appendices.

**Claims as a distinct layer.** Claims (`~example`, `~property`, `~proof`)
are not comments and not code. They have one face pointing at the prose
(they are part of the explanation, attached to a doc-node) and another
face pointing at the formal layer (they make checkable assertions). The
claim layer is not a gradient between prose and code; it is a separate
layer with its own syntax.

**Examples are curated witnesses.** An `~example` is chosen to make a
specific design decision palpable, not to provide coverage. Coverage is
the `#Tests` appendix's job. The inline example illuminates; the appendix
exhausts.

**`~property` syntax is binding-determined.** The body of a `~property`
block uses the real syntax of the declared property-testing library. For
the Python/Hypothesis binding, this is a `@given`-decorated function
body. The literate processor does not invent a property mini-language;
the binding owns the syntax entirely.

**Test names are navigational.** In a large test appendix, `##` heading
groups provide navigation. Unnamed tests are anonymous witnesses —
epistemically humble, just facts.

**References as bibliography.** Imports at the end acknowledge what the
argument depends on, after the argument has been made. Code blocks in the
essay body do not contain imports; `#References` is the authoritative
import list.

**Node addresses and labels are distinct.** Every named node in the
name-graph has two representations:

- *Address* — the globally unique machine identifier, derived
  deterministically from the node's position in the package hierarchy.
  A module address is its path: `pricing/discounts`. A subheading
  address appends a fragment: `pricing/discounts#Stacking Discounts`.
  Addresses are not written by authors; they are computed by tooling.

- *Label* — the human-readable name as written in the source file:
  `Stacking Discounts`. Labels are locally unique within their parent
  node. The address is derived from the label plus context.

The two are mechanically related: `address = parent_address + "#" +
label`. This mirrors the URI fragment convention and is isomorphic to
an RDF URI, enabling a mechanical export to RDF/Turtle as a build
artifact (planned, not yet implemented).

**Cross-references use heading sigil syntax and are scope-resolved.**
A reference in prose reuses the heading sigils but in reference
position:

- `##Name` refers to a subheading node — resolved against the current
  module's subheadings. Mirrors the `##` definition syntax.
- `#Name` refers to any other named node — resolved in order:
  1. A symbol defined in the current module (function, class,
     constant extracted from code blocks).
  2. A subheading of the current module (fallback for bare `#`).
  3. An imported module declared in the current `#References`
     section.

`#` is the universal dereference operator for the name-graph.
NodeKind distinguishes what kind of thing was found; the reference
syntax does not need to encode it. This means `#NUMERALS` in prose
is a live cross-reference to the constant definition, with the same
hyperlink semantics as a subheading or module reference. All named
things are first-class in prose.

This means `#References` does double duty: it is a bibliography
(acknowledging what the argument depends on) and a scope declaration
(bringing module labels into reference resolution context). An
unresolved reference is an error; the name-graph is closed-world.
Cross-references are machine-validated against the name-graph.

**`binding.lob` is a reserved structural filename.** Each package
directory must contain a `binding.lob` that declares the execution
substrate and property-testing library for all modules in that package.
It is the one file whose title names its *parent* address rather than its
own — `binding.lob` in `pricing/` carries the title `#Pricing`. The
filename is a tooling convention, not a module address; it is not subject
to the title-as-path rule. The name is a pun: it binds the package in the
bibliographic sense and declares the technical binding in the execution
sense.

**`#Binding` is inherited from the package.** A module file that lacks a
`#Binding` section inherits its binding from the package's `binding.lob`.
A standalone `.lob` file not in a named package may include `#Binding`
directly in its own post-text. Any file in a directory structure or
multi-file package without a `binding.lob` is an error.

**Block termination.** All indented blocks (code, `~example`, `~property`,
`#Tests` assertions) use the same rule: dedent terminates. A block body
is the contiguous region following the opener where every non-blank line
is indented. Blank lines within the region are part of the block. The
block ends at the first non-blank line with less indentation than the
body. There are no special-case terminators; headings and `~sigils`
terminate blocks only because they start at column zero.

**Cross-references use `##Name` syntax.** A cross-reference to a doc-node
in prose uses the same `##Name` sigil as a subheading. A `##` at the
start of a line is a heading; `##` mid-prose is a reference. The tooling
validates references against the doc-node graph.

---

## Sample `.lob` File

```
#Pricing Discounts

A discount strategy applies a multiplier to a price, yielding a reduced
price. Strategies are values in [0,1] representing the proportion of the
price to retain. A value of 1.0 means no discount; 0.0 means free.

The choice of "proportion to retain" rather than "proportion to remove"
is deliberate — it composes naturally under multiplication.
See ##Stacking Discounts.

    def apply_discount(strategy: Decimal, price: Decimal) -> Decimal:
        return price * strategy

~example
    apply_discount(Decimal('0.8'), Decimal('100')) == Decimal('80')

##Stacking Discounts

When multiple strategies apply, they compose multiplicatively. A 20%
discount followed by a 10% discount yields 72% of the original price,
not 70%.

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
    apply_discount(Decimal('0.5'), Decimal('0')) == Decimal('0')

##composition
    (apply_discount(Decimal('0.8'),
                    apply_discount(Decimal('0.9'), Decimal('100')))
     == Decimal('72'))
    (apply_discount(Decimal('0.9'),
                    apply_discount(Decimal('0.8'), Decimal('100')))
     == Decimal('72'))

#Binding
    ~language python
    ~property-testing hypothesis

#References
    from decimal import Decimal
    from hypothesis import given, strategies as st
```

---

## Tooling Architecture

The literate layer (parser, name-graph, claim runner, diagnostics) is
independent of the execution substrate. Code blocks are currently Python
for ecosystem access (Hypothesis for property testing, Pandas for data
experiments). The plan is to support Haskell blocks when the type safety
story needs proper exploration.

**Parser:** Lark grammar (`notlob/grammar.lark`) for the `.lob` format.
Headings, code blocks, claim sigils, post-text boundary, and reserved
post-text sections all become first-class AST nodes. The grammar file is
the canonical syntax specification; the parser produces a Lark `Tree`
serialisable to JSON for use by tooling and LLM context. Parse tree
access will also be exposed via MCP.

**Name-graph:** The central data structure of the tooling layer. Every
named thing in a `.lob` file or package is a node; relationships between
them are edges. The name-graph is built in stages:

- *Stage 1 — structural names.* Module addresses and subheading nodes,
  derived from the `.lob` parser alone. No language binding required.
  Sufficient for cross-reference validation, doc-node navigation, and
  LLM context. This layer is binding-agnostic and always available.

- *Stage 2 — defined symbols.* Code-level names (functions, classes,
  top-level assignments) extracted by a language-specific analyser over
  code block content. For Python, `ast.parse` suffices. Each symbol is
  located under its containing structural node. This layer is where the
  binding earns its keep.

- *Stage 3 — reference edges.* Uses as well as definitions: which claims
  reference which symbols, which prose cross-references which nodes. The
  graph becomes a navigable map of the argument.

- *Stage 4 — cross-file.* Module addresses resolved across a package,
  with `binding.lob` providing the package root. The name-graph spans
  the full package.

The seam between stage 1 and stage 2 is the binding boundary. The
structural layer is the common vocabulary across all languages; the
symbolic layer is language-specific richness.

**Binding kit architecture:** A binding is not a single function; it is a
kit of cooperating tools that share a language substrate. The binding
layer is organised language-first:

```
notlob/bindings/
    __init__.py          ← BindingKit dataclass + Extractor type alias
    python/
        __init__.py      ← assembles the Python kit; exposes `kit`
        symbols.py       ← extract_symbols for stage-2 name-graph
        hypothesis.py    ← ~property-testing (future)
        pytest.py        ← ~testing runner (future)
    haskell/             ← future
        __init__.py
        symbols.py
```

`BindingKit` is a dataclass that composes callables — one per tooling
concern — so the name-graph and claim runner can ask for exactly the
capability they need without coupling to a particular language:

```python
@dataclass
class BindingKit:
    extract_symbols: Extractor
    # future fields: assemble, run_examples, run_properties, ...
```

The declarations in a `#Binding` section (`~language python`,
`~property-testing hypothesis`, `~testing pytest`) map to submodule
choices within the language package. The language is the primary axis;
the tool components are secondary. A package that declares
`~language python` gets `bindings.python.symbols` for the name-graph
and will eventually get `bindings.python.pytest` for its test runner.

**Claim runner:**
- `~example` claims run as doctests
- `~property` claims are executed using the declared property-testing
  library
- `~proof` claims are reserved for future formal verification integration

**Diagnostics:** Failures report by doc-node address, not line number. A
failing claim in `##Stacking Discounts` says so. The node has a prose
face, a claim face, and an executable face; all three are candidates for
being wrong.

**LLM harness:** Feed a `.lob` file as context; ask for extension or
modification; evaluate whether the linked structure produces less aberrant
output than equivalent unstructured code. This is an early experiment
worth running before the claim runner is complete.

---

## Later Features

**Cross-reference aliasing.** Cross-references use `##Name` syntax in
prose, validated against the doc-node graph. A future extension would
allow aliasing long reference names — display text separate from the
node address, as in LaTeX `\ref` with custom text or named imports in
programming languages.

**Kit bindings.** A `#Binding` section should eventually be able to
import a named `.lob` package defining a standard toolset —
`import notlob/bindings/python-hypothesis` — making the binding itself a
literate document inspectable in the same format.

---

## What This Is Not

Not a production language. Not a compiler. Not making grand claims. The
name is not a palindrome and the project is not finished. It is an
experiment in whether the document structure is the right place to put
the theory that Naur says lives in programmers' heads and Fox says should
be transmissible.
