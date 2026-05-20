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
examples/               ← mount root (not a package)
  pricing/
    binding.lob         ← #Pricing  (package manifest)
    discounts.lob       ← #Pricing Discounts
  roman/
    binding.lob         ← #Roman  (package manifest)
    numerals.lob        ← #Roman Numerals
```

`examples/` is a mount point analogous to `src/main/java` — the tooling
strips it when resolving module addresses. Package addresses are
determined by directory structure and `.lob` file titles alone.

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
