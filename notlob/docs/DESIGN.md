# Notlob — Implementation Design

> **Language reference for users and agents:** see `LANGUAGE.md` in
> this repository, or run `notlob docs` to write it to `notlob-docs/`
> in any project.  This document covers internal architecture and
> design rationale.

---

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

**Single artifact, multiple renderings.** A `.lob` file is the primary
artifact — not a meta-language from which separate outputs are extracted.
The same source is read as structured text in an editor, rendered as a
typeset document, executed by the runtime, traversed as a name-graph, and
consumed as self-contained context by an LLM. These are renderings, not
extractions; the `.lob` file does not change between them.

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

## Syntax Decisions

**Headings as module addresses.** `#Pricing Discount Strategies` is both
the document title and the module address. It translates deterministically
to `pricing/discount/strategies/` — lowercase, spaces to slashes. The
author maintains the title; the tooling derives the path. The `.`
namespace separator is a machine convention that should not leak into the
human-facing layer. The tooling enforces consistency: `notlob test`
reports an address mismatch as a build error if a module's title-derived
address does not match its file path, before running any claims.

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

**`~run` is the program entry point.** A `~run` claim marks code that
executes only when the module is *run* (`notlob run` / `lob`), not when
it is *tested* (`notlob test`).  It is the notlob equivalent of
`if __name__ == "__main__"` — but expressed as a claim, keeping the
entry point visible in the document structure rather than buried in a
guard.

Side-effecting code (printing, writing files, making requests) belongs
in a function defined in the essay body; the `~run` claim calls it.
This keeps the function testable — its behaviour can be verified with
`~example` or `#Tests` — while confining the side effects to the run
path.  Multiple `~run` claims in a module execute in document order.

**`~property` syntax is binding-determined.** The body of a `~property`
block uses the real syntax of the declared property-testing library. For
the Python/Hypothesis binding, this is a `@given`-decorated function
body. The literate processor does not invent a property mini-language;
the binding owns the syntax entirely.

**`~property` naming.** A `~property` claim may optionally carry a name
(`~property commutativity`), which creates a named node in the name-graph
at the level of its containing doc-node. Named properties are like named
theorems in a formal paper — some properties are significant enough to
deserve a name that can be cross-referenced in prose (`#commutativity`);
others are anonymous lemmas, identified only by their position in the
argument.

The `_` convention for the function name inside a named property is a
deliberate signal: the meaningful name is on the sigil line, not in the
code. Authors may use any function name — the name-graph address comes
from the sigil parameter, not the function — but `_` communicates that
this is an anonymous witness whose identity is its location in the
argument.

Functions defined inside a named `~property` (other than `_`) become
`NodeKind.SYMBOL` nodes in the name-graph under the property node:

```
roman/numerals#Round-Trip#commutativity        ← property node
roman/numerals#Round-Trip#commutativity#prop   ← named function within
```

Unnamed `~property` claims have no property node in the name-graph; the
runner addresses them by ordinal within their containing doc-node.

**Test names are navigational.** In a large test appendix, `##` heading
groups provide navigation. Unnamed tests are anonymous witnesses —
epistemically humble, just facts.

**References as bibliography.** Imports at the end acknowledge what the
argument depends on, after the argument has been made. Code blocks in the
essay body do not contain imports; `#References` is the authoritative
import list.

**Two kinds of `#References` entry.** A `#References` section contains
two interleaved kinds of line:

- *Lob module references* — lines whose stripped content begins with `#`,
  e.g. `    #Gutenberg Corpus`. The label is resolved to a module in the
  same project by title; the module's names are loaded into the importing
  module's namespace before assembly.
- *Language imports* — all other non-blank lines, e.g.
  `    from pathlib import Path`. These are passed through verbatim to
  the language runtime.

The `#` prefix is unambiguous in the `.lob` line grammar — no new syntax
is required; the existing dereference operator doubles as the import
sigil.

**Lob-to-lob imports must be declared explicitly.** Each module declares
exactly which other lob modules it depends on. There is no implicit
package import (as in Java, where all classes in a package are available
to any other class in that package without declaration). If module A uses
names from C, A must list `#C` in its own `#References`, even if B
(which A already imports) also imports C.

This explicitness is intentional. The small friction it creates is a
design pressure: if two modules are routinely needed together, that is a
signal they belong in one module. Explicit imports make the dependency
graph readable directly from source; the `#References` list is a true
bibliography.

**Python-level imports are transitive across lob boundaries — by binding
design, not by notlob rule.** When module B declares
`from decimal import Decimal`, that name is visible to any lob module
that imports B. This follows from the Python binding's exec-chain
implementation: dependency namespaces are merged before the importing
module is executed, so Python names travel with their enclosing namespace.
It is not a notlob design decision; it is Python behaving Pythonically.
Other bindings — Haskell, compiled languages — will enforce their own
module boundaries and will not exhibit this behaviour. The take-away: lob
module boundaries govern notlob theory (explicit, declared, navigable);
language-level name visibility is governed by the language binding.

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

