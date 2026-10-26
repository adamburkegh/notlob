# Changelog

All notable changes to this project are documented here. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added
- `build.py`: builds the release `.pyz` (`dist/notlob-<version>.pyz`) with
  shiv from a git ref (`python build.py --ref v0.6.0`), so the same ref
  gives the same artifact whatever is in the working tree. It refuses a
  version with no dated changelog section or a ref other than the one the
  version's tag points at, and smoke-tests what it built (version, shipped
  docs and schemas, a real `notlob test`). It does not tag or publish.
  `shiv` is added to the `dev` extra.
- `quantifier` check (`notlob check`): flags a prose sentence that
  makes a quantified claim about behaviour ("each token fires...")
  with no `~example`/`~property` co-located in the same section to pin
  it down. A structural proxy for a semantic smell, not a semantic
  judgment — it notices the *absence* of a nearby runnable claim, never
  whether the prose or the claim is actually correct. See
  `meta/features/2026-10-02-quantifier-check/design.md` for the full
  design and its deliberate limits.
- `notlob docs` (and `notlob init`) now also write the JSON Schemas for
  the stable-tier output to `notlob-docs/schema/`, and `grammar.lark`,
  the formal `.lob` syntax, to `notlob-docs/grammar.lark` (headed by a
  note that its rule and terminal names may change). Agents working in
  another project can now read the exact shapes and syntax, not only
  prose. `DESIGN.md` states the rule: structured output has a schema.
  The `schema/*.json` files are added to the package data; they were not
  shipped in installs before.
- An ontology for the Turtle export (`schema/notlob.ttl`), written to
  `notlob-docs/schema/` with the JSON Schemas: a class per node kind
  (UpperCamelCase: `notlob:PostText`, `notlob:TestGroup`), a property per
  edge kind, and the literals a node carries, each with a label and a
  comment. Tests parse real output at every level with `rdflib` (added
  to the `[dev]` extra; notlob itself does not depend on it) and fail if
  the ontology and the emitter drift apart.
- A JSON Schema for the `notlob query` outputs (`schema/query_result.json`):
  node arrays, the single node or `null` of `resolve`, and the subtree of
  `content`. Nodes and edges are the name-graph's, with identical
  definitions kept in step by a test. The query outputs are bare JSON
  values; `content`'s subtree carries the graph document's `version`.
- `notlob query content --depth N`: the subtree at an address, down N
  containment steps (`0` is the node alone; the default is all of it).
- `notlob graph --level outline|index|full` (or `1|2|3`), for JSON and
  Turtle alike. See "Changed" for the graph itself.
- Every example project is run end to end by the test suite (`notlob
  test` and `notlob build`), skipping one whose toolchain is not
  installed, with the reason. Nothing ran them before, which is how the
  Gutenberg example stayed broken for months.
- A JSON Schema for `notlob check --json` (`schema/check_result.json`).
  The document gains a `version` field (`1`): it is now
  `{version, findings, counts}`. A finding is unchanged and is specified
  once, with the same definition in `test_result.json`'s `checks` list
  (kept identical by a test). `check` in a finding is now an enum of the
  registered checks plus `names`. Adding a check without updating the
  schema fails a test.
- Fixed with it: under an address collision (a subheading and a symbol
  sharing a name) `notlob check --json` printed an error to stderr and
  nothing to stdout, so a consumer could not `json.loads` it. It now
  prints a valid document holding a single `names` finding (as
  `notlob test --json` already did) and an empty `counts`, and exits 1.
  With no project at all it still prints nothing to stdout and exits 1,
  which the schema now states.
- A JSON Schema for the `~on-build` hook manifest
  (`schema/build_manifest.json`), which hook scripts are written against.
  The manifest gains a `version` field (`1`); no field was removed or
  renamed, so existing hooks are unaffected. `DESIGN.md`'s example of the
  manifest, which had no `entry_points`, is corrected.

