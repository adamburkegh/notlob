"""notlob.bindings.typescript — TypeScript language binding kit.

Assembles the TypeScript ``BindingKit`` from its submodules and exposes
``kit`` as the canonical TypeScript binding instance.

Usage::

    from notlob.bindings.typescript import kit
    results = kit.run_examples(module, cache=cache)

Runner availability
-------------------
The runner requires ``tsx`` (preferred) or ``ts-node`` on PATH, or
``node_modules/.bin/tsx`` relative to the project root.  When none is
available ``run_examples``, ``run_tests``, and ``run_properties``
return a single ERROR result rather than raising.

Linting
-------
``kit.lint`` runs ``tsc --noEmit`` for type-checking — the type errors
``tsx`` skips at runtime.  Requires ``tsc`` (project-local
``node_modules/.bin/tsc`` or on PATH); degrades to no findings when
absent.  See ``lint.py``.
"""

from pathlib import Path

from notlob.bindings import BindingKit, collect_run_bodies
from notlob.bindings.typescript.assemble import assemble
from notlob.bindings.typescript.lint import lint_typescript
from notlob.bindings.typescript.runner import (
    _build_module_source,
    run_examples, run_properties, run_tests,
)
from notlob.bindings.typescript.symbols import extract_calls, extract_symbols
from notlob.model import Module


def build_typescript(module: Module, file_path: Path | None = None) -> str:
    """Assemble *module* with inlined deps into one TypeScript source string.

    Dependencies declared as lob-refs in ``#References`` are assembled
    and prepended so the output is self-contained.

    Unlike ``assemble``, which is used for testing and excludes all
    claims, ``build_typescript`` appends ``~run`` claim bodies at the
    end of the assembled source, since a build artifact needs its
    entry point present to do anything once loaded.

    ``~run on-load`` bodies are appended unconditionally, at module
    scope — the natural choice for browser-target code (DOM wiring,
    event listeners): a page loading the script *is* the deliberate
    execution moment, there's no meaningful "imported vs run" split to
    guard against there.

    ``~run`` (bare) and ``~run on-invocation`` bodies are appended
    together afterwards, wrapped in a Node/ESM entry-point guard (only
    added when at least one such block exists, so browser-only modules
    get no Node-specific code at all) so those side effects fire only
    when the artifact is executed directly, not merely imported by
    other Node code.
    """
    from notlob.project import find_project_root

    root   = find_project_root(file_path) if file_path else None
    source = _build_module_source(module, root)

    on_load, on_invocation = collect_run_bodies(module)
    if on_load:
        source = source + '\n\n' + '\n\n'.join(on_load)
    if on_invocation:
        source = _wrap_on_invocation(source, on_invocation)
    return source


def _wrap_on_invocation(source: str, on_invocation: list[str]) -> str:
    """Append *on_invocation* bodies wrapped in an ESM Node entry-point
    guard, prepending the ``node:url`` import the guard needs.

    ``import.meta.url === pathToFileURL(process.argv[1]).href`` is true
    only when this module is the one Node was asked to run directly —
    false when it's imported by other code. Using ``pathToFileURL``
    (rather than manual string comparison against ``process.argv[1]``)
    matters on Windows: raw paths use backslashes and aren't
    URL-encoded, so a naive string-template comparison against
    ``import.meta.url`` fails there; ``pathToFileURL`` handles the
    platform-correct
    conversion. Verified against a real ``tsx`` run in both directions
    (direct execution and import) before relying on it.
    """
    import textwrap

    guard_body = textwrap.indent('\n\n'.join(on_invocation), '  ')
    guard = (
        "if (import.meta.url === pathToFileURL(process.argv[1]).href) {\n"
        + guard_body
        + '\n}'
    )
    return (
        "import { pathToFileURL } from 'node:url';\n\n"
        + source + '\n\n' + guard
    )


#: The assembled TypeScript binding kit.
kit = BindingKit(
    extract_symbols=extract_symbols,
    extract_calls=extract_calls,
    assemble=assemble,
    run_examples=run_examples,
    run_properties=run_properties,
    run_tests=run_tests,
    lint=lint_typescript,
    extension='ts',
    comment_prefix='//',
    build=build_typescript,
)

__all__ = [
    'kit', 'extract_symbols', 'assemble',
    'run_examples', 'run_tests', 'run_properties',
]