**`binding.lob` is a reserved structural filename.** Each project root
contains a `binding.lob` that declares the execution substrate and
tooling libraries for all modules in that project. It is the one file
whose title names its *parent* address rather than its own — `binding.lob`
at the root of the `roman` project carries the title `#Roman`. The
filename is a tooling convention, not a module address; it is not subject
to the title-as-path rule. The name is a pun: it binds the package in the
bibliographic sense and declares the technical binding in the execution
sense.

`binding.lob` is **purely declarative**: it contains only a `#Binding`
section with `~sigil` declarations. It does not contain `#References`
with shared imports. Shared imports are a module concern — each module
imports what it uses in its own `#References`. The binding declares which
libraries are *available* to the project (a dependency declaration); the
module declares which names are *used* in that module (an import). This
mirrors the package-vs-import distinction in any language: `pyproject.toml`
lists dependencies, each `.py` file imports what it needs.

**`#Binding` is inherited from the package.** A module file that lacks a
`#Binding` section inherits its binding from the project's `binding.lob`.
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
them are edges. The name-graph accumulates in layers, each adding richer
information:

- *Structure.* Module addresses and subheading nodes, derived from the
  `.lob` parser alone. No language binding required. Sufficient for
  cross-reference validation, doc-node navigation, and LLM context.
  This layer is binding-agnostic and always available.

- *Symbols.* Code-level names extracted from code blocks and named
  `~property` claims by a language-specific analyser. Code block names
  (functions, classes, top-level assignments) become `NodeKind.SYMBOL`
  nodes under their containing structural node. Named `~property` claims
  become `NodeKind.PROPERTY` nodes, with any named functions defined
  within them as `NodeKind.SYMBOL` children. The `_` convention marks
  anonymous witness functions and they are not extracted. This layer is
  where the binding earns its keep.

- *Cross-references.* Prose `#Label` and `##Label` mentions are
  first-class `Ref` objects extracted by the lexer. The tooling validates
  them against the name-graph using a three-step resolution order: symbol
  or subheading in the current module, then module reached via a declared
  `IMPORTS` edge. Unresolved references are build errors, reported
  alongside address mismatches before any claim runs. Planned extension:
  `REFERENCES` edges recording each resolved mention, enabling navigation
  and cross-reference coverage analysis.

- *Package graph.* Module addresses resolved across a package, with
  `binding.lob` providing the project root. IMPORTS edges connect
  modules via their declared `#References`; the name-graph spans the
  full package.

The seam between the structural and symbolic layers is the binding
boundary. The structural layer is the common vocabulary across all
languages; the symbolic layer is language-specific richness.

**Binding kit architecture:** A binding is not a single function; it is a
kit of cooperating tools that share a language substrate. The binding
layer is organised language-first:

```
notlob/bindings/
    __init__.py          ← BindingKit dataclass + shared result types
    python/
        __init__.py      ← assembles the Python kit; exposes `kit`
        assemble.py      ← Module → executable Python with # <addr> markers
        symbols.py       ← extract_symbols for stage-2 name-graph
        runner.py        ← run_examples, run_properties, run_tests
        lint.py          ← lint_python via ruff; source-map translation
        loader.py        ← ModuleCache for cross-file dep resolution
    haskell/
        __init__.py      ← Haskell kit; requires runghc or stack on PATH
        assemble.py      ← Module → Haskell source with -- <addr> markers
        symbols.py       ← extract_symbols (top-level type signatures)
        runner.py        ← subprocess harness; CLAIM/PASS/FAIL protocol
        lint.py          ← lint_haskell via hlint
    typescript/
        __init__.py      ← TypeScript kit; requires tsx on PATH or in node_modules
        assemble.py      ← Module → TypeScript source with // <addr> markers
        symbols.py       ← extract_symbols (function/const/class/interface/type/enum)
        runner.py        ← tsx harness; CLAIM/PASS/FAIL protocol; lhs/rhs extraction
        tokenizer.py     ← bracket-counting scanner for claim completion + === split
        lint.py          ← stub; biome integration planned
```

`BindingKit` is a dataclass that composes callables — one per tooling
concern — so the name-graph and claim runner can ask for exactly the
capability they need without coupling to a particular language:

