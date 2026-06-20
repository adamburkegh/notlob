# Notlob — developer guide for agents

Notlob is an experimental literate programming environment. Source files
(`.lob`) combine prose, executable code, and verifiable claims in a
single document. The format is the experiment.

## Key documentation

- `notlob/docs/LANGUAGE.md` — language reference (syntax, claims,
  project structure). This is what `notlob docs` emits to new projects.
- `notlob/docs/DESIGN.md` — internal architecture and design rationale.
- `origin.md` — founding conversation and intellectual background.

## Project structure

```
notlob/              the Python package
  bindings/          language binding kits (python/, haskell/)
  check.py           semantic consistency checker (notlob check)
  docs/              bundled documentation
    LANGUAGE.md      user-facing language spec
    DESIGN.md        internal architecture and rationale
    USER-AGENTS.md   template emitted as AGENTS.md by notlob init
editors/vim/         vim syntax highlighting for .lob files
examples/            independent example notlob projects
  roman/             Python example project
  retail/            larger Python example project
tests/               pytest test suite
```

## Development setup

The project venv is `notlobenv/`. Never install into the global
interpreter.

```
python -m venv notlobenv                  create venv (if missing)
notlobenv/Scripts/pip install -e .        install in editable mode
notlobenv/Scripts/pytest                  run the full test suite
```

## Conventions

- 80-character line width.
- Follow Python conventions in `notlob/`; Haskell conventions in
  Haskell binding code.
- Keep other technologies boring — this is an experiment in document
  structure, not build tooling.
- Tests live in `tests/`. Run them with `notlobenv/Scripts/pytest`.
- Each binding kit lives in `notlob/bindings/<language>/` and exposes
  a `kit` instance of `BindingKit`.