### Changed
- **Breaking: the name-graph is the parse tree of each `.lob` file, with
  cross-references** (`notlob graph`, `schema/name_graph.json`). Every
  element of a file is a node, contained by what it is written in, in
  document order: paragraphs (`PROSE`), code blocks (`CODE`), bullet
  lists (`BULLETS`), claims, `#Tests` (`TESTS`) with its `##groups`
  (`TEST_GROUP`) and tests (`TEST`, a `~test` or a run of bare
  assertions), each `#Appendix` (`APPENDIX`), `#References`
  (`REFERENCES`) with a `LISTING` for each module it lists and an
  `IMPORT` for each import statement of the bound language (one node for a
  statement over several lines, found by the binding), `#Binding`
  (`BINDING`) with a `DECLARATION` for each line, which has `declares`
  and `value` fields, and what follows `---` (`POST_TEXT`). `IMPORTS` and
  `USES_EXTERNAL` edges start at the line that makes them, the listing or
  the declaration, not at the module. Text is held once, on the leaf that
  holds it; a symbol
  holds its first and last line and none of the text, which is read from
  its code block. A `~run` of any mode is a `RUN` node with its `mode`
  (`on-load`, or `on-invocation` for a bare `~run`); a `~run on-load` was
  a `PROPERTY` before. `CONTAINS` is the only tree edge: `DEFINES` is
  gone. The `REFERENCES` edge is now `CITES` (the Turtle property is
  `notlob:cites`), so that it no longer contradicts the `#References`
  section, whose lines make `IMPORTS` edges; it runs from the paragraph
  that holds the reference, which keeps the references as written (`refs`).
  The document is `{version: 2, level, nodes, edges}`, at one of three
  levels: `outline` (the default) has every node but paragraphs, code
  blocks, bullet lists, listings, import statements and declarations,
  with their edges moved to the nearest node shown; `index` adds those, each paragraph's `refs`, and each node's
  `size`; `full` adds the text. A node written in a `.lob` file has its
  `file`, `start_line` and `end_line`; a node the document names has
  `"named": true`. `--content`
  and the `content` object are gone: use `--level full`, or `notlob
  query content` for part of the graph. The Turtle export prints the same
  nodes and edges at the same levels.
- **Breaking: addresses.** A paragraph, code block or bullet list is
  addressed by position, as a claim already was (`mod#Decoding#prose#2`,
  `mod#code#1`). A named `~property` belongs to its module's namespace,
  as a symbol does: `roman/numerals#commutativity`, not
  `roman/numerals#Round-Trip#commutativity`, so two named properties of
  one name in one module, or one named like a subheading or a symbol,
  are a name collision. A run of bare assertions in `#Tests` is reported
  at its own address, numbered within its group
  (`roman/numerals#Tests#encoding#test#1`), not the group's; each
  assertion is still reported with its own line. Haskell numbers
  unnamed properties per section, as Python and TypeScript do, not
  across the module. These addresses appear in `notlob test` output
  (text and `--json`) and in every graph and query output.
- **Breaking: `notlob query`.** Each query prints nodes as `notlob graph`
  does at `outline`. `content` prints the subtree at an address as a
  graph document at `full` (see "Added"). `children --kind` no longer
  offers `DEFINES`. `references` and `referenced-by` are now `cites` and
  `cited-by`, to match the `CITES` edge: they read the citations each
  paragraph holds, and `cited-by` reports a paragraph as the section that
  holds it.
- **Breaking, for language bindings (`BindingKit`, stable tier):** notlob
  now decides what a binding runs and what its code is loaded with, from
  the name-graph; the binding keeps everything about its language
  (assembling, splitting a claim into assertions, running, reporting).
  The runners are called as `(module, claims, *, file_path, root, deps)`,
  `build` as `(module, claims, file_path, *, deps)` and `lint` as
  `(module, claims, *, root)`. `claims` is a list of `ClaimToRun`
  (address, kind, name, mode, lines, first line, sigil line); `deps` is
  the modules the code needs, dependencies first; `root` is the project
  root. The `cache=` keyword is gone, with `ModuleCache`
  (`bindings/python/loader.py`). New: `complete_references` (default
  `False`), which a binding sets when its call extraction sees every
  name its code uses (see the next entry), and `SymbolInfo.first_line`
  and `last_line`, a symbol's lines within its block, and
  `split_imports`, which says where an import statement of the language
  ends in the lines of `#References` (one statement for each non-blank
  line by default, so a binding that does not say keeps working). A
  binding that collected its own claims or loaded its own dependencies
  must stop. The grammar now tells a listing (`    #Title`) from an
  import line, so a `    # comment` or `    ##Notes` line in
  `#References` is an import line, not a listing of a module named by the
  comment's words or of one called "#notes"; `project.parse_lob_refs` and
  `parse_python_imports`, which filtered on `#`, are gone, and the
  model's `ReferencesSection` has `listings` and `imports`.
  From `notlob`: `subheading_address`, `symbol_address`,
  `property_address` and `claim_address` are gone, replaced by
  `named_address` and `anonymous_address`; `project.transitive_lob_refs`
  is gone, replaced by `project.load_order` and `load_dependencies`.
