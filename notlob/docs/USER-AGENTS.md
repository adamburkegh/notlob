# {project_title}

A notlob literate programming project.

## Getting oriented

Run `notlob docs` to write the language reference to `notlob-docs/LANGUAGE.md`.

Read `notlob-docs/LANGUAGE.md` for syntax, claims, and project structure.

## Key commands

```
notlob test                       run all claims in the project
notlob build                      assemble modules to dist/
notlob run <file>                 execute a module
notlob weave                      render project as Markdown
notlob new <name>                 create a new module
notlob docs                       write language reference to notlob-docs/
notlob graph                      export the name-graph for the entire project
notlob query search <pattern>     find nodes by label
notlob query content <address>    show source at an address
notlob query children <address>   list child nodes
```

## Project structure

- `binding.lob` — project manifest (language, tooling)
- `*.lob` — modules (prose + code + claims)
- `notlob-docs/` — generated reference docs (not checked in)

## Source of Truth

`.lob` files are the source of truth for this project. **Never create or edit `.py` files (or any other generated files) directly.**

Generated artifacts are read-only diagnostics:

- `dist/` — output of `notlob build`
- `notlob-docs/` — output of `notlob docs`
- `--keep-generated-src` output — assembled source with assertions, written on request for debugging

When investigating a behaviour or debugging a test, read the `.lob` source first. Use `--keep-generated-src` only when you need to inspect the assembled executable form. Any change you want to make must be made in the corresponding `.lob` file.

## Style Guidance

Notlob source files should be written in a literate programming style. Each file is organised around a concept. An initial short essay should introduce the purpose. Executable code, executable examples and runnable properties should be interleaved with clear technical prose. Tests are not only encouraged but expected, and a linter runs by default.

## Command Guidance

Notlob has specific features which make it easier to search for concepts in documentation and code. Use `notlob graph` to get a project-level overview of a notlob project. Favour using `notlob query` over filesystem searches to navigate for the meaning of names and use of symbols throughout the codebase.


