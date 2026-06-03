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
``kit.lint`` is ``None`` pending biome integration.  See ``lint.py``
for implementation notes.
"""

from pathlib import Path

from notlob.bindings import BindingKit
from notlob.bindings.typescript.assemble import assemble
from notlob.bindings.typescript.runner import (
    _build_module_source,
    run_examples, run_properties, run_tests,
)
from notlob.bindings.typescript.symbols import extract_symbols
from notlob.model import Module


def build_typescript(module: Module, file_path: Path | None = None) -> str:
    """Assemble *module* with inlined deps into one TypeScript source string.

    Dependencies declared as lob-refs in ``#References`` are assembled
    and prepended so the output is self-contained.

    Unlike ``assemble``, which is used for testing and excludes all
    claims, ``build_typescript`` appends ``~run`` claim bodies at the
    end of the assembled source.  ``~run`` is the program entry point —
    it wires up event listeners, calls ``main()``, etc. — and must be
    present in the build artifact for the program to do anything when
    loaded by a browser or runtime.
    """
    import textwrap
    from notlob.model import Claim, Subheading
    from notlob.project import find_project_root

    root       = find_project_root(file_path) if file_path else None
    source     = _build_module_source(module, root)

    run_blocks: list[str] = []

    def _collect_run(body: list) -> None:
        for item in body:
            if isinstance(item, Claim) and item.sigil == '~run':
                block = textwrap.dedent('\n'.join(item.lines)).strip()
                if block:
                    run_blocks.append(block)
            elif isinstance(item, Subheading):
                _collect_run(item.body)

    _collect_run(module.body)

    if run_blocks:
        source = source + '\n\n' + '\n\n'.join(run_blocks)

    return source


#: The assembled TypeScript binding kit.
kit = BindingKit(
    extract_symbols=extract_symbols,
    assemble=assemble,
    run_examples=run_examples,
    run_properties=run_properties,
    run_tests=run_tests,
    lint=None,          # biome integration: see lint.py
    extension='ts',
    comment_prefix='//',
    build=build_typescript,
)

__all__ = [
    'kit', 'extract_symbols', 'assemble',
    'run_examples', 'run_tests', 'run_properties',
]