- **Behaviour change: modules may list each other.** A `#References`
  listing no longer loads the listed module's code unless the listing
  module's code (body, claims or tests) uses a name the listed module's
  own code defines, less names it defines itself; that is read from the
  name-graph's `IMPORTS` and `USES` edges. A listing nothing uses is a
  citation and loads nothing, so an overview may list the parts it
  explains, parts may list the overview, and siblings may cite one
  another. A module's code is loaded after that of every module it needs,
  and of what those need, each once, in `notlob test`, `run` and `build`
  alike. A cycle of need is an error that names it (`ERROR <imports>
  circular code dependency: a -> b -> a`) instead of a `NameError`.
  TypeScript's and Haskell's call extraction is not complete (calls
  only; lowercase names only), so there every listing is loaded except
  one of a module below the listing one, and two siblings that list each
  other are a cycle. What breaks: a module that lists another only for
  its top-level side effects. The rules are in `DESIGN.md` ("Listing,
  citing and loading") and `LANGUAGE.md`. See
  `meta/bugs/2026-10-22-mutual-references`.
- The `titles`, `style` and `quantifier` checks read an `#Appendix` as
  they read any section: its title, its bullet lists, its prose against
  its claims. They skipped it before, by accident.
- TypeScript: a module with an empty `#Tests` section reports nothing to
  run, rather than a runner error when `tsx` is not installed.
- **Breaking:** the Turtle export (`notlob graph --format turtle`).
  The vocabulary namespace was `https://notlob.dev/ns#`, a domain nobody
  here controls; it is now `urn:notlob:ns:`, an informal namespace (it
  needs no URL to keep alive, and the ontology file says it is informal).
  The default `@base https://notlob.dev/project/` is gone: a project's
  nodes do not belong in notlob's namespace, so node IRIs are relative
  references and `@base` is emitted only when a caller of
  `NameGraph.to_turtle(base=...)` supplies one. Anyone holding exports
  made with the old namespace must re-export; there were no known users.
  Class and property names are unchanged (`notlob:Module`, `notlob:uses`,
  ...).
- The Turtle export was also made well-formed for awkward names: an
  address with a space, quote, `<`, `>`, `{`, `}`, `|`, `^`, a backtick, a
  `%`, a second `#`, or a `:` in its first segment is now percent-encoded
  to a valid IRI reference (the exact address stays in `notlob:address`),
  a prose literal ending in a quote no longer risks an ambiguous close,
  and a carriage return in a label is escaped. Found by parsing the output
  with rdflib.
- **Breaking:** the shape of `notlob test --json`, which was
  undocumented and is now specified (`notlob/schema/test_result.json`,
  documented in `LANGUAGE.md`) with a `version` field (now `1`). The old
  document was `{passed, failed, lint, results, check_findings}`. The
  new one is `{version, summary: {passed, failed, lint}, claims, lint,
  checks}`:
  - Claims, lint findings and check findings are separate lists
    (`results` mixed the first two).
  - A claim's `line` is now the 1-based line number, as an integer
    (previously `source_line`); the assertion text moved to `source`
    (previously `line`).
  - `file` is relative to the project root, e.g. `petri/marking.lob`
    (previously a bare file name).
  - Each claim has a `kind` (`EXAMPLE`, `PROPERTY`, `TEST`).
  - `checks` replaces `check_findings`, and is always present in a
    whole-project run (it was omitted when empty); it is absent for a
    single-file run.
  Exit codes and `--json` on `check` are unchanged. The old shape was
  undocumented and the only known consumer is being moved over, so there
  is no deprecation period.
- TypeScript: a failing boolean claim (one whose root is not `===`, or
  that uses `!==`) no longer prints `left: False` / `right: None`. There
  is no right side to report, and `right: None` read as a missing one;
  the failing line is shown without sides, as the Python runner does. A
  failing `===` still reports both sides, including a `null` right side.
- Python: when an `~example` or `#Tests` line fails to parse as an
  assertion because it is really a statement (a `def`, `class`,
  `import` or assignment), the error now says why instead of a bare
  "invalid syntax". A claim body ends only at the first non-indented,
  non-blank line, so a code block placed directly after a claim is
  absorbed into it; the new message names that cause and the fix
  (a line of prose between the claim and the code). `LANGUAGE.md` now
  states the convention. Other bindings are not changed yet.
- Docs: `LANGUAGE.md` now states `**/*.lob` module discovery, the
  one-namespace-per-module rule, and that `build` and `docs` write
  relative to the current directory. The Python `BINDING.md` now covers
  what the linter sees, what a lob-ref brings into scope, the names in a
  `~property` block, and per-batch module loading.
- `notlob docs` (and `notlob init`) also write the `BINDING.md` of every
  registered binding, third-party ones included, as
  `BINDING-<language>.md`, since `LANGUAGE.md` now points to them. A
  binding opts in by shipping a `BINDING.md` in its package directory.
  The built-in `BINDING.md` files are added to the package data; they
  were not shipped in installs before.

### Fixed
- **An `#Appendix` was invisible** to the name-graph and to claim
  collection: its code defined no symbols and its claims did not run.
  The grammar defines an Appendix as
  the same thing as the module body; everything now reads it so. See
  `meta/bugs/2026-10-20-name-graph-incomplete`.
- `#Tests` assertions after a paragraph of commentary were reported at
  the wrong line, and runs of bare assertions were grouped differently
  by the graph and each runner. notlob now finds them once, and
  commentary ends a run. See
  `meta/bugs/2026-10-25-tests-commentary-line-drift`.
- The name-graph's `USES` edges missed everything a multi-line `#Tests`
  group or `~test` used (its code was not dedented as a block, so it did
  not parse), and `[imports]` could report a module used only from
  `#Tests` as unused.
- **Python and Haskell loaded only a module's direct `#References`.** A
  module `Top` that lists `Middle`, where `Middle` lists and uses `Base`,
  failed with a `NameError` from `Middle`'s own code, though `notlob
  test` on `Middle` passed. Loading is now transitive in every binding
  (TypeScript already was). What a module may *use* is unchanged: the
  Python linter still reports a name from a module it did not list. See
  `meta/bugs/2026-10-21-transitive-lob-refs`.
- **Python claims ran with the harness script's `__file__`,** so a module
  that finds files relative to itself (`Path(__file__).parent / "data"`)
  failed under `notlob test`. Claims now see the module's `.lob` path; a
  built artifact carries no source path. The Gutenberg example was
  broken by it, and also cites `#Gutenberg Hamlet` now (it lists it) and
  has its three placeholder-less f-strings fixed. See
  `meta/bugs/2026-10-22-python-claims-file-attribute`.
- `notlob build` reports a name collision as an error instead of
  building the colliding module.
- The `quantifier` advisory read a section's paragraphs run together
  with no separator, so "...use three." and "The patterns..." read as
  "three.The patterns" and a sentence boundary was lost. Each paragraph
  is now its own node, and a section's prose joins them with a blank
  line. See `meta/bugs/2026-10-18-prose-paragraphs-run-together`.
- Python: `approx`, `raises` and `pytest` were in scope for `#Tests`
  assertions but not for `~example`, so the same line (`x ==
  approx(0.3)`) passed in one and raised `NameError` in the other. They
  are now in scope for `~example` too, working even when the target
  interpreter has no pytest of its own. A module's own `approx`/`raises`
  is kept in `~example` (in `#Tests` the pytest helper still replaces it).
  See `meta/bugs/2026-10-18-example-lacks-pytest-helpers`.
- TypeScript: a claim line mixing `===` with `&&`, `||`, `??`, a ternary
  or a bitwise operator was split at the first `===` as though it were an
  equality, ignoring that those operators bind more loosely. True
  conjunctions failed, and a false one could pass: `0 === 0 && false`
  was evaluated as `0 === 0`, silently dropping `&& false`. The line is
  now an equality claim only when `===` is its root operator, and is
  otherwise evaluated whole. Claims that passed only because an operand
  was dropped will now fail, correctly. Python and Haskell were not
  affected. See `meta/bugs/2026-10-12-claim-equality-precedence`.
- Python lint flagged an import used only by a `~run` body as unused
  (`F401`): `~run` code is not part of the linted source, and the
  by-name suppression that already covered `~example`, `#Tests` and
  `~property` didn't include it. See
  `meta/bugs/2026-10-03-run-body-imports-flagged-unused/`.
- A failing `~property` could lose its real exception: Hypothesis's
  own stdout reporting (e.g. "You can reproduce this failure by adding
  @seed(...)") is interleaved into the harness's output *during* the
  call, ahead of the runner's own result line, for exceptions like
  `FailedHealthCheck` — so the parser picked up Hypothesis's own line
  instead and reported a meaningless `unexpected runner output`. Now
  suppressed at the source; every property failure's reported message
  is also now prefixed with the real exception's type name (the
  protocol already carried it; the parser just wasn't using it). See
  `meta/bugs/2026-10-02-property-exception-swallowed/`.
- `notlob run` crashed for TypeScript-bound projects: it only
  special-cased Haskell before falling through to Python-only
  build/execution logic, so a TypeScript module's correctly-assembled
  source was written to a `.py` file and handed to a Python
  interpreter. See `meta/bugs/2026-10-02-notlob-run-typescript/`.
- A `##Subheading` and a symbol (e.g. a class) sharing one name in the
  same module crashed `notlob test`/`notlob graph`/`notlob check` with
  an uncaught traceback instead of a reported error — the rule being
  enforced (one namespace per module) was already right, only the
  delivery was a crash. See
  `meta/bugs/2026-10-02-address-collision-crash/`.
- The blank-line gap right after `#References` imports is now dynamic
  rather than always two lines, matching isort's own rule for that
  specific position: two blank lines before a following `def`/`class`
  (decorators skipped), but only *one* before a plain top-level
  statement, e.g. a module-level constant assignment. The 0.5.4 fix
  below inserted two blank lines unconditionally, which fixed the
  def/class case but is itself flagged `I001` the opposite way —
  wanting the gap reduced — whenever the module's first assembled
  code isn't a definition. Every other assembler-inserted boundary is
  unaffected and stays at two blank lines unconditionally, since
  isort/pycodestyle only special-case the position immediately after
  an import block.
- Python lint false positives when a module references another
  module: an import used only inside a claim (`~example`/`#Tests`/
  `~property`) was flagged unused (`F401`); a dependency's own lint
  findings were reported against the module referencing it instead of
  being dropped; and an import a module correctly re-declares itself
  was flagged as redefining a dependency's import (`F811`). The lint
  path no longer prepends a dependency's source to the module being
  linted at all — only the module's own source is ever sent to ruff,
  and a cross-module name lookup (via the same `extract_symbols` the
  graph builder already uses) suppresses the one real false positive
  that remains (`F821` "undefined name" for a name a dependency
  genuinely defines). See
  `meta/bugs/2026-10-01-python-lint-cross-module/` for the full
  investigation.

## [0.5.4] - 2026-08-27

### Added
- Cross-reference labels (`#Label`/`##Label`) are Unicode-aware, not
  ASCII-only. A label word's first character may be an uppercase or
  titlecase letter (Latin, Cyrillic, Greek, ...) *or* a letter from a
  script with no case distinction at all — CJK, Arabic, Hebrew, Thai,
  Devanagari, etc. (Unicode categories Lu/Lt/Lo). Lowercase-first words
  in scripts that do have case (`#pricing`, `#café`) still stay
  ordinary prose, exactly as before — the Title Case convention is
  preserved where it's meaningful, not imposed where it isn't. Requires
  the new `regex` dependency (stdlib `re` has no Unicode property
  escapes); the Lark parser now runs with `regex=True`.
- `tests/test_language_md_currency.py`: extracts enumerable facts
  (sigil vocabulary, `#Binding` declarations, CLI subcommands,
  semantic check names) directly from `grammar.lark`/`cli.py` and
  asserts `notlob/docs/LANGUAGE.md` mentions each one in the right
  section — a drift detector, not a generator, for the class of
  staleness that actually kept happening ("we added/removed/renamed a
  thing and forgot to update the reference").

### Fixed
- Python's assembler now separates every assembler-inserted boundary
  (after `#References` imports, between module/subheading/`#Appendix`
  code, between separate code blocks within one section) with two
  blank lines instead of one, matching PEP8/isort's convention for
  top-level definitions. Previously a module with a `#References`
  import and a top-level `def` immediately following could be flagged
  `I001` ("Import block is un-sorted or un-formatted") by any ruff
  config that selects `I` (isort) rules — not ruff's default selection,
  which is why this went unnoticed here, but a common enough choice
  that it surfaced as a real false-positive lint failure in a project
  using notlob. Haskell and TypeScript are unaffected — PEP8's
  two-blank-line convention has no equivalent there.
- `#Appendix` code blocks are now assembled and included in the
  executable namespace (all three bindings), exactly like a main-body
  subheading — previously they parsed fine but were silently dropped
  from assembly entirely, so anything defined there (a shared test
  fixture, a supporting helper) was invisible to `~example`/`#Tests`/
  `~property` claims and absent from `notlob build`/`notlob run`
  output, with no error or warning. Included unconditionally, not
  test-only: `#Appendix` isn't structurally test-support-only, so
  scoping inclusion to `notlob test` would just move the "looks the
  same, silently behaves differently" problem rather than close it.
- `notlob/docs/LANGUAGE.md` (the user-facing language reference) was
  out of date in several places: the removed `~property-testing`/
  `~unit-testing` declaration syntax was still shown in two worked
  examples; `#Binding`'s declaration table was missing `~external`,
  `~on-build`, and `~keep-generated-src`; `~run`'s on-load/on-invocation
  modes weren't documented at all; `#Appendix` wasn't documented as a
  post-text section; the cross-reference disambiguation rule (must
  start uppercase, or any letter for caseless scripts) wasn't
  mentioned; the Commands list was missing `notlob mcp` and
  `notlob graph`'s Turtle/RDF output format.
- Python claims (`~example`, `#Tests`, `~property`) and `notlob run`
  now execute in a subprocess under an interpreter resolved from
  `PATH`, instead of `exec()`-ing inside notlob's own process.
  Previously, any module importing a third-party library only
  installed in the target project's own environment (a venv, an
  asdf/mise-managed interpreter) failed with `ModuleNotFoundError`,
  because notlob's own interpreter — e.g. a pipx-isolated venv — was
  always used regardless of the caller's shell state. Matches how the
  Haskell and TypeScript runners already resolve their toolchains.
  `pytest`/`hypothesis` remain available with no extra setup: the
  `#Tests`/`~property` harnesses append notlob's own site-packages to
  `sys.path` as a fallback (searched *after* the target interpreter's
  own, so a project's own pinned versions still win if present) — see
  `notlob.bindings.python.runner`'s module docstring. `ruff` is
  unaffected; it's static analysis and continues running under
  notlob's own interpreter.
- Python and Haskell linting/running crashed on Windows when a
  module's assembled source contained non-ASCII characters (e.g. a
  Unicode heading title embedded in a `# <addr>`/`-- <addr>` location
  comment) — `subprocess.run(..., text=True)` without an explicit
  encoding fell back to the console's codepage instead of UTF-8.
  TypeScript's runner/linter already forced `encoding="utf-8"`; Python's
  `lint.py` and Haskell's `runner.py`/`lint.py` now do too.
- The Python binding's `pytest`/`hypothesis` fallback (see above) found
  their location via `sysconfig.get_paths()["purelib"]`, which derives
  its answer from the running interpreter's `sys.prefix` — correct for
  a normal venv or pipx/uvx install, but wrong for a zipapp-style bundle
  (e.g. one built with `shiv`) that makes packages importable by
  prepending an extraction-cache directory to `sys.path` without ever
  changing `sys.prefix`. `_notlob_site_packages` now resolves the path
  via `pytest.__file__`'s actual import location instead, which is
  correct under both packaging schemes.

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


