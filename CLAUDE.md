# Notlob

Notlob is an experimental literate programming environment exploring the intersection of
document structure, formal claims, and LLM collaboration. The name is from the Monty Python
parrot sketch. It is not a palindrome.

The core hypothesis: a source file structured as a document — with prose, formal claims,
executable examples, and tests as distinct but co-located layers — produces better software
and better LLM collaboration than code with comments, or code and documentation as separate
artefacts.

This is an experiment, not a product. The ideas are being validated incrementally. The
literate infrastructure is largely independent of the execution substrate, which is
intentional.

---

## Philosophy

The intellectual lineage is Knuth's literate programming, Naur's theory-building view of
programming, and Dominic Fox's observation that LLMs are good at following theory-traces
in a codebase but lack the overarching theory that would let them extend it non-aberrantly.
The Confucian rectification of names (正名) is also in the background: names should fit the
shape of things, be community-owned, and be continuously rectified.

The key moves away from Knuth:

- The document structure is the primary innovation, not the tangling/weaving mechanism
- Claims (examples, properties, proofs) are a distinct syntactic layer between prose and code
- Tests live in a post-text appendix, as a different genre — assertional rather than
  discursive — bound into the same volume
- References (imports) live at the end as a bibliography, not at the top as preamble
- The module name is the document title, and translates deterministically to a filesystem
  path

The LLM collaboration story: a `.lob` file is self-contained context. Prose establishes
the concept. Claims make it checkable. Examples make it palpable. Tests nail it to the
executable surface. An LLM reading a well-structured `.lob` file has the theory, not just
the code.

---

## File Structure

A `.lob` file has two sections divided by `---`: the essay body and the post-text.

```
#Module Name            ← document title and module address

Prose establishing the concept...

    code block          ← indented, execution substrate (currently Python or Haskell)

~example                ← concrete executable claim
    expression == value

~property               ← abstract claim, verified by property testing
    forall x : Type. condition

##Subsection            ← heading hierarchy creates doc-node graph, auto-numbered

Further prose...

---                     ← semantic boundary: post-text begins here

#Tests                  ← reserved heading, compiler runs these

    expression == value
    expression == value

##boundary conditions   ← grouping headings within tests, for navigation

    expression == value

#References             ← reserved heading, compiler resolves these
    import Something
    from library import Thing
```

---

## Syntax Decisions

**Headings as module addresses.** `#Pricing Discount Strategies` is both the document
title and the module address. It translates deterministically to
`pricing/discount/strategies/` — lowercase, spaces to slashes. The author maintains the
title; the tooling derives the path. The `.` namespace separator is a machine convention
that should not leak into the human-facing layer.

**`---` as post-text boundary.** Everything after `---` is post-text. The compiler treats
`#Tests` and `#References` as reserved headings with special behaviour. `#Appendix:` is
available as an open extension point for domain-specific appendices.

**Claims as a distinct layer.** Claims (`~example`, `~property`, `~proof`) are not
comments and not code. They have one face pointing at the prose (they are part of the
explanation, attached to a doc-node) and another face pointing at the formal layer (they
make checkable assertions). The claim layer is not a gradient between prose and code; it
is a separate layer with its own syntax.

**Examples are curated witnesses.** An `~example` is chosen to make a specific design
decision palpable, not to provide coverage. Coverage is the `#Tests` appendix's job.
The inline example illuminates; the appendix exhausts.

**Test names are navigational.** In a large test appendix, heading groups and occasional
named tests provide navigation. Unnamed tests are anonymous witnesses — epistemically
humble, just facts. If a test needs a name, that name probably also deserves a doc-node
in the essay body.

**References as bibliography.** Imports at the end acknowledge what the argument depends
on, after the argument has been made. This mirrors academic convention and keeps the
opening of the file in the prose register.

**`binding.lob` is a reserved structural filename.** Each package directory may contain a
`binding.lob` that declares the execution substrate and property-testing library for all
modules in that package. It is the one file whose title names its *parent* address rather
than its own — `binding.lob` in `pricing/` carries the title `#Pricing`. The filename is a
tooling convention, not a module address; it is not subject to the title-as-path rule. The
name is a pun: it binds the package in the bibliographic sense and declares the technical
binding in the execution sense. `binding.lob` sigils:

```
~binding python          ← execution substrate
~property-testing hypothesis   ← property testing library
```

---

## Sample `.lob` File

```
#Pricing Discounts

A discount strategy applies a multiplier to a price, yielding a reduced price.
Strategies are values in [0,1] representing the proportion of the price to retain.
A value of 1.0 means no discount; 0.0 means free.

The choice of "proportion to retain" rather than "proportion to remove" is
deliberate — it composes naturally under multiplication. See ##Stacking Discounts.

    from decimal import Decimal

    def apply_discount(strategy: Decimal, price: Decimal) -> Decimal:
        return price * strategy

~example
    apply_discount(Decimal('0.8'), Decimal('100')) == Decimal('80')

##Stacking Discounts

When multiple strategies apply, they compose multiplicatively. A 20% discount
followed by a 10% discount yields 72% of the original price, not 70%.

~example
    apply_discount(Decimal('0.8'), apply_discount(Decimal('0.9'), Decimal('100'))) == Decimal('72')

~property
    forall s1 s2 in [0,1], price >= 0:
        apply_discount(s1, apply_discount(s2, price)) == apply_discount(s1 * s2, price)

---

#Tests

##boundary conditions
    apply_discount(Decimal('1'), Decimal('100')) == Decimal('100')
    apply_discount(Decimal('0'), Decimal('100')) == Decimal('0')
    apply_discount(Decimal('0.5'), Decimal('0')) == Decimal('0')

##composition
    apply_discount(Decimal('0.8'), apply_discount(Decimal('0.9'), Decimal('100'))) == Decimal('72')
    apply_discount(Decimal('0.9'), apply_discount(Decimal('0.8'), Decimal('100'))) == Decimal('72')

##regression: negative price bug 2024-03
    apply_discount(Decimal('0.3'), Decimal('1')) == Decimal('0.7')

#References
    from decimal import Decimal
    from hypothesis import given, strategies as st
```

---

## Tooling Architecture

The literate layer (parser, doc-node graph, claim runner, diagnostics) is independent of
the execution substrate. Code blocks are currently Python for ecosystem access (Hypothesis
for property testing, Pandas for data experiments). The plan is to support Haskell blocks
when the type safety story needs proper exploration. A new surface language, when it
arrives, will slot into the same harness as a transpilation layer.

**Parser:** Tree-sitter grammar for the `.lob` format. Headings, code blocks, claim
sigils, post-text boundary, reference blocks all become first-class AST nodes.

**Claim runner:**
- `~example` claims run as doctests
- `~property` claims run via Hypothesis
- `~proof` claims are reserved for future formal verification integration

**Diagnostics:** Failures report by doc-node address, not line number. A failing claim in
`##Stacking Discounts` says so. The node has a prose face, a claim face, and an executable
face; all three are candidates for being wrong.

**LLM harness:** Feed a `.lob` file as context; ask for extension or modification; evaluate
whether the linked structure produces less aberrant output than equivalent unstructured
code. This is an early experiment worth running before the claim runner is complete.

---

## What This Is Not

Not a production language. Not a compiler. Not making grand claims. The name is not a
palindrome and the project is not finished. It is an experiment in whether the document
structure is the right place to put the theory that Naur says lives in programmers' heads
and Fox says should be transmissible.

---
## Project Structure

`origin.md` is a long conversation giving background on the project, which is summarised here and in README.

Follow Python and Haskell conventions otherwise. As this is a radical experiment, keep other technologies boring as a rule.



