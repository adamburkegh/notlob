"""notlob.bindings.haskell — Haskell language binding kit.

Assembles the Haskell ``BindingKit`` from its submodules and exposes
``kit`` as the canonical Haskell binding instance.

Usage::

    from notlob.bindings.haskell import kit
    results = kit.run_examples(module, file_path=path)

Runner availability
-------------------
The runner requires ``runghc`` on PATH or the Stack build tool
(``stack`` on PATH).  When neither is available, ``run_examples``,
``run_tests``, and ``run_properties`` return a single ERROR result
rather than raising.
"""

from pathlib import Path

from notlob.bindings import BindingKit
from notlob.bindings.haskell.assemble import assemble, assemble_with_deps
from notlob.bindings.haskell.lint import lint_haskell
from notlob.bindings.haskell.runner import (
    _load_dep_modules, run_examples, run_tests, run_properties,
)
from notlob.bindings.haskell.symbols import extract_symbols
from notlob.model import Module


def build_haskell(
    module: Module,
    file_path: Path | None = None,
) -> str:
    """Assemble *module* with inlined deps for the build command.

    Loads lob-ref dependencies from the project tree rooted at
    *file_path*, inlines their code before the module's own code, and
    returns a single self-contained Haskell source string.
    """
    dep_modules = _load_dep_modules(module, file_path)
    return assemble_with_deps(module, dep_modules)


#: The assembled Haskell binding kit.
kit = BindingKit(
    extract_symbols=extract_symbols,
    assemble=assemble,
    run_examples=run_examples,
    run_properties=run_properties,
    run_tests=run_tests,
    lint=lint_haskell,
    extension="hs",
    comment_prefix="--",
    build=build_haskell,
)

__all__ = [
    "kit", "extract_symbols", "assemble",
    "run_examples", "run_tests", "run_properties", "lint_haskell",
]
