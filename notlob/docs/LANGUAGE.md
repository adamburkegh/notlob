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

The formal syntax is `grammar.lark`, written beside this file by
`notlob docs`. Where this reference is unclear at an edge, the grammar
decides.

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

A claim's body ends at the first line that is neither indented nor
blank. An indented code block that follows a claim directly, even
across blank lines, is therefore part of the claim, not a code block of
its own. Always put at least a line of prose between a claim and the
code that comes next; it keeps the claim and the code apart, and it is
better literate style anyway, since prose should introduce code. When a
definition does get absorbed this way, `notlob test` reports the line as
a statement where an assertion was expected and says why.

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
test — unlike a bare line, which is only addressable through its block
(`roman/numerals#Tests#larger values#test#1`). `~test` has no bare
(nameless) form; naming is the point of using it over a plain assertion
line.

```
##larger values
    fib(10) == 55

~test known_large_value
    fib(50) == 12586269025
```

Bare assertions, `~test <name>` blocks, and prose commentary can repeat
and interleave in any order within one group. All assertion lines
sharing one block of bare lines or one `~test` block share a single
address — `roman/numerals#Tests#larger values#test#1` for the bare block
above (a block is numbered within its group, and prose commentary ends
it), or `roman/numerals#Tests#larger values#known_large_value` for the
named one — and the runner reports each assertion under it with its own
source line, not a separate address per line.

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
package import (not for siblings, not for the project); each module lists
exactly what it uses or cites.

**Listing, citing and loading.** A listing says this module is in
conversation with that one. It does three separate things:

- **Citing.** A prose `#Name` that names a module resolves only if the
  module is listed. Siblings list each other to cite one another.
- **Using.** A module may use only names from modules it lists. The
  Python linter reports a name from an unlisted module as undefined.
- **Loading.** A module runs with the code of the modules it *needs*: those
  it lists whose names its code uses (calls, references, in the body or in
  its claims; a name inside a string or comment does not count), and what
  those need, each once and before it. A listing that the code does not
  use is a *citation*: it loads nothing.

So if `Top` lists `Middle` and `Middle` lists `Base`, `Middle`'s code can
use `Base` whether it is loaded by itself or by `Top`: a module that works
on its own works when another module uses it, and `Top` need not list
`Base` just to make `Middle` run.

**Listings may be circular.** An overview module can list the parts it
explains and cite them in prose; the parts can list the overview, or
anything above them. Only a cycle of *need* is an error: if `A`'s code
uses names `B` defines and `B`'s code uses names `A` defines, no load order
exists, and `notlob test` reports `circular code dependency: a -> b -> a`.
Cycles made of citations are fine.

