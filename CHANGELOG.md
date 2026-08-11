# Changelog

All notable changes to this project are documented here. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

## [0.5.3] - 2026-08-11

### Added
- `notlob init --agents`: writes `AGENTS.md` and `notlob-docs/` into an
  existing project that already has a `binding.lob`. Intended for projects
  that were started manually and now want agent-friendly documentation.
- `REFERENCES` edge kind: a fourth `build_package` pass walks prose
  `#Label` mentions and emits `REFERENCES` edges (MODULE/SUBHEADING →
  target node) with `start_line`. Enables `notlob query references
  <addr>` and `notlob query referenced-by <addr>`.
- `start_line` on `USES` edges — the absolute `.lob` line of the first
  call site within the source symbol, enabling precise navigation from
  the call graph to the source location.
- `start_line` on `IMPORTS` and `USES_EXTERNAL` edges, taken from Lark
  token positions at parse time.
- `~run` takes an optional mode: `~run on-load` (fires unconditionally
  whenever the built artifact is loaded) or `~run on-invocation` (fires
  only when the artifact is the program's entry point — the default for
  bare `~run`). The notlob equivalent of `if __name__ == "__main__":`.
  Python wraps `on-invocation` bodies in exactly that guard; TypeScript
  wraps them in a verified ESM Node entry-point guard; Haskell has no
  meaningful "on-load" (importing a module never runs `IO` actions
  there), so `on-load` is a build/run-time error for that binding —
  bare `~run` and `~run on-invocation` are equivalent for Haskell.

### Changed
- `extract_calls` in all three language bindings now returns
  `list[tuple[str, int]]` (name, 1-indexed line within the source block)
  instead of `list[str]`.  The line is used to compute `start_line` on
  USES edges.
- `add_uses_edges` now walks `~run`, `~example`, `~property`, and
  `#Tests` claim blocks in addition to symbol definitions, so calls
  inside any claim are tracked in the call graph and satisfy
  `check_imports`.
- `check_imports` rewritten to use USES and REFERENCES edges rather
  than a regex scan over raw text. Consequences: (1) a bare word mention
  of a symbol in prose no longer satisfies the check — only a `#Label`
  reference does; (2) imports of prose-only modules are now flagged
  unless a `#Label` reference exists; (3) calls inside `~run` blocks now
  satisfy the check.
- TypeScript `extract_symbols` now captures the full source block for
  each declaration (header line plus continuation lines), fixing a
  regression where `source` was always `None` and no USES edges were
  emitted for TypeScript projects.

### Fixed
- `notlob run` on a Haskell module now includes the module's `~run`
  claim bodies — where `main` is conventionally defined — in the
  assembled source. Previously they were silently dropped, so any
  module relying on `~run` for its entry point (rather than a bare
  top-level `main` code block) failed with `Not in scope: 'main'`.
- `#Appendix` no longer uses a colon (`#Appendix: Title` → `#Appendix
  Title`), matching every other `#`/`##` heading convention in the
  language. The old colon form still parses (it's just ordinary title
  text now, not a special separator) and renders identically — no
  stray leading colon — but new appendices should drop it.
- Subheadings inside `#Appendix` sections are now registered as graph
  nodes and can be resolved by prose `##Label` references from the main
  module body. Previously they were silently absent from the graph,
  causing valid references to report as unresolved.

## [0.5.2] - 2026-07-21

### Changed
- `#Binding` declarations (`~language`, `~external`, `~on-build`,
  `~keep-generated-src`) are now first-class grammar terminals.
  Unknown declarations inside `#Binding` are now parse errors rather
  than silently ignored lines.
- hypothesis (Python) and QuickCheck (Haskell) are now implicit in
  their binding toolchains — no declaration is needed beyond
  `~language python` or `~language haskell`.
### Removed
- `~property-testing` and `~unit-testing` sigils in `binding.lob` are
  no longer recognised. Projects using them must remove those lines.
  They were never part of the grammar; this formalises what the grammar
  already implied. Breaking change for projects using these sigils.


## [0.5.1] - 2026-07-21

