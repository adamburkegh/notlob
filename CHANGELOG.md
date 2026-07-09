# Changelog

All notable changes to this project are documented here. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/).

Entries begin at 0.5.0 — this file didn't exist before. For earlier
history, see `git log`. One known quirk worth recording: the `v0.4.0`
git tag (2026-06-03) was cut without bumping `pyproject.toml`'s version
field, which still read `0.3.1` at that commit. The tag is already
public, so it hasn't been rewritten; this file starts clean from the
version where the file and the tag are back in sync.

## [0.5.0] - 2026-07-09

### Added
- Semantic checks (`notlob check`): missing-import detection, coverage
  reporting, handling for symbols imported but used only in prose.
- Zero-dependency MCP server exposing notlob commands as tools.
- RDF export of the name-graph.
- JSON output for `test`/`check`.
- `scripts/gen_grammar_latex.py`, generating a formatted EBNF/backnaur
  LaTeX rendering of `grammar.lark`.

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