A listing you neither use in code nor mention in prose is an `[imports]`
error. A module is not loaded just because it is listed, so do not list
one in the hope of running its top-level code; use it. Where a binding
cannot tell what a module uses, the address tree decides: a listing of a
descendant is a citation and any other listing is loaded. Anything else a
lob-ref does or does not bring into scope depends on the binding; see
[Toolchains](#toolchains).

### #Appendix

An open extension point for content that doesn't belong in the main
narrative — a glossary, supporting helper code, supplementary notes —
without being test-support specifically. `#Appendix` optionally
carries a title (`#Appendix Glossary`); its body is a regular body
(prose, code, subheadings, claims), so `##Subheading` inside it works
exactly like a body subheading, including being cross-referenceable by
`##Name` from the main module body.

Code blocks in `#Appendix` are assembled exactly like main-body code —
in scope for `~example`/`#Tests`/`~property` claims, and included in
`notlob build`/`notlob run` output. There's no test-only special case:
an author might move a shared test fixture there, or just as easily a
supporting helper that the main argument's code genuinely calls at
runtime — both need to actually work, not just parse.

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

**Discovery** — whole-project commands (`test`, `check`, `build`,
`graph`) take every `**/*.lob` under the project root, including any
nested project's modules. There is no ignore mechanism yet.

**One namespace per module** — a subheading and a symbol in the same
module cannot share a name. The collision is reported as an error naming
both lines.

---

## Cross-references in prose

`#Name` and `##Name` in prose are live cross-references validated
against the name-graph.

- `##Name` — refers to a subheading in the current module.
- `#Name` — resolves in order: symbol in current module, subheading in
  current module, module listed in `#References`. A module that is not
  listed does not resolve, however near it is: the scope of a citation is
  what the author lists, as in a paper's bibliography.

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
| `quantifier`  | advisory  | a quantified claim about behaviour ("each token fires...") with no `~example`/`~property` in that section |

`notlob check -v` adds a coverage summary; `--only <names>` runs a
subset. Advisory findings never fail the build; only error-severity
findings (and a missing linter) do.

---

## Toolchains

Each language binding needs its tools available; how they are provided
differs by ecosystem. Binding-specific behaviour (how claims run, what
the linter sees) is in each binding's doc, written beside this file as
`BINDING-<language>.md` by `notlob docs`.

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
notlob test [file] [--json]     run all claims (project or one file)
notlob check [--only ...] [-v] [--json]  run semantic checks on the name-graph
notlob build [file]             assemble to source artifacts in dist/
notlob run <file>               execute a module
notlob weave [file]             render as Markdown
notlob new <name>               create a new module
notlob docs [--output DIR]      write this reference to notlob-docs/
notlob query search <pattern>   find nodes by label (bare word = substring)
notlob query content <address> [--depth N]  the subtree at an address, with text
notlob query children <address> list child nodes
notlob query imports <address>  modules imported by an address
notlob query imported-by <addr> modules that import an address
notlob graph [--level LEVEL] [--format json|turtle]  export the name-graph
notlob mcp                      start the MCP tool server (stdin/stdout)
```

File arguments accept either a filesystem path or a module address via
`-m` (e.g. `notlob test -m pricing/discounts`).

`notlob build` (`--output DIR`) and `notlob docs` write relative to the
current directory, not the project root.

`--json` prints a machine-readable document to stdout (diagnostics go to
stderr) and leaves the exit code unchanged. `notlob test --json` prints
`{version, summary, claims, lint}`, plus `checks` for a whole-project run.
Each claim has `address`, `kind` (`EXAMPLE`, `PROPERTY`, `TEST`),
`status`, `source` (the assertion text), `file` (relative to the project
root) and `line`, plus `left`/`right` on a failed equality; claims, lint
findings and check findings are separate lists. The shape is specified by
`schema/test_result.json`, written beside this file by `notlob docs`, and
`version` changes on a breaking change. `notlob check --json` prints
`{version, findings, counts}` (`schema/check_result.json`); a finding has
`check`, `message`, `addresses` and `severity` (`error` or `advisory`),
and is the same shape as an entry in `checks` above. The `notlob query`
commands print nodes as `notlob graph` does at `outline` (`address`,
`label`, `kind`, and `named`, `mode`, `file`, `start_line`, `end_line`
where they apply): an array, or for `resolve` a single node, or `null`
with exit code 1 when it does not resolve. `children` follows any edge kind
the graph holds (`CONTAINS` by default, and a section's paragraphs and code
blocks are among its children); `search` finds the nodes `outline` shows;
`references` and `referenced-by` give a section for a paragraph.
`content` prints the subtree at an address as a `notlob graph --level full`
document with a `root`: each line of text once, on the leaf it is written
in, except that a symbol whose code block is not in the answer carries its
text; `--depth N` stops N containment steps down (0 is the node alone).
The shapes are specified by `schema/query_result.json`.
`notlob graph` prints the graph itself, `{version, level, nodes, edges}`
(`schema/name_graph.json`): one tree of nodes for each file, joined by
`CONTAINS` edges, with `REFERENCES`, `USES`, `IMPORTS` and `USES_EXTERNAL`
edges between them. `--level` (a name or a number) says how much to show:
`outline` (1, the default) every node but the paragraphs, code blocks and
bullet lists, with their edges moved to the section that holds them;
`index` (2) those too, the references a paragraph holds and a `size` for
each node; `full` (3) the `text` of each node that holds text, once.
`notlob graph --format turtle` exports the same nodes and edges as RDF, at
the same `--level`; its vocabulary is declared in `schema/notlob.ttl`
(informal namespace `urn:notlob:ns:`), and node IRIs are relative
references, so they resolve against wherever the file is loaded.
