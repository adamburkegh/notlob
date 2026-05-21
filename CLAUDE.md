# Notlob

Notlob is an experimental literate programming environment. Source files
(`.lob`) are structured documents combining prose, formal claims,
executable code, and tests in a single file. The format is the experiment.

See [DESIGN.md](DESIGN.md) for language design decisions and syntax
specification. See [origin.md](origin.md) for the founding conversation
and intellectual background.

---

## Project Structure

```
examples/               ← container for independent example projects
  roman/                ← project root (self-contained)
    binding.lob         ← #Roman  (project manifest)
    roman/              ← roman package
      numerals.lob      ← #Roman Numerals
  retail/               ← project root (larger scope)
    binding.lob         ← #Retail  (project manifest)
    pricing/            ← pricing package
      discounts.lob     ← #Pricing Discounts
```

Each subdirectory of `examples/` is an independent notlob project (the
equivalent of a git repository).  Within a project, the project root
is the mount point: module addresses are resolved relative to it.
`binding.lob` at the project root signals the project boundary and
carries language, dependency, and shared-reference declarations.

---

## Conventions

Follow Python and Haskell conventions for their respective substrates.
Keep other technologies boring — this is a radical experiment in document
structure, not in build tooling or infrastructure.

Keep to 80 character wide lines.

**Never install packages into the global Python interpreter.** The project
venv is `notlobenv/`. Always use `notlobenv/Scripts/pip` to install
dependencies, and `notlobenv/Scripts/python` (or `notlobenv/Scripts/pytest`)
to run code. If the venv is missing, create it with
`python -m venv notlobenv` and install with
`notlobenv/Scripts/pip install -e .` before doing anything else.
