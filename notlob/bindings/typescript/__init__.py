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
    and prepended so the output is self-contained.  The result is
    suitable for bundling or direct embedding in a ``<script>`` tag
    (after transpilation).
    """
    from notlob.project import find_project_root
    root = find_project_root(file_path) if file_path else None
    return _build_module_source(module, root)


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