### Added
- `notlob --version`.
- `notlob init` starter template now includes `~property`, `~example`,
  `#Tests`, and `#References` stubs with guiding prose, to set
  expectations for the richness of language from the start.
- `~test <name>` sigil for naming individual assertions within a
  `#Tests` `##group`, addressed the same way as a named `~property`
  claim (one address per block, not a per-line ordinal). Fully
  supported by all three bindings (Python, Haskell, TypeScript).
- Prose commentary is now legal inside `#Tests`, both directly under
  the section head and within a `##group`, freely interleaved with
  assertions and `~test` blocks.
- TypeScript `~property` claims now run via fast-check. `fc` is
  injected into the claim scope automatically; no `~property-testing`
  declaration is needed beyond `~language typescript`. If fast-check
  is not installed, claims error rather than skip.
- `gen_listings_lang.py`, generating a `listings` `\lstdefinelanguage{notlob}`
  block for typesetting `.lob` source in the paper (`~example`/`~run`/
  `~property`/`~test`/`---` colored; reuses the same `grammar.lark`
  parse as `gen_grammar_latex.py` for the keyword list). `#`-prefixed
  markers (`#Tests`, `##`, ...) are deliberately left uncolored — every
  escaping strategy tried for them fails against this listings version,
  confirmed by compiling; see the script's own docstring.

### Changed
- `gen_grammar_latex.py` now reads `grammar.lark` directly as its
  source of truth, closing the drift risk noted in the 0.5.0 entry.

### Fixed
- Missing `import textwrap` in the TypeScript runner caused a
  `NameError` when executing any `~property` claim.

## [0.5.0] - 2026-07-09

### Added
- Semantic checks (`notlob check`): missing-import detection, coverage
  reporting, handling for symbols imported but used only in prose.
- Zero-dependency MCP server exposing notlob commands as tools.
- RDF export of the name-graph.
- JSON output for `test`/`check`.
- `scripts/gen_grammar_latex.py`, generating a formatted EBNF/backnaur
  LaTeX rendering of the grammar, from a hand-maintained model intended
  to mirror `grammar.lark` — not parsed from it directly, so the two
  can drift; see the script's own docstring for the known gap.

### Changed
- Rewrote `.lob` line-classification from a hand-written Python line
  classifier into native Lark grammar terminals, disambiguated by
  explicit priority — `grammar.lark` is now the actual specification,
  not a thin shell over Python conditionals.
- Closed the claim-sigil vocabulary at the grammar level: an
  unrecognised `~sigil` is now a parse error, not a silent misparse.
  `~test` is explicitly reserved for a future feature.
- TypeScript binding matured: `tsc --noEmit` linting (fail-loud when
  the tool is missing, matching the other bindings' contract),
  transitive dependency handling, `notlob init --language typescript`
  scaffolding, per-binding `BINDING.md` docs.

### Fixed
- Python `notlob build` omitted cross-module `#References` dependency
  code from build artifacts, causing `NameError` when an artifact was
  run standalone (`notlob test`/`notlob run` were unaffected — they
  resolve dependencies at runtime via a different mechanism). Fixed by
  inlining dependency modules into the artifact, matching the Haskell
  and TypeScript bindings' existing behaviour.
- Inline references at column 0 misparsed as headings.
- Semantic-check false positives: unused-import detection now considers
  prose references; symbols referenced only via a concept ref are no
  longer flagged as unused.
- A module with no code is now correctly treated as valid, not a bug.
- `ts-media` example prose claimed "eight" axes/dimensions in three
  places; code, tests, and `binding.lob` all agreed on five.

### Other
- Improved `~run` support, including command-line parameters.
- Bullet-list support, with a style-check nudge against overuse.
- Anonymous `~property` claims included in the name-graph; property
  tests added.
- Shared assembler and source-map code deduplicated across all three
  language bindings.


## Pre-0.5.0 Historical Note

Entries begin at 0.5.0 — this file didn't exist before. For earlier
history, see `git log`. One known quirk worth recording: the `v0.4.0`
git tag (2026-06-03) was cut without bumping `pyproject.toml`'s version
field, which still read `0.3.1` at that commit. The tag is already
public, so it hasn't been rewritten; this file starts clean from the
version where the file and the tag are back in sync.


