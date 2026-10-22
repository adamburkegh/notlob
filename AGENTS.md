# Notlob — developer guide for agents

Notlob is an experimental literate programming environment. Source files
(`.lob`) combine prose, executable code, and verifiable claims in a
single document. The format is the experiment.

## Key documentation

- `notlob/docs/LANGUAGE.md` — language reference (syntax, claims,
  project structure). This is what `notlob docs` emits to new projects.
- `notlob/docs/DESIGN.md` — internal architecture and design rationale.
- `meta/origin.md` — founding conversation and intellectual background.
- `meta/bugs/` — one directory per investigated bug report, named
  `YYYY-MM-DD-slug` (dated by when filed, not resolved). Holds the
  investigation narrative and any MRE fixture files — the detail that
  doesn't belong in `CHANGELOG.md` (which stays a terse, user-facing
  summary) or in code comments (which shouldn't carry historical
  narrative). Always a directory, even for a bug that's just prose
  today, so one that later grows an MRE never needs renaming. Once
  fixed, add a `**Resolved:** <date>, commit <sha>` note rather than
  deleting the report — the history is the point.
- `meta/features/` — same convention, for queued feature proposals
  (`YYYY-MM-DD-slug/`, dated by when filed) that aren't being
  implemented yet. A design doc that arrives for later work goes here
  rather than being lost between conversations.
- `meta/retrospectives/` — same convention (`YYYY-MM-DD-slug/`), for a
  look back at *why* something went wrong when the fix alone doesn't
  answer that: what happened, how it was found, what let it through, and
  what changes so the class of problem is caught next time. Written for
  the bugs that point at a missing property of the project, not for every
  bug; the bug itself still gets its `meta/bugs/` note.

  Note: `notlob/docs/` (above) ships with the installed package
  (`pyproject.toml` package-data) and is aimed at notlob *users*;
  top-level `meta/` is project background for notlob-lab
  *contributors* and is never packaged. The name is deliberately not
  `docs/`, to avoid exactly this confusion with `notlob/docs/`.

## Project structure

```
notlob/              the Python package
  bindings/          language binding kits (python/, haskell/)
  check.py           semantic consistency checker (notlob check)
  docs/              bundled documentation
    LANGUAGE.md      user-facing language spec
    DESIGN.md        internal architecture and rationale
    USER-AGENTS.md   template emitted as AGENTS.md by notlob init
meta/                project background (not packaged)
  origin.md          founding conversation and intellectual background
  bugs/              investigated bug reports, one dir per bug
  features/          queued feature proposals, one dir per proposal
  retrospectives/    why a significant bug happened, one dir each
editors/vim/         vim syntax highlighting for .lob files
examples/            independent example notlob projects
  roman/             Python example project
  retail/            larger Python example project
tests/               pytest test suite
build.py             builds the release .pyz from a git ref
```

## Development setup

The project venv is `notlobenv/`. Never install into the global
interpreter.

```
python -m venv notlobenv                  create venv (if missing)
notlobenv/Scripts/pip install -e ".[dev]" install in editable mode, with dev tooling
notlobenv/Scripts/pytest                  run the full test suite
npm install                               install TypeScript toolchain (tsx, tsc, fast-check)
```

## Releasing

The version in `pyproject.toml` is bumped forward when a cycle opens, so
development happens under the number it will ship as. The released
artifact is built by `build.py`, and only by it: a `.pyz` that was not
built from source control by that script is not a release.

1. Move `CHANGELOG.md`'s `[Unreleased]` section into a dated
   `[X.Y.Z] - date` section (and leave an empty `[Unreleased]`). Commit.
2. Tag that commit `vX.Y.Z`.
3. `notlobenv/Scripts/python build.py --ref vX.Y.Z` writes
   `dist/notlob-X.Y.Z.pyz` (`dist/` is git-ignored). It builds from the
   ref, not the working tree; refuses a version with no dated changelog
   section or a tag pointing elsewhere; and smoke-tests the result.
4. Attach the file to the GitHub release for the tag. The script prints
   the SHA-256 and does not tag, push or publish.
5. Bump `pyproject.toml` forward to the next patch version, in its own
   commit, and `pipx reinstall notlob` so `notlob --version` is current
   (the version is read from installed metadata, so an editable install
   reports the version it was last installed at).

## Conventions

- 80-character line width.
- Follow Python conventions in `notlob/`; Haskell conventions in
  Haskell binding code.
- Keep other technologies boring — this is an experiment in document
  structure, not build tooling.
- Tests live in `tests/`. Run them with `notlobenv/Scripts/pytest`.
- Each binding kit lives in `notlob/bindings/<language>/` and exposes
  a `kit` instance of `BindingKit`.