```python
@dataclass
class BindingKit:
    extract_symbols: Extractor            # code lines → defined names
    assemble:        Assembler            # Module → executable string
    run_examples:    Callable[..., list]  # ~example claims
    run_properties:  Callable[..., list]  # ~property claims
    run_tests:       Callable[..., list]  # #Tests assertions
    lint:            Callable[..., list] | None  # static analysis; None if unsupported
    extension:       str                  # output file extension ("py", "hs", "ts")
    comment_prefix:  str                  # location-comment prefix ("#", "--", "//")
    build:           Callable[..., str] | None   # assembly for notlob build
```

The declarations in a `#Binding` section (`~language python`,
`~property-testing hypothesis`, `~unit-testing pytest`) map to submodule
choices within the language package. The language is the primary axis;
the tool components are secondary. A package that declares
`~language python` gets the full Python kit from `bindings.python`.

**Claim runner:**
- `~example` claims run as inline assertions in the assembled namespace
- `~run` claims execute only during `notlob run`; they are ignored by
  `notlob test`.  All `~run` bodies in a module execute in document
  order, in the assembled namespace, after the module code has run.
- `~property` claims are executed using the declared property-testing
  library. The binding assembles the module into a namespace, then
  exec's each `~property` block into a *fresh copy* of that namespace
  (isolating the ephemeral witness function from the module's permanent
  state). The binding then calls the decorated function; the
  property-testing library (e.g. Hypothesis) drives the execution.
- `~proof` claims are reserved for future formal verification integration

**Binding declarations drive namespace injection.** The `~property-testing`
and `~unit-testing` declarations in `binding.lob` are not just metadata —
they determine which names are injected into claim execution namespaces:

- `~property-testing hypothesis` → the Python binding injects `given`,
  `settings`, `assume`, `st`, `HealthCheck`, etc. into every `~property`
  claim namespace. Authors do not import hypothesis; the binding provides
  it.
- `~unit-testing pytest` → the Python binding injects pytest helpers
  (`pytest.approx`, `pytest.raises`, etc.) into `#Tests` assertion
  namespaces.

This is a uniform mechanism, not hypothesis-specific magic. The pattern
is: *declaration in `binding.lob` → injection kit prepared by the
language binding → names available in the relevant claim context*. A
Haskell binding would respond to `~property-testing quickcheck` by
preparing a completely different execution strategy; the `~property` sigil
is language-agnostic, the binding owns the implementation entirely.

**CLI commands.** The notlob command surface:

- `notlob run` / `lob` — assemble and execute a module.  Runs `~run`
  claims in document order after the module code.  For compiled
  languages (Haskell) this invokes the compiler and runtime; for
  interpreted languages it exec's directly.
