"""notlob.bindings.python — Python binding kit.

Assembles the Python BindingKit from its component submodules and
exposes `kit` as the canonical Python binding instance.

Usage::

    from notlob.bindings.python import kit
    enrich(graph, module, kit.extract_symbols)
    source = kit.assemble(module)
    results = kit.run_examples(module, file_path=path)
"""

from pathlib import Path

import textwrap

from notlob.bindings import BindingKit, ClaimResult, Status, collect_run_bodies
from notlob.bindings.python.assemble import assemble, assemble_with_deps
from notlob.bindings.python.lint import lint_python
from notlob.bindings.python.runner import (
    _load_dep_modules, run_examples, run_tests, run_properties,
)
from notlob.bindings.python.symbols import extract_calls, extract_symbols
from notlob.model import Module


def build_python(
    module: Module,
    file_path: Path | None = None,
) -> str:
    """Assemble *module* with inlined deps for the build command.

    Loads lob-ref dependencies from the project tree rooted at
    *file_path*, inlines their code before the module's own code (see
    ``assemble_with_deps``), and returns a single self-contained Python
    source string — only the target module's ``~run`` claims are
    appended, never a dependency's.

    ``~run on-load`` bodies are appended unconditionally, at module
    scope. ``~run`` (bare) and ``~run on-invocation`` bodies -- Python
    treats these as equivalent, since there's only ever one meaningful
    choice for a Python process -- are appended together afterwards,
    wrapped in ``if __name__ == "__main__":`` so those side effects
    fire when the artifact is run directly but not when it's merely
    imported as a module.
    """
    dep_modules = _load_dep_modules(module, file_path)
    source = assemble_with_deps(module, dep_modules)
    on_load, on_invocation = collect_run_bodies(module)
    if on_load:
        source = source + "\n\n" + "\n\n".join(on_load)
    if on_invocation:
        run_body = textwrap.indent("\n\n".join(on_invocation), "    ")
        source = source + '\n\n\nif __name__ == "__main__":\n' + run_body
    return source


#: The assembled Python binding kit.
kit = BindingKit(
    extract_symbols=extract_symbols,
    extract_calls=extract_calls,
    assemble=assemble,
    run_examples=run_examples,
    run_properties=run_properties,
    run_tests=run_tests,
    lint=lint_python,
    build=build_python,
    comment_prefix="#",
)

__all__ = [
    "kit", "extract_symbols", "assemble",
    "run_examples", "run_tests", "run_properties", "ClaimResult", "Status",
]