- `notlob test` — run all claims (examples, properties, #Tests) and
  report results by address.  Runs the linter if the binding supports
  it.  Exit 1 on any failure or lint diagnostic.  `--only lint|examples|props|tests`
  restricts which check types run.
- `notlob build` — assemble a module (or all project modules) with
  inlined deps and write artifacts to an output directory (default:
  `dist/`).  After assembly, runs the `~on-build` hook if declared in
  `binding.lob`.  The primary entry point for browser-target languages.
- `notlob weave` — render a `.lob` file (or project) as Markdown.
- `notlob graph` — export the package name-graph as JSON.
- `notlob query` — navigate the name-graph from the command line
  (`children`, `resolve`, `search`, `imports`, `imported-by`,
  `content`).
- `notlob docs` — write the language reference to `notlob-docs/`.
- `notlob init` — initialise a new notlob project in the current directory.
- `notlob new` — create a new `.lob` module in the current project.

All file-targeting commands accept either a filesystem path or a module
address via `-m` (resolved from CWD against the nearest `binding.lob`).

**Document output (weave).** The runtime can render a `.lob` file or
package as a human-readable document — the complement of execution.
Target formats:

- *Markdown* — near-term target.  Module heading becomes `# Title`;
  subheadings become `## Subheading`; prose blocks become paragraphs;
  code blocks become fenced ` ```python ` blocks; inline refs become
  anchor links backed by the name-graph (no dead links).  Claims render
  as labelled blocks — `~example` as a numbered example, `~property` as
  a named invariant — distinct from plain code.  A package weave
  produces a linked set of `.md` files.

- *Typst* — medium-term target for typeset PDF output.  Typst is chosen
  over LaTeX because notlob source uses `#` heavily; generating LaTeX
  would require escaping a minefield of special characters.  Typst has
  no such conflict and produces comparable output with far less
  ceremony.  Claims map naturally to Typst theorem/example environments;
  cross-references become typed `@label` citations backed by the
  name-graph.

The weave operation exposes the same validated cross-reference structure
that the runtime uses — a rendered document cannot contain a dead link
to a node that does not exist.

**Diagnostics:** Failures report by doc-node address, not line number. A
failing claim in `##Stacking Discounts` says so. The node has a prose
face, a claim face, and an executable face; all three are candidates for
being wrong.

**LLM harness:** Feed a `.lob` file as context; ask for extension or
modification; evaluate whether the linked structure produces less aberrant
output than equivalent unstructured code. This is an early experiment
worth running before the claim runner is complete.

---

## External files and build hooks

Some projects need to coordinate with files that are part of the
project but outside the `.lob` world — HTML templates, C extensions,
static assets.  Two declarations in `binding.lob` handle this:

**`~external <filename>`** — declares a file relative to the project
root that `notlob build` should be aware of.  The file is not
assembled, tested, or owned by notlob; it is passed to the build hook
and appears as a `NodeKind.EXTERNAL` node in the name-graph (connected
to the binding module via a `USES` edge, visible via `notlob query`).

**`~on-build <script>`** — a hook script in the binding's own language
(TypeScript for TypeScript projects, Python for Python projects).
`notlob build` runs this script after assembling all artifacts, passing
a JSON manifest as the path of a temporary file (first argument):

```json
{
  "artifacts":    ["/abs/path/to/dist/module_name.ts"],
  "externals":    ["/abs/path/to/index.html"],
  "language":     "typescript",
  "project_root": "/abs/path/to/project",
  "output_dir":   "/abs/path/to/dist"
}
```

The script owns the integration logic — injecting a bundle into an
HTML template, compiling a C extension, whatever the project needs.
notlob runs it and forwards its stdout/stderr to the terminal.

The design goal is **visibility, not friction**.  When a project
reaches outside the notlob abstraction, it should be obvious where and
why.  `binding.lob` is the right place for this declaration: it is
already the project's configuration document, and its prose body can
explain the intent.  A developer or agent doing a cold read sees both
the declaration and the explanation in one file.

The hook is "slightly discouraged" by the requirement to write a script,
but deliberately not more than that — determined developers will break
abstractions regardless.  The seam should be explicit, not painful.

`~external` and `~on-build` are only valid in `binding.lob`, never in
individual `.lob` modules.  Module-level `#References` remains
homogeneous: lob-module references and language package imports only.
Mixing external file references into `#References` would risk the
anti-pattern of thin `.lob` wrappers over collections of external
source files.

---

## Later Features

**Property testing for TypeScript.** `run_properties` currently returns
SKIP for all `~property` claims in TypeScript modules.  The planned
integration is fast-check (`~property-testing fast-check` in
`binding.lob`), following the same pattern as the Python/Hypothesis
binding.

**TypeScript linting.** `kit.lint` is `None` for the TypeScript binding.
The planned tool is Biome — fast, zero-config, ruff-equivalent for
TypeScript.  The source-map mechanism (translating `// <address>`
location comments back to `.lob` sections) is already designed;
`lint.py` in `notlob/bindings/typescript/` documents the implementation
plan.

**TypeScript build output.** `notlob build` for TypeScript currently
produces a `.ts` source file.  The natural next step is to invoke
esbuild (a transitive dependency of tsx) to produce a bundled `.js`
file directly, so the build artifact is browser-runnable without a
separate bundling step.  The `~on-build` hook mechanism handles this
today (see `examples/ts-media/inject-script.ts`); native bundling in
`build_typescript` would make it the default.

**fast-check property testing.** TypeScript `~property` claims are
currently skipped.  The runner harness already supports the extension
point; fast-check integration requires adding the import injection and
harness generation for `fc.assert(fc.property(...))` blocks.

**Cross-reference aliasing.** Cross-references use `##Name` syntax in
prose, validated against the doc-node graph. A future extension would
allow aliasing long reference names — display text separate from the
node address, as in LaTeX `\ref` with custom text or named imports in
programming languages.

**Kit bindings.** A `#Binding` section should eventually be able to
import a named `.lob` package defining a standard toolset —
`import notlob/bindings/python-hypothesis` — making the binding itself a
literate document inspectable in the same format.

**Typst weave.** A Typst backend for `notlob weave` producing PDF.
Claims become typed environments (example, property/invariant);
cross-references become `@label` citations.  Typst is preferred over
direct LaTeX generation because the notlob `#` syntax conflicts with
LaTeX comment characters.

**Tree-sitter grammar.** A `grammar.js` living in this repository
(not a separate package — `grammar.js` *is* the canonical notlob
grammar, not a reimplementation of one).  The primary motivation is
editor tooling: syntax highlighting, language injection of Python into
code blocks, and navigation queries.  The compiled C parser is
generated by CI and committed; users never run `tree-sitter generate`.

---

## What This Is Not

Not a production language. Not a compiler. Not making grand claims. The
name is not a palindrome and the project is not finished. It is an
experiment in whether the document structure is the right place to put
the theory that Naur says lives in programmers' heads and Fox says should
be transmissible.
